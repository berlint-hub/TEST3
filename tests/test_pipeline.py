import time

import numpy as np
import pytest
from PIL import Image

from texup.config import Config
from texup.engine import Upscaler
from texup.pipeline import Pipeline


def _wait(pred, timeout=20.0):
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if pred():
            return True
        time.sleep(0.1)
    return False


def test_engine_upscales_and_tiles(tiny_model):
    eng = Upscaler(tiny_model, device="cpu", tile_size=32, tile_overlap=8)
    assert eng.scale == 2 and eng.info.architecture == "ESRGAN"

    small = np.random.default_rng(1).integers(0, 256, (20, 28, 3), dtype=np.uint8)
    out = eng.upscale(small)
    assert out.shape == (40, 56, 3) and out.dtype == np.uint8

    # Larger than tile_size -> tiled path. Compare against the untiled result.
    big = np.random.default_rng(2).integers(0, 256, (70, 90, 3), dtype=np.uint8)
    tiled = eng.upscale(big)
    eng.tile_size = 4096
    direct = eng.upscale(big)
    assert tiled.shape == direct.shape == (140, 180, 3)
    diff = np.abs(tiled.astype(int) - direct.astype(int))
    assert diff.mean() < 2.0 and np.percentile(diff, 99) <= 6  # only border-of-tile rounding


def test_pipeline_end_to_end_simulated_dumping(tmp_path, tiny_model):
    dumps = tmp_path / "SLUS-00000" / "dumps"
    reps = tmp_path / "SLUS-00000" / "replacements"
    dumps.mkdir(parents=True)

    rng = np.random.default_rng(3)

    def write_tex(name, w, h, alpha=128):
        arr = rng.integers(0, 256, (h, w, 4), dtype=np.uint8)
        arr[..., 3] = alpha
        Image.fromarray(arr, "RGBA").save(dumps / name)

    write_tex("aaaa-0000-00000000.png", 32, 16)          # pre-existing
    write_tex("huge-fmv-frame.png", 300, 300)              # filtered by max_size
    (dumps / "notes.txt").write_text("ignore me")

    cfg = Config(
        dump_dir=str(dumps), output_dir=str(reps), model_path=str(tiny_model),
        device="cpu", fp16=False, max_size=128, settle_ms=150, io_workers=2,
    )
    logs = []
    p = Pipeline(cfg, log=logs.append)
    p.start()
    try:
        assert _wait(lambda: (reps / "aaaa-0000-00000000.png").exists())

        # simulate PCSX2 dumping two textures while the game runs; one written in chunks
        write_tex("bbbb-0000-00000000.png", 24, 24, alpha=64)
        chunked = dumps / "cccc-0000-00000000.png"
        buf = tmp_path / "tmp.png"
        arr = rng.integers(0, 256, (24, 40, 3), dtype=np.uint8)
        Image.fromarray(arr, "RGB").save(buf)
        data = buf.read_bytes()
        with open(chunked, "wb") as fh:
            fh.write(data[: len(data) // 2])
            fh.flush()
            time.sleep(0.3)
            fh.write(data[len(data) // 2 :])

        assert _wait(lambda: (reps / "bbbb-0000-00000000.png").exists())
        assert _wait(lambda: (reps / "cccc-0000-00000000.png").exists())
        assert _wait(lambda: p.queue_depth() == 0)
    finally:
        p.stop()

    out_a = np.asarray(Image.open(reps / "aaaa-0000-00000000.png"))
    assert out_a.shape == (32, 64, 4)
    assert (out_a[..., 3] == 128).all(), "PS2 alpha value must be preserved exactly"

    out_b = np.asarray(Image.open(reps / "bbbb-0000-00000000.png"))
    assert out_b.shape == (48, 48, 4) and (out_b[..., 3] == 64).all()

    out_c = np.asarray(Image.open(reps / "cccc-0000-00000000.png"))
    assert out_c.shape == (48, 80, 3)

    assert not (reps / "huge-fmv-frame.png").exists()
    assert not (reps / "notes.txt").exists()
    assert p.stats.done == 3 and p.stats.failed == 0 and p.stats.skipped >= 1
    assert any("Model ready" in l for l in logs)


def test_pipeline_output_scale_and_overwrite(tmp_path, tiny_model):
    dumps = tmp_path / "dumps"
    reps = tmp_path / "replacements"
    dumps.mkdir()
    Image.fromarray(np.zeros((16, 16, 3), np.uint8), "RGB").save(dumps / "x.png")
    (reps).mkdir()
    (reps / "x.png").write_bytes(b"stale")

    cfg = Config(dump_dir=str(dumps), output_dir=str(reps), model_path=str(tiny_model),
                 device="cpu", output_scale=3.0, overwrite_existing=True, settle_ms=100)
    p = Pipeline(cfg, log=lambda m: None)
    p.start()
    try:
        assert _wait(lambda: p.stats.done == 1)
    finally:
        p.stop()
    assert Image.open(reps / "x.png").size == (48, 48)


def test_pipeline_rejects_bad_config(tmp_path, tiny_model):
    with pytest.raises(ValueError):
        Pipeline(Config(dump_dir=str(tmp_path), output_dir=str(tmp_path), model_path=str(tiny_model))).start()
