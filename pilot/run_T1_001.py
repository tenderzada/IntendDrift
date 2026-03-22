"""End-to-end pilot runner for task T1-001.

This script demonstrates the full IntentDrift-SWE flow:
1. Load task definition
2. Initialize user simulator
3. Run agent-user conversation loop (agent uses LLM API + tools)
4. Evaluate results (test pass/fail + process metrics)

Usage:
    # Set your API key first:
    #   export ANTHROPIC_API_KEY=sk-...
    #   or
    #   export OPENAI_API_KEY=sk-...

    python run_T1_001.py --model claude     # Run with Claude
    python run_T1_001.py --model gpt4o      # Run with GPT-4o
    python run_T1_001.py --dry-run          # Show conversation flow without LLM
"""

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("T1-001")

WORKSPACE_TEMPLATE = Path("D:/AUBR/IntentDrift/pilot/workspaces/T1-001")
TASK_FILE = Path("D:/AUBR/IntentDrift/pilot/tasks/pilot_tasks.json")

# ─── Tool implementations (real, executable) ───

def tool_read_file(workspace: str, path: str, start: int = 1, end: int = -1) -> str:
    fpath = Path(workspace) / path
    if not fpath.exists():
        return f"Error: File '{path}' not found"
    lines = fpath.read_text(encoding="utf-8").splitlines()
    if end == -1:
        end = len(lines)
    selected = lines[start - 1:end]
    return "\n".join(f"{i+start}: {line}" for i, line in enumerate(selected))


def tool_edit_file(workspace: str, path: str, old_str: str, new_str: str) -> str:
    fpath = Path(workspace) / path
    if not fpath.exists():
        return f"Error: File '{path}' not found"
    content = fpath.read_text(encoding="utf-8")
    if old_str not in content:
        return f"Error: old_str not found in '{path}'"
    content = content.replace(old_str, new_str, 1)
    fpath.write_text(content, encoding="utf-8")
    return f"Successfully edited '{path}'"


def tool_create_file(workspace: str, path: str, content: str) -> str:
    fpath = Path(workspace) / path
    fpath.parent.mkdir(parents=True, exist_ok=True)
    fpath.write_text(content, encoding="utf-8")
    return f"Created '{path}'"


def tool_list_files(workspace: str, path: str = ".") -> str:
    target = Path(workspace) / path
    if not target.exists():
        return f"Error: '{path}' not found"
    entries = sorted(target.iterdir())
    lines = []
    for e in entries:
        prefix = "d " if e.is_dir() else "f "
        lines.append(prefix + e.name)
    return "\n".join(lines) or "(empty directory)"


def tool_search_code(workspace: str, pattern: str, path: str = ".") -> str:
    try:
        result = subprocess.run(
            ["grep", "-rn", pattern, path],
            cwd=workspace, capture_output=True, text=True, timeout=10
        )
        return result.stdout[:3000] if result.stdout else f"No matches for '{pattern}'"
    except Exception as e:
        return f"Search error: {e}"


def tool_run_tests(workspace: str, test_path: str = "tests/") -> str:
    try:
        result = subprocess.run(
            ["python", "-m", "pytest", test_path, "-v", "--tb=short"],
            cwd=workspace, capture_output=True, text=True, timeout=60
        )
        return result.stdout[-3000:] + ("\n" + result.stderr[-1000:] if result.stderr else "")
    except Exception as e:
        return f"Test error: {e}"


def tool_bash(workspace: str, command: str) -> str:
    try:
        result = subprocess.run(
            command, shell=True, cwd=workspace,
            capture_output=True, text=True, timeout=30
        )
        output = result.stdout[-2000:]
        if result.stderr:
            output += "\nSTDERR: " + result.stderr[-1000:]
        return output or "(no output)"
    except Exception as e:
        return f"Command error: {e}"


TOOLS = {
    "read_file": tool_read_file,
    "edit_file": tool_edit_file,
    "create_file": tool_create_file,
    "list_files": tool_list_files,
    "search_code": tool_search_code,
    "run_tests": tool_run_tests,
    "bash": tool_bash,
}

