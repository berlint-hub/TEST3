"""Processing pipeline: watcher -> settle -> decode pool -> GPU thread -> encode pool."""
from __future__ import annotations

import fnmatch
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from . import imaging
from .config import Config
from .engine import Upscaler, vram_usage_mb
from .pcsx2 import send_reload_hotkey
from .watcher import SettleQueue, is_image_file, start_observer

LogFn = Callable[[str], None]


@dataclass
class Stats:
    done: int = 0
    skipped: int = 0
    failed: int = 0
    total_ms: float = 0.0
    last_ms: float = 0.0
    gpu_ms: float = 0.0
    started_at: float = field(default_factory=time.monotonic)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add_done(self, ms: float, gpu_ms: float) -> None:
        with self._lock:
            self.done += 1
            self.total_ms += ms
            self.gpu_ms += gpu_ms
            self.last_ms = ms

    def add_skipped(self) -> None:
        with self._lock:
            self.skipped += 1

    def add_failed(self) -> None:
        with self._lock:
            self.failed += 1

    @property
    def avg_ms(self) -> float:
        return self.total_ms / self.done if self.done else 0.0

    @property
    def avg_gpu_ms(self) -> float:
        return self.gpu_ms / self.done if self.done else 0.0


@dataclass
class _Job:
    src: Path
    dst: Path
    t_start: float
    rgb: np.ndarray | None = None
    alpha: np.ndarray | None = None
    out_rgb: np.ndarray | None = None
    out_alpha: np.ndarray | None = None
    gpu_ms: float = 0.0


_STOP = object()


