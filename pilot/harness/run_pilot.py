"""IntentDrift-SWE Pilot Runner.

Usage:
    python run_pilot.py                    # Run all tasks on all models
    python run_pilot.py --task T1-001      # Run a specific task
    python run_pilot.py --model gpt-4o     # Run on a specific model
    python run_pilot.py --dry-run          # Print tasks without executing
"""

import argparse
import json
import logging
import os
import sys
from pathlib import Path

from config import PilotConfig
from evaluator import EvalResult, evaluate_task, aggregate_results
from user_simulator import UserSimulator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("IntentDrift-SWE")


def load_tasks(config: PilotConfig) -> list[dict]:
    with open(config.tasks_file, "r", encoding="utf-8") as f:
        return json.load(f)


def setup_workspace(task: dict, workspace_dir: Path) -> bool:
    """Set up a clean workspace for a task.

    In a full implementation, this would:
    1. Clone the repo at the specified commit
    2. Set up the Docker environment
    3. Install dependencies
    4. Initialize git for change tracking

    For the pilot, we create a minimal project structure.
    """
    workspace_dir.mkdir(parents=True, exist_ok=True)

    # Initialize git for change tracking
    os.system(f'cd "{workspace_dir}" && git init -q && git add -A && git commit -q -m "initial" --allow-empty 2>/dev/null')

    logger.info(f"Workspace ready: {workspace_dir}")
    return True


def run_agent_conversation(
    task: dict,
    model: str,
    workspace_dir: Path,
    config: PilotConfig,
) -> tuple[list[dict], dict]:
    """Run a full agent-user conversation.

    Returns:
        (conversation_log, simulator_metrics)

    In a full implementation, this would:
    1. Initialize the agent with the workspace and tools
    2. Send the initial user message
    3. Loop: agent acts → user simulator responds → repeat
    4. Stop when user returns None or max_turns reached
    """
    simulator = UserSimulator(task, str(workspace_dir))
    conversation_log = []
    turn_id = 0

    # Initial user message
    user_msg = simulator.initial_message
    conversation_log.append({
        "turn_id": turn_id,
        "role": "user",
        "content": user_msg,
    })
    turn_id += 1

    logger.info(f"[{task['task_id']}][{model}] Starting conversation")
    logger.info(f"  User: {user_msg[:100]}...")

    for _ in range(config.max_turns):
        # --- Agent turn ---
        # In a full implementation, call the agent API here
        # For now, we log a placeholder
        agent_response = _call_agent_placeholder(
            model=model,
            conversation=conversation_log,
            workspace=str(workspace_dir),
            tools=config.tools,
        )

        conversation_log.append({
            "turn_id": turn_id,
            "role": "agent",
            "content": agent_response.get("message", ""),
            "tool_calls": agent_response.get("tool_calls", []),
        })
        turn_id += 1

        # --- User turn ---
        user_response = simulator.respond(agent_response.get("message", ""))
        if user_response is None:
            logger.info(f"  Conversation ended at turn {turn_id}")
            break

        conversation_log.append({
            "turn_id": turn_id,
            "role": "user",
            "content": user_response,
        })
        turn_id += 1

        # Check if this was a drift message
        if user_response in [e.user_message for e in simulator.drift_events]:
            logger.info(f"  [DRIFT] Turn {turn_id}: {user_response[:80]}...")

    return conversation_log, simulator.get_metrics()


def _call_agent_placeholder(
    model: str,
    conversation: list[dict],
    workspace: str,
    tools: list[str],
) -> dict:
    """Placeholder for actual agent API call.

    Replace this with actual LLM API integration:
    - For Claude: use anthropic SDK with tool_use
    - For GPT-4o: use openai SDK with function_calling
    - For open-source: use vllm or together API

    The agent should receive:
    - System prompt with workspace path and available tools
    - Conversation history
    - Tool definitions

    And return:
    - message: text response
    - tool_calls: list of {tool_name, parameters, result}
    """
    return {
        "message": "[Agent placeholder — replace with actual LLM call]",
        "tool_calls": [],
    }