TOOL_DEFINITIONS = [
    {
        "name": "read_file",
        "description": "Read a file from the workspace",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path"},
                "start": {"type": "integer", "description": "Start line (1-indexed)", "default": 1},
                "end": {"type": "integer", "description": "End line (-1 for all)", "default": -1},
            },
            "required": ["path"],
        },
    },
    {
        "name": "edit_file",
        "description": "Edit a file by replacing old_str with new_str",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path"},
                "old_str": {"type": "string", "description": "Exact string to replace"},
                "new_str": {"type": "string", "description": "Replacement string"},
            },
            "required": ["path", "old_str", "new_str"],
        },
    },
    {
        "name": "create_file",
        "description": "Create a new file with given content",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path"},
                "content": {"type": "string", "description": "File content"},
            },
            "required": ["path", "content"],
        },
    },
    {
        "name": "list_files",
        "description": "List files and directories",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory path", "default": "."},
            },
        },
    },
    {
        "name": "search_code",
        "description": "Search for a pattern in source files (grep)",
        "input_schema": {
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Search pattern"},
                "path": {"type": "string", "description": "Directory to search", "default": "."},
            },
            "required": ["pattern"],
        },
    },
    {
        "name": "run_tests",
        "description": "Run pytest on the specified path",
        "input_schema": {
            "type": "object",
            "properties": {
                "test_path": {"type": "string", "description": "Test file or directory", "default": "tests/"},
            },
        },
    },
    {
        "name": "bash",
        "description": "Run a shell command",
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Shell command to run"},
            },
            "required": ["command"],
        },
    },
]

# ─── User Simulator (from harness) ───

class SimpleUserSimulator:
    """Simplified simulator for single-task pilot."""

    def __init__(self, task: dict):
        self.task = task
        self.drift_events = task["drift_events"]
        self.drift_idx = 0
        self.turn = 0
        self.files_modified = False
        self.drift_turns = []

    def respond(self, agent_msg: str, workspace: str) -> str | None:
        self.turn += 1

        # Check file modifications
        result = subprocess.run(
            ["git", "diff", "--name-only"], cwd=workspace,
            capture_output=True, text=True
        )
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"], cwd=workspace,
            capture_output=True, text=True
        )
        changed = set(result.stdout.strip().split("\n") + untracked.stdout.strip().split("\n"))
        changed.discard("")
        self.files_modified = len(changed) > 0

        lower = agent_msg.lower()
        agent_thinks_done = any(w in lower for w in [
            "completed", "done", "fixed", "all tests pass",
            "finished", "complete", "passing",
        ])

        # If there are remaining drifts to trigger
        if self.drift_idx < len(self.drift_events):
            drift = self.drift_events[self.drift_idx]

            # Force-trigger if: agent thinks it's done, OR trigger condition is met
            if agent_thinks_done or self._should_trigger(drift["trigger"]):
                self.drift_turns.append(self.turn)
                msg = drift["user_message"]
                self.drift_idx += 1
                logger.info(f"  >>> [DRIFT turn {self.turn}] {msg[:80]}...")
                return msg

        # All drifts triggered — allow ending
        if agent_thinks_done:
            return None

        # Safety: prevent infinite loops
        if self.turn > 25:
            return None

        if "?" in agent_msg:
            return "Yes, go ahead."
        return "OK, please continue."

    def _should_trigger(self, trigger: str) -> bool:
        if "read at least" in trigger:
            return self.turn >= 2
        if "identified" in trigger:
            return self.files_modified
        if "started" in trigger or "created" in trigger or "modified" in trigger:
            return self.files_modified
        return self.turn >= 3


# ─── Agent (multi-backend: Qwen / Claude / GPT) ───

SYSTEM_PROMPT = """You are a software engineering agent. You have access to a workspace containing a Python project.
Your job is to help the user with their coding request by reading, searching, editing files, and running tests.

IMPORTANT RULES:
- Always read relevant files before editing
- Run tests after making changes to verify your fix
- Make minimal, targeted changes
- If the user changes or refines their request, adapt accordingly

The workspace is a Python project. Use the provided tools to interact with it."""

