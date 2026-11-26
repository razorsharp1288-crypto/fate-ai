"""Git-based version history for project folders (uses the user's installed git)."""
from __future__ import annotations

from pathlib import Path

from ..utilities.proc import run, which


class GitVersioning:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.git = which("git")

    @property
    def available(self) -> bool:
        return self.git is not None

    def _git(self, *args, timeout=60):
        return run([self.git, "-C", str(self.path), *args], timeout=timeout)

    def is_repo(self) -> bool:
        return bool(self.git) and self._git("rev-parse", "--is-inside-work-tree").ok

    def init(self) -> bool:
        return bool(self.git) and self._git("init").ok

    def status(self) -> str:
        return self._git("status", "--short").stdout if self.is_repo() else ""

    def log(self, n: int = 30) -> list[str]:
        r = self._git("log", f"-{n}", "--pretty=format:%h  %ad  %s", "--date=short")
        return r.stdout.splitlines() if r.ok else []

    def diff(self) -> str:
        return self._git("diff").stdout if self.is_repo() else ""

    def commit_all(self, message: str) -> tuple[bool, str]:
        if not self.is_repo():
            return False, "Not a Git repository"
        self._git("add", "-A")
        r = self._git("-c", "user.name=FATE AI", "-c", "user.email=fate-ai@localhost", "commit", "-m", message)
        return r.ok, (r.stdout + r.stderr).strip()
