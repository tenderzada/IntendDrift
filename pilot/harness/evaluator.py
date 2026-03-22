"""Deterministic evaluator for IntentDrift-SWE.

Evaluation is based on:
1. Test pass/fail (primary) — deterministic
2. Code constraint checks — deterministic
3. Process metrics (DDL, CPS, Rollback) — deterministic/semi-deterministic
"""

import json
import logging
import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class EvalResult:
    task_id: str
    drift_type: str
    model: str
    run_id: int
    # Core: pass/fail
    passed: bool = False
    tests_passed: list[str] = field(default_factory=list)
    tests_failed: list[str] = field(default_factory=list)
    regressions: list[str] = field(default_factory=list)
    code_constraints_met: bool = True
    # Process metrics
    ddl: int = -1         # Drift Detection Latency (turns)
    cps: float = -1.0     # Context Preservation Score (0-1)
    rollback_clean: bool | None = None  # T3/T6: was invalidated code removed?
    pcr: bool | None = None  # T4/T5: did agent proactively clarify?
    # Meta
    total_turns: int = 0
    drift_turn_ids: list[int] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "task_id": self.task_id,
            "drift_type": self.drift_type,
            "model": self.model,
            "run_id": self.run_id,
            "passed": self.passed,
            "tests_passed": self.tests_passed,
            "tests_failed": self.tests_failed,
            "regressions": self.regressions,
            "code_constraints_met": self.code_constraints_met,
            "ddl": self.ddl,
            "cps": self.cps,
            "rollback_clean": self.rollback_clean,
            "pcr": self.pcr,
            "total_turns": self.total_turns,
            "drift_turn_ids": self.drift_turn_ids,
            "error": self.error,
        }


def run_tests_in_workspace(workspace: str, test_names: list[str]) -> dict[str, bool]:
    """Run specific tests and return pass/fail for each."""
    results = {}
    for test in test_names:
        try:
            proc = subprocess.run(
                ["python", "-m", "pytest", "-xvs", test],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=120,
            )
            results[test] = proc.returncode == 0
        except subprocess.TimeoutExpired:
            results[test] = False
        except Exception as e:
            logger.error(f"Test execution error for {test}: {e}")
            results[test] = False
    return results


def check_code_constraints(workspace: str, constraints: dict) -> bool:
    """Check code constraints (must_contain / must_not_contain patterns)."""
    must_contain = constraints.get("must_contain", [])
    must_not_contain = constraints.get("must_not_contain", [])

    # Aggregate all Python source files
    all_code = ""
    for root, _, files in os.walk(workspace):
        for f in files:
            if f.endswith(".py"):
                try:
                    with open(os.path.join(root, f), "r", encoding="utf-8") as fh:
                        all_code += fh.read() + "\n"
                except Exception:
                    pass

    for pattern in must_contain:
        if pattern not in all_code:
            logger.warning(f"Code constraint FAIL: must_contain '{pattern}' not found")
            return False

    for pattern in must_not_contain:
        if pattern and pattern in all_code:
            logger.warning(f"Code constraint FAIL: must_not_contain '{pattern}' found")
            return False

    return True


def compute_ddl(
    conversation_log: list[dict],
    drift_turn_ids: list[int],
    task: dict,
) -> int:
    """Compute Drift Detection Latency.

    DDL = number of agent turns between drift message and first agent action
    that addresses the new intent (heuristic: first file edit or tool call
    after drift that relates to the new requirement).
    """
    if not drift_turn_ids:
        return -1

    last_drift_turn = drift_turn_ids[-1]

    # Count agent turns after drift before first relevant action
    agent_turns_after = 0
    for entry in conversation_log:
        if entry.get("turn_id", 0) <= last_drift_turn:
            continue
        if entry.get("role") == "agent":
            agent_turns_after += 1
            # Check if this turn contains a tool call (file edit, code search, etc.)
            if entry.get("tool_calls"):
                return agent_turns_after - 1  # 0-indexed: first response = DDL 0
    return agent_turns_after


