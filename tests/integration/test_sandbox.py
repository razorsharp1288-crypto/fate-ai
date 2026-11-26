import shutil
import sys
import zipfile

import pytest

from fate_ai.core.exceptions import SandboxError
from fate_ai.sandbox.base import SandboxLimits
from fate_ai.sandbox.container_sandbox import ContainerSandbox
from fate_ai.sandbox.process_sandbox import ProcessSandbox


def test_process_sandbox_runs_project(ctx, tmp_path):
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "main.py").write_text("import os\nprint('hello', os.environ.get('FATE_SANDBOX'))\n")
    (proj / "test_math.py").write_text("assert 1 + 1 == 2\nprint('tests ok')\n")
    sb = ctx.sandboxes.create("demo", "process")
    assert ctx.sandboxes.import_project(sb["id"], proj) == 2
    with pytest.raises(SandboxError):
        ctx.sandboxes.run(sb["id"], "python proj/main.py")  # consent required
    res = ctx.sandboxes.run(sb["id"], "python proj/main.py", host_consent=True)
    assert res.ok and res.stdout.strip() == "hello 1"
    res2 = ctx.sandboxes.run(sb["id"], "python proj/test_math.py", host_consent=True)
    assert "tests ok" in res2.stdout
    out = ctx.sandboxes.export_results(sb["id"], tmp_path / "out.zip")
    names = zipfile.ZipFile(out).namelist()
    assert "proj/main.py" in names and "_fate_run_log.txt" in names


def test_environment_is_scrubbed(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-leak-1234567890")
    sbx = ProcessSandbox(tmp_path, SandboxLimits(timeout_s=10))
    res = sbx.run([sys.executable, "-c", "import os;print(os.environ.get('OPENAI_API_KEY'))"])
    assert res.stdout.strip() == "None"


def test_timeout_kills_process(tmp_path):
    sbx = ProcessSandbox(tmp_path, SandboxLimits(timeout_s=1))
    res = sbx.run([sys.executable, "-c", "import time; time.sleep(30)"])
    assert res.timed_out and res.duration_ms < 10_000


def test_output_limit(tmp_path):
    sbx = ProcessSandbox(tmp_path, SandboxLimits(timeout_s=10, output_limit_kb=1))
    res = sbx.run([sys.executable, "-c", "print('x' * 100000)"])
    assert res.truncated and len(res.stdout) <= 1024


def test_memory_limit_enforced(tmp_path):
    sbx = ProcessSandbox(tmp_path, SandboxLimits(timeout_s=20, memory_mb=200))
    res = sbx.run([sys.executable, "-c", "b = bytearray(600 * 1024 * 1024); print('allocated')"])
    assert "allocated" not in res.stdout and res.exit_code != 0
    assert any("MB" in e for e in res.enforced)


def test_reset_and_delete(ctx):
    sb = ctx.sandboxes.create("r", "process")
    ctx.sandboxes.write_file(sb["id"], "a/b.txt", "x")
    assert ctx.sandboxes.files(sb["id"]) == ["a/b.txt"]
    ctx.sandboxes.reset(sb["id"])
    assert ctx.sandboxes.files(sb["id"]) == []
    with pytest.raises(Exception):
        ctx.sandboxes.write_file(sb["id"], "../escape.txt", "x")
    ctx.sandboxes.delete(sb["id"])
    assert ctx.sandboxes.list() == []


def test_container_args_are_locked_down(tmp_path):
    c = ContainerSandbox("docker", tmp_path, SandboxLimits(cpu_limit=1.5, memory_mb=256))
    args = c.build_args(["python", "x.py"], "n")
    for flag in ("--network=none", "--cap-drop=ALL", "--read-only", "--cpus=1.5", "--memory=256m",
                 "--security-opt=no-new-privileges"):
        assert flag in args


@pytest.mark.skipif(not shutil.which("docker"), reason="docker not installed")
def test_container_sandbox_real(tmp_path):
    from fate_ai.utilities.proc import run
    if not run(["docker", "info"], timeout=20).ok:
        pytest.skip("docker engine not running")
    (tmp_path / "t.py").write_text("print('in container')")
    c = ContainerSandbox(shutil.which("docker"), tmp_path, SandboxLimits(timeout_s=120), image="python:3.12-slim")
    res = c.run(["python", "t.py"])
    assert res.ok, res.stderr
    assert "in container" in res.stdout
