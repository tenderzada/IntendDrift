"""Stage 4: Three-Layer Verification Pipeline.

Layer 1: Automated structural and logical checks
Layer 2: LLM review committee (cross-model verification)
Layer 3: Human annotation interface (outputs annotation tasks)
"""

import json
import logging
from dataclasses import dataclass
from typing import Any

from config import DriftType, PipelineConfig

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    trajectory_id: str
    layer1_pass: bool
    layer1_issues: list[str]
    layer2_scores: dict[str, dict]  # model -> {criterion: score}
    layer2_pass: bool
    layer3_annotations: dict | None  # filled after human review
    layer3_pass: bool | None
    overall_pass: bool

    def to_dict(self) -> dict:
        return {
            "trajectory_id": self.trajectory_id,
            "layer1": {"pass": self.layer1_pass, "issues": self.layer1_issues},
            "layer2": {"pass": self.layer2_pass, "scores": self.layer2_scores},
            "layer3": {"pass": self.layer3_pass, "annotations": self.layer3_annotations},
            "overall_pass": self.overall_pass,
        }


# ============================================================
# Layer 1: Automated Checks
# ============================================================

def layer1_automated_checks(trajectory: dict) -> tuple[bool, list[str]]:
    """Structural and logical validation."""
    issues = []

    # --- Structure checks ---
    if "turns" not in trajectory:
        issues.append("CRITICAL: missing 'turns' field")
        return False, issues

    turns = trajectory["turns"]

    if len(turns) < 4:
        issues.append(f"Too few turns: {len(turns)} (minimum 4)")

    # Check all turns have required fields
    for i, turn in enumerate(turns):
        if "role" not in turn:
            issues.append(f"Turn {i}: missing 'role'")
        if "content" not in turn:
            issues.append(f"Turn {i}: missing 'content'")
        if not turn.get("content", "").strip():
            issues.append(f"Turn {i}: empty content")

    # --- Drift point checks ---
    drift_points = trajectory.get("drift_points", [])
    if not drift_points:
        issues.append("No drift points annotated")

    for dp in drift_points:
        turn_id = dp.get("turn_id", -1)
        if turn_id < 1 or turn_id > len(turns):
            issues.append(f"Drift point turn_id {turn_id} out of range")
        if "intent_before" not in dp or "intent_after" not in dp:
            issues.append(f"Drift point at turn {turn_id}: missing intent_before/after")

    # --- Tool call checks ---
    agent_turns = [t for t in turns if t.get("role") == "agent"]
    tool_calls = []
    for at in agent_turns:
        for tc in at.get("tool_calls", []):
            if "tool_name" not in tc:
                issues.append(f"Tool call missing 'tool_name'")
            else:
                tool_calls.append(tc)

    if not tool_calls:
        issues.append("No tool calls found in any agent turn")

    # --- Consistency checks ---
    intent_states = [t.get("intent_state") for t in turns if t.get("intent_state")]
    if len(intent_states) < 2:
        issues.append("Fewer than 2 intent state annotations")

    # --- Check drift type validity ---
    drift_type = trajectory.get("drift_type", "")
    valid_types = [dt.value for dt in DriftType]
    if drift_type not in valid_types:
        issues.append(f"Invalid drift_type: {drift_type}")

    has_critical = any("CRITICAL" in issue for issue in issues)
    passed = not has_critical and len(issues) <= 2  # allow minor issues

    return passed, issues


# ============================================================
# Layer 2: LLM Review Committee
# ============================================================

REVIEW_PROMPT = """You are reviewing an intent drift evaluation scenario for quality. \
Evaluate the following trajectory on five criteria.

**Trajectory**:
{trajectory_json}

**Criteria** (score each 1-5):
1. **Naturalness**: Would a real user plausibly behave this way? Is the drift trigger believable?
2. **Drift Type Accuracy**: Is the labeled drift type correct for the behavior shown?
3. **Tool Groundedness**: Are the tool calls realistic and correctly structured?
4. **Intent Annotation Quality**: Are the per-turn intent states and drift points correctly labeled?
5. **Difficulty Calibration**: Is the difficulty label accurate?

Output ONLY a JSON object:
{{
  "naturalness": {{"score": <1-5>, "justification": "<brief>"}},
  "drift_accuracy": {{"score": <1-5>, "justification": "<brief>"}},
  "tool_groundedness": {{"score": <1-5>, "justification": "<brief>"}},
  "annotation_quality": {{"score": <1-5>, "justification": "<brief>"}},
  "difficulty_calibration": {{"score": <1-5>, "justification": "<brief>"}},
  "overall_recommendation": "accept|revise|reject",
  "revision_notes": "<if revise, what to fix>"
}}"""


