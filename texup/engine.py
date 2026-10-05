"""CUDA inference engine built on PyTorch + spandrel (loads any ESRGAN-family checkpoint)."""
from __future__ import annotations

import math
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import torch
from spandrel import ImageModelDescriptor, ModelLoader

MODEL_EXTENSIONS = (".pth", ".pt", ".safetensors", ".ckpt")


@dataclass
class EngineInfo:
    model_name: str
    architecture: str
    scale: int
    device: str
    dtype: str
    tags: list[str]

    def pretty(self) -> str:
        tags = f" [{', '.join(self.tags)}]" if self.tags else ""
        return f"{self.model_name} · {self.architecture} x{self.scale}{tags} · {self.device} · {self.dtype}"


def resolve_device(requested: str) -> torch.device:
    req = (requested or "cuda").lower()
    if req.startswith("cuda"):
        if torch.cuda.is_available():
            return torch.device(req)
        raise RuntimeError(
            "CUDA requested but torch.cuda.is_available() is False. "
            "Install the CUDA build of PyTorch (see install.bat) and check your NVIDIA driver."
        )
    return torch.device("cpu")


def cuda_summary() -> str:
    if not torch.cuda.is_available():
        return f"torch {torch.__version__} · CUDA not available"
    idx = torch.cuda.current_device()
    props = torch.cuda.get_device_properties(idx)
    return (
        f"torch {torch.__version__} · CUDA {torch.version.cuda} · {props.name} "
        f"({props.total_memory / 2**30:.1f} GB)"
    )


def vram_usage_mb() -> tuple[float, float]:
    if not torch.cuda.is_available():
        return 0.0, 0.0
    return torch.cuda.memory_allocated() / 2**20, torch.cuda.max_memory_allocated() / 2**20


class Upscaler:
    """Keeps a model resident on the GPU and upscales uint8 RGB arrays."""

    def __init__(
        self,
        model_path: str | Path,
        device: str = "cuda",
        fp16: bool = True,
        channels_last: bool = True,
        tile_size: int = 512,
        tile_overlap: int = 16,
    ) -> None:
        self.model_path = Path(model_path)
        self.device = resolve_device(device)
        self.tile_size = int(tile_size)
        self.tile_overlap = int(tile_overlap)

        descriptor = ModelLoader(device=self.device).load_from_file(str(self.model_path))
        if not isinstance(descriptor, ImageModelDescriptor):
            raise RuntimeError(f"{self.model_path.name} is not a single-image model ({type(descriptor).__name__}).")
        if descriptor.input_channels != 3 or descriptor.output_channels != 3:
            raise RuntimeError(
                f"Only RGB->RGB models are supported, got {descriptor.input_channels}->{descriptor.output_channels} channels."
            )

        descriptor.eval()
        use_half = bool(fp16) and self.device.type == "cuda" and descriptor.supports_half
        self.dtype = torch.float16 if use_half else torch.float32
        descriptor.to(self.device, self.dtype)
        self.channels_last = bool(channels_last) and self.device.type == "cuda"
        if self.channels_last:
            descriptor.model.to(memory_format=torch.channels_last)

        if self.device.type == "cuda":
            torch.backends.cudnn.benchmark = True

        self.descriptor = descriptor
        self.scale = int(descriptor.scale)
        self.info = EngineInfo(
            model_name=self.model_path.stem,
            architecture=descriptor.architecture.name,
            scale=self.scale,
            device=str(self.device) + (f" ({torch.cuda.get_device_name(self.device)})" if self.device.type == "cuda" else ""),
            dtype="fp16" if use_half else "fp32",
            tags=list(descriptor.tags),
        )

    # ------------------------------------------------------------------
    def warmup(self, size: int = 64) -> float:
        t0 = time.perf_counter()
        self.upscale(np.zeros((size, size, 3), dtype=np.uint8))
        if self.device.type == "cuda":
            torch.cuda.synchronize(self.device)
        return (time.perf_counter() - t0) * 1000

    # ------------------------------------------------------------------
    @torch.inference_mode()
    def upscale(self, rgb: np.ndarray) -> np.ndarray:
        """uint8 HxWx3 -> uint8 (H*s)x(W*s)x3."""
        if rgb.ndim != 3 or rgb.shape[2] != 3 or rgb.dtype != np.uint8:
            raise ValueError("expected uint8 HxWx3 RGB array")

        tensor = torch.from_numpy(rgb).to(self.device, non_blocking=True)
        tensor = tensor.permute(2, 0, 1).unsqueeze(0).to(self.dtype).div_(255.0)
        if self.channels_last:
            tensor = tensor.contiguous(memory_format=torch.channels_last)

        out = self._run(tensor)
        out = out.clamp_(0.0, 1.0).mul_(255.0).round_().to(torch.uint8)
        return out.squeeze(0).permute(1, 2, 0).contiguous().cpu().numpy()

    # ------------------------------------------------------------------
    def _run(self, t: torch.Tensor) -> torch.Tensor:
        _, _, h, w = t.shape
        if max(h, w) <= self.tile_size:
            return self._forward(t)
        return self._run_tiled(t)

    def _forward(self, t: torch.Tensor) -> torch.Tensor:
        try:
            return self.descriptor(t)
        except torch.cuda.OutOfMemoryError:
            torch.cuda.empty_cache()
            if self.tile_size > 64 and max(t.shape[-2:]) > 64:
                # Shrink tiles and retry once.
                self.tile_size = max(64, self.tile_size // 2)
                return self._run_tiled(t)
            raise

    def _run_tiled(self, t: torch.Tensor) -> torch.Tensor:
        """Overlapping tiles; the overlap region is discarded from each tile's output."""
        _, c, h, w = t.shape
        s = self.scale
        tile = self.tile_size
        ov = min(self.tile_overlap, tile // 4)
        step = tile - 2 * ov

        out = torch.empty((1, c, h * s, w * s), dtype=t.dtype, device=t.device)
        ny = max(1, math.ceil(h / step))
        nx = max(1, math.ceil(w / step))

        for iy in range(ny):
            y0 = iy * step
            y1 = min(y0 + step, h)
            ty0 = max(0, y0 - ov)
            ty1 = min(h, y1 + ov)
            for ix in range(nx):
                x0 = ix * step
                x1 = min(x0 + step, w)
                tx0 = max(0, x0 - ov)
                tx1 = min(w, x1 + ov)

                patch = t[:, :, ty0:ty1, tx0:tx1]
                res = self.descriptor(patch)

                # crop back to the "core" region of the tile
                cy0 = (y0 - ty0) * s
                cx0 = (x0 - tx0) * s
                core = res[:, :, cy0 : cy0 + (y1 - y0) * s, cx0 : cx0 + (x1 - x0) * s]
                out[:, :, y0 * s : y1 * s, x0 * s : x1 * s] = core
        return out


def list_models(folder: str | Path) -> list[Path]:
    folder = Path(folder)
    if not folder.is_dir():
        return []
    return sorted(p for p in folder.iterdir() if p.suffix.lower() in MODEL_EXTENSIONS and p.is_file())