class Pipeline:
    def __init__(self, cfg: Config, log: LogFn | None = None) -> None:
        self.cfg = cfg
        self.log = log or (lambda msg: print(msg, flush=True))
        self.stats = Stats()
        self.engine: Upscaler | None = None

        self._running = False
        self._stop_evt = threading.Event()
        self._seen: set[Path] = set()
        self._seen_lock = threading.Lock()
        self._retries: dict[Path, int] = {}

        self._gpu_q: queue.Queue = queue.Queue(maxsize=max(4, cfg.queue_size))
        self._enc_q: queue.Queue = queue.Queue(maxsize=max(4, cfg.queue_size))
        self._decode_pool: ThreadPoolExecutor | None = None
        self._encode_threads: list[threading.Thread] = []
        self._gpu_thread: threading.Thread | None = None
        self._hotkey_thread: threading.Thread | None = None
        self._dirty = threading.Event()
        self._observer = None
        self._settle: SettleQueue | None = None
        self._inflight = 0
        self._inflight_lock = threading.Lock()

    # ------------------------------------------------------------------ lifecycle
    @property
    def running(self) -> bool:
        return self._running

    def start(self) -> None:
        errors = self.cfg.validate()
        if errors:
            raise ValueError("\n".join(errors))
        cfg = self.cfg
        self._stop_evt.clear()

        self.log(f"Loading model {Path(cfg.model_path).name} on {cfg.device} …")
        t0 = time.perf_counter()
        self.engine = Upscaler(
            cfg.model_path,
            device=cfg.device,
            fp16=cfg.fp16,
            channels_last=cfg.channels_last,
            tile_size=cfg.tile_size,
            tile_overlap=cfg.tile_overlap,
        )
        warm = self.engine.warmup()
        self.log(f"Model ready in {time.perf_counter() - t0:.1f}s · {self.engine.info.pretty()} · warmup {warm:.0f} ms")

        Path(cfg.output_dir).mkdir(parents=True, exist_ok=True)
        self.stats = Stats()
        self._running = True

        self._decode_pool = ThreadPoolExecutor(max_workers=max(1, cfg.io_workers), thread_name_prefix="texup-decode")
        self._gpu_thread = threading.Thread(target=self._gpu_loop, name="texup-gpu", daemon=True)
        self._gpu_thread.start()
        self._encode_threads = [
            threading.Thread(target=self._encode_loop, name=f"texup-encode-{i}", daemon=True)
            for i in range(max(1, cfg.io_workers))
        ]
        for t in self._encode_threads:
            t.start()

        if cfg.reload_hotkey:
            self._hotkey_thread = threading.Thread(target=self._hotkey_loop, name="texup-hotkey", daemon=True)
            self._hotkey_thread.start()

        self._settle = SettleQueue(cfg.settle_ms, self._on_file_ready)
        self._settle.start()
        self._observer = start_observer(cfg.dump_dir, cfg.recursive, self._settle.touch)
        self.log(f"Watching {cfg.dump_dir}  →  {cfg.output_dir}")

        if cfg.process_existing:
            threading.Thread(target=self._scan_existing, name="texup-scan", daemon=True).start()

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        self._stop_evt.set()
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=3)
            self._observer = None
        if self._settle:
            self._settle.stop()
        if self._decode_pool:
            self._decode_pool.shutdown(wait=False, cancel_futures=True)
        self._drain(self._gpu_q)
        self._gpu_q.put(_STOP)
        if self._gpu_thread:
            self._gpu_thread.join(timeout=10)
        self._drain(self._enc_q)
        for _ in self._encode_threads:
            self._enc_q.put(_STOP)
        for t in self._encode_threads:
            t.join(timeout=5)
        self._encode_threads = []
        self.engine = None
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass
        self.log("Stopped.")

    @staticmethod
    def _drain(q: queue.Queue) -> None:
        try:
            while True:
                q.get_nowait()
        except queue.Empty:
            pass

    # ------------------------------------------------------------------ status
    def queue_depth(self) -> int:
        pending = self._settle.pending_count() if self._settle else 0
        with self._inflight_lock:
            return pending + self._inflight

    def status_line(self) -> str:
        s = self.stats
        elapsed = max(1e-6, time.monotonic() - s.started_at)
        rate = s.done / elapsed * 60
        used, peak = vram_usage_mb()
        vram = f" · VRAM {used:.0f}/{peak:.0f} MB" if peak else ""
        return (
            f"done {s.done} · skipped {s.skipped} · failed {s.failed} · queue {self.queue_depth()} · "
            f"avg {s.avg_ms:.0f} ms (gpu {s.avg_gpu_ms:.0f}) · {rate:.0f}/min{vram}"
        )

    # ------------------------------------------------------------------ intake
    def _scan_existing(self) -> None:
        root = Path(self.cfg.dump_dir)
        it = root.rglob("*") if self.cfg.recursive else root.iterdir()
        n = 0
        for p in it:
            if self._stop_evt.is_set():
                return
            if p.is_file() and is_image_file(p):
                self._on_file_ready(str(p))
                n += 1
        self.log(f"Queued {n} existing texture(s) from dump folder.")

    def _dst_for(self, src: Path) -> Path:
        try:
            rel = src.relative_to(self.cfg.dump_dir)
        except ValueError:
            rel = Path(src.name)
        return Path(self.cfg.output_dir) / rel.with_suffix(".png")

    def _on_file_ready(self, path: str) -> None:
        if not self._running or self._decode_pool is None:
            return
        src = Path(path)
        with self._seen_lock:
            if src in self._seen:
                return
            self._seen.add(src)
        with self._inflight_lock:
            self._inflight += 1
        try:
            self._decode_pool.submit(self._decode, src)
        except RuntimeError:
            self._dec_inflight()

    def _dec_inflight(self) -> None:
        with self._inflight_lock:
            self._inflight -= 1

    # ------------------------------------------------------------------ stage 1: decode (CPU pool)
    MAX_RETRIES = 8

    def _retry_later(self, src: Path, reason: str) -> None:
        """File is still being written (or locked by the emulator) – try again shortly."""
        n = self._retries.get(src, 0) + 1
        self._retries[src] = n
        if n > self.MAX_RETRIES:
            self._retries.pop(src, None)
            self.stats.add_failed()
            self.log(f"✗ {src.name}: {reason} (gave up after {self.MAX_RETRIES} retries)")
            return
        with self._seen_lock:
            self._seen.discard(src)
        delay = min(2.0, 0.2 * n)
        timer = threading.Timer(delay, lambda: self._settle.touch(str(src)) if self._settle and self._running else None)
        timer.daemon = True
        timer.start()

    def _decode(self, src: Path) -> None:
        cfg = self.cfg
        handed_off = False
        try:
            name = src.name
            if any(fnmatch.fnmatch(name, pat) for pat in cfg.ignore_patterns):
                self.stats.add_skipped()
                return
            dst = self._dst_for(src)
            if dst.exists() and not cfg.overwrite_existing:
                self.stats.add_skipped()
                return
            if not imaging.looks_complete(src):
                self._retry_later(src, "file incomplete")
                return
            try:
                w, h = imaging.image_size(src)
                if min(w, h) < cfg.min_size or max(w, h) > cfg.max_size:
                    self.stats.add_skipped()
                    return
                rgb, alpha = imaging.load_rgba(src)
            except (OSError, SyntaxError, ValueError) as exc:
                # Truncated / still-open file: PIL raises OSError("image file is truncated") or
                # "cannot identify image file"; sharing violations on Windows are PermissionError.
                self._retry_later(src, f"cannot read ({exc})")
                return
            self._retries.pop(src, None)
            if cfg.alpha_mode == "drop":
                alpha = None
            job = _Job(src=src, dst=dst, t_start=time.perf_counter(), rgb=rgb, alpha=alpha)
            while self._running:
                try:
                    self._gpu_q.put(job, timeout=0.5)
                    handed_off = True
                    return
                except queue.Full:
                    continue
        except Exception as exc:  # pragma: no cover - defensive
            self.stats.add_failed()
            self.log(f"✗ {src.name}: {exc}")
        finally:
            if not handed_off:
                self._dec_inflight()

    # ------------------------------------------------------------------ stage 2: GPU thread
    def _gpu_loop(self) -> None:
        import torch

        while True:
            job = self._gpu_q.get()
            if job is _STOP:
                return
            engine = self.engine
            if engine is None:
                self._dec_inflight()
                continue
            try:
                t0 = time.perf_counter()
                job.out_rgb = engine.upscale(job.rgb)
                if job.alpha is not None:
                    oh, ow = job.out_rgb.shape[:2]
                    if self.cfg.alpha_mode == "model" and not imaging.is_uniform(job.alpha):
                        a_in, scale = imaging.alpha_to_model_input(job.alpha)
                        job.out_alpha = imaging.alpha_from_model_output(
                            engine.upscale(a_in), scale, int(job.alpha.min()), int(job.alpha.max())
                        )
                    else:
                        job.out_alpha = imaging.resize_alpha(job.alpha, ow, oh)
                if engine.device.type == "cuda":
                    torch.cuda.synchronize(engine.device)
                job.gpu_ms = (time.perf_counter() - t0) * 1000
                job.rgb = job.alpha = None
                while self._running:
                    try:
                        self._enc_q.put(job, timeout=0.5)
                        break
                    except queue.Full:
                        continue
                else:
                    self._dec_inflight()
            except Exception as exc:
                self.stats.add_failed()
                self.log(f"✗ {job.src.name}: GPU error: {exc}")
                self._dec_inflight()

    # ------------------------------------------------------------------ stage 3: encode (CPU pool)
    def _encode_loop(self) -> None:
        while True:
            job = self._enc_q.get()
            if job is _STOP:
                return
            try:
                self._finish(job)
            except Exception as exc:
                self.stats.add_failed()
                self.log(f"✗ {job.src.name}: write error: {exc}")
            finally:
                self._dec_inflight()

    def _finish(self, job: _Job) -> None:
        cfg = self.cfg
        out_rgb, out_alpha = job.out_rgb, job.out_alpha
        assert out_rgb is not None
        if cfg.output_scale and self.engine is not None and abs(cfg.output_scale - self.engine.scale) > 1e-6:
            sh, sw = out_rgb.shape[:2]
            s = self.engine.scale
            tw = max(1, int(round(sw / s * cfg.output_scale)))
            th = max(1, int(round(sh / s * cfg.output_scale)))
            out_rgb = imaging.resize_rgb(out_rgb, tw, th)
            if out_alpha is not None:
                out_alpha = imaging.resize_alpha(out_alpha, tw, th)

        imaging.save_png_atomic(imaging.merge(out_rgb, out_alpha), job.dst, cfg.png_compress_level)

        if cfg.delete_originals:
            try:
                job.src.unlink()
            except OSError:
                pass

        total_ms = (time.perf_counter() - job.t_start) * 1000
        self.stats.add_done(total_ms, job.gpu_ms)
        self._dirty.set()
        h, w = out_rgb.shape[:2]
        self.log(f"✓ {job.src.name} → {w}x{h}  ({job.gpu_ms:.0f} ms gpu / {total_ms:.0f} ms)")

    # ------------------------------------------------------------------ PCSX2 hotkey
    def _hotkey_loop(self) -> None:
        interval = max(1.0, float(self.cfg.reload_interval_s))
        while not self._stop_evt.wait(interval):
            if self._dirty.is_set() and self.queue_depth() == 0:
                if send_reload_hotkey(self.cfg.reload_hotkey):
                    self._dirty.clear()
                    self.log(f"↻ sent '{self.cfg.reload_hotkey}' to PCSX2 (reload texture replacements)")
