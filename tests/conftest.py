from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def tiny_model(tmp_path_factory) -> Path:
    """A real (tiny, untrained) ESRGAN x2 checkpoint that spandrel can load."""
    import torch
    from spandrel.architectures.ESRGAN.__arch.RRDB import RRDBNet

    torch.manual_seed(0)
    net = RRDBNet(in_nc=3, out_nc=3, num_filters=8, num_blocks=1, scale=2)
    path = tmp_path_factory.mktemp("models") / "tiny_esrgan_x2.pth"
    torch.save(net.state_dict(), path)
    return path
