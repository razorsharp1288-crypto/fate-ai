import hashlib
import json

import httpx
import pytest

from fate_ai.ai.model_manager.catalog import CATALOG, assess, recommended_tier
from fate_ai.core.exceptions import FateError
from fate_ai.hardware.detection import detect_all
from fate_ai.monitoring.collector import MetricsCollector
from fate_ai.resources.manager import PRESETS, apply_preset, inference_threads
from fate_ai.updater.updater import Updater, UpdateInfo, parse_version


def test_detect_all_reports_real_values():
    hw = detect_all()
    assert hw.memory.total_gb > 0
    assert hw.cpu.logical_threads >= 1
    for g in hw.gpus:  # never fabricated: VRAM is either measured or None
        assert g.vram_total_gb is None or g.vram_total_gb > 0


def test_collector_samples():
    c = MetricsCollector(history=5, gpu=False)
    for _ in range(7):
        s = c.sample()
    assert len(c.history) == 5 and 0 <= s.cpu_percent <= 100


def test_catalog_assessment():
    small = next(m for m in CATALOG if m.tag == "llama3.2:1b")
    big = next(m for m in CATALOG if m.tag == "llama3.3:70b")
    assert assess(small, 8, 6, None, 100).verdict == "cpu"
    assert assess(big, 8, 6, None, 100).verdict == "too_large"
    assert assess(small, 8, 6, 8, 100).verdict == "gpu"
    assert assess(small, 64, 60, 24, 0.5).verdict == "too_large"  # disk
    assert recommended_tier(8, None) == "lightweight"
    assert recommended_tier(16, None) == "balanced"
    assert recommended_tier(16, 24) == "high"


def test_presets_apply(ctx):
    apply_preset(ctx.settings, "low")
    assert ctx.settings.settings.resources.max_cpu_percent == PRESETS["low"].max_cpu_percent
    assert inference_threads(1) >= 1


def test_version_parse():
    assert parse_version("v1.2.3") > parse_version("1.2.0")
    assert parse_version("0.1") == (0, 1, 0)


def test_updater_verifies_hash(tmp_path):
    payload = b"installer-bytes"
    good = hashlib.sha256(payload).hexdigest()

    def make(hash_):
        def handler(req):
            p = req.url.path
            if p.endswith("/releases"):
                return httpx.Response(200, json=[{"tag_name": "v9.0.0", "body": "notes", "assets": [
                    {"name": "FateAI-9.0.0-setup.exe", "browser_download_url": "https://x/FateAI-9.0.0-setup.exe"},
                    {"name": "SHA256SUMS.txt", "browser_download_url": "https://x/SHA256SUMS.txt"}]}])
            if p.endswith("SHA256SUMS.txt"):
                return httpx.Response(200, content=f"{hash_}  FateAI-9.0.0-setup.exe\n".encode())
            return httpx.Response(200, content=payload)
        return httpx.MockTransport(handler)

    u = Updater("owner/repo", tmp_path, transport=make(good))
    info = u.check()
    assert info.available and info.latest == "9.0.0"
    assert u.download(info).read_bytes() == payload
    bad = Updater("owner/repo", tmp_path / "b", transport=make("0" * 64))
    with pytest.raises(FateError):
        bad.download(bad.check())
    assert not list((tmp_path / "b").glob("*.exe"))


def test_updater_requires_repo(tmp_path):
    with pytest.raises(FateError):
        Updater("", tmp_path).check()


def test_settings_validation_and_recovery(tmp_path):
    from fate_ai.core.settings import SettingsStore
    p = tmp_path / "s.json"
    p.write_text("{not json")
    s = SettingsStore(p)
    assert s.settings.ai.temperature == 0.7
    s.update(ai={"temperature": 1.1})
    assert json.loads(p.read_text())["ai"]["temperature"] == 1.1
    with pytest.raises(Exception):
        s.update(ai={"temperature": 9})
