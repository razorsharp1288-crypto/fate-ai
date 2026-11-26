"""Local project workspaces with safe file access and Git-based history."""
from __future__ import annotations

import difflib
import shutil
import zipfile
from pathlib import Path

from ..core.exceptions import ValidationError
from ..security.paths import resolve_inside
from .versioning import GitVersioning  # noqa: F401  (re-exported)

_SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".idea", ".vs"}


class ProjectManager:
    def __init__(self, repo, root: Path, audit=None):
        self.repo = repo
        self.root = Path(root)
        self.audit = audit

    def create(self, name: str, path: Path | None = None, instructions: str = "") -> dict:
        from ..security.paths import safe_name
        p = Path(path) if path else self.root / safe_name(name)
        p.mkdir(parents=True, exist_ok=True)
        pid = self.repo.create(name=name, path=str(p.resolve()), instructions=instructions)
        if self.audit:
            self.audit.log("projects", "created", name)
        return self.repo.get(pid)

    def import_folder(self, folder: Path) -> dict:
        folder = Path(folder).resolve()
        if not folder.is_dir():
            raise ValidationError("Folder not found")
        for p in self.repo.list():
            if Path(p["path"]) == folder:
                return p
        return self.create(folder.name, folder)

    def list(self) -> list[dict]:
        return self.repo.list()

    def get(self, pid: int) -> dict:
        p = self.repo.get(pid)
        if not p:
            raise ValidationError("Project not found")
        return p

    def remove(self, pid: int) -> None:
        """Forget the project (files on disk are left untouched)."""
        self.repo.delete(pid)

    def tree(self, pid: int, limit: int = 5000) -> list[str]:
        root = Path(self.get(pid)["path"])
        out = []
        for p in sorted(root.rglob("*")):
            if any(part in _SKIP_DIRS for part in p.relative_to(root).parts):
                continue
            if p.is_file():
                out.append(str(p.relative_to(root)).replace("\\", "/"))
                if len(out) >= limit:
                    break
        return out

    def read(self, pid: int, rel: str) -> str:
        target = resolve_inside(self.get(pid)["path"], rel)
        if target.stat().st_size > 5 * 2 ** 20:
            raise ValidationError("File too large to open in the editor (5 MB max).")
        return target.read_text("utf-8", errors="replace")

    def diff(self, pid: int, rel: str, new_content: str) -> str:
        try:
            old = self.read(pid, rel)
        except FileNotFoundError:
            old = ""
        return "".join(difflib.unified_diff(old.splitlines(True), new_content.splitlines(True),
                                            f"a/{rel}", f"b/{rel}"))

    def write(self, pid: int, rel: str, content: str, confirmed: bool) -> Path:
        """Write a file. Callers must obtain user confirmation first (``confirmed=True``)."""
        if not confirmed:
            raise ValidationError("Writing project files requires confirmation.")
        target = resolve_inside(self.get(pid)["path"], rel)
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            backup_dir = Path(self.get(pid)["path"]) / ".fate" / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup_dir / (rel.replace("/", "__").replace("\\", "__") + ".bak"))
        target.write_text(content, "utf-8")
        if self.audit:
            self.audit.log("projects", "file_written", f"{self.get(pid)['name']}: {rel}")
        return target

    def export_zip(self, pid: int, dest: Path) -> Path:
        root = Path(self.get(pid)["path"])
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            for rel in self.tree(pid, limit=100_000):
                z.write(root / rel, rel)
        return Path(dest)

    def import_zip(self, archive: Path, name: str) -> dict:
        from ..security.paths import safe_name
        dest = self.root / safe_name(name)
        if dest.exists():
            raise ValidationError("A project folder with this name already exists")
        dest.mkdir(parents=True)
        with zipfile.ZipFile(archive) as z:
            for member in z.infolist():
                target = resolve_inside(dest, member.filename)  # blocks zip-slip
                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with z.open(member) as src, open(target, "wb") as dst:
                        shutil.copyfileobj(src, dst)
        return self.create(name, dest)
