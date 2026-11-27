"""Secure update checks against GitHub Releases (optional; no FATE backend).

Release assets must include ``SHA256SUMS.txt``. When ``FATE_UPDATE_PUBKEY`` is
configured (Ed25519, base64) the checksum file must also have a valid
``SHA256SUMS.txt.sig``. Installers are never executed automatically: after
verification the user is asked to launch the downloaded installer.
"""
from __future__ import annotations

import base64
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

from .. import __version__
from ..core.exceptions import FateError

# Fill in when you publish signed releases (base64 Ed25519 public key).
FATE_UPDATE_PUBKEY = ""
# Public repository whose GitHub Releases publish FATE AI installers.
DEFAULT_REPOSITORY = "razorsharp1288-crypto/fate-ai"


def parse_version(v: str) -> tuple:
    nums = re.findall(r"\d+", v.split("-")[0])
    return tuple(int(n) for n in nums[:3]) + (0,) * (3 - len(nums[:3]))


@dataclass
class UpdateInfo:
    current: str
    latest: str
    available: bool
    notes: str
    installer_url: str | None
    sums_url: str | None
    sig_url: str | None
    installer_name: str | None


class Updater:
    def __init__(self, repository: str, dest: Path, transport=None, pubkey: str = FATE_UPDATE_PUBKEY):
        self.repository = repository or DEFAULT_REPOSITORY
        self.dest = Path(dest)
        self.transport = transport
        self.pubkey = pubkey

    def _client(self):
        return httpx.Client(timeout=30, transport=self.transport, follow_redirects=True,
                            headers={"User-Agent": "FateAI-Updater", "Accept": "application/vnd.github+json"})

    def check(self, include_prerelease: bool = False) -> UpdateInfo:
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", self.repository or ""):
            raise FateError("No update repository configured (Settings → Advanced).")
        url = f"https://api.github.com/repos/{self.repository}/releases"
        with self._client() as c:
            r = c.get(url)
            if r.status_code != 200:
                raise FateError(f"Update check failed (HTTP {r.status_code}).")
            releases = [x for x in r.json() if not x.get("draft") and (include_prerelease or not x.get("prerelease"))]
        if not releases:
            return UpdateInfo(__version__, __version__, False, "", None, None, None, None)
        rel = max(releases, key=lambda x: parse_version(x.get("tag_name", "0")))
        latest = rel.get("tag_name", "0").lstrip("v")
        assets = {a["name"]: a["browser_download_url"] for a in rel.get("assets", [])}
        installer = next((n for n in assets if n.lower().endswith("-setup.exe")), None)
        return UpdateInfo(__version__, latest, parse_version(latest) > parse_version(__version__),
                          rel.get("body") or "", assets.get(installer) if installer else None,
                          assets.get("SHA256SUMS.txt"), assets.get("SHA256SUMS.txt.sig"), installer)

    def download(self, info: UpdateInfo, progress=None, cancel=None) -> Path:
        if not info.installer_url or not info.sums_url:
            raise FateError("This release has no verifiable installer (missing SHA256SUMS.txt).")
        self.dest.mkdir(parents=True, exist_ok=True)
        with self._client() as c:
            sums = c.get(info.sums_url).content
            if self.pubkey:
                if not info.sig_url:
                    raise FateError("Release is not signed; refusing to install.")
                self._verify_signature(sums, c.get(info.sig_url).content)
            expected = self._expected_hash(sums.decode("utf-8", "replace"), info.installer_name)
            target = self.dest / info.installer_name
            h = hashlib.sha256()
            with c.stream("GET", info.installer_url) as r, open(target, "wb") as fh:
                total = int(r.headers.get("content-length") or 0)
                done = 0
                for chunk in r.iter_bytes(1 << 16):
                    if cancel is not None and cancel.cancelled:
                        raise FateError("Download cancelled")
                    fh.write(chunk)
                    h.update(chunk)
                    done += len(chunk)
                    if progress:
                        progress(done, total)
        if h.hexdigest().lower() != expected.lower():
            target.unlink(missing_ok=True)
            raise FateError("Downloaded installer failed integrity verification and was deleted.")
        return target

    @staticmethod
    def _expected_hash(sums: str, name: str) -> str:
        for line in sums.splitlines():
            parts = line.strip().split()
            if len(parts) == 2 and parts[1].lstrip("*") == name:
                return parts[0]
        raise FateError("Installer hash not listed in SHA256SUMS.txt")

    def _verify_signature(self, data: bytes, sig: bytes) -> None:
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        except ImportError:
            raise FateError("Signature verification requires the 'cryptography' package.") from None
        try:
            Ed25519PublicKey.from_public_bytes(base64.b64decode(self.pubkey)).verify(base64.b64decode(sig.strip()), data)
        except Exception:
            raise FateError("Update signature is invalid; refusing to install.") from None


def install_and_restart(installer: Path) -> None:
    """Run a verified installer silently; it closes FATE AI, upgrades in place and relaunches it.

    Windows only. The caller must quit the application right after this returns.
    """
    import subprocess
    import sys
    if sys.platform != "win32":
        raise FateError("Automatic installation is only available on Windows.")
    installer = Path(installer)
    if not installer.is_file() or installer.suffix.lower() != ".exe":
        raise FateError("Installer file not found.")
    DETACHED, NEW_GROUP = 0x00000008, 0x00000200
    subprocess.Popen([str(installer), "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS",
                      "/UPDATE=1"], creationflags=DETACHED | NEW_GROUP, close_fds=True)
