"""Stage 1 & 2: Seed Task Collection and Blueprint Generation.

Generates intent drift blueprints using the blueprint-to-trajectory paradigm
inspired by APIGen-MT. Uses one LLM for generation and different LLMs for
cross-validation to avoid source bias.
"""

import json
import logging
from pathlib import Path
from typing import Any

from config import DriftType, Difficulty, PipelineConfig, DOMAINS

logger = logging.getLogger(__name__)

# --- Prompt Templates ---

SYSTEM_PROMPT = """You are an expert in designing realistic multi-turn tool-use evaluation scenarios. \
Your task is to create "intent drift blueprints" — structured descriptions of how a user's intent \
evolves during a tool-assisted conversation.

CRITICAL REQUIREMENTS:
1. NATURALNESS: Every drift must be something a real user would plausibly do. Not adversarial, not contrived.
2. TOOL-GROUNDED: The user's requests must be achievable through the provided tool set.
3. STRUCTURED OUTPUT: Follow the exact JSON output schema provided.
4. DIVERSITY: Avoid repetitive patterns across blueprints."""

DRIFT_TYPE_DEFINITIONS = {
    DriftType.PROGRESSIVE_REFINEMENT: {
        "name": "Progressive Refinement",
        "definition": "The user starts with a vague or broad intent and progressively narrows/specifies it over multiple turns.",
        "key_challenge": "Agent must update incrementally, not restart from scratch.",
        "example": 'User starts with "find a restaurant" and over 3-4 turns narrows to specific cuisine, price range, and features.',
    },
    DriftType.TOPIC_SHIFT: {
        "name": "Topic Shift",
        "definition": "The user temporarily or permanently shifts to a completely different task topic during the conversation.",
        "key_challenge": "Agent must manage context switch and potentially restore prior context.",
        "example": "User is booking a flight, suddenly asks about visa requirements, then returns to booking.",
    },
    DriftType.CONSTRAINT_ADDITION: {
        "name": "Constraint Addition",
        "definition": "The user adds NEW constraints AFTER the agent has already partially executed the task.",
        "key_challenge": "Agent must assess if prior results still hold or if backtracking is needed.",
        "example": 'User asks for cheapest flight, agent finds options, user adds "must be direct" — invalidating some results.',
    },
    DriftType.GOAL_CONFLICT: {
        "name": "Goal Conflict",
        "definition": "The user expresses mutually contradictory requirements.",
        "key_challenge": "Agent must detect the conflict and proactively seek clarification.",
        "example": 'User wants "cheapest hotel" but also "must be 5-star" — agent should flag the tension.',
    },
    DriftType.IMPLICIT_NEED: {
        "name": "Implicit Need Emergence",
        "definition": "The user has needs they haven't explicitly stated but which can be inferred from context.",
        "key_challenge": "Agent should proactively offer to address inferred needs without overstepping.",
        "example": "User books flight to unfamiliar city — agent proactively offers hotel/transport suggestions.",
    },
    DriftType.INTENT_BACKTRACKING: {
        "name": "Intent Backtracking",
        "definition": "The user reverts a previous decision and wants to return to an earlier choice point.",
        "key_challenge": "Agent must recall prior options and handle any state that needs reversal.",
        "example": 'User chose option B, agent acted on it, user says "actually go back to option A."',
    },
}


def build_blueprint_prompt(
    seed_task: dict,
    drift_type: DriftType,
    domain: str,
    tool_list: list[dict],
) -> str:
    """Build the prompt for generating a single blueprint."""
    dt = DRIFT_TYPE_DEFINITIONS[drift_type]

    return f"""### Task: Generate an Intent Drift Blueprint

**Drift Type**: {dt['name']} ({drift_type.value})
**Definition**: {dt['definition']}
**Key Challenge for Agent**: {dt['key_challenge']}
**Reference Example**: {dt['example']}

**Seed Task**: {json.dumps(seed_task, ensure_ascii=False)}
**Domain**: {domain}
**Available Tools**: {json.dumps([t['name'] + ': ' + t['description'] for t in tool_list[:20]], ensure_ascii=False)}

Generate a single intent drift blueprint as a JSON object with these fields:
- blueprint_id: string ("{drift_type.value}-{domain}-XXX")
- drift_type: "{drift_type.value}"
- domain: "{domain}"
- seed_task_id: "{seed_task.get('id', 'unknown')}"
- initial_intent: string (the user's starting request)
- drift_events: array of objects, each with:
  - turn: int (which conversation turn)
  - trigger: string (what causes the drift)
  - user_utterance: string (what the user says)
  - intent_before: string
  - intent_after: string
  - tools_affected: array of strings
- final_intent: string
- expected_end_state: object (database/API state after ideal completion)
- ideal_agent_behavior: string
- anti_pattern: string (common failure mode)
- expected_tool_call_sequence: array of strings
- difficulty: "easy" | "medium" | "hard"
- naturalness_score: int (1-5, self-assessed)
- num_turns: int (total expected conversation turns)

Output ONLY the JSON object, no other text."""


