import pytest

from fate_ai.core.exceptions import BackendUnavailableError, ResourceLimitError, ValidationError
from fate_ai.virtualization.backends.base import (BackendStatus, Cap, VirtualizationBackend, VMInfo, VMSpec)
from fate_ai.virtualization.backends.container import _to_mb
from fate_ai.virtualization.backends.virtualbox import VirtualBoxBackend
from fate_ai.virtualization.vm_manager import VMManager, host_limits, recommend, validate_spec


class FakeBackend(VirtualizationBackend):
    name = "fake"
    label = "Fake"
    caps = {Cap.CREATE, Cap.START, Cap.STOP, Cap.DELETE, Cap.SNAPSHOT}

    def __init__(self):
        self.vms = {}
        self.snaps = {}

    def status(self):
        return BackendStatus(True, "ok")

    def list(self):
        return list(self.vms.values())

    def create(self, spec):
        self.vms[spec.name] = VMInfo(spec.name, spec.name, self.name, "stopped", cpus=spec.cpus,
                                     memory_mb=spec.memory_mb)
        return self.vms[spec.name]

    def start(self, i):
        self.vms[i].state = "running"

    def stop(self, i, force=False):
        self.vms[i].state = "stopped"

    def delete(self, i):
        del self.vms[i]

    def create_snapshot(self, i, n):
        self.snaps.setdefault(i, []).append(n)


class Unavailable(FakeBackend):
    name = "nope"

    def status(self):
        return BackendStatus(False, "not installed")


def test_lifecycle_and_emergency_stop(ctx):
    fb = FakeBackend()
    m = VMManager(backends=[fb, Unavailable()], audit=ctx.audit)
    m.create("fake", VMSpec("dev-box", cpus=1, memory_mb=512, disk_gb=10))
    m.op("fake", "start", "dev-box")
    assert [v.name for v in m.running()] == ["dev-box"]
    m.op("fake", "create_snapshot", "dev-box", "clean")
    assert fb.snaps["dev-box"] == ["clean"]
    assert m.stop_all() == []
    assert m.running() == []
    with pytest.raises(BackendUnavailableError):
        m.backend("nope")
    assert any(r["action"] == "vm_created" for r in ctx.audit.recent())


def test_resource_validation():
    max_cpu, max_ram = host_limits()
    with pytest.raises(ResourceLimitError):
        validate_spec(VMSpec("x", cpus=max_cpu + 1))
    with pytest.raises(ResourceLimitError):
        validate_spec(VMSpec("x", cpus=1, memory_mb=max_ram + 1))
    with pytest.raises(ResourceLimitError):
        validate_spec(VMSpec("x", cpus=1, memory_mb=1024), running_ram_mb=max_ram)
    with pytest.raises(ValidationError):
        validate_spec(VMSpec("bad/name", cpus=1, memory_mb=512))
    cpus, ram, disk = recommend()
    validate_spec(VMSpec("ok", cpus=cpus, memory_mb=ram, disk_gb=disk))


def test_vbox_machine_readable_parser():
    d = VirtualBoxBackend._parse_info('name="Dev"\nUUID="1234"\nVMState="running"\ncpus=2\nmemory=2048\n')
    assert d == {"name": "Dev", "UUID": "1234", "VMState": "running", "cpus": "2", "memory": "2048"}


def test_unavailable_backends_report_reason():
    vb = VirtualBoxBackend(None)
    st = vb.status()
    assert not st.available and "virtualbox.org" in st.reason.lower()


def test_container_mem_units():
    assert _to_mb("1.5GiB") == 1536
    assert _to_mb("512MiB") == 512
