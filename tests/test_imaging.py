import numpy as np
from PIL import Image

from texup import imaging
from texup.config import Config, suggest_output_dir


def test_suggest_output_dir_pcsx2_layout():
    assert suggest_output_dir(r"C:\PCSX2\textures\SLUS-20312\dumps").replace("/", "\\").endswith("SLUS-20312\\replacements")
    assert suggest_output_dir("") == ""


def test_resize_alpha_keeps_ps2_opaque_value_bit_exact():
    alpha = np.full((16, 16), 128, dtype=np.uint8)  # PS2 "fully opaque"
    out = imaging.resize_alpha(alpha, 64, 64)
    assert out.shape == (64, 64)
    assert (out == 128).all()


def test_resize_alpha_non_uniform_stays_in_range():
    alpha = np.zeros((8, 8), dtype=np.uint8)
    alpha[:, 4:] = 128
    out = imaging.resize_alpha(alpha, 32, 32)
    assert out.min() == 0 and out.max() == 128  # bicubic overshoot must be clamped to the source range
    assert out[:, :4].max() <= 10 and out[:, -4:].min() >= 118


def test_looks_complete_detects_truncated_png(tmp_path):
    src = tmp_path / "a.png"
    Image.fromarray(np.zeros((4, 4, 3), np.uint8), "RGB").save(src)
    assert imaging.looks_complete(src)
    data = src.read_bytes()
    (tmp_path / "half.png").write_bytes(data[: len(data) // 2])
    assert not imaging.looks_complete(tmp_path / "half.png")
    (tmp_path / "empty.png").write_bytes(b"")
    assert not imaging.looks_complete(tmp_path / "empty.png")


def test_alpha_model_roundtrip_scaling():
    alpha = np.array([[0, 64], [128, 128]], dtype=np.uint8)
    rgb_like, scale = imaging.alpha_to_model_input(alpha)
    assert rgb_like.shape == (2, 2, 3)
    assert scale > 1.0 and rgb_like[1, 1, 0] == 255
    back = imaging.alpha_from_model_output(rgb_like, scale)
    assert (back == alpha).all()

    # masks that already use the full 0..255 range must not be rescaled
    full = np.array([[0, 255]], dtype=np.uint8)
    _, scale_full = imaging.alpha_to_model_input(full)
    assert scale_full == 1.0


def test_load_rgba_and_merge_roundtrip(tmp_path):
    rgba = np.random.default_rng(0).integers(0, 256, (10, 12, 4), dtype=np.uint8)
    src = tmp_path / "t.png"
    Image.fromarray(rgba, "RGBA").save(src)

    rgb, alpha = imaging.load_rgba(src)
    assert rgb.shape == (10, 12, 3) and alpha.shape == (10, 12)
    assert (rgb == rgba[..., :3]).all() and (alpha == rgba[..., 3]).all()

    dst = tmp_path / "out" / "t.png"
    imaging.save_png_atomic(imaging.merge(rgb, alpha), dst)
    assert dst.exists() and not list(dst.parent.glob("*.texup_tmp"))
    assert (np.asarray(Image.open(dst)) == rgba).all()

    rgb_only = tmp_path / "rgb.png"
    Image.fromarray(rgba[..., :3], "RGB").save(rgb_only)
    _, a = imaging.load_rgba(rgb_only)
    assert a is None


def test_config_roundtrip_and_validation(tmp_path):
    cfg = Config(dump_dir=str(tmp_path), output_dir=str(tmp_path / "rep"), model_path="missing.pth")
    p = tmp_path / "cfg.json"
    cfg.save(p)
    loaded = Config.load(p)
    assert loaded == cfg
    errs = loaded.validate()
    assert any("Model file not found" in e for e in errs)
    assert Config.load(tmp_path / "nope.json") == Config()