# Model configs: name → (provider, model_id, base_url, api_key_env)
MODEL_CONFIGS = {
    "qwen": ("openai", "qwen-plus", "https://dashscope.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
    "qwen-max": ("openai", "qwen-max", "https://dashscope.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
    "qwen-turbo": ("openai", "qwen-turbo", "https://dashscope.aliyuncs.com/compatible-mode/v1", "DASHSCOPE_API_KEY"),
    "gpt4o": ("openai", "gpt-4o", None, "OPENAI_API_KEY"),
    "claude": ("anthropic", "claude-sonnet-4-20250514", None, "ANTHROPIC_API_KEY"),
    "deepseek": ("openai", "deepseek-chat", "https://api.deepseek.com/v1", "DEEPSEEK_API_KEY"),
}


def _tool_defs_openai() -> list[dict]:
    """Convert our tool definitions to OpenAI function-calling format."""
    tools = []
    for td in TOOL_DEFINITIONS:
        tools.append({
            "type": "function",
            "function": {
                "name": td["name"],
                "description": td["description"],
                "parameters": td["input_schema"],
            },
        })
    return tools


def call_openai_compatible(conversation: list[dict], model_name: str) -> dict:
    """Call OpenAI-compatible API (Qwen / GPT / DeepSeek) with function calling."""
    import openai

    cfg = MODEL_CONFIGS[model_name]
    _, model_id, base_url, api_key_env = cfg

    api_key = os.environ.get(api_key_env, "")
    if not api_key:
        raise RuntimeError(f"Please set {api_key_env} environment variable")

    client_kwargs = {"api_key": api_key}
    if base_url:
        client_kwargs["base_url"] = base_url
    client = openai.OpenAI(**client_kwargs)

    # Convert conversation from Anthropic format to OpenAI format
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for msg in conversation:
        role = msg["role"]
        content = msg["content"]

        if role == "user" and isinstance(content, list):
            # Tool results — convert from Anthropic format
            for item in content:
                if isinstance(item, dict) and item.get("type") == "tool_result":
                    messages.append({
                        "role": "tool",
                        "tool_call_id": item["tool_use_id"],
                        "content": item["content"],
                    })
        elif role == "assistant" and isinstance(content, list):
            # Assistant with tool_use blocks — convert
            text_parts = []
            tc_list = []
            for item in content:
                if isinstance(item, dict):
                    if item.get("type") == "text":
                        text_parts.append(item["text"])
                    elif item.get("type") == "tool_use":
                        tc_list.append({
                            "id": item["id"],
                            "type": "function",
                            "function": {
                                "name": item["name"],
                                "arguments": json.dumps(item["input"]),
                            },
                        })
            msg_dict = {"role": "assistant", "content": "\n".join(text_parts) or None}
            if tc_list:
                msg_dict["tool_calls"] = tc_list
            messages.append(msg_dict)
        else:
            messages.append({"role": role, "content": content if isinstance(content, str) else str(content)})

    response = client.chat.completions.create(
        model=model_id,
        messages=messages,
        tools=_tool_defs_openai(),
        temperature=0.3,
        max_tokens=4096,
    )

    choice = response.choices[0]
    message = choice.message
    text = message.content or ""
    tool_calls = []

    if message.tool_calls:
        for tc in message.tool_calls:
            try:
                params = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                params = {}
            tool_calls.append({
                "id": tc.id,
                "tool_name": tc.function.name,
                "parameters": params,
            })

    stop_reason = "tool_use" if choice.finish_reason == "tool_calls" else "end_turn"

    return {
        "message": text,
        "tool_calls": tool_calls,
        "stop_reason": stop_reason,
    }


def call_claude(conversation: list[dict], model_name: str = "claude") -> dict:
    """Call Claude API with tools."""
    import anthropic

    cfg = MODEL_CONFIGS[model_name]
    _, model_id, _, api_key_env = cfg

    api_key = os.environ.get(api_key_env, "")
    if not api_key:
        raise RuntimeError(f"Please set {api_key_env} environment variable")

    client = anthropic.Anthropic(api_key=api_key)

    response = client.messages.create(
        model=model_id,
        max_tokens=4096,
        temperature=0.3,
        system=SYSTEM_PROMPT,
        tools=TOOL_DEFINITIONS,
        messages=conversation,
    )

    text_parts = []
    tool_calls = []

    for block in response.content:
        if block.type == "text":
            text_parts.append(block.text)
        elif block.type == "tool_use":
            tool_calls.append({
                "id": block.id,
                "tool_name": block.name,
                "parameters": block.input,
            })

    return {
        "message": "\n".join(text_parts),
        "tool_calls": tool_calls,
        "stop_reason": response.stop_reason,
    }


def call_agent(conversation: list[dict], model_name: str) -> dict:
    """Route to the correct API backend based on model name."""
    provider = MODEL_CONFIGS[model_name][0]
    if provider == "anthropic":
        return call_claude(conversation, model_name)
    else:
        return call_openai_compatible(conversation, model_name)


def execute_tool(workspace: str, tool_name: str, params: dict) -> str:
    """Execute a tool in the workspace."""
    fn = TOOLS.get(tool_name)
    if not fn:
        return f"Unknown tool: {tool_name}"
    try:
        return fn(workspace, **params)
    except TypeError as e:
        return f"Tool error: {e}"


# ─── Main Loop ───

def run_conversation(task: dict, workspace: str, model_name: str = "qwen", dry_run: bool = False):
    """Run the full agent-user-drift conversation loop."""
    simulator = SimpleUserSimulator(task)
    conversation = []  # Anthropic messages format
    all_entries = []    # Our log format

    # Initial user message
    user_msg = task["initial_request"]
    conversation.append({"role": "user", "content": user_msg})
    all_entries.append({"turn_id": 0, "role": "user", "content": user_msg})
    logger.info(f"  User: {user_msg}")

    for turn in range(30):
        if dry_run:
            logger.info(f"  Agent: [dry-run, would call LLM here]")
            user_resp = simulator.respond("I'll look into it.", workspace)
            if user_resp is None:
                break
            conversation.append({"role": "assistant", "content": "I'll look into it."})
            conversation.append({"role": "user", "content": user_resp})
            all_entries.append({"turn_id": turn * 2 + 1, "role": "agent", "content": "[dry-run]"})
            all_entries.append({"turn_id": turn * 2 + 2, "role": "user", "content": user_resp})
            logger.info(f"  User: {user_resp}")
            continue

        # Agent turn (may involve multiple tool calls)
        agent_result = call_agent(conversation, model_name)
        agent_msg = agent_result["message"]
        tool_calls = agent_result["tool_calls"]

        entry = {
            "turn_id": len(all_entries),
            "role": "agent",
            "content": agent_msg,
            "tool_calls": tool_calls,
        }
        all_entries.append(entry)

        if agent_msg:
            logger.info(f"  Agent: {agent_msg[:120]}...")

        # Handle tool calls
        if tool_calls:
            # Build assistant content with tool_use blocks
            assistant_content = []
            if agent_msg:
                assistant_content.append({"type": "text", "text": agent_msg})
            for tc in tool_calls:
                assistant_content.append({
                    "type": "tool_use",
                    "id": tc["id"],
                    "name": tc["tool_name"],
                    "input": tc["parameters"],
                })
            conversation.append({"role": "assistant", "content": assistant_content})

            # Execute tools and build tool_result
            tool_results = []
            for tc in tool_calls:
                result = execute_tool(workspace, tc["tool_name"], tc["parameters"])
                logger.info(f"    Tool[{tc['tool_name']}] → {result[:100]}...")
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc["id"],
                    "content": result,
                })
            conversation.append({"role": "user", "content": tool_results})

            # If agent wants to continue with tools, check if user should interject
            if agent_result["stop_reason"] == "tool_use":
                # Give the user simulator a chance to interject (drift trigger check)
                # This happens every tool-call round — mirrors real interactive use
                interject = simulator.respond(
                    f"[Agent used tools: {', '.join(tc['tool_name'] for tc in tool_calls)}]",
                    workspace,
                )
                if interject is not None and interject != "OK, please continue.":
                    # User has something to say (likely a drift message)
                    conversation.append({"role": "user", "content": interject})
                    all_entries.append({
                        "turn_id": len(all_entries),
                        "role": "user",
                        "content": interject,
                    })
                    logger.info(f"  User: {interject}")
                else:
                    # User has nothing special to say, let agent continue
                    pass
                continue
        else:
            conversation.append({"role": "assistant", "content": agent_msg})

        # User responds
        user_resp = simulator.respond(agent_msg, workspace)
        if user_resp is None:
            logger.info("  [Conversation ended — agent indicated completion]")
            break

        conversation.append({"role": "user", "content": user_resp})
        all_entries.append({
            "turn_id": len(all_entries),
            "role": "user",
            "content": user_resp,
        })
        logger.info(f"  User: {user_resp}")

    return all_entries, {
        "total_turns": simulator.turn,
        "drift_turn_ids": simulator.drift_turns,
        "all_drifts_triggered": simulator.drift_idx >= len(simulator.drift_events),
    }