def compute_cps(conversation_log: list[dict], drift_turn_ids: list[int]) -> float:
    """Compute Context Preservation Score.

    CPS = 1 - (redundant_post_drift_calls / unique_pre_drift_calls)
    A call is redundant if it re-reads a file or re-searches code that was
    already accessed before drift with the same parameters.
    """
    if not drift_turn_ids:
        return -1.0

    last_drift_turn = drift_turn_ids[-1]

    pre_drift_calls = set()
    post_drift_redundant = 0

    for entry in conversation_log:
        if entry.get("role") != "agent":
            continue
        for tc in entry.get("tool_calls", []):
            sig = f"{tc.get('tool_name')}:{json.dumps(tc.get('parameters', {}), sort_keys=True)}"
            if entry.get("turn_id", 0) <= last_drift_turn:
                pre_drift_calls.add(sig)
            else:
                if sig in pre_drift_calls:
                    post_drift_redundant += 1

    if not pre_drift_calls:
        return 1.0

    return max(0.0, 1.0 - post_drift_redundant / len(pre_drift_calls))


def evaluate_task(
    task: dict,
    workspace: str,
    conversation_log: list[dict],
    simulator_metrics: dict,
    model: str,
    run_id: int,
) -> EvalResult:
    """Evaluate a single task run."""
    result = EvalResult(
        task_id=task["task_id"],
        drift_type=task["drift_type"],
        model=model,
        run_id=run_id,
        total_turns=simulator_metrics.get("total_turns", 0),
        drift_turn_ids=simulator_metrics.get("drift_turn_ids", []),
    )

    # 1. Run required tests
    test_results = run_tests_in_workspace(workspace, task["tests_must_pass"])
    result.tests_passed = [t for t, v in test_results.items() if v]
    result.tests_failed = [t for t, v in test_results.items() if not v]

    # 2. Check no regressions (if specified)
    if task.get("tests_must_not_regress"):
        regression_results = run_tests_in_workspace(
            workspace, task["tests_must_not_regress"]
        )
        result.regressions = [t for t, v in regression_results.items() if not v]

    # 3. Check code constraints
    if task.get("code_constraints"):
        result.code_constraints_met = check_code_constraints(
            workspace, task["code_constraints"]
        )

    # 4. Core pass/fail
    result.passed = (
        len(result.tests_failed) == 0
        and len(result.regressions) == 0
        and result.code_constraints_met
    )

    # 5. Process metrics
    result.ddl = compute_ddl(
        conversation_log, result.drift_turn_ids, task
    )
    result.cps = compute_cps(conversation_log, result.drift_turn_ids)

    return result


def compute_pass_k(results: list[EvalResult], k: int) -> float:
    """Compute pass^k: probability of at least one success in k runs.

    Estimated as: 1 - (1 - p_hat)^k, where p_hat = successes / total_runs.
    """
    if not results:
        return 0.0
    successes = sum(1 for r in results if r.passed)
    p_hat = successes / len(results)
    return 1 - (1 - p_hat) ** k


def aggregate_results(all_results: list[EvalResult], k: int = 4) -> dict:
    """Aggregate results across tasks, models, and drift types."""
    from collections import defaultdict

    by_model = defaultdict(list)
    by_drift = defaultdict(list)
    by_model_drift = defaultdict(list)

    for r in all_results:
        by_model[r.model].append(r)
        by_drift[r.drift_type].append(r)
        by_model_drift[(r.model, r.drift_type)].append(r)

    summary = {
        "total_tasks": len(set(r.task_id for r in all_results)),
        "total_runs": len(all_results),
        "by_model": {},
        "by_drift_type": {},
        "by_model_drift": {},
    }

    for model, results in by_model.items():
        # Group by task for pass^k
        tasks = defaultdict(list)
        for r in results:
            tasks[r.task_id].append(r)

        pass_1_scores = [compute_pass_k(runs, 1) for runs in tasks.values()]
        pass_k_scores = [compute_pass_k(runs, k) for runs in tasks.values()]

        n = len(tasks)
        summary["by_model"][model] = {
            "n_tasks": n,
            "pass_1": round(sum(pass_1_scores) / n, 4) if n else 0,
            f"pass_{k}": round(sum(pass_k_scores) / n, 4) if n else 0,
            "avg_ddl": round(
                sum(r.ddl for r in results if r.ddl >= 0)
                / max(1, sum(1 for r in results if r.ddl >= 0)),
                2,
            ),
            "avg_cps": round(
                sum(r.cps for r in results if r.cps >= 0)
                / max(1, sum(1 for r in results if r.cps >= 0)),
                2,
            ),
        }

    for dt, results in by_drift.items():
        tasks = defaultdict(list)
        for r in results:
            tasks[r.task_id].append(r)

        pass_1_scores = [compute_pass_k(runs, 1) for runs in tasks.values()]
        n = len(tasks)
        summary["by_drift_type"][dt] = {
            "n_tasks": n,
            "pass_1": round(sum(pass_1_scores) / n, 4) if n else 0,
        }

    return summary
