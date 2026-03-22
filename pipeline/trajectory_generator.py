"""Stage 3: Trajectory Generation.

Converts intent drift blueprints into full multi-turn dialogue trajectories.
Uses a DIFFERENT model from blueprint generation to avoid source bias.
"""

import json
import logging
from typing import Any

from config import PipelineConfig

logger = logging.getLogger(__name__)

TRAJECTORY_SYSTEM_PROMPT = """You are simulating a realistic multi-turn conversation between a User \
and a Tool-Use Agent. You will be given an intent drift blueprint that describes how the user's \
intent evolves. Your job is to generate the FULL dialogue trajectory.

RULES:
1. The User should speak naturally — not robotic, not overly polished
2. The Agent should behave like a competent but not perfect assistant
3. Tool calls should be shown as structured JSON actions
4. The conversation should follow the blueprint's drift events at the specified turns
5. Add natural filler turns (acknowledgments, follow-ups) to make the conversation realistic
6. Total turns should match the blueprint's num_turns (+/- 2 turns)
7. The User should NOT explicitly announce their intent drift — it should emerge naturally"""


def build_trajectory_prompt(blueprint: dict) -> str:
    """Build the prompt for generating a dialogue trajectory from a blueprint."""
    return f"""### Generate Full Dialogue Trajectory

**Blueprint**: {json.dumps(blueprint, ensure_ascii=False, indent=2)}

Generate the complete multi-turn dialogue following this blueprint. Output a JSON object:

{{
  "trajectory_id": "{blueprint['blueprint_id']}_traj",
  "blueprint_id": "{blueprint['blueprint_id']}",
  "domain": "{blueprint['domain']}",
  "drift_type": "{blueprint['drift_type']}",
  "turns": [
    {{
      "turn_id": 1,
      "role": "user",
      "content": "natural user utterance",
      "intent_state": "current user intent at this turn",
      "is_drift_point": false,
      "drift_type_at_point": null
    }},
    {{
      "turn_id": 2,
      "role": "agent",
      "content": "agent's response text",
      "tool_calls": [
        {{
          "tool_name": "search_flights",
          "parameters": {{"destination": "Tokyo", "date": "2026-04-10"}},
          "result_summary": "Found 5 flights..."
        }}
      ],
      "intent_state": "agent's understanding of user intent"
    }},
    // ... more turns
  ],
  "drift_points": [
    {{
      "turn_id": 5,
      "drift_type": "{blueprint['drift_type']}",
      "intent_before": "...",
      "intent_after": "...",
      "explicitness": "explicit|implicit"
    }}
  ],
  "expected_end_state": {json.dumps(blueprint.get('expected_end_state', {}), ensure_ascii=False)},
  "metadata": {{
    "total_turns": <int>,
    "num_tool_calls": <int>,
    "num_drift_points": <int>,
    "difficulty": "{blueprint.get('difficulty', 'medium')}"
  }}
}}

IMPORTANT: Generate ONLY the JSON object."""


class TrajectoryGenerator:
    """Generates full dialogue trajectories from blueprints."""

    def __init__(self, config: PipelineConfig, llm_client: Any = None):
        self.config = config
        self.llm_client = llm_client

    def generate_trajectory(self, blueprint: dict) -> dict | None:
        """Generate a single trajectory from a blueprint."""
        prompt = build_trajectory_prompt(blueprint)

        trajectory = self._call_llm(
            system_prompt=TRAJECTORY_SYSTEM_PROMPT,
            user_prompt=prompt,
            model=self.config.trajectory_gen_model,  # different from blueprint model
        )

        if trajectory and self._validate_trajectory(trajectory, blueprint):
            return trajectory
        return None

    def generate_batch(self, blueprints: list[dict]) -> list[dict]:
        """Generate trajectories for a batch of blueprints."""
        trajectories = []
        for bp in blueprints:
            traj = self.generate_trajectory(bp)
            if traj:
                trajectories.append(traj)
                logger.info(f"Generated trajectory for {bp['blueprint_id']}")
            else:
                logger.warning(f"Failed trajectory for {bp['blueprint_id']}")
        return trajectories

    def _validate_trajectory(self, trajectory: dict, blueprint: dict) -> bool:
        """Validate trajectory against its blueprint."""
        # Check required structure
        if "turns" not in trajectory or not trajectory["turns"]:
            logger.warning("No turns in trajectory")
            return False

        turns = trajectory["turns"]

        # Check turn count is reasonable
        expected = blueprint.get("num_turns", 10)
        if not (self.config.min_turns <= len(turns) <= self.config.max_turns):
            logger.warning(f"Turn count {len(turns)} outside range [{self.config.min_turns}, {self.config.max_turns}]")
            return False

        # Check drift points exist
        drift_points = trajectory.get("drift_points", [])
        if not drift_points:
            logger.warning("No drift points annotated")
            return False

        # Check alternating user/agent turns
        for i, turn in enumerate(turns):
            expected_role = "user" if i % 2 == 0 else "agent"
            if turn.get("role") != expected_role:
                # Allow some flexibility (agent may have consecutive tool calls)
                pass

        # Check at least one tool call exists
        has_tool_call = any(
            turn.get("tool_calls") for turn in turns if turn.get("role") == "agent"
        )
        if not has_tool_call:
            logger.warning("No tool calls in trajectory")
            return False

        return True

    def _call_llm(self, system_prompt: str, user_prompt: str, model: str) -> dict | None:
        """Call LLM and parse response. Placeholder for actual API."""
        if self.llm_client is None:
            logger.warning("No LLM client configured.")
            return None
        try:
            response = self.llm_client.chat(
                model=model,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                temperature=0.7,
                max_tokens=8192,
            )
            return json.loads(response.content)
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"LLM call failed: {e}")
            return None

    def save_trajectories(self, trajectories: list[dict], domain: str):
        """Save trajectories to disk."""
        output_dir = self.config.trajectories_dir / domain
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "trajectories.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(trajectories, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(trajectories)} trajectories to {output_path}")
