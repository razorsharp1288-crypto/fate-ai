"""Exercises the container backend + container sandbox against a real Docker engine (skipped if absent)."""
import shutil
import uuid

import pytest

from fate_ai.sandbox.base import SandboxLimits
from fate_ai.sandbox.container_sandbox import ContainerSandbox
from fate_ai.utilities.proc import run
from fate_ai.virtualization.backends.base import VMSpec
from fate_ai.virtualization.backends.container import ContainerBackend
from fate_ai.virtualization.vm_manager import VMManager

IMAGE = "python:3.12-slim"


def _docker_ready():
    exe = shutil.which("docker")
    if not exe:
        return False
    info = run([exe, "info", "--format", "{{.OSType}}"], timeout=20)
    return info.ok and info.stdout.strip() == "linux" and run([exe, "image", "inspect", IMAGE], timeout=20).ok


pytestmark = pytest.mark.skipif(not _docker_ready(), reason=f"docker engine with {IMAGE} not available")


def test_container_environment_lifecycle(ctx):
    b = ContainerBackend(shutil.which("docker"), "docker")
    m = VMManager(backends=[b], audit=ctx.audit)
    name = f"fate-test-{uuid.uuid4().hex[:6]}"
    try:
        info = m.create("docker", VMSpec(name, cpus=1, memory_mb=256, image=IMAGE, network="none",
                                         start_after_create=True))
        assert info.state == "running"
        r = b.exec(info.id, ["python", "-c", "print(6*7)"])
        assert r.ok and r.stdout.strip() == "42"
        b.set_resources(info.id, cpus=1, memory_mb=300)
        m.op("docker", "pause", info.id)
        assert next(v for v in b.list() if v.id == info.id).state == "paused"
        m.op("docker", "resume", info.id)
        b.create_snapshot(info.id, "clean")
        assert run(["docker", "image", "inspect", f"fate-snapshot/{info.id[:12]}:clean"]).ok
        assert m.stop_all(force=True) == []
        assert next(v for v in b.list() if v.id == info.id).state == "stopped"
    finally:
        run(["docker", "rm", "-f", name])
        run(["docker", "image", "rm", "-f", f"fate-snapshot/{name}"])
        for line in run(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"]).stdout.splitlines():
            if line.startswith("fate-snapshot/"):
                run(["docker", "image", "rm", "-f", line])


def test_container_sandbox_enforces_network_and_memory(tmp_path):
    (tmp_path / "net.py").write_text(
        "import socket\ntry:\n    socket.create_connection(('1.1.1.1', 53), timeout=3)\n    print('NET OK')\n"
        "except OSError as e:\n    print('NET BLOCKED', type(e).__name__)\n")
    (tmp_path / "mem.py").write_text("b = bytearray(400 * 1024 * 1024)\nprint('ALLOCATED')\n")
    (tmp_path / "fs.py").write_text("open('/etc/evil', 'w')\n")
    sb = ContainerSandbox(shutil.which("docker"), tmp_path, SandboxLimits(timeout_s=60, memory_mb=128), IMAGE)
    assert "NET BLOCKED" in sb.run(["python", "net.py"]).stdout
    mem = sb.run(["python", "mem.py"])
    assert "ALLOCATED" not in mem.stdout and mem.exit_code != 0
    fs = sb.run(["python", "fs.py"])
    assert fs.exit_code != 0 and "Read-only file system" in fs.stderr
    (tmp_path / "out.py").write_text("open('result.txt','w').write('done')")
    assert sb.run(["python", "out.py"]).ok and (tmp_path / "result.txt").read_text() == "done"


def test_container_timeout(tmp_path):
    sb = ContainerSandbox(shutil.which("docker"), tmp_path, SandboxLimits(timeout_s=2), IMAGE)
    sb.limits.timeout_s = 2
    (tmp_path / "sleep.py").write_text("import time; time.sleep(120)")
    import time
    t = time.time()
    res = sb.run(["python", "sleep.py"])
    assert res.timed_out or res.exit_code != 0
    assert time.time() - t < 60
