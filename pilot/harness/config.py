"""IntentDrift-SWE Pilot Configuration."""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PilotConfig:
    # Paths
    tasks_file: Path = Path("D:/AUBR/IntentDrift/pilot/tasks/pilot_tasks.json")
    workspaces_dir: Path = Path("D:/AUBR/IntentDrift/pilot/workspaces")
    results_dir: Path = Path("D:/AUBR/IntentDrift/pilot/results")
    setups_dir: Path = Path("D:/AUBR/IntentDrift/pilot/setups")

    # Agent models to evaluate
    models: list[str] = field(default_factory=lambda: [
        "claude-sonnet-4-20250514",
        "gpt-4o",
        "deepseek-chat",
    ])

    # Evaluation settings
    k_runs: int = 4           # runs per task for pass^k
    max_turns: int = 30       # max agent turns per task
    timeout_seconds: int = 600  # 10 min timeout per task
    temperature: float = 0.3

    # Tools available to agent
    tools: list[str] = field(default_factory=lambda: [
        "read_file",
        "edit_file",
        "create_file",
        "search_code",
        "run_tests",
        "bash",
        "list_files",
    ])