def run_single_task(
    task: dict,
    model: str,
    run_id: int,
    config: PilotConfig,
) -> EvalResult:
    """Run and evaluate a single task."""
    workspace = config.workspaces_dir / f"{task['task_id']}_{model}_run{run_id}"

    # Setup
    if not setup_workspace(task, workspace):
        result = EvalResult(
            task_id=task["task_id"],
            drift_type=task["drift_type"],
            model=model,
            run_id=run_id,
            error="Workspace setup failed",
        )
        return result

    # Run conversation
    conversation_log, sim_metrics = run_agent_conversation(
        task, model, workspace, config
    )

    # Evaluate
    result = evaluate_task(
        task=task,
        workspace=str(workspace),
        conversation_log=conversation_log,
        simulator_metrics=sim_metrics,
        model=model,
        run_id=run_id,
    )

    return result


def main():
    parser = argparse.ArgumentParser(description="IntentDrift-SWE Pilot Runner")
    parser.add_argument("--task", type=str, help="Run specific task ID")
    parser.add_argument("--model", type=str, help="Run specific model")
    parser.add_argument("--dry-run", action="store_true", help="Print tasks only")
    parser.add_argument("--k", type=int, default=4, help="Number of runs for pass^k")
    args = parser.parse_args()

    config = PilotConfig()
    config.k_runs = args.k
    tasks = load_tasks(config)

    # Filter
    if args.task:
        tasks = [t for t in tasks if t["task_id"] == args.task]
    models = [args.model] if args.model else config.models

    if args.dry_run:
        print(f"\n{'='*60}")
        print(f"IntentDrift-SWE Pilot: {len(tasks)} tasks × {len(models)} models × {config.k_runs} runs")
        print(f"{'='*60}\n")
        for t in tasks:
            print(f"  [{t['task_id']}] {t['drift_type']}")
            print(f"    Request: {t['initial_request'][:80]}...")
            print(f"    Drift events: {len(t['drift_events'])}")
            print(f"    Tests: {len(t['tests_must_pass'])} must-pass")
            print()
        return

    # Run
    all_results: list[EvalResult] = []
    config.results_dir.mkdir(parents=True, exist_ok=True)

    for task in tasks:
        for model in models:
            for run_id in range(config.k_runs):
                logger.info(
                    f"=== {task['task_id']} | {model} | run {run_id+1}/{config.k_runs} ==="
                )
                result = run_single_task(task, model, run_id, config)
                all_results.append(result)

                logger.info(
                    f"  Result: {'PASS' if result.passed else 'FAIL'} | "
                    f"DDL={result.ddl} | CPS={result.cps:.2f}"
                )

    # Aggregate and save
    summary = aggregate_results(all_results, k=config.k_runs)

    results_file = config.results_dir / "pilot_results.json"
    with open(results_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "summary": summary,
                "raw_results": [r.to_dict() for r in all_results],
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    # Print summary
    print(f"\n{'='*60}")
    print(f"PILOT RESULTS SUMMARY")
    print(f"{'='*60}")
    print(f"Tasks: {summary['total_tasks']} | Runs: {summary['total_runs']}")
    print()

    print("By Model:")
    for model, stats in summary["by_model"].items():
        print(f"  {model}:")
        print(f"    pass^1 = {stats['pass_1']:.1%}")
        print(f"    pass^{config.k_runs} = {stats.get(f'pass_{config.k_runs}', 0):.1%}")
        print(f"    avg DDL = {stats['avg_ddl']:.1f} turns")
        print(f"    avg CPS = {stats['avg_cps']:.2f}")
    print()

    print("By Drift Type:")
    for dt, stats in summary["by_drift_type"].items():
        print(f"  {dt}: pass^1 = {stats['pass_1']:.1%} (n={stats['n_tasks']})")
    print()

    print(f"Results saved to: {results_file}")


if __name__ == "__main__":
    main()
