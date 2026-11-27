import sys

import pytest

from fate_ai.core.exceptions import VirtualizationError
from fate_ai.virtualization import setup
from fate_ai.virtualization.backends.base import VMSpec
from fate_ai.virtualization.backends.windows_sandbox import WindowsSandboxBackend, build_wsb


def test_wsb_config():
    xml = build_wsb(VMSpec("t", memory_mb=4096, network="none", shared_folder=r"C:\proj & <x>",
                           image="cmd /c echo hi"))
    assert "<MemoryInMB>4096</MemoryInMB>" in xml and "<Networking>Disable</Networking>" in xml
    assert "C:\\proj &amp; &lt;x&gt;" in xml and "<ReadOnly>true</ReadOnly>" in xml
    assert "<Command>cmd /c echo hi</Command>" in xml
    import xml.etree.ElementTree as ET
    ET.fromstring(xml)  # well-formed


def test_environment_files_lifecycle(tmp_path):
    b = WindowsSandboxBackend(tmp_path)
    info = b.create(VMSpec("test-box", memory_mb=2048))
    assert info.state == "stopped" and (tmp_path / "test-box.wsb").exists()
    assert [v.name for v in b.list()] == ["test-box"]
    with pytest.raises(VirtualizationError):
        b.create(VMSpec("test-box"))
    with pytest.raises(Exception):
        b._file("../escape")
    if sys.platform != "win32":
        assert not b.status().available
        with pytest.raises(VirtualizationError):
            b.start("test-box")
    b.delete("test-box")
    assert b.list() == []


def test_setup_actions():
    ids = {a.id for a in setup.ACTIONS}
    assert {"winsandbox", "wsl", "docker", "virtualbox", "hyperv"} <= ids
    assert setup.is_home_edition("Core") and not setup.is_home_edition("Professional")
    ok, why = setup.availability(setup.BY_ID["hyperv"], "Core")
    assert not ok
    exe, params = setup.command_line(setup.BY_ID["wsl"])
    assert exe == "powershell.exe" and "wsl --install" in params and "Restart Windows" in params
    if sys.platform != "win32":
        with pytest.raises(VirtualizationError):
            setup.run("wsl")