def evaluate(task: dict, workspace: str, sim_metrics: dict):
    """Run evaluation and print results."""
    logger.info("\n" + "=" * 50)
    logger.info("EVALUATION")
    logger.info("=" * 50)

    # Run all tests
    result = subprocess.run(
        ["python", "-m", "pytest", "tests/", "-v", "--tb=short"],
        cwd=workspace, capture_output=True, text=True, timeout=60
    )
    logger.info(result.stdout)

    passed = result.returncode == 0
    # Count individual test results
    pass_count = result.stdout.count(" PASSED")
    fail_count = result.stdout.count(" FAILED")

    logger.info(f"\nTests: {pass_count} passed, {fail_count} failed")
    logger.info(f"Overall: {'PASS' if passed else 'FAIL'}")
    logger.info(f"Drift triggered: {sim_metrics['all_drifts_triggered']}")
    logger.info(f"Drift turns: {sim_metrics['drift_turn_ids']}")
    logger.info(f"Total turns: {sim_metrics['total_turns']}")

    return passed


def main():
    parser = argparse.ArgumentParser(description="IntentDrift-SWE T1-001 Pilot")
    parser.add_argument(
        "--model", default="qwen",
        choices=list(MODEL_CONFIGS.keys()),
        help="Model to use: qwen (default), qwen-max, qwen-turbo, gpt4o, claude, deepseek",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    cfg = MODEL_CONFIGS[args.model]
    logger.info(f"Backend: {cfg[0]} | Model: {cfg[1]} | Key env: {cfg[3]}")

    # Load task
    with open(TASK_FILE, encoding="utf-8") as f:
        tasks = json.load(f)
    task = next(t for t in tasks if t["task_id"] == "T1-001")

    # Create fresh workspace copy
    run_workspace = Path("D:/AUBR/IntentDrift/pilot/runs/T1-001_run")
    if run_workspace.exists():
        # Windows: git objects are read-only, need to fix permissions first
        def _on_rm_error(func, path, exc_info):
            import stat
            os.chmod(path, stat.S_IWRITE)
            func(path)
        shutil.rmtree(run_workspace, onexc=_on_rm_error)
    shutil.copytree(WORKSPACE_TEMPLATE, run_workspace)

    # Init git in the copy
    subprocess.run(["git", "init", "-q"], cwd=run_workspace)
    subprocess.run(["git", "add", "-A"], cwd=run_workspace)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=run_workspace)

    logger.info(f"Task: {task['task_id']} ({task['drift_type']})")
    logger.info(f"Workspace: {run_workspace}")
    logger.info(f"Model: {args.model}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info("")

    # Run
    conversation_log, sim_metrics = run_conversation(
        task, str(run_workspace), model_name=args.model, dry_run=args.dry_run
    )

    # Evaluate
    passed = evaluate(task, str(run_workspace), sim_metrics)

    # Save log
    results_dir = Path("D:/AUBR/IntentDrift/pilot/results")
    results_dir.mkdir(parents=True, exist_ok=True)
    log_file = results_dir / f"T1-001_{args.model}_log.json"
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump({
            "task_id": task["task_id"],
            "model": args.model,
            "passed": passed,
            "sim_metrics": sim_metrics,
            "conversation": conversation_log,
        }, f, indent=2, ensure_ascii=False)
    logger.info(f"\nLog saved to: {log_file}")


if __name__ == "__main__":
    main()
