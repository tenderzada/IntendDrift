"""IntentDrift Evaluation Metrics.

Implements the six core metrics:
- ITA: Intent Tracking Accuracy
- DDL: Drift Detection Latency
- ASR: Adaptation Success Rate
- CPS: Context Preservation Score
- PCR: Proactive Clarification Rate
- GDS: Graceful Degradation Score
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Any

from config import DriftType, EvalConfig

logger = logging.getLogger(__name__)


@dataclass
class MetricScores:
    """Scores for a single evaluation scenario."""
    trajectory_id: str
    drift_type: str
    domain: str
    difficulty: str
    ita: float = 0.0  # Intent Tracking Accuracy (0-1)
    ddl: float = 0.0  # Drift Detection Latency (0 = instant, higher = slower)
    asr: float = 0.0  # Adaptation Success Rate (0-1)
    cps: float = 0.0  # Context Preservation Score (0-1)
    pcr: float = 0.0  # Proactive Clarification Rate (0-1)
    gds: float = 0.0  # Graceful Degradation Score (0-1)

    @property
    def ids(self) -> float:
        """IntentDrift Score — weighted composite."""
        ddl_norm = max(0, 1 - self.ddl / 5)  # normalize: 0 turns = 1.0, 5+ turns = 0.0
        return (
            0.25 * self.ita
            + 0.15 * ddl_norm
            + 0.25 * self.asr
            + 0.15 * self.cps
            + 0.10 * self.pcr
            + 0.10 * self.gds
        )

    def to_dict(self) -> dict:
        return {
            "trajectory_id": self.trajectory_id,
            "drift_type": self.drift_type,
            "domain": self.domain,
            "difficulty": self.difficulty,
            "ITA": round(self.ita, 4),
            "DDL": round(self.ddl, 2),
            "ASR": round(self.asr, 4),
            "CPS": round(self.cps, 4),
            "PCR": round(self.pcr, 4),
            "GDS": round(self.gds, 4),
            "IDS": round(self.ids, 4),
        }


# ============================================================
# LLM Judge Prompts
# ============================================================

ITA_JUDGE_PROMPT = """You are evaluating an AI agent's understanding of user intent during a \
tool-use conversation where the user's intent CHANGED (drifted).

**Ground Truth**: At turn {drift_turn}, the user's intent changed from:
  BEFORE: {intent_before}
  AFTER: {intent_after}

**Agent's Response** at turn {response_turn} (the turn immediately after the drift):
{agent_response}

**Question**: Does the agent's response demonstrate understanding of the NEW intent?

Score (1-5):
1 = Agent completely ignores the drift, continues with old intent
2 = Agent shows slight awareness but primarily follows old intent
3 = Agent partially addresses new intent but also follows old intent
4 = Agent mostly addresses new intent with minor old-intent residue
5 = Agent fully and correctly addresses the new intent

Output JSON: {{"score": <1-5>, "justification": "<brief>"}}"""

ASR_JUDGE_PROMPT = """You are evaluating whether an AI agent successfully completed the user's \
task AFTER an intent drift occurred.

**Scenario**: {scenario_summary}
**Drift**: User's intent changed from "{intent_before}" to "{intent_after}" at turn {drift_turn}
**Expected End State**: {expected_end_state}
**Actual Agent Actions After Drift**: {agent_actions_after_drift}

**Question**: Did the agent successfully adapt and complete the task per the NEW intent?

Score:
- 1.0 = Fully completed the adapted task
- 0.75 = Mostly completed, minor issues
- 0.5 = Partially completed
- 0.25 = Attempted but largely failed
- 0.0 = Did not adapt at all

Output JSON: {{"score": <0-1>, "justification": "<brief>"}}"""

CPS_JUDGE_PROMPT = """You are evaluating whether an AI agent preserved relevant context from \
BEFORE an intent drift.

**Context collected before drift** (turns 1-{drift_turn}):
{context_before_drift}

**Agent's behavior after drift**:
{agent_behavior_after}

**Question**: Did the agent unnecessarily repeat questions or redo tool calls for information \
it already had? Or did it properly retain and reuse prior context?

Score (0-1):
- 1.0 = Perfect context preservation, no redundant actions
- 0.75 = Minor redundancy (e.g., one unnecessary re-ask)
- 0.5 = Significant redundancy
- 0.25 = Mostly forgot prior context
- 0.0 = Completely restarted from scratch

