"""IntentDrift-Bench: Main Pipeline Orchestrator.

Usage:
    python run_pipeline.py --stage all          # Run full pipeline
    python run_pipeline.py --stage blueprints   # Generate blueprints only
    python run_pipeline.py --stage trajectories # Generate trajectories only
    python run_pipeline.py --stage verify       # Run verification only
    python run_pipeline.py --stage evaluate     # Run evaluation only
"""

import argparse
import json
import logging
from pathlib import Path

from config import PipelineConfig, EvalConfig, DOMAINS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("IntentDrift")


def load_seed_tasks(config: PipelineConfig, domain: str) -> list[dict]:
    """Load seed tasks for a domain."""
    seed_file = config.seed_tasks_dir / domain / "seed_tasks.json"
    if seed_file.exists():
        with open(seed_file, "r", encoding="utf-8") as f:
            return json.load(f)
    logger.warning(f"No seed tasks found at {seed_file}, using placeholder")
    return [{"id": f"{domain}_{i}", "task": f"Placeholder task {i} for {domain}"}
            for i in range(config.seed_tasks_per_domain)]


def load_tool_list(domain: str) -> list[dict]:
    """Load available tools for a domain."""
    tools_file = Path(f"D:/AUBR/IntentDrift/data/tools/{domain}/tools.json")
    if tools_file.exists():
        with open(tools_file, "r", encoding="utf-8") as f:
            return json.load(f)
    # Placeholder tools
    return [
        {"name": f"{domain}_search", "description": f"Search {domain} resources"},
        {"name": f"{domain}_book", "description": f"Book/reserve {domain} item"},
        {"name": f"{domain}_cancel", "description": f"Cancel {domain} booking"},
        {"name": f"{domain}_details", "description": f"Get details of {domain} item"},
        {"name": f"{domain}_compare", "description": f"Compare {domain} options"},
        {"name": f"{domain}_review", "description": f"Get reviews for {domain} item"},
    ]


def stage_blueprints(config: PipelineConfig, llm_client=None):
    """Stage 1-2: Generate blueprints for all domains."""
    from blueprint_generator import BlueprintGenerator

    generator = BlueprintGenerator(config, llm_client)
    total = 0

    for domain in DOMAINS:
        logger.info(f"=== Generating blueprints for domain: {domain} ===")
        seed_tasks = load_seed_tasks(config, domain)
        tool_list = load_tool_list(domain)

        blueprints = generator.generate_blueprints_for_domain(domain, seed_tasks, tool_list)
        generator.save_blueprints(blueprints, domain)
        total += len(blueprints)

    logger.info(f"Total blueprints generated: {total}")


def stage_trajectories(config: PipelineConfig, llm_client=None):
    """Stage 3: Generate trajectories from blueprints."""
    from trajectory_generator import TrajectoryGenerator

    generator = TrajectoryGenerator(config, llm_client)
    total = 0

    for domain in DOMAINS:
        bp_file = config.blueprints_dir / domain / "blueprints.json"
        if not bp_file.exists():
            logger.warning(f"No blueprints for {domain}, skipping")
            continue

        with open(bp_file, "r", encoding="utf-8") as f:
            blueprints = json.load(f)

        logger.info(f"=== Generating trajectories for {domain} ({len(blueprints)} blueprints) ===")
        trajectories = generator.generate_batch(blueprints)
        generator.save_trajectories(trajectories, domain)
        total += len(trajectories)

    logger.info(f"Total trajectories generated: {total}")


def stage_verify(config: PipelineConfig, llm_client=None):
    """Stage 4: Three-layer verification."""
    from verifier import VerificationPipeline

    pipeline = VerificationPipeline(config, llm_client)
    all_results = []

    for domain in DOMAINS:
        traj_file = config.trajectories_dir / domain / "trajectories.json"
        if not traj_file.exists():
            continue

        with open(traj_file, "r", encoding="utf-8") as f:
            trajectories = json.load(f)

        logger.info(f"=== Verifying {domain} ({len(trajectories)} trajectories) ===")
        results = pipeline.verify_batch(trajectories)
        all_results.extend(results)

        # Save verified (L1+L2 passed) trajectories
        verified = []
        for traj, result in zip(trajectories, results):
            if result.layer2_pass:
                verified.append(traj)

        if verified:
            output_dir = config.verified_dir / domain
            output_dir.mkdir(parents=True, exist_ok=True)
            with open(output_dir / "verified.json", "w", encoding="utf-8") as f:
                json.dump(verified, f, ensure_ascii=False, indent=2)

    passed = sum(1 for r in all_results if r.layer2_pass)
    logger.info(f"Verification complete: {passed}/{len(all_results)} passed L1+L2")

    # Save verification report
    report_path = config.output_dir / "verification_report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump([r.to_dict() for r in all_results], f, ensure_ascii=False, indent=2)


def stage_evaluate(eval_config: EvalConfig):
    """Stage 5: Run evaluation experiments."""
    from evaluator import IntentDriftEvaluator, aggregate_scores

    evaluator = IntentDriftEvaluator(eval_config)
    logger.info("Evaluation stage — requires agent responses. See eval runner for details.")
    logger.info(f"Models to evaluate: {len(eval_config.closed_source_models) + len(eval_config.open_source_models)}")
    logger.info(f"Agent frameworks: {eval_config.agent_frameworks}")
    logger.info(f"Results dir: {eval_config.results_dir}")


def main():
    parser = argparse.ArgumentParser(description="IntentDrift-Bench Pipeline")
    parser.add_argument(
        "--stage",
        choices=["blueprints", "trajectories", "verify", "evaluate", "all"],
        default="all",
        help="Which pipeline stage to run",
    )
    args = parser.parse_args()

    config = PipelineConfig()
    eval_config = EvalConfig()

    # Ensure output directories exist
    for d in [config.output_dir, config.seed_tasks_dir, config.blueprints_dir,
              config.trajectories_dir, config.verified_dir, eval_config.results_dir]:
        d.mkdir(parents=True, exist_ok=True)

    # NOTE: Replace None with actual LLM client initialization
    # Example: llm_client = AnthropicClient(api_key=os.environ["ANTHROPIC_API_KEY"])
    llm_client = None

    if args.stage in ("blueprints", "all"):
        stage_blueprints(config, llm_client)

    if args.stage in ("trajectories", "all"):
        stage_trajectories(config, llm_client)

    if args.stage in ("verify", "all"):
        stage_verify(config, llm_client)

    if args.stage in ("evaluate", "all"):
        stage_evaluate(eval_config)

    logger.info("Pipeline complete.")


if __name__ == "__main__":
    main()
