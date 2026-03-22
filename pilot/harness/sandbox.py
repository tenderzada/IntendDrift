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


class DaytonaSandbox(Sandbox):
    """Daytona sandbox backend (works with both cloud and self-hosted)."""

    def __init__(self):
        from daytona import Daytona, DaytonaConfig, CreateSandboxFromImageParams
        import os

        config = DaytonaConfig(
            api_key=os.environ.get("DAYTONA_API_KEY", ""),
            server_url=os.environ.get("DAYTONA_API_URL", "https://app.daytona.io/api"),
        )
        self._client = Daytona(config)

        params = CreateSandboxFromImageParams(
            image="python:3.11-slim",
            language="python",
        )
        self._sandbox = self._client.create(params)
        self._workspace = "/home/daytona"

    def exec(self, command: str, cwd: str = "") -> str:
        work_cwd = cwd or self._workspace
        result = self._sandbox.process.exec(
            f"cd {work_cwd} && {command}",
            timeout=120,
        )
        # Handle different result types across SDK versions
        if hasattr(result, 'output'):
            return result.output or ""
        if hasattr(result, 'result'):
            return result.result or ""
        return str(result)

    def read_file(self, path: str) -> str:
        full_path = f"{self._workspace}/{path}" if not path.startswith("/") else path
        data = self._sandbox.fs.download_file(full_path)
        return data.decode("utf-8") if isinstance(data, bytes) else str(data)

    def write_file(self, path: str, content: str) -> None:
        full_path = f"{self._workspace}/{path}" if not path.startswith("/") else path
        data = content.encode("utf-8") if isinstance(content, str) else content
        self._sandbox.fs.upload_file(full_path, data)

    def upload_dir(self, local_dir: str, remote_dir: str = "/workspace") -> None:
        for root, dirs, files in os.walk(local_dir):
            for f in files:
                local_path = os.path.join(root, f)
                rel_path = os.path.relpath(local_path, local_dir)
                remote_path = f"{remote_dir}/{rel_path}".replace("\\", "/")
                with open(local_path, "rb") as fh:
                    self._sandbox.fs.upload_file(remote_path, fh.read())

    def file_exists(self, path: str) -> bool:
        try:
            self.read_file(path)
            return True
        except Exception:
            return False

    def list_files(self, path: str = "/workspace") -> list[str]:
        result = self.exec(f"ls -1 {path}")
        return [f for f in result.strip().split("\n") if f]

    def destroy(self) -> None:
        try:
            self._client.delete(self._sandbox)
        except Exception:
            pass

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


def create_sandbox(backend: str = "local", workspace_path: str = "") -> Sandbox:
    """Factory: create a sandbox with the specified backend."""
    if backend == "daytona":
        sb = DaytonaSandbox()
        if workspace_path:
            sb.upload_dir(workspace_path, sb._workspace)
            sb.exec("git init -q && git add -A && git commit -q -m initial --allow-empty")
            sb.exec("pip install flask pytest -q")
        return sb
    elif backend == "local":
        return LocalSandbox(workspace_path)
    else:
        raise ValueError(f"Unknown backend: {backend}")