def build_batch_prompt(
    seed_tasks: list[dict],
    drift_type: DriftType,
    domain: str,
    tool_list: list[dict],
    count: int = 5,
) -> str:
    """Build prompt for batch blueprint generation."""
    dt = DRIFT_TYPE_DEFINITIONS[drift_type]

    tasks_str = "\n".join(
        f"  {i+1}. {json.dumps(t, ensure_ascii=False)}"
        for i, t in enumerate(seed_tasks[:count])
    )

    return f"""### Batch Task: Generate {count} Intent Drift Blueprints

**Drift Type**: {dt['name']} ({drift_type.value})
**Definition**: {dt['definition']}
**Key Challenge**: {dt['key_challenge']}

**Domain**: {domain}
**Seed Tasks**:
{tasks_str}

**Available Tools**: {json.dumps([t['name'] + ': ' + t['description'] for t in tool_list[:20]], ensure_ascii=False)}

Requirements:
1. Generate exactly ONE blueprint per seed task
2. Ensure DIVERSITY — vary triggers, timing, difficulty, and patterns
3. Difficulty distribution: ~30% easy, ~50% medium, ~20% hard
4. All must have naturalness_score >= 4
5. Total turns per dialogue: 6-18

Output a JSON array of blueprint objects (same schema as single blueprint generation)."""


class BlueprintGenerator:
    """Generates intent drift blueprints from seed tasks."""

    def __init__(self, config: PipelineConfig, llm_client: Any = None):
        self.config = config
        self.llm_client = llm_client  # abstract LLM client

    def generate_blueprints_for_domain(
        self, domain: str, seed_tasks: list[dict], tool_list: list[dict]
    ) -> list[dict]:
        """Generate blueprints for all seed tasks in a domain."""
        all_blueprints = []

        # Distribute drift types across seed tasks
        drift_types = list(DriftType)
        for i, seed_task in enumerate(seed_tasks):
            # Each seed task gets assigned a primary drift type (rotating)
            primary_drift = drift_types[i % len(drift_types)]

            prompt = build_blueprint_prompt(
                seed_task=seed_task,
                drift_type=primary_drift,
                domain=domain,
                tool_list=tool_list,
            )

            blueprint = self._call_llm(
                system_prompt=SYSTEM_PROMPT,
                user_prompt=prompt,
                model=self.config.blueprint_gen_model,
            )

            if blueprint and self._passes_basic_checks(blueprint):
                all_blueprints.append(blueprint)
                logger.info(
                    f"Generated blueprint {blueprint.get('blueprint_id', '?')} "
                    f"[{primary_drift.value}] for domain={domain}"
                )
            else:
                logger.warning(
                    f"Blueprint generation failed for seed_task={seed_task.get('id')} "
                    f"drift_type={primary_drift.value}"
                )

        return all_blueprints

    def _call_llm(self, system_prompt: str, user_prompt: str, model: str) -> dict | None:
        """Call the LLM and parse JSON response.

        This is a placeholder — replace with actual LLM API call.
        """
        if self.llm_client is None:
            logger.warning("No LLM client configured. Returning None.")
            return None

        try:
            response = self.llm_client.chat(
                model=model,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                temperature=0.8,
                max_tokens=4096,
            )
            return json.loads(response.content)
        except (json.JSONDecodeError, Exception) as e:
            logger.error(f"LLM call failed: {e}")
            return None

    def _passes_basic_checks(self, blueprint: dict) -> bool:
        """Basic structural validation of a blueprint."""
        required_fields = [
            "blueprint_id", "drift_type", "domain", "initial_intent",
            "drift_events", "final_intent", "difficulty", "naturalness_score",
        ]
        for field in required_fields:
            if field not in blueprint:
                logger.warning(f"Missing field: {field}")
                return False

        if blueprint.get("naturalness_score", 0) < self.config.min_naturalness_score:
            logger.warning(f"Naturalness too low: {blueprint.get('naturalness_score')}")
            return False

        if not blueprint.get("drift_events"):
            logger.warning("No drift events defined")
            return False

        return True

    def save_blueprints(self, blueprints: list[dict], domain: str) -> Path:
        """Save blueprints to file."""
        output_dir = self.config.blueprints_dir / domain
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "blueprints.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(blueprints, f, ensure_ascii=False, indent=2)
        logger.info(f"Saved {len(blueprints)} blueprints to {output_path}")
        return output_path
