"""IntentDrift-Bench Pipeline Configuration."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path


class DriftType(str, Enum):
    PROGRESSIVE_REFINEMENT = "T1_progressive_refinement"
    TOPIC_SHIFT = "T2_topic_shift"
    CONSTRAINT_ADDITION = "T3_constraint_addition"
    GOAL_CONFLICT = "T4_goal_conflict"
    IMPLICIT_NEED = "T5_implicit_need_emergence"
    INTENT_BACKTRACKING = "T6_intent_backtracking"


class Difficulty(str, Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


DOMAINS = [
    "travel",        # flights, hotels, transportation
    "restaurant",    # booking, search, reviews
    "finance",       # banking, payments, investment
    "e_commerce",    # shopping, returns, comparisons
    "productivity",  # calendar, email, documents
    "programming",   # code search, debugging, deployment
    "data_analysis", # queries, visualization, reports
    "healthcare",    # appointments, medication, records
]


@dataclass
class PipelineConfig:
    # Paths
    output_dir: Path = Path("D:/AUBR/IntentDrift/data")
    seed_tasks_dir: Path = Path("D:/AUBR/IntentDrift/data/seed_tasks")
    blueprints_dir: Path = Path("D:/AUBR/IntentDrift/data/blueprints")
    trajectories_dir: Path = Path("D:/AUBR/IntentDrift/data/trajectories")
    verified_dir: Path = Path("D:/AUBR/IntentDrift/data/verified")

    # Models
    blueprint_gen_model: str = "claude-sonnet-4-20250514"
    trajectory_gen_model: str = "gpt-4o"
    verification_models: list[str] = field(default_factory=lambda: [
        "claude-sonnet-4-20250514",
        "gpt-4o",
        "gemini-2.5-pro",
    ])

    # Scale
    seed_tasks_per_domain: int = 18
    blueprints_per_seed: int = 4  # across different drift types
    trajectories_per_blueprint: int = 1
    target_total_scenarios: int = 576  # 8 domains x 18 seeds x 4 blueprints

    # Quality thresholds
    min_naturalness_score: float = 4.0
    min_verification_agreement: int = 2  # out of 3 verification models must agree
    target_cohens_kappa: float = 0.75

    # Dialogue parameters
    min_turns: int = 6
    max_turns: int = 18
    min_drift_points: int = 1
    max_drift_points: int = 3

    # Difficulty distribution targets
    difficulty_dist: dict = field(default_factory=lambda: {
        Difficulty.EASY: 0.30,
        Difficulty.MEDIUM: 0.50,
        Difficulty.HARD: 0.20,
    })


@dataclass
class EvalConfig:
    """Configuration for running evaluation experiments."""
    # Models to evaluate
    closed_source_models: list[str] = field(default_factory=lambda: [
        "gpt-4o",
        "gpt-4o-mini",
        "claude-sonnet-4-20250514",
        "claude-haiku-4-5-20251001",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "deepseek-v3",
    ])
    open_source_models: list[str] = field(default_factory=lambda: [
        "meta-llama/Llama-3.1-70B-Instruct",
        "meta-llama/Llama-3.1-8B-Instruct",
        "Qwen/Qwen2.5-72B-Instruct",
        "Qwen/Qwen2.5-7B-Instruct",
        "mistralai/Mistral-Large-Instruct-2407",
    ])

    # Agent frameworks
    agent_frameworks: list[str] = field(default_factory=lambda: [
        "react",
        "function_calling",
        "reflexion",
    ])

    # Judge model
    judge_model: str = "gpt-4o"
    judge_temperature: float = 0.0

    # Experiment settings
    max_turns_per_dialogue: int = 25
    num_runs_per_scenario: int = 3  # for consistency measurement
    results_dir: Path = Path("D:/AUBR/IntentDrift/results")
