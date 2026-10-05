"""CustomTkinter front-end – AutoCrispy-style: pick folders, pick model, press Start."""
from __future__ import annotations

import queue
import threading
import traceback
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk

from . import __version__
from .config import ALPHA_MODES, Config, suggest_output_dir
from .engine import cuda_summary, list_models
from .pcsx2 import default_textures_dir
from .pipeline import Pipeline

APP_TITLE = f"TexUp {__version__} – real-time texture upscaler"
MODELS_DIR = Path(__file__).resolve().parent.parent / "models"


class App(ctk.CTk):
    def __init__(self, config_path: Path) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.title(APP_TITLE)
        self.geometry("980x760")
        self.minsize(820, 620)

        self.config_path = config_path
        self.cfg = Config.load(config_path)
        self.pipeline: Pipeline | None = None
        self._log_q: queue.Queue[str] = queue.Queue()
        self._ui_q: queue.Queue = queue.Queue()  # callables to run on the Tk thread

        self._build()
        self._load_into_widgets()
        self.after(100, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._log(cuda_summary())

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # --- folders ---------------------------------------------------
        f = ctk.CTkFrame(self)
        f.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        f.grid_columnconfigure(1, weight=1)

        self.var_dump = ctk.StringVar()
        self.var_out = ctk.StringVar()
        self.var_model = ctk.StringVar()

        ctk.CTkLabel(f, text="Dump folder").grid(row=0, column=0, padx=8, pady=6, sticky="w")
        ctk.CTkEntry(f, textvariable=self.var_dump).grid(row=0, column=1, padx=4, pady=6, sticky="ew")
        ctk.CTkButton(f, text="Browse…", width=90, command=self._pick_dump).grid(row=0, column=2, padx=8, pady=6)

        ctk.CTkLabel(f, text="Replacements folder").grid(row=1, column=0, padx=8, pady=6, sticky="w")
        ctk.CTkEntry(f, textvariable=self.var_out).grid(row=1, column=1, padx=4, pady=6, sticky="ew")
        ctk.CTkButton(f, text="Browse…", width=90, command=self._pick_out).grid(row=1, column=2, padx=8, pady=6)

        ctk.CTkLabel(f, text="Model (.pth)").grid(row=2, column=0, padx=8, pady=6, sticky="w")
        self.model_menu = ctk.CTkOptionMenu(f, variable=self.var_model, values=["<no models found>"], dynamic_resizing=False)
        self.model_menu.grid(row=2, column=1, padx=4, pady=6, sticky="ew")
        mb = ctk.CTkFrame(f, fg_color="transparent")
        mb.grid(row=2, column=2, padx=4, pady=6)
        ctk.CTkButton(mb, text="Browse…", width=90, command=self._pick_model).pack(side="left", padx=(4, 2))
        ctk.CTkButton(mb, text="⟳", width=32, command=self._refresh_models).pack(side="left", padx=(2, 4))

        # --- settings ---------------------------------------------------
        s = ctk.CTkFrame(self)
        s.grid(row=1, column=0, sticky="ew", padx=12, pady=6)
        for c in range(8):
            s.grid_columnconfigure(c, weight=1 if c % 2 else 0)

        self.var_device = ctk.StringVar(value="cuda")
        self.var_fp16 = ctk.BooleanVar(value=True)
        self.var_alpha = ctk.StringVar(value="resize")
        self.var_out_scale = ctk.StringVar(value="0")
        self.var_tile = ctk.StringVar(value="512")
        self.var_min = ctk.StringVar(value="8")
        self.var_max = ctk.StringVar(value="1024")
        self.var_ignore = ctk.StringVar(value="")
        self.var_existing = ctk.BooleanVar(value=True)
        self.var_delete = ctk.BooleanVar(value=False)
        self.var_overwrite = ctk.BooleanVar(value=False)
        self.var_recursive = ctk.BooleanVar(value=False)
        self.var_hotkey = ctk.StringVar(value="")
        self.var_png = ctk.StringVar(value="1")

        def lab(r, c, text):
            ctk.CTkLabel(s, text=text).grid(row=r, column=c, padx=(10, 4), pady=5, sticky="w")

        lab(0, 0, "Device")
        ctk.CTkOptionMenu(s, variable=self.var_device, values=["cuda", "cuda:1", "cpu"], width=110).grid(row=0, column=1, sticky="w", padx=4)
        ctk.CTkSwitch(s, text="FP16 (tensor cores)", variable=self.var_fp16).grid(row=0, column=2, columnspan=2, sticky="w", padx=10)
        lab(0, 4, "Alpha")
        ctk.CTkOptionMenu(s, variable=self.var_alpha, values=list(ALPHA_MODES), width=110).grid(row=0, column=5, sticky="w", padx=4)
        lab(0, 6, "Output scale (0 = model)")
        ctk.CTkEntry(s, textvariable=self.var_out_scale, width=70).grid(row=0, column=7, sticky="w", padx=4)

        lab(1, 0, "Tile size")
        ctk.CTkEntry(s, textvariable=self.var_tile, width=70).grid(row=1, column=1, sticky="w", padx=4)
        lab(1, 2, "Min texture px")
        ctk.CTkEntry(s, textvariable=self.var_min, width=70).grid(row=1, column=3, sticky="w", padx=4)
        lab(1, 4, "Max texture px")
        ctk.CTkEntry(s, textvariable=self.var_max, width=70).grid(row=1, column=5, sticky="w", padx=4)
        lab(1, 6, "PNG compression 0-9")
        ctk.CTkEntry(s, textvariable=self.var_png, width=70).grid(row=1, column=7, sticky="w", padx=4)

        lab(2, 0, "Ignore patterns")
        ctk.CTkEntry(s, textvariable=self.var_ignore, placeholder_text="*-mipmap*, *.txt").grid(row=2, column=1, columnspan=5, sticky="ew", padx=4)
        lab(2, 6, "PCSX2 reload hotkey")
        ctk.CTkEntry(s, textvariable=self.var_hotkey, width=70, placeholder_text="F10").grid(row=2, column=7, sticky="w", padx=4)

        ctk.CTkSwitch(s, text="Process existing dumps", variable=self.var_existing).grid(row=3, column=0, columnspan=2, sticky="w", padx=10, pady=(4, 8))
        ctk.CTkSwitch(s, text="Delete originals", variable=self.var_delete).grid(row=3, column=2, columnspan=2, sticky="w", padx=10, pady=(4, 8))
        ctk.CTkSwitch(s, text="Overwrite existing", variable=self.var_overwrite).grid(row=3, column=4, columnspan=2, sticky="w", padx=10, pady=(4, 8))
        ctk.CTkSwitch(s, text="Recursive", variable=self.var_recursive).grid(row=3, column=6, columnspan=2, sticky="w", padx=10, pady=(4, 8))

        # --- controls ---------------------------------------------------
        c = ctk.CTkFrame(self, fg_color="transparent")
        c.grid(row=2, column=0, sticky="ew", padx=12, pady=6)
        c.grid_columnconfigure(1, weight=1)
        self.btn_start = ctk.CTkButton(c, text="▶  Start", width=140, height=40, font=ctk.CTkFont(size=15, weight="bold"), command=self._toggle)
        self.btn_start.grid(row=0, column=0, padx=(0, 12))
        self.lbl_status = ctk.CTkLabel(c, text="Idle", anchor="w", justify="left")
        self.lbl_status.grid(row=0, column=1, sticky="ew")

        # --- log --------------------------------------------------------
        self.txt_log = ctk.CTkTextbox(self, font=ctk.CTkFont(family="Consolas", size=12), wrap="none")
        self.txt_log.grid(row=3, column=0, sticky="nsew", padx=12, pady=(6, 12))
        self.txt_log.configure(state="disabled")

    # ------------------------------------------------------------------ config <-> widgets
    def _load_into_widgets(self) -> None:
        cfg = self.cfg
        self.var_dump.set(cfg.dump_dir or default_textures_dir())
        self.var_out.set(cfg.output_dir)
        self.var_device.set(cfg.device)
        self.var_fp16.set(cfg.fp16)
        self.var_alpha.set(cfg.alpha_mode)
        self.var_out_scale.set(str(cfg.output_scale or 0))
        self.var_tile.set(str(cfg.tile_size))
        self.var_min.set(str(cfg.min_size))
        self.var_max.set(str(cfg.max_size))
        self.var_ignore.set(", ".join(cfg.ignore_patterns))
        self.var_existing.set(cfg.process_existing)
        self.var_delete.set(cfg.delete_originals)
        self.var_overwrite.set(cfg.overwrite_existing)
        self.var_recursive.set(cfg.recursive)
        self.var_hotkey.set(cfg.reload_hotkey)
        self.var_png.set(str(cfg.png_compress_level))
        self._refresh_models(select=cfg.model_path)

    def _collect(self) -> Config:
        cfg = self.cfg

        def num(var, cast, default):
            try:
                return cast(var.get().strip())
            except Exception:
                return default

        cfg.dump_dir = self.var_dump.get().strip()
        cfg.output_dir = self.var_out.get().strip()
        cfg.model_path = self._model_path_from_menu()
        cfg.device = self.var_device.get().strip() or "cuda"
        cfg.fp16 = bool(self.var_fp16.get())
        cfg.alpha_mode = self.var_alpha.get()
        cfg.output_scale = num(self.var_out_scale, float, 0.0)
        cfg.tile_size = num(self.var_tile, int, 512)
        cfg.min_size = num(self.var_min, int, 8)
        cfg.max_size = num(self.var_max, int, 1024)
        cfg.ignore_patterns = [p.strip() for p in self.var_ignore.get().split(",") if p.strip()]
        cfg.process_existing = bool(self.var_existing.get())
        cfg.delete_originals = bool(self.var_delete.get())
        cfg.overwrite_existing = bool(self.var_overwrite.get())
        cfg.recursive = bool(self.var_recursive.get())
        cfg.reload_hotkey = self.var_hotkey.get().strip()
        cfg.png_compress_level = max(0, min(9, num(self.var_png, int, 1)))
        return cfg

    # ------------------------------------------------------------------ model menu
    def _refresh_models(self, select: str | None = None) -> None:
        MODELS_DIR.mkdir(exist_ok=True)
        self._models = {p.name: str(p) for p in list_models(MODELS_DIR)}
        if select and Path(select).is_file() and Path(select).name not in self._models:
            self._models[Path(select).name] = select
        names = list(self._models) or ["<put .pth files into models/>"]
        self.model_menu.configure(values=names)
        if select and Path(select).name in self._models:
            self.var_model.set(Path(select).name)
        elif self.var_model.get() not in self._models:
            self.var_model.set(names[0])

    def _model_path_from_menu(self) -> str:
        return self._models.get(self.var_model.get(), "")

    # ------------------------------------------------------------------ pickers
    def _pick_dump(self) -> None:
        d = filedialog.askdirectory(title="PCSX2 dump folder (textures/<SERIAL>/dumps)", initialdir=self.var_dump.get() or default_textures_dir())
        if d:
            self.var_dump.set(d)
            if not self.var_out.get().strip():
                self.var_out.set(suggest_output_dir(d))

    def _pick_out(self) -> None:
        d = filedialog.askdirectory(title="PCSX2 replacements folder", initialdir=self.var_out.get() or self.var_dump.get())
        if d:
            self.var_out.set(d)

    def _pick_model(self) -> None:
        p = filedialog.askopenfilename(
            title="Select ESRGAN model", initialdir=str(MODELS_DIR),
            filetypes=[("Model files", "*.pth *.pt *.safetensors *.ckpt"), ("All files", "*.*")],
        )
        if p:
            self._refresh_models(select=p)

    # ------------------------------------------------------------------ start/stop
    def _toggle(self) -> None:
        if self.pipeline and self.pipeline.running:
            self._stop()
        else:
            self._start()

    def _start(self) -> None:
        cfg = self._collect()
        if not cfg.output_dir and cfg.dump_dir:
            cfg.output_dir = suggest_output_dir(cfg.dump_dir)
            self.var_out.set(cfg.output_dir)
        errors = cfg.validate()
        if errors:
            for e in errors:
                self._log("! " + e)
            return
        cfg.save(self.config_path)
        self.btn_start.configure(state="disabled", text="Loading…")
        self.pipeline = Pipeline(cfg, log=self._log)

        def run():
            try:
                self.pipeline.start()
                self._ui(lambda: self.btn_start.configure(state="normal", text="■  Stop", fg_color="#a33333", hover_color="#7a2626"))
            except Exception as exc:
                self._log("! " + str(exc))
                self._log(traceback.format_exc(limit=3))
                self.pipeline = None
                self._ui(self._reset_start_button)

        threading.Thread(target=run, daemon=True).start()

    def _stop(self) -> None:
        p = self.pipeline
        if not p:
            return
        self.btn_start.configure(state="disabled", text="Stopping…")

        def run():
            p.stop()
            self._ui(self._reset_start_button)

        threading.Thread(target=run, daemon=True).start()

    def _reset_start_button(self) -> None:
        theme = ctk.ThemeManager.theme["CTkButton"]
        self.btn_start.configure(state="normal", text="▶  Start", fg_color=theme["fg_color"], hover_color=theme["hover_color"])
        self.lbl_status.configure(text="Idle")

    def _ui(self, fn) -> None:
        """Schedule a callable on the Tk main loop from any thread."""
        self._ui_q.put(fn)

    def _on_close(self) -> None:
        try:
            self._collect().save(self.config_path)
        except Exception:
            pass
        if self.pipeline and self.pipeline.running:
            self.pipeline.stop()
        self.destroy()

    # ------------------------------------------------------------------ log / status
    def _log(self, msg: str) -> None:
        self._log_q.put(msg)

    def _poll(self) -> None:
        try:
            while True:
                self._ui_q.get_nowait()()
        except queue.Empty:
            pass
        lines = []
        try:
            while len(lines) < 200:
                lines.append(self._log_q.get_nowait())
        except queue.Empty:
            pass
        if lines:
            self.txt_log.configure(state="normal")
            self.txt_log.insert("end", "\n".join(lines) + "\n")
            # keep the widget bounded
            if int(self.txt_log.index("end-1c").split(".")[0]) > 2000:
                self.txt_log.delete("1.0", "500.0")
            self.txt_log.see("end")
            self.txt_log.configure(state="disabled")
        if self.pipeline and self.pipeline.running:
            self.lbl_status.configure(text=self.pipeline.status_line())
        self.after(150, self._poll)


def run_gui(config_path: Path) -> None:
    app = App(config_path)
    app.mainloop()
