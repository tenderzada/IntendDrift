"""Environment-coupled User Simulator for IntentDrift-SWE.

The user simulator follows τ-Knowledge's flow-based approach:
- Drift messages are deterministic (read from blueprint)
- Trigger conditions are based on agent's code state (files modified, tests run)
- Pre/post-drift responses are rule-governed (acknowledge, confirm, answer)
"""

import json
import logging
import os
from pathlib import Path
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DriftEvent:
    trigger: str
    user_message: str
    intent_before: str
    intent_after: str


class UserSimulator:
    """Simulates a developer user who drifts intent based on agent's code state."""

    def __init__(self, task: dict, workspace_dir: str):
        self.task = task
        self.workspace_dir = Path(workspace_dir)
        self.drift_events = [DriftEvent(**e) for e in task["drift_events"]]
        self.current_drift_idx = 0
        self.all_drifts_triggered = False
        self.turn_count = 0
        self.drift_turn_ids = []  # track when drifts occurred

    @property
    def initial_message(self) -> str:
        return self.task["initial_request"]

    def respond(self, agent_message: str) -> str | None:
        """Generate user response based on agent's message and environment state.

        Returns None if conversation should end (agent says it's done).
        """
        self.turn_count += 1

        # Check if we should trigger the next drift
        if not self.all_drifts_triggered:
            drift = self.drift_events[self.current_drift_idx]
            if self._check_trigger(drift.trigger):
                self.drift_turn_ids.append(self.turn_count)
                self.current_drift_idx += 1
                if self.current_drift_idx >= len(self.drift_events):
                    self.all_drifts_triggered = True
                logger.info(
                    f"[Turn {self.turn_count}] DRIFT triggered: {drift.trigger}"
                )
                return drift.user_message

        # Post-drift or pre-first-drift: rule-based responses
        return self._rule_response(agent_message)

    def _check_trigger(self, trigger: str) -> bool:
        """Check if a drift trigger condition is met based on workspace state."""
        if "read at least" in trigger and "files" in trigger:
            # Approximation: check if agent has been active for a few turns
            return self.turn_count >= 3

        if "started implementing" in trigger or "has created/modified" in trigger:
            # Check if any source files were modified
            return self._files_modified() > 0

        if "implemented" in trigger or "has written" in trigger:
            # Check if meaningful code was written
            return self._files_modified() >= 1 and self._lines_changed() > 10

        if "identified" in trigger:
            return self.turn_count >= 2

        if "started" in trigger:
            return self.turn_count >= 2

        if "addressed" in trigger or "fixed" in trigger or "updated" in trigger:
            return self._files_modified() >= 1

        # Default: trigger after a few turns
        return self.turn_count >= 4

    def _files_modified(self) -> int:
        """Count modified/new files in workspace (heuristic via git or file timestamps)."""
        try:
            result = os.popen(
                f'cd "{self.workspace_dir}" && git diff --name-only 2>/dev/null'
            ).read()
            untracked = os.popen(
                f'cd "{self.workspace_dir}" && git ls-files --others --exclude-standard 2>/dev/null'
            ).read()
            files = set(result.strip().split("\n") + untracked.strip().split("\n"))
            files.discard("")
            return len(files)
        except Exception:
            return 0

    def _lines_changed(self) -> int:
        """Count lines changed in workspace."""
        try:
            result = os.popen(
                f'cd "{self.workspace_dir}" && git diff --stat 2>/dev/null'
            ).read()
            # Parse "X files changed, Y insertions, Z deletions"
            for line in result.strip().split("\n"):
                if "insertion" in line or "deletion" in line:
                    parts = line.split(",")
                    total = 0
                    for p in parts:
                        nums = [int(s) for s in p.split() if s.isdigit()]
                        total += sum(nums)
                    return total
            return 0
        except Exception:
            return 0

    def _rule_response(self, agent_message: str) -> str | None:
        """Simple rule-based responses for non-drift turns."""
        msg_lower = agent_message.lower()

        # Agent indicates completion
        if any(phrase in msg_lower for phrase in [
            "i've completed", "the task is done", "all tests pass",
            "implementation is complete", "i'm done", "finished",
            "changes have been made", "everything should work now",
        ]):
            return None  # End conversation

        # Agent asks a question
        if "?" in agent_message:
            return "Yes, go ahead with that approach."

        # Agent reports progress
        if any(phrase in msg_lower for phrase in [
            "i found", "i see", "looking at", "let me", "i'll",
            "running tests", "the test", "error", "failed",
        ]):
            return "OK, sounds good. Please continue."

        # Default acknowledgment
        return "Got it. Please proceed."

    def get_metrics(self) -> dict:
        """Return simulator metrics for evaluation."""
        return {
            "total_turns": self.turn_count,
            "drift_turn_ids": self.drift_turn_ids,
            "all_drifts_triggered": self.all_drifts_triggered,
            "num_drifts": len(self.drift_events),
        }