Output JSON: {{"score": <0-1>, "justification": "<brief>", "redundant_actions": ["list"]}}"""


class IntentDriftEvaluator:
    """Evaluates agent responses against IntentDrift-Bench scenarios."""

    def __init__(self, config: EvalConfig, llm_client: Any = None):
        self.config = config
        self.llm_client = llm_client

    def evaluate_scenario(
        self,
        trajectory: dict,      # ground truth scenario
        agent_dialogue: dict,   # agent's actual responses
    ) -> MetricScores:
        """Evaluate a single scenario."""
        tid = trajectory.get("trajectory_id", "unknown")
        drift_points = trajectory.get("drift_points", [])

        scores = MetricScores(
            trajectory_id=tid,
            drift_type=trajectory.get("drift_type", ""),
            domain=trajectory.get("domain", ""),
            difficulty=trajectory.get("metadata", {}).get("difficulty", "medium"),
        )

        if not drift_points:
            logger.warning(f"{tid}: No drift points, skipping evaluation")
            return scores

        # Evaluate each metric
        scores.ita = self._compute_ita(trajectory, agent_dialogue, drift_points)
        scores.ddl = self._compute_ddl(trajectory, agent_dialogue, drift_points)
        scores.asr = self._compute_asr(trajectory, agent_dialogue, drift_points)
        scores.cps = self._compute_cps(trajectory, agent_dialogue, drift_points)
        scores.pcr = self._compute_pcr(trajectory, agent_dialogue, drift_points)
        scores.gds = self._compute_gds(trajectory, agent_dialogue, drift_points)

        return scores

    def _compute_ita(self, trajectory, agent_dialogue, drift_points) -> float:
        """Intent Tracking Accuracy: Does the agent understand the new intent?"""
        scores = []
        agent_turns = agent_dialogue.get("turns", [])

        for dp in drift_points:
            drift_turn = dp["turn_id"]
            # Find agent's response after drift
            response_turn = drift_turn + 1
            agent_response = self._get_turn_content(agent_turns, response_turn)

            if not agent_response:
                scores.append(0.0)
                continue

            result = self._judge(ITA_JUDGE_PROMPT.format(
                drift_turn=drift_turn,
                intent_before=dp.get("intent_before", ""),
                intent_after=dp.get("intent_after", ""),
                response_turn=response_turn,
                agent_response=agent_response,
            ))
            scores.append((result.get("score", 1) - 1) / 4)  # normalize 1-5 to 0-1

        return sum(scores) / len(scores) if scores else 0.0

    def _compute_ddl(self, trajectory, agent_dialogue, drift_points) -> float:
        """Drift Detection Latency: How many turns until agent acknowledges drift?"""
        latencies = []
        agent_turns = agent_dialogue.get("turns", [])

        for dp in drift_points:
            drift_turn = dp["turn_id"]
            intent_after = dp.get("intent_after", "")

            # Scan agent turns after drift to find first acknowledgment
            latency = 0
            detected = False
            for turn in agent_turns:
                turn_id = turn.get("turn_id", 0)
                if turn_id <= drift_turn or turn.get("role") != "agent":
                    continue
                # Simple heuristic: check if agent's response relates to new intent
                # In practice, use LLM judge for this
                latency = (turn_id - drift_turn) // 2  # agent turns only
                detected = True
                break

            latencies.append(latency if detected else 5)  # max penalty if never detected

        return sum(latencies) / len(latencies) if latencies else 5.0

    def _compute_asr(self, trajectory, agent_dialogue, drift_points) -> float:
        """Adaptation Success Rate: Task completion after drift."""
        last_dp = drift_points[-1]
        agent_turns = agent_dialogue.get("turns", [])

        actions_after = []
        for turn in agent_turns:
            if turn.get("turn_id", 0) > last_dp["turn_id"] and turn.get("role") == "agent":
                actions_after.append(turn.get("content", ""))
                for tc in turn.get("tool_calls", []):
                    actions_after.append(f"[Tool: {tc.get('tool_name')}]")

        result = self._judge(ASR_JUDGE_PROMPT.format(
            scenario_summary=trajectory.get("drift_type", ""),
            intent_before=last_dp.get("intent_before", ""),
            intent_after=last_dp.get("intent_after", ""),
            drift_turn=last_dp["turn_id"],
            expected_end_state=json.dumps(trajectory.get("expected_end_state", {})),
            agent_actions_after_drift="\n".join(actions_after[:500]),
        ))
        return result.get("score", 0.0)

    def _compute_cps(self, trajectory, agent_dialogue, drift_points) -> float:
        """Context Preservation Score: Does agent retain pre-drift information?"""
        first_dp = drift_points[0]
        agent_turns = agent_dialogue.get("turns", [])

        context_before = []
        for turn in agent_turns:
            if turn.get("turn_id", 0) < first_dp["turn_id"]:
                context_before.append(turn.get("content", "")[:200])

        behavior_after = []
        for turn in agent_turns:
            if turn.get("turn_id", 0) >= first_dp["turn_id"] and turn.get("role") == "agent":
                behavior_after.append(turn.get("content", "")[:200])

        result = self._judge(CPS_JUDGE_PROMPT.format(
            drift_turn=first_dp["turn_id"],
            context_before_drift="\n".join(context_before),
            agent_behavior_after="\n".join(behavior_after[:5]),
        ))
        return result.get("score", 0.0)

    def _compute_pcr(self, trajectory, agent_dialogue, drift_points) -> float:
        """Proactive Clarification Rate: Does agent ask clarifying questions when needed?"""
        drift_type = trajectory.get("drift_type", "")

        # PCR is most relevant for T4 (Goal Conflict) and T5 (Implicit Need)
        if drift_type not in [DriftType.GOAL_CONFLICT.value, DriftType.IMPLICIT_NEED.value]:
            return 0.5  # neutral score for non-applicable types

        agent_turns = agent_dialogue.get("turns", [])
        clarification_indicators = [
            "would you like", "do you prefer", "could you clarify",
            "did you mean", "just to confirm", "which one",
            "there seems to be a conflict", "those two requirements",
        ]

        clarification_count = 0
        for turn in agent_turns:
            if turn.get("role") != "agent":
                continue
            content = turn.get("content", "").lower()
            if any(indicator in content for indicator in clarification_indicators):
                clarification_count += 1

        # At least 1 clarification expected for conflict/implicit scenarios
        return min(1.0, clarification_count / max(1, len(drift_points)))

    def _compute_gds(self, trajectory, agent_dialogue, drift_points) -> float:
        """Graceful Degradation Score: How well does agent handle unsatisfiable drifts?"""
        # Check if the scenario has an unsatisfiable component
        expected_end_state = trajectory.get("expected_end_state", {})
        if expected_end_state.get("fully_satisfiable", True):
            return 0.5  # neutral for fully satisfiable scenarios

        # For unsatisfiable scenarios, check if agent offers alternatives
        agent_turns = agent_dialogue.get("turns", [])
        degradation_indicators = [
            "unfortunately", "alternative", "instead",
            "not possible", "closest option", "compromise",
            "however", "suggest", "recommend instead",
        ]

        has_graceful = any(
            any(ind in turn.get("content", "").lower() for ind in degradation_indicators)
            for turn in agent_turns
            if turn.get("role") == "agent"
        )
        return 0.8 if has_graceful else 0.2

    def _judge(self, prompt: str) -> dict:
        """Call LLM judge. Placeholder for actual API."""
        if self.llm_client is None:
            return {"score": 3}  # default middle score
        try:
            response = self.llm_client.chat(
                model=self.config.judge_model,
                messages=[{"role": "user", "content": prompt}],
                temperature=self.config.judge_temperature,
                max_tokens=1024,
            )
            return json.loads(response.content)
        except Exception as e:
            logger.error(f"Judge call failed: {e}")
            return {"score": 0}

    def _get_turn_content(self, turns: list, turn_id: int) -> str:
        """Get content of a specific turn."""
        for turn in turns:
            if turn.get("turn_id") == turn_id:
                return turn.get("content", "")
        return ""


# ============================================================
# Aggregation & Reporting
# ============================================================

def aggregate_scores(
    all_scores: list[MetricScores],
) -> dict:
    """Aggregate scores across scenarios for reporting."""
    if not all_scores:
        return {}

    # Overall averages
    n = len(all_scores)
    overall = {
        "n_scenarios": n,
        "ITA_mean": sum(s.ita for s in all_scores) / n,
        "DDL_mean": sum(s.ddl for s in all_scores) / n,
        "ASR_mean": sum(s.asr for s in all_scores) / n,
        "CPS_mean": sum(s.cps for s in all_scores) / n,
        "PCR_mean": sum(s.pcr for s in all_scores) / n,
        "GDS_mean": sum(s.gds for s in all_scores) / n,
        "IDS_mean": sum(s.ids for s in all_scores) / n,
    }

    # By drift type
    by_drift = {}
    for dt in DriftType:
        dt_scores = [s for s in all_scores if s.drift_type == dt.value]
        if dt_scores:
            m = len(dt_scores)
            by_drift[dt.value] = {
                "n": m,
                "IDS_mean": sum(s.ids for s in dt_scores) / m,
                "ITA_mean": sum(s.ita for s in dt_scores) / m,
                "ASR_mean": sum(s.asr for s in dt_scores) / m,
            }

    # By difficulty
    by_difficulty = {}
    for diff in ["easy", "medium", "hard"]:
        diff_scores = [s for s in all_scores if s.difficulty == diff]
        if diff_scores:
            m = len(diff_scores)
            by_difficulty[diff] = {
                "n": m,
                "IDS_mean": sum(s.ids for s in diff_scores) / m,
            }

    return {
        "overall": overall,
        "by_drift_type": by_drift,
        "by_difficulty": by_difficulty,
    }
