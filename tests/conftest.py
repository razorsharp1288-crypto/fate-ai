import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fate_ai.security.credential_manager import MemoryBackend  # noqa: E402


@pytest.fixture
def ctx(tmp_path):
    from fate_ai.bootstrap import build_context
    c = build_context(tmp_path / "data", credential_backend=MemoryBackend())
    yield c
    c.shutdown()
