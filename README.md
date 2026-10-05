# TexUp – real-time AI upscaler textur pro PCSX2 (náhrada AutoCrispy)

TexUp hlídá složku, kam PCSX2 dumpuje textury, každou novou texturu prožene ESRGAN modelem
na **CUDA (PyTorch, FP16)** a výsledek uloží do složky `replacements`. Během hraní se tak
textury objevují ve hře v HD pár desítek milisekund poté, co je hra poprvé použila.

```
PCSX2 ──dump──▶ textures/<SERIAL>/dumps/*.png
                        │  watchdog + settle (soubor dopsán?)
                        ▼
              decode pool (CPU) ─▶ GPU vlákno (model stále ve VRAM) ─▶ encode pool (CPU)
                                                                           │
PCSX2 ◀──load── textures/<SERIAL>/replacements/*.png  ◀────────────────────┘
```

## Instalace (Windows, NVIDIA)

1. Nainstaluj **Python 3.12** (python.org, zaškrtni *Add to PATH*).
2. Spusť **`install.bat`** – vytvoří `.venv`, nainstaluje PyTorch s CUDA (vybere `cu130`/`cu128`
   podle tvého driveru, ~3 GB), spandrel, watchdog, customtkinter a ověří `torch.cuda.is_available()`.
3. Stáhni modely z [openmodeldb.info](https://openmodeldb.info) do složky **`models/`**
   (viz [`models/README.md`](models/README.md) – doporučení pro textury a rychlost).
4. Spusť **`TexUp.bat`**.

## Použití

| Pole | Co nastavit |
|---|---|
| **Dump folder** | `Dokumenty\PCSX2\textures\<SERIAL>\dumps` (v PCSX2: *Graphics → Texture Replacement → Dump Textures*) |
| **Replacements folder** | doplní se automaticky na `…\<SERIAL>\replacements` (v PCSX2 zapni *Load Textures*) |
| **Model** | libovolný `.pth` ze složky `models/` |
| **Device / FP16** | `cuda` + FP16 = tensor cores na RTX 4080 |
| **Alpha** | `resize` (výchozí, bezpečné pro PCSX2) · `model` (alfa přes model, 2× pomalejší) · `drop` |
| **Output scale** | `0` = nativní měřítko modelu; `2` = 4× model, výstup zmenšený na 2× (menší VRAM v PCSX2) |
| **Min / Max texture px** | filtr – `Max 1024` odfiltruje FMV snímky a HUD atlasy, které nechceš upscalovat |
| **Ignore patterns** | glob masky názvů souborů (`*-mipmap*` …) |
| **PCSX2 reload hotkey** | např. `F10` – TexUp ji po dokončení dávky pošle oknu PCSX2 (jen když je v popředí), takže se nové textury načtou bez restartu. V PCSX2 ji nabinduj: *Settings → Hotkeys → Graphics → Reload Texture Replacements*. |

Headless režim (bez GUI, např. do autostartu):

```bat
TexUp.bat --headless --dump "D:\PCSX2\textures\SLUS-20312\dumps" --model models\4x-UltraSharp.pth
TexUp.bat --headless --once ...     REM jen jednorázově zpracuje existující dumpy
```

## Proč je tu zvláštní zacházení s alfou

PS2 má rozsah alfy 0–2.0, PCSX2 ho dumpuje jako 0–255, kde **128 = plně neprůhledná**.
Replacement **musí zachovat stejné hodnoty** – když ESRGAN alfu „přikreslí“ (např. 128 → 140),
textura ve hře přesvětlí nebo zprůhlední. TexUp proto upscaluje RGB a alfu odděleně, alfu
převzorkuje bez změny hodnot a výsledek vždy ořízne do rozsahu původní masky
(uniformní maska → zkopíruje se bit-přesně).

## Co je ověřené

`pytest tests/` – 11 testů běží na CPU s miniaturním ESRGAN checkpointem:

- engine (spandrel, tiling s překryvem vs. přímý průchod),
- zachování PS2 alfy, clamp bicubic overshootu, detekce useknutého PNG,
- **end-to-end**: simulované dumpování během běhu (včetně souboru zapisovaného po částech),
  filtry velikosti/názvu, output scale, overwrite, zastavení pipeline.

Testy běží automaticky v GitHub Actions (`tests.yml`). CUDA část je stejný kód jako CPU
(jen `device="cuda"` + `.half()`), ale GPU runner tu není – první ostré spuštění bude u tebe.

## Struktura

```
texup/
  config.py    – nastavení (JSON), návrh složky replacements z dumps
  engine.py    – spandrel model, CUDA/FP16/channels_last, tiling, OOM fallback
  imaging.py   – načítání, PS2-safe alfa, atomický zápis PNG, kontrola IEND
  watcher.py   – watchdog + SettleQueue (čeká, až se soubor dopíše)
  pipeline.py  – fronty, vlákna, retry, statistiky, PCSX2 hotkey
  pcsx2.py     – hledání složky textures, odeslání hotkey oknu PCSX2
  gui.py       – CustomTkinter okno
install.bat / TexUp.bat / requirements.txt / models/
```

---

### Bonus: Build QualityScaler (Windows .exe)

Workflow [`.github/workflows/build-qualityscaler.yml`](.github/workflows/build-qualityscaler.yml)
zkompiluje [Djdefrag/QualityScaler](https://github.com/Djdefrag/QualityScaler) přes PyInstaller
na Windows runneru a nahraje artifact `QualityScaler-windows-x64` (ručně: *Actions → Run workflow*).
