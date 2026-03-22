#!/usr/bin/env python3
"""IntentDrift-SWE Pilot Runner (Daytona + Local sandbox support).

Usage:
    # Local mode (default, no sandbox service needed):
    python run.py --task T1-001 --model qwen

    # Daytona mode (requires DAYTONA_API_KEY):
    python run.py --task T1-001 --model qwen --sandbox daytona

    # Dry run (no LLM calls):
    python run.py --task T1-001 --dry-run

    # List all tasks:
    python run.py --list

Environment variables:
    DASHSCOPE_API_KEY   - for Qwen models (DashScope)
    OPENAI_API_KEY      - for GPT models
    ANTHROPIC_API_KEY   - for Claude models
    DEEPSEEK_API_KEY    - for DeepSeek models
    DAYTONA_API_KEY     - for Daytona sandbox (optional)
"""

import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

# Add harness to path
sys.path.insert(0, str(Path(__file__).parent / "harness"))

from sandbox import create_sandbox, Sandbox

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("IntentDrift-SWE")

PROJECT_ROOT = Path(__file__).parent
TASKS_FILE = PROJECT_ROOT / "tasks" / "pilot_tasks.json"

# ─── Model configs ───

MODEL_CONFIGS = {
    "qwen":       ("openai", "qwen-plus",                 "https://dashscope.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
    "qwen-max":   ("openai", "qwen-max",                  "https://dashscope.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
    "qwen-turbo": ("openai", "qwen-turbo",                "https://dashscope.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
    "gpt4o":      ("openai", "gpt-4o",                    None,                                                "OPENAI_API_KEY"),
    "claude":     ("openai", "claude-sonnet-4-20250514",   "https://api.anthropic.com/v1",                      "ANTHROPIC_API_KEY"),
    "deepseek":   ("openai", "deepseek-chat",              "https://api.deepseek.com/v1",                       "DEEPSEEK_API_KEY"),
}

SYSTEM_PROMPT = """You are a software engineering agent. You have access to a workspace containing a Python project.
Your job is to help the user with their coding request by reading, searching, editing files, and running tests.

IMPORTANT RULES:
- Always read relevant files before editing them
- Run tests after making changes to verify your fix
- Make minimal, targeted changes
- If the user changes or refines their request, adapt accordingly
- When you are done, say "The fix is complete" or similar

The workspace is a Python project. Use the provided tools to interact with it."""

TOOL_DEFS_OPENAI = [
    {"type": "function", "function": {"name": "read_file", "description": "Read a file from the workspace", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Relative file path"}, "start": {"type": "integer", "description": "Start line (1-indexed)", "default": 1}, "end": {"type": "integer", "description": "End line (-1 for all)", "default": -1}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "edit_file", "description": "Edit a file by replacing old_str with new_str", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Relative file path"}, "old_str": {"type": "string", "description": "Exact string to replace"}, "new_str": {"type": "string", "description": "Replacement string"}}, "required": ["path", "old_str", "new_str"]}}},
    {"type": "function", "function": {"name": "create_file", "description": "Create a new file", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Relative file path"}, "content": {"type": "string", "description": "File content"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "list_files", "description": "List files in a directory", "parameters": {"type": "object", "properties": {"path": {"type": "string", "description": "Directory path", "default": "."}}}}},
    {"type": "function", "function": {"name": "search_code", "description": "Grep for a pattern in source files", "parameters": {"type": "object", "properties": {"pattern": {"type": "string", "description": "Search pattern"}, "path": {"type": "string", "description": "Directory to search", "default": "."}}, "required": ["pattern"]}}},
    {"type": "function", "function": {"name": "run_tests", "description": "Run pytest", "parameters": {"type": "object", "properties": {"test_path": {"type": "string", "description": "Test file or directory", "default": "tests/"}}}}},
    {"type": "function", "function": {"name": "bash", "description": "Run a shell command", "parameters": {"type": "object", "properties": {"command": {"type": "string", "description": "Command to run"}}, "required": ["command"]}}},
]


# ─── Tool execution (via sandbox) ───

def execute_tool(sandbox: Sandbox, tool_name: str, params: dict) -> str:
    """Execute a tool inside the sandbox."""
    try:
        if tool_name == "read_file":
            path = params["path"]
            content = sandbox.read_file(path)
            lines = content.splitlines()
            start = params.get("start", 1) - 1
            end = params.get("end", -1)
            if end == -1:
                end = len(lines)
            selected = lines[start:end]
            return "\n".join(f"{i+start+1}: {l}" for i, l in enumerate(selected))

        elif tool_name == "edit_file":
            content = sandbox.read_file(params["path"])
            if params["old_str"] not in content:
                return f"Error: old_str not found in '{params['path']}'"
            content = content.replace(params["old_str"], params["new_str"], 1)
            sandbox.write_file(params["path"], content)
            return f"Successfully edited '{params['path']}'"

        elif tool_name == "create_file":
            sandbox.write_file(params["path"], params["content"])
            return f"Created '{params['path']}'"

        elif tool_name == "list_files":
            path = params.get("path", ".")
            entries = sandbox.list_files(path)
            return "\n".join(entries) or "(empty)"

        elif tool_name == "search_code":
            return sandbox.exec(f"grep -rn '{params['pattern']}' {params.get('path', '.')}")

        elif tool_name == "run_tests":
            return sandbox.exec(f"python -m pytest {params.get('test_path', 'tests/')} -v --tb=short")

        elif tool_name == "bash":
            return sandbox.exec(params["command"])

        else:
            return f"Unknown tool: {tool_name}"
    except Exception as e:
        return f"Tool error: {e}"


# ─── LLM call (unified OpenAI-compatible) ───

def call_llm(messages: list[dict], model_name: str) -> dict:
    """Call LLM via OpenAI-compatible API. Returns {message, tool_calls, stop_reason}."""
    import openai

    _, model_id, base_url, api_key_env = MODEL_CONFIGS[model_name]
    api_key = os.environ.get(api_key_env, "")
    if not api_key:
        raise RuntimeError(f"Set {api_key_env} environment variable")

    client_kw = {"api_key": api_key}
    if base_url:
        client_kw["base_url"] = base_url
    client = openai.OpenAI(**client_kw)

    resp = client.chat.completions.create(
        model=model_id,
        messages=messages,
        tools=TOOL_DEFS_OPENAI,
        temperature=0.3,
        max_tokens=4096,
    )

    choice = resp.choices[0]
    msg = choice.message
    tool_calls = []
    if msg.tool_calls:
        for tc in msg.tool_calls:
            try:
                params = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                params = {}
            tool_calls.append({"id": tc.id, "name": tc.function.name, "params": params})

    return {
        "message": msg.content or "",
        "tool_calls": tool_calls,
        "finish": choice.finish_reason,
    }


# ─── User Simulator ───

class UserSimulator:
    def __init__(self, task: dict):
        self.drift_events = task["drift_events"]
        self.drift_idx = 0
        self.turn = 0
        self.drift_turns = []

    def respond(self, agent_msg: str, sandbox: Sandbox) -> str | None:
        self.turn += 1

        # Check workspace changes
        diff = sandbox.exec("git diff --name-only 2>/dev/null").strip()
        untracked = sandbox.exec("git ls-files --others --exclude-standard 2>/dev/null").strip()
        files_changed = bool(diff or untracked)

        agent_done = any(w in agent_msg.lower() for w in [
            "complete", "done", "fixed", "all tests pass", "finished", "passing",
        ])

        # Trigger next drift if conditions met
        if self.drift_idx < len(self.drift_events):
            trigger = self.drift_events[self.drift_idx]["trigger"]
            should = (
                agent_done
                or (files_changed and any(k in trigger for k in ["started", "created", "modified", "implemented", "written"]))
                or (self.turn >= 2 and any(k in trigger for k in ["read", "identified"]))
                or self.turn >= 4
            )
            if should:
                msg = self.drift_events[self.drift_idx]["user_message"]
                self.drift_turns.append(self.turn)
                self.drift_idx += 1
                logger.info(f"  >>> [DRIFT turn {self.turn}] {msg[:80]}...")
                return msg

        # All drifts done — allow ending
        if agent_done:
            return None

        # Safety valve
        if self.turn > 25:
            return None

        if "?" in agent_msg:
            return "Yes, go ahead."
        return "OK, please continue."

    @property
    def metrics(self) -> dict:
        return {
            "total_turns": self.turn,
            "drift_turn_ids": self.drift_turns,
            "all_drifts_triggered": self.drift_idx >= len(self.drift_events),
        }


# ─── Main conversation loop ───

def run_task(task: dict, model_name: str, sandbox: Sandbox, dry_run: bool = False) -> dict:
    """Run one task. Returns full result dict."""
    sim = UserSimulator(task)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    log = []

    # Initial user message
    user_msg = task["initial_request"]
    messages.append({"role": "user", "content": user_msg})
    log.append({"turn": 0, "role": "user", "content": user_msg})
    logger.info(f"  User: {user_msg}")

    for step in range(60):  # max iterations (tool loops + user turns)
        if dry_run:
            resp_text = "[dry-run]"
            user_resp = sim.respond(resp_text, sandbox)
            if user_resp is None:
                break
            messages.append({"role": "assistant", "content": resp_text})
            messages.append({"role": "user", "content": user_resp})
            log.append({"turn": len(log), "role": "agent", "content": resp_text})
            log.append({"turn": len(log), "role": "user", "content": user_resp})
            logger.info(f"  User: {user_resp}")
            continue

        # Call LLM
        result = call_llm(messages, model_name)
        text = result["message"]
        tool_calls = result["tool_calls"]

        log.append({"turn": len(log), "role": "agent", "content": text,
                     "tool_calls": [{"name": tc["name"], "params": tc["params"]} for tc in tool_calls]})

        if text:
            logger.info(f"  Agent: {text[:120]}...")

        # Execute tool calls
        if tool_calls:
            assistant_msg = {"role": "assistant", "content": text or None, "tool_calls": [
                {"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": json.dumps(tc["params"])}}
                for tc in tool_calls
            ]}
            messages.append(assistant_msg)

            for tc in tool_calls:
                tool_result = execute_tool(sandbox, tc["name"], tc["params"])
                logger.info(f"    [{tc['name']}] → {tool_result[:100]}...")
                messages.append({"role": "tool", "tool_call_id": tc["id"], "content": tool_result})

            # Check if user should interject (drift trigger)
            if result["finish"] == "tool_calls":
                interject = sim.respond(
                    f"[agent used: {', '.join(tc['name'] for tc in tool_calls)}]", sandbox
                )
                if interject and interject not in ("OK, please continue.", "Yes, go ahead."):
                    messages.append({"role": "user", "content": interject})
                    log.append({"turn": len(log), "role": "user", "content": interject})
                    logger.info(f"  User: {interject}")
                continue
        else:
            messages.append({"role": "assistant", "content": text})

        # User turn
        user_resp = sim.respond(text, sandbox)
        if user_resp is None:
            logger.info("  [Conversation ended]")
            break
        messages.append({"role": "user", "content": user_resp})
        log.append({"turn": len(log), "role": "user", "content": user_resp})
        logger.info(f"  User: {user_resp}")

    # Evaluate
    logger.info("\n" + "=" * 50 + "\nEVALUATION\n" + "=" * 50)
    test_output = sandbox.exec("python -m pytest tests/ -v --tb=short")
    logger.info(test_output)

    passed = "failed" not in test_output.split("=")[-1].lower() and "passed" in test_output.lower()
    pass_count = test_output.count(" PASSED")
    fail_count = test_output.count(" FAILED")

    logger.info(f"\nTests: {pass_count} passed, {fail_count} failed")
    logger.info(f"Overall: {'PASS' if passed else 'FAIL'}")
    logger.info(f"Drifts triggered: {sim.metrics['drift_turn_ids']}")

    return {
        "task_id": task["task_id"],
        "drift_type": task["drift_type"],
        "model": model_name,
        "passed": passed,
        "tests_passed": pass_count,
        "tests_failed": fail_count,
        "sim_metrics": sim.metrics,
        "conversation": log,
    }


# ─── CLI ───

def main():
    parser = argparse.ArgumentParser(description="IntentDrift-SWE Pilot Runner")
    parser.add_argument("--task", type=str, help="Task ID (e.g. T1-001). Run all if omitted.")
    parser.add_argument("--model", default="qwen", choices=list(MODEL_CONFIGS.keys()))
    parser.add_argument("--sandbox", default="local", choices=["local", "daytona"])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list", action="store_true", help="List all tasks and exit")
    args = parser.parse_args()

    with open(TASKS_FILE, encoding="utf-8") as f:
        all_tasks = json.load(f)

    if args.list:
        for t in all_tasks:
            print(f"  [{t['task_id']}] {t['drift_type']:30s} {t['initial_request'][:60]}...")
        return

    tasks = [t for t in all_tasks if t["task_id"] == args.task] if args.task else all_tasks
    if not tasks:
        print(f"Task '{args.task}' not found.")
        return

    cfg = MODEL_CONFIGS[args.model]
    logger.info(f"Model: {cfg[1]} via {cfg[0]} | Sandbox: {args.sandbox}")

    results = []
    for task in tasks:
        logger.info(f"\n{'='*60}\nTask: {task['task_id']} ({task['drift_type']})\n{'='*60}")

        tid = task["task_id"]  # e.g. "T1-001"
        workspace_path = str(PROJECT_ROOT / "workspaces" / tid)
        # Fallback: use T1-001 workspace for all tasks (only T1-001 has a workspace for now)
        if not Path(workspace_path).exists():
            workspace_path = str(PROJECT_ROOT / "workspaces" / "T1-001")
            if not Path(workspace_path).exists():
                logger.warning(f"No workspace for {task['task_id']}, skipping")
                continue

        sandbox = create_sandbox(backend=args.sandbox, workspace_path=workspace_path)
        try:
            result = run_task(task, args.model, sandbox, dry_run=args.dry_run)
            results.append(result)
        finally:
            sandbox.destroy()

    # Save results
    results_dir = PROJECT_ROOT / "results"
    results_dir.mkdir(exist_ok=True)
    out_file = results_dir / f"results_{args.model}_{args.sandbox}.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    logger.info(f"\nResults saved to: {out_file}")

    # Summary
    print(f"\n{'='*50}")
    print(f"SUMMARY: {len(results)} tasks on {args.model}")
    print(f"{'='*50}")
    passed = sum(1 for r in results if r["passed"])
    print(f"Pass: {passed}/{len(results)}")
    for r in results:
        status = "PASS" if r["passed"] else "FAIL"
        drifts = len(r["sim_metrics"]["drift_turn_ids"])
        print(f"  [{r['task_id']}] {status} | drifts:{drifts} | turns:{r['sim_metrics']['total_turns']}")


if __name__ == "__main__":
    main()
