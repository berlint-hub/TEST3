"""Entry point: ``python -m texup`` (GUI) or ``python -m texup --headless`` (console)."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .config import Config, suggest_output_dir

DEFAULT_CONFIG = Path(__file__).resolve().parent.parent / "texup_config.json"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="texup", description="Real-time AI upscaler for PCSX2 texture dumps.")
    ap.add_argument("--config", default=str(DEFAULT_CONFIG), help="path to texup_config.json")
    ap.add_argument("--headless", action="store_true", help="run without GUI (uses config + overrides)")
    ap.add_argument("--dump", help="dump folder (overrides config)")
    ap.add_argument("--out", help="replacements folder (overrides config)")
    ap.add_argument("--model", help="model .pth (overrides config)")
    ap.add_argument("--device", help="cuda | cuda:1 | cpu")
    ap.add_argument("--no-fp16", action="store_true")
    ap.add_argument("--alpha", choices=("resize", "model", "drop"))
    ap.add_argument("--once", action="store_true", help="headless: process existing files, then exit")
    args = ap.parse_args(argv)

    cfg_path = Path(args.config)
    cfg = Config.load(cfg_path)
    if args.dump:
        cfg.dump_dir = args.dump
    if args.out:
        cfg.output_dir = args.out
    elif args.dump and not cfg.output_dir:
        cfg.output_dir = suggest_output_dir(args.dump)
    if args.model:
        cfg.model_path = args.model
    if args.device:
        cfg.device = args.device
    if args.no_fp16:
        cfg.fp16 = False
    if args.alpha:
        cfg.alpha_mode = args.alpha

    if not args.headless:
        from .gui import run_gui

        run_gui(cfg_path)
        return 0

    from .pipeline import Pipeline

    errors = cfg.validate()
    if errors:
        print("Configuration errors:\n  " + "\n  ".join(errors), file=sys.stderr)
        return 2

    p = Pipeline(cfg)
    p.start()
    try:
        if args.once:
            time.sleep(1.0)
            while p.queue_depth() > 0:
                time.sleep(0.2)
        else:
            while True:
                time.sleep(5)
                print(p.status_line(), flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        p.stop()
        print(p.status_line())
    return 0


if __name__ == "__main__":
    sys.exit(main())
