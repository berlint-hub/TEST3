# Changes

Bug fixes on top of [WalkerMx/AutoCrispy](https://github.com/WalkerMx/AutoCrispy) `1.2.0.1`.
Assembly version bumped to **1.2.1.0**.

Files touched:

```
AutoCrispy/AutoCrispy/Form1.vb            chaining, batch queue, process handling, post-processing
AutoCrispy/AutoCrispy/Form1.Designer.vb   Tile Size range + hint label
AutoCrispy/AutoCrispy/DragDropList.vb     hit testing, drag & drop, redraw
AutoCrispy/AutoCrispy/FormSettings.vb     chain loading, numeric clamping
AutoCrispy/AutoCrispy/My Project/AssemblyInfo.vb
.github/workflows/build.yml               new
.gitignore                                new
```

No backend, no output format and no settings schema changed. Existing `settings.xml`,
`portable.xml` and saved chain `.xml` files load unchanged.

---

## 1. Model chaining

### 1.1 Reordering overwrote models

`DragDropList` commits a drag in its own `ListCanvas_MouseUp` handler, and `Form1` reordered
`ChainList` from a *separate* `Handles ChainPreview.MouseUp` handler on the very same control.
WinForms invokes handlers in subscription order, and `Form1`'s handler is wired up during
`InitializeComponent` — i.e. **before** `DragDropList` exists. So the sequence on every drop was:

1. `Form1.ChainPreview_MouseUp` reads `ChainControl.ListItems` — still the **pre-drag** order, each
   item still carrying its **old** `Index`. Rebuilding `ChainList` from that is a no-op.
2. `DragDropList.ListCanvas_MouseUp` commits the new visual order and calls `ReorderList()`, which
   renumbers every item to its *visual* position.

Result: the preview showed the new order while `ChainList` kept the old one, and the renumbering
destroyed the mapping between them. The next drag, delete or edit then indexed `ChainList` with
positions that meant something else — models were silently replaced, duplicated or lost.

**Fix.** `DragDropList` now raises a `ListReordered` event *after* committing the new order but
*before* renumbering, so `Item.Index` is still the `ChainList` position the thumbnail came from.
`Form1` subscribes with `AddHandler` (the control is created at runtime, so `Handles` cannot be
used) and remaps `ChainList` from that mapping. The broken `ChainPreview_MouseUp` handler is gone.

`DragDropList.ListCanvas_MouseUp` also only commits when a drag actually started (`IsDragging`) and
when `TempListItems` holds a complete copy. Previously a stray left `MouseUp` with an empty
`TempListItems` cleared `ListItems` and wiped the whole chain.

### 1.2 Drag & drop synchronisation

- `DrawList` positioned thumbnails with `ItemList.IndexOf(Item)`. `DragDropItem` is a **structure**,
  so `IndexOf` compares by value and returns the *first* equal entry: two identical chain steps were
  drawn on top of each other and everything after them shifted. It is also O(n²) per redraw. Now
  positions come from the loop index.
- Redraws are driven by `MouseMove` as well as the timer, and the timer went from 100 ms to 50 ms,
  so the dragged thumbnail follows the pointer instead of lagging behind it.
- `UpdateDrag` bounds-checks before `RemoveAt`/`Insert`, which the old `DragTimer_Tick` did not.
- The previous `BackgroundImage` is now disposed on redraw. Setting `BackgroundImage` does not
  release the old bitmap, so every redraw — and during a drag that is every mouse move — leaked a
  GDI+ surface.
- `Form1.Cursor` (the *default form instance*) is no longer poked from `DragDropList`; the cursor is
  set on the canvas that owns the drag.

### 1.3 Context menu hit the wrong item

`GetCurrentIndex()` fell back to `ClickedIndex` — the index of the *last* mouse-down — whenever the
cursor was outside the canvas or past the last item. When the context menu is open the cursor is
over the **menu**, not over the preview, so `Edit`/`Delete` always resolved through that fallback
and acted on whatever had been clicked before. On an empty area after deleting items it produced a
stale index and threw `ArgumentOutOfRangeException`.

The hit test itself was also off: it computed `XPos = MPos.X \ (ThumbSize + 10)` while thumbnails
are drawn at `10 + (Cell * BaseX)`. Ignoring the 10 px left margin shifted clicks near a
thumbnail's right edge into the next column.

**Fix.**

- `GetIndexAt(Point)` returns the real index or **`-1`** for "nothing here" — no fallback. It
  accounts for the left margin and treats the 10 px gutters as a miss.
- `Form1` resolves the target in `ChainContext.Opening`, while the cursor is still over the
  thumbnail, and disables `Edit`/`Delete` when there is nothing under it. Both handlers use that
  captured index and validate it against `ChainList.Count`.
- Left-clicking a thumbnail selects it (highlighted in the preview), and the **Delete** button now
  removes the selection. That button existed in the UI with no handler at all — it did nothing.

### 1.4 Real model names

Every ESRGAN step was captioned `"ESRGAN"` regardless of which `.pth` model it ran, so a chain of
two different ESRGAN models was indistinguishable.

`ChainObject.Name` cannot carry the model: `MakeUpscale` compares it against `"TexConv"` to decide
where the pre/post-processing passes belong, so it has to stay the backend id. The caption is now
derived instead, by `Form1.GetChainDisplayName`, which unboxes `ChainObject.Package` and returns the
model file name for ESRGAN steps (falling back to the backend id for everything else, and for
presets that cannot be unboxed). Because it is derived from the chain data, it also works for chains
loaded from `settings.xml` or an `.xml` preset.

Long captions are clipped to the thumbnail width with `...` instead of running into the neighbour.

### 1.5 Chain loading

- `FormSettings.LoadSettings` and `ChainLoad_Click` built the preview with
  `ChainList.IndexOf(ChainItem)` — the same value-equality trap as 1.2: identical steps all
  received the index of the first one, so every later item pointed at the wrong model. Loading now
  goes through `Form1.RebuildChainPreview()`, which numbers items positionally.
- An empty `<Chain />` element deserialises to `Nothing` and threw in the following `For Each`. It
  now loads as an empty list.
- `ChainLoad_Click` reports a parse failure instead of throwing.
- `FormSettings.GetPyStr` only checked that the model list was non-empty and then indexed it with
  whatever `SelectedIndex` held. With no ESRGAN models found, `SelectedIndex` is `-1` and the lookup
  threw while building a `ChainObject`. It now validates the index and returns `""`.

### 1.6 Implicit chain entries leaked into the saved chain

With an empty chain, both `WatchDog_Tick` and `RunOnceButton_Click` call
`AddModelToChain(..., AddPreview:=False)` to run the currently selected backend once.
`AddModelToChain` **declared `AddPreview` but never used it**, so the entry was added to the visible
chain too. The cleanup in `WorkHorse_RunWorkerCompleted` tested
`If ChainControl.ListItems.Count = 0 Then ChainList.Clear()` — which could never be true, because
the implicit entry was already in the preview. The silently added model stayed in the chain and was
written to `settings.xml` on exit.

`AddPreview` is now honoured: implicit entries go into `ChainList` only and are counted in
`ImplicitChainCount`, which `WorkHorse_RunWorkerCompleted` removes again when the run ends. The
"chain is empty" tests now look at `ChainList` rather than the preview.

---

## 2. Deadlock on `Threads: All`

`StartBuilder` started every backend with `RedirectStandardOutput` and `RedirectStandardError` set,
and then blocked in `WaitForExit()` without ever reading from those pipes. A pipe holds roughly
4 KB; once the backend wrote more than that it blocked in `write()` while AutoCrispy blocked in
`WaitForExit()` — a hard deadlock that looked like a frozen program and never recovered.

`Threads: All` made this near-unavoidable: one process then reports progress for every texture in
the queue, which is far more than 4 KB of output.

The per-image branch had two further problems:

- `WriteLog` was called *inside* the start loop, and it did `StandardOutput.ReadToEnd()` followed by
  `StandardError.ReadToEnd()`. Reading stdout to the end blocks until the process exits, so the
  "parallel" batch was actually serialised — and a full stderr pipe deadlocked it outright.
- Completion was polled with a `Do … Loop` over `HasExited` with no sleep, pinning a core at 100 %.

**Fix.** A new `Form1.BackendJob` class owns the process plus its captured output:

- `Start()` calls `BeginOutputReadLine()` / `BeginErrorReadLine()` after `Process.Start()`, so both
  pipes are drained continuously on thread-pool threads. The backend can never block on write.
- `Wait()` polls `HasExited` with a 50 ms sleep and finishes with the parameterless `WaitForExit()`,
  which also waits for the async readers to flush — so the captured text is complete.
- Cancellation is observed while waiting: the process is killed instead of leaving a stuck backend
  running after the user pressed the toggle.
- Logging happens **after** completion from the captured buffers, and the file name includes the
  process id, so concurrent backends finishing within the same second no longer overwrite each
  other's log.
- Per-image batches are throttled to a bounded number of live processes (`RetireFinished` retires
  and logs finished ones, and the loop blocks on the oldest job when saturated) rather than being
  fully serialised or fully unbounded.

---

## 3. Smooth queue on `Threads: All`

`MakeUpscale` walks the queue with `For i = 0 To Source.Count - 1 Step ThreadCount`, copying
`ThreadCount` textures into the temp directory and calling `StartBuilder` once per batch.
`GetThreads` returned `Environment.ProcessorCount` for `Threads: All`, so a 200-texture queue on an
8-core machine meant 25 batches — and for the folder-based backends (ESRGAN, `*-ncnn-vulkan`), which
take a whole directory in one invocation, **25 separate Python/Vulkan startups**, each paying model
load time again.

**Fix.** `GetThreads` now takes the number of pending files and returns that for `Threads: All`, so
the loop runs exactly once and the backend receives the entire queue in a single batch. Python is
started once.

Because that batch can now be very large, `MakeUpscale` also computes a `PerImageLimit`: in
`Threads: All` mode a *per-image* backend (Waifu2x Caffe/CPP, Anime4K, xBRZ, TexConv) is capped at
`Environment.ProcessorCount` concurrent processes instead of spawning one per texture. Folder-based
backends are unaffected — they are a single process either way. `Single`, `Custom` and `Max (512)`
keep their previous batch sizes.

Progress reporting was `Math.Floor(((i * 100) + 1) / Source.Count)`, which stays at 0 for a single
mega batch (and could exceed 100, which makes `ReportProgress` throw). It is now the end of the
current batch, clamped to 0–100.

---

## 4. `Tile Size: 0` unlocked

`PyTileSize` was limited to `Minimum = 64`, `Maximum = 1024`. ESRGAN's `--tile_size 0` means *no
tiling*: the model runs on the whole image, which removes tile seams entirely and is considerably
faster when the texture fits in VRAM.

**Fix.** The range is now `0–4096`, and the ESRGAN group carries a hint that `0` means no tiling and
uses the full frame of VRAM. `MakePyCommand` passes the value through unchanged, so `0` reaches the
backend as `--tile_size 0`.

Loading a stored value is now clamped into the control's current range (`FormSettings.SetNumeric`)
instead of assigned directly. `NumericUpDown.Value` throws `ArgumentOutOfRangeException` on an
out-of-range value, which aborted loading the *entire* settings file — a hand-edited
`settings.xml`, or any future range change, would otherwise have reset all settings. The same
clamping now covers `NumericThreads`, `DefringeThresh`, `SeamScale` and `SeamMargin`.

> `Tile Size: 0` needs the texture to fit in VRAM. If the backend reports an out-of-memory error,
> raise it — 512 is a sane default.

---

## 5. Fast CPU post-processing

`Defringe`, `RemovePS2Alpha` and `AddPS2Alpha` looped over every pixel calling
`DirectBitmap.GetPixel` / `SetPixel`. Each call re-resolved the `Bits` **property**, built a `Color`
structure via `Color.FromArgb`, and converted back with `Color.ToArgb()` — per pixel, for read and
write. On a 4× upscaled texture that is millions of allocations for what is integer arithmetic on a
contiguous buffer.

**Fix.** All three now take one local reference to `NewImage.Bits` and work on the packed ARGB
integers directly:

- alpha is `(pixel >> 24) And &HFF` (masked, because VB's `>>` is an arithmetic shift and the packed
  value is negative for alpha ≥ 128),
- writes keep the low 24 bits and swap in the new high byte with `(newAlpha << 24) Or (pixel And &HFFFFFF)`.

The output is bit-identical to before. `AddPS2Alpha` uses an explicit `CInt((Alpha + 1) / 2)` to
preserve VB's banker's rounding, which is what the old implicit `Double → Integer` conversion at
`Color.FromArgb` did. `RemovePS2Alpha` still bails out without touching the file as soon as it sees
alpha above 128, i.e. when the texture is not a PS2 dump.

Two leaks in the same code path are fixed as well:

- Neither `DirectBitmap` nor the intermediate bitmap from `GetUnlockedImage` was disposed (except on
  `RemovePS2Alpha`'s early exit), leaking a GDI+ handle and a **pinned `GCHandle`** per texture. All
  three routines now run inside a `Using`, and a shared `LoadDirectBitmap` helper releases the
  intermediate copy as soon as the pinned buffer has been filled.
- `Defringe` wrote `Color.Transparent` through `SetPixel`; it now writes `0`, the same packed value.

---

## CI

`.github/workflows/build.yml` builds `AutoCrispy.sln` with MSBuild and publishes `AutoCrispy.exe`
(and its `.config`, `.pdb` and `.xml`) as a workflow artifact. See the README for why the job is
pinned to `windows-2022` rather than `windows-latest`.

`AutoCrispy.vbproj.user` is no longer tracked, and a `.gitignore` covers `bin/`, `obj/`, `.vs/` and
the runtime files AutoCrispy drops next to itself (`portable.xml`, `Log_*.txt`).
