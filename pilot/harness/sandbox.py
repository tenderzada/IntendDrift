"""Sandbox abstraction layer.

Supports two backends:
- "daytona": Daytona cloud sandboxes (for Ubuntu server / production)
- "local": Local subprocess execution (for quick local testing)

Usage:
    sandbox = create_sandbox(backend="daytona", workspace_path="pilot/workspaces/T1-001")
    result = sandbox.exec("python -m pytest tests/ -v")
    content = sandbox.read_file("app.py")
    sandbox.write_file("app.py", new_content)
    sandbox.destroy()
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path
from abc import ABC, abstractmethod


class Sandbox(ABC):
    """Abstract sandbox interface."""

    @abstractmethod
    def exec(self, command: str, cwd: str = "/workspace") -> str:
        """Execute a shell command, return stdout+stderr."""

    @abstractmethod
    def read_file(self, path: str) -> str:
        """Read a file from the sandbox."""

    @abstractmethod
    def write_file(self, path: str, content: str) -> None:
        """Write a file in the sandbox."""

    @abstractmethod
    def upload_dir(self, local_dir: str, remote_dir: str = "/workspace") -> None:
        """Upload a local directory to the sandbox."""

    @abstractmethod
    def file_exists(self, path: str) -> bool:
        """Check if a file exists."""

    @abstractmethod
    def list_files(self, path: str = "/workspace") -> list[str]:
        """List files in a directory."""

    @abstractmethod
    def destroy(self) -> None:
        """Destroy the sandbox."""

    @property
    @abstractmethod
    def workspace_dir(self) -> str:
        """Return the workspace directory path."""


class DockerSandbox(Sandbox):
    """Docker-based sandbox using BeyondSWE pre-built images.

    Each sandbox is an isolated Docker container with the real project
    environment (dependencies, code, tests) already set up by BeyondSWE.
    The container is created from the BeyondSWE image, checked out to the
    bug-version commit, and destroyed after evaluation.

    For tasks without a BeyondSWE image (e.g. custom tasks), falls back
    to python:3.11-slim with workspace files copied in.
    """

    def __init__(self, workspace_template: str = "", task: dict = None):
        import uuid
        self._container_name = f"intentdrift-{uuid.uuid4().hex[:8]}"
        self._template = workspace_template

        image = None
        parent_commit = None
        repo_subdir = None

        # If task has BeyondSWE image info, use it
        if task:
            image = task.get("image")
            parent_commit = task.get("commit")
            # Detect repo subdirectory from task source
            repo = task.get("repo", "")
            if "/" in repo:
                repo_subdir = repo.split("/")[1]  # e.g. "Pylons/pyramid" -> "pyramid"

        if image:
            # BeyondSWE mode: use pre-built image with real project
            self._image = image
            subprocess.run(
                ["docker", "run", "-d", "--name", self._container_name,
                 image, "sleep", "3600"],
                capture_output=True, check=True,
            )

            # Find the workspace directory (BeyondSWE puts repo in /workspace/<repo_name>/)
            if repo_subdir:
                self._workspace = f"/workspace/{repo_subdir}"
            else:
                # Auto-detect: find the git repo inside /workspace
                result = subprocess.run(
                    ["docker", "exec", self._container_name, "bash", "-c",
                     "find /workspace -maxdepth 2 -name '.git' -type d | head -1"],
                    capture_output=True, text=True,
                )
                git_dir = result.stdout.strip()
                self._workspace = str(Path(git_dir).parent) if git_dir else "/workspace"

            # Checkout to the bug version (parent commit)
            if parent_commit:
                self._docker_exec(f"git checkout {parent_commit}")
                self._docker_exec("git checkout -b agent-work")  # clean branch for agent's changes

        else:
            # Fallback: plain python image + copy files in
            self._image = "python:3.11-slim"
            self._workspace = "/workspace"
            subprocess.run(
                ["docker", "run", "-d", "--name", self._container_name,
                 "-w", self._workspace, self._image,
                 "sleep", "3600"],
                capture_output=True, check=True,
            )
            self._docker_exec("pip install flask pytest -q")

            if workspace_template and Path(workspace_template).exists():
                subprocess.run(
                    ["docker", "cp", f"{workspace_template}/.",
                     f"{self._container_name}:{self._workspace}/"],
                    capture_output=True, check=True,
                )
                self._docker_exec("git init -q && git add -A && git commit -q -m initial --allow-empty")

    def _docker_exec(self, command: str) -> str:
        result = subprocess.run(
            ["docker", "exec", self._container_name, "bash", "-c",
             f"cd {self._workspace} && {command}"],
            capture_output=True, text=True, timeout=120,
        )
        output = result.stdout
        if result.stderr:
            output += "\n" + result.stderr
        return output

    def exec(self, command: str, cwd: str = "") -> str:
        work_cwd = cwd or self._workspace
        return self._docker_exec(f"cd {work_cwd} && {command}")

    def read_file(self, path: str) -> str:
        return self._docker_exec(f"cat {path}")

    def write_file(self, path: str, content: str) -> None:
        # Write via heredoc to handle special chars
        escaped = content.replace("'", "'\\''")
        self._docker_exec(f"mkdir -p $(dirname {path}) && cat > {path} << 'INNEREOF'\n{escaped}\nINNEREOF")

    def upload_dir(self, local_dir: str, remote_dir: str = "/workspace") -> None:
        subprocess.run(
            ["docker", "cp", f"{local_dir}/.", f"{self._container_name}:{remote_dir}/"],
            capture_output=True, check=True,
        )

    def file_exists(self, path: str) -> bool:
        result = self._docker_exec(f"test -f {path} && echo yes || echo no")
        return "yes" in result

    def list_files(self, path: str = ".") -> list[str]:
        result = self._docker_exec(f"ls -1 {path}")
        return [f for f in result.strip().split("\n") if f]

    def destroy(self) -> None:
        subprocess.run(
            ["docker", "rm", "-f", self._container_name],
            capture_output=True,
        )

    @property
    def workspace_dir(self) -> str:
        return self._workspace


class LocalSandbox(Sandbox):
    """Local filesystem sandbox (subprocess-based)."""

    def __init__(self, workspace_template: str):
        # Copy template to a temp run directory
        self._template = Path(workspace_template)
        self._run_dir = self._template.parent.parent / "runs" / f"{self._template.name}_run"

        if self._run_dir.exists():
            def _on_rm_error(func, path, exc_info):
                os.chmod(path, stat.S_IWRITE)
                func(path)
            shutil.rmtree(self._run_dir, onexc=_on_rm_error)

        shutil.copytree(self._template, self._run_dir)

        # Init git for change tracking
        subprocess.run(["git", "init", "-q"], cwd=self._run_dir, capture_output=True)
        subprocess.run(["git", "add", "-A"], cwd=self._run_dir, capture_output=True)
        subprocess.run(
            ["git", "commit", "-q", "-m", "initial", "--allow-empty"],
            cwd=self._run_dir, capture_output=True,
        )

    def exec(self, command: str, cwd: str = "") -> str:
        work_dir = cwd if cwd and cwd != "/workspace" else str(self._run_dir)
        try:
            result = subprocess.run(
                command, shell=True, cwd=work_dir,
                capture_output=True, text=True, timeout=120,
            )
            output = result.stdout
            if result.stderr:
                output += "\n" + result.stderr
            return output
        except subprocess.TimeoutExpired:
            return "ERROR: Command timed out"
        except Exception as e:
            return f"ERROR: {e}"

    def read_file(self, path: str) -> str:
        fpath = self._run_dir / path
        return fpath.read_text(encoding="utf-8")

    def write_file(self, path: str, content: str) -> None:
        fpath = self._run_dir / path
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(content, encoding="utf-8")

    def upload_dir(self, local_dir: str, remote_dir: str = "/workspace") -> None:
        # Local sandbox: template already copied at init
        pass

    def file_exists(self, path: str) -> bool:
        return (self._run_dir / path).exists()

    def list_files(self, path: str = ".") -> list[str]:
        target = self._run_dir / path if path != "/workspace" else self._run_dir
        return [e.name for e in sorted(target.iterdir())]

    def destroy(self) -> None:
        # Keep run dir for inspection; user can clean up manually
        pass

    @property
    def workspace_dir(self) -> str:
        return str(self._run_dir)


def create_sandbox(backend: str = "local", workspace_path: str = "", task: dict = None) -> Sandbox:
    """Factory: create a sandbox with the specified backend.

    Backends:
        - "local": runs directly on host filesystem (fast, no isolation)
        - "docker": runs in a Docker container (isolated, needs Docker)
                    If task has a BeyondSWE image, uses that instead of python:3.11-slim
    """
    if backend == "docker":
        return DockerSandbox(workspace_template=workspace_path, task=task)
    elif backend == "local":
        return LocalSandbox(workspace_path)
    else:
        raise ValueError(f"Unknown backend: {backend}. Use 'local' or 'docker'.")
