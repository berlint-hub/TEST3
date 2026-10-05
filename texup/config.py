from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path, PureWindowsPath

ALPHA_MODES = ("resize", "model", "drop")
DEVICES = ("cuda", "cpu")

DEFAULT_IGNORE = ["*-mipmap*", "*.txt", "*.tmp"]


@dataclass
class Config:
    # Folders -----------------------------------------------------------
    dump_dir: str = ""            # PCSX2: textures/<SERIAL>/dumps
    output_dir: str = ""          # PCSX2: textures/<SERIAL>/replacements
    recursive: bool = False

    # Model / device ------------------------------------------------------
    model_path: str = ""          # any spandrel-supported .pth / .safetensors
    device: str = "cuda"          # "cuda" | "cuda:1" | "cpu"
    fp16: bool = True
    channels_last: bool = True
    tile_size: int = 512          # inputs larger than this are tiled
    tile_overlap: int = 16

    # Output --------------------------------------------------------------
    output_scale: float = 0.0     # 0 = native model scale, else final = original * output_scale
    alpha_mode: str = "resize"    # resize (safe for PCSX2) | model | drop
    png_compress_level: int = 1   # 0-9; low = faster writes
    overwrite_existing: bool = False
    delete_originals: bool = False

    # Filters -------------------------------------------------------------
    min_size: int = 8             # skip textures smaller than this (either side)
    max_size: int = 1024          # skip textures larger than this (FMV frames etc.)
    ignore_patterns: list[str] = field(default_factory=lambda: list(DEFAULT_IGNORE))

    # Runtime -------------------------------------------------------------
    process_existing: bool = True
    settle_ms: int = 250          # file must be unchanged this long before processing
    io_workers: int = 4
    queue_size: int = 64

    # PCSX2 integration ---------------------------------------------------
    reload_hotkey: str = ""       # e.g. "F10" – sent to the PCSX2 window after a batch
    reload_interval_s: float = 5.0

    # -----------------------------------------------------------------------
    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.dump_dir:
            errors.append("Dump folder is not set.")
        elif not Path(self.dump_dir).is_dir():
            errors.append(f"Dump folder does not exist: {self.dump_dir}")
        if not self.output_dir:
            errors.append("Replacements folder is not set.")
        if self.dump_dir and self.output_dir and Path(self.dump_dir).resolve() == Path(self.output_dir).resolve():
            errors.append("Dump and replacements folders must differ.")
        if not self.model_path:
            errors.append("Model file is not set.")
        elif not Path(self.model_path).is_file():
            errors.append(f"Model file not found: {self.model_path}")
        if self.alpha_mode not in ALPHA_MODES:
            errors.append(f"alpha_mode must be one of {ALPHA_MODES}")
        if self.min_size < 1 or self.max_size < self.min_size:
            errors.append("Invalid min/max size.")
        if self.tile_size < 32:
            errors.append("tile_size must be >= 32")
        if self.output_scale < 0:
            errors.append("output_scale must be >= 0")
        return errors

    # Persistence -----------------------------------------------------------
    @classmethod
    def load(cls, path: str | Path) -> "Config":
        path = Path(path)
        if not path.is_file():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")


def suggest_output_dir(dump_dir: str) -> str:
    """PCSX2 layout: .../textures/<SERIAL>/dumps -> .../textures/<SERIAL>/replacements."""
    if not dump_dir:
        return ""
    p = PureWindowsPath(dump_dir) if ("\\" in dump_dir and "/" not in dump_dir) else Path(dump_dir)
    if p.name.lower() == "dumps":
        return str(p.with_name("replacements"))
    return str(p.parent / "replacements")