class LLMReviewCommittee:
    """Layer 2: Cross-model verification using multiple LLMs."""

    def __init__(self, config: PipelineConfig, llm_client: Any = None):
        self.config = config
        self.llm_client = llm_client
        self.models = config.verification_models

    def review_trajectory(self, trajectory: dict) -> tuple[bool, dict]:
        """Have multiple LLMs review a trajectory."""
        all_scores = {}
        accept_votes = 0

        for model in self.models:
            review = self._get_review(trajectory, model)
            if review:
                all_scores[model] = review
                if review.get("overall_recommendation") == "accept":
                    accept_votes += 1

        passed = accept_votes >= self.config.min_verification_agreement
        return passed, all_scores

    def _get_review(self, trajectory: dict, model: str) -> dict | None:
        """Get a single model's review."""
        if self.llm_client is None:
            return None

        prompt = REVIEW_PROMPT.format(
            trajectory_json=json.dumps(trajectory, ensure_ascii=False, indent=2)[:6000]
        )

        try:
            response = self.llm_client.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.0,
                max_tokens=2048,
            )
            return json.loads(response.content)
        except Exception as e:
            logger.error(f"Review failed for model {model}: {e}")
            return None


# ============================================================
# Layer 3: Human Annotation Task Generation
# ============================================================

def generate_human_annotation_task(trajectory: dict) -> dict:
    """Generate a structured annotation task for human reviewers."""
    turns_summary = []
    for turn in trajectory.get("turns", []):
        turns_summary.append({
            "turn_id": turn.get("turn_id"),
            "role": turn.get("role"),
            "content": turn.get("content", "")[:200],  # truncate for readability
            "has_tool_calls": bool(turn.get("tool_calls")),
        })

    return {
        "task_id": f"human_review_{trajectory.get('trajectory_id', 'unknown')}",
        "trajectory_id": trajectory.get("trajectory_id"),
        "drift_type": trajectory.get("drift_type"),
        "domain": trajectory.get("domain"),
        "instructions": """Please review this multi-turn dialogue and answer the following:

1. NATURALNESS (1-5): Does the user's behavior feel natural and realistic?
2. DRIFT CORRECTNESS: Is the labeled drift type correct? If not, what should it be?
3. INTENT ANNOTATIONS: For each marked drift point, is the intent_before/intent_after correct?
4. IDEAL RESPONSE: At each drift point, what would an ideal agent do?
5. DIFFICULTY (easy/medium/hard): How challenging is this scenario for an AI agent?
6. OVERALL: Accept / Revise / Reject

If REVISE, please describe what needs to change.""",
        "turns": turns_summary,
        "drift_points": trajectory.get("drift_points", []),
        "annotation_fields": {
            "naturalness_score": "int (1-5)",
            "drift_type_correct": "bool",
            "corrected_drift_type": "string (if incorrect)",
            "drift_point_annotations": [
                {
                    "turn_id": "int",
                    "intent_before_correct": "bool",
                    "intent_after_correct": "bool",
                    "ideal_agent_response": "string",
                }
            ],
            "difficulty_label": "easy|medium|hard",
            "decision": "accept|revise|reject",
            "revision_notes": "string",
        },
    }


# ============================================================
# Full Verification Pipeline
# ============================================================

class VerificationPipeline:
    """Orchestrates the three-layer verification process."""

    def __init__(self, config: PipelineConfig, llm_client: Any = None):
        self.config = config
        self.llm_committee = LLMReviewCommittee(config, llm_client)

    def verify_trajectory(self, trajectory: dict) -> VerificationResult:
        """Run full verification pipeline on a single trajectory."""
        tid = trajectory.get("trajectory_id", "unknown")

        # Layer 1
        l1_pass, l1_issues = layer1_automated_checks(trajectory)
        if not l1_pass:
            logger.info(f"{tid}: REJECTED at Layer 1 — {l1_issues}")
            return VerificationResult(
                trajectory_id=tid,
                layer1_pass=False, layer1_issues=l1_issues,
                layer2_scores={}, layer2_pass=False,
                layer3_annotations=None, layer3_pass=None,
                overall_pass=False,
            )

        # Layer 2
        l2_pass, l2_scores = self.llm_committee.review_trajectory(trajectory)
        if not l2_pass:
            logger.info(f"{tid}: REJECTED at Layer 2")
            return VerificationResult(
                trajectory_id=tid,
                layer1_pass=True, layer1_issues=l1_issues,
                layer2_scores=l2_scores, layer2_pass=False,
                layer3_annotations=None, layer3_pass=None,
                overall_pass=False,
            )

        # Layer 3: generate task for human review (async)
        human_task = generate_human_annotation_task(trajectory)
        logger.info(f"{tid}: Passed L1+L2, queued for human review")

        return VerificationResult(
            trajectory_id=tid,
            layer1_pass=True, layer1_issues=l1_issues,
            layer2_scores=l2_scores, layer2_pass=True,
            layer3_annotations=None, layer3_pass=None,  # pending human review
            overall_pass=False,  # not final until human review
        )

    def verify_batch(self, trajectories: list[dict]) -> list[VerificationResult]:
        """Verify a batch of trajectories."""
        results = []
        for traj in trajectories:
            result = self.verify_trajectory(traj)
            results.append(result)

        passed = sum(1 for r in results if r.layer2_pass)
        logger.info(
            f"Verification batch: {passed}/{len(results)} passed L1+L2 "
            f"(pending human review)"
        )
        return results
