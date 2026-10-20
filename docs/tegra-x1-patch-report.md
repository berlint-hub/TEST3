# libemucore.so → Nintendo Switch (Nvidia Tegra X1) — report a patch

**Zdroj patchů:** <https://github.com/mininxd/NetherSX2-patch>
**Vstup:** `4248/arm64-v8a/libemucore.so` (12 162 984 B, build-id `2b4fe70f…`)
**Výstup:** `4248/arm64-v8a/libemucore_tegrax1.so`
**Branch:** `arena/8b264db8-test3`

---

## ⚠️ Oprava: předchozí verze tohoto patchu byla špatně

Předchozí iterace přejmenovávala `libvulkan.so` → `libvulkad.so` (= **vypnutí Vulkanu**).
Vycházel jsem z obecné představy, že Vulkan na Tegra X1 je problematický. **Bylo to chyba.**

Upstream projekt `NetherSX2-patch` má přímo funkci `apply_switch_optimizations()`
určenou pro *„Nintendo Switch (Nvidia Tegra X1 / Maxwell 256 CUDA cores)"*, a ta říká
opačně:

> **1. Vulkan backend (14)** — direct command buffer execution on Nvidia's
> **desktop-grade** Vulkan driver.
>
> **2. DisableDualSourceBlend: „false"** — Maxwell GM20B má nativní hardwarové
> dual-source blending.

**Vulkan na Switchi zůstává zapnutý.** Aktuální výstup má `libvulkan.so` 3× (původní),
`libvulkad.so` 0×.

---

## 1. Kde se vzaly patche

Nejsou vymyšlené. Jsou vyčtené z upstream repozitáře, konkrétně z těchto míst:

| Zdroj | Co dává |
|---|---|
| `scripts/build.py :: patch_libemucore_settings_defaults()` | Full Texture Preload, větev „v1.5-4248" |
| `scripts/build.py :: patch_preserve_user_data_on_reset()` | Zachování dat při resetu presetu, větev „**v1.5-4248 (Adreno & Switch)**" |
| `patches/patch_scale_multiplier.py :: patch_emucore_scale_clamp()` | Odstranění 0.5f clampu rozlišení |
| `scripts/build.py :: apply_switch_optimizations()` | Kompletní Tegra X1 profil (Preferences) |

### Ověření, že sedíme na správnou binárku

`build.py` vybírá větev podle velikosti souboru:

```python
if file_len == 12162984:   patches = adreno_patches   # ← NÁŠ SOUBOR
elif file_len == 12094744: patches = mali_patches     # (Classic 3668)
```

Náš soubor má přesně **12 162 984 B** → větev **4248**.
Dále `patch_preserve_user_data_on_reset()` uvádí pro „v1.5-4248 (Adreno & Switch)"
offsety `0x840f48` a `0x840fd4` — oba se v naší binárce potvrdily na bajt přesně.

---

## 2. Aplikované binární patche

Všechny jsou **délkově zachovné**, hledané podle obsahu (nebo pevného offsetu tam,
kde vzor není unikátní), s ověřením původních bajtů před zápisem.

| # | Patch | Offset | Změna | Efekt na Tegra X1 |
|---|---|---|---|---|
| 1 | `scale-unclamp` | `0x4bab80` | `fcsel s0,s2,s1,mi` → `fmov s0,s1` | **Odstraní dolní clamp 0.5×** — půjde renderovat na 0.25× / 0.1× / 0.05×. Na slabém Maxwellu největší jednotlivá páka na FPS. |
| 2 | `texture-preload-defaults` | `0x84179c` | → `mov w0, #2` | Full Texture Hash Cache jako default |
| 3 | `texture-preload-gssettings` | `0x4bac34` | → `mov w3, #2` | Totéž pro `GSSettings::Load` (uložená nastavení) |
| 4 | `preserve-user-data-1` | `0x840f48` | `bl` → `nop`, arg registry → 0 | Reset presetu nemaže paměťové karty, achievementy, ovládání |
| 5 | `preserve-user-data-2` | `0x840fd4` | totéž | Totéž pro `ApplyPerformancePreset` |

Původní kód clampu (ověřeno dekompilací):

```asm
0x4bab78: mov   w8, #0x42480000     ; 50.0f   (horní clamp)
0x4bab7c: fmov  s1, w8
0x4bab80: fmin  s1, s0, s1
0x4bab84: fmov  s2, #0.5            ; 0.5f    (dolní clamp)
0x4bab88: fcmp  s0, s2
0x4bab8c: fcsel s0, s2, s1, mi      ; s0 < 0.5  →  s0 = 0.5   ← TOHLE MAZEME
0x4bab90: str   s0, [x21]
```

### Nepovinný, nepotvrzený

`--with-vulkan-bypass` (offset `0x65afa0`, `b.ne` → `nop`) obchází kontrolu podporovaných
Vulkan formátů. `build.py` tento patch pouze **verifikuje** (čeká `nop` na `0x65afa0`
nebo `0x681e7c`), sám ho neaplikuje — pochází z xdelta. Nemám jeho původní bajty,
proto je **vypnutý implicitně**.

### Verifikace výstupu

```
velikost           12 162 984 B   (beze změny)
tabulka sekci      26             (identická)
ELF                platný ELF64 / AArch64
patchů aplikováno  5 / 5          (ověřeno na offsetech)
Vulkan             libvulkan.so 3x — ZAPNUT
změněno bajtů      31
sha256             be64362a525e43e67d2816e60ef197e84b8c82fc2af1655c1504fecc40fc1b4f
ISA kontrola       bezpečné na Cortex-A57 (0 SIGILL rizik)
```

Build-id zůstává `2b4fe70f…` — po binárním patchi se nepřepočítává (vyžadovalo by relink).
Pro běh nevadí, při ladění přes `simpleperf` na to mysli.

---

## 3. Tegra X1 profil — většina je v APK, ne v .so

Tohle je důležité: hlavní část optimalizace upstream dělá přes **Preferences XML v APK**,
ne přes binární patch `libemucore.so`. Hodnoty z `apply_switch_optimizations()`:

| Nastavení | Klíč | Hodnota | Proč |
|---|---|---|---|
| **Renderer** | `EmuCore/GS/Renderer` | **14 = Vulkan** | Nvidia driver na Tegra je desktop-grade |
| Threaded Presentation | `EmuCore/GS/ThreadedPresentation` | `true` | Odpojí prezentační vlákno, odstraní frame pacing jitter na 4× A57 |
| HW Download Mode | `EmuCore/GS/HWDownloadMode` | `1` | Disable Readbacks — odstraní CPU/GPU sync wait-states |
| Blending Accuracy | `EmuCore/GS/accurate_blending_unit` | `1` | Basic — Maxwell blending zvládá hardwarově |
| Texture Preloading | `EmuCore/GS/texture_preloading` | `2` | Full Hash Cache |
| Dual-Source Blend | `EmuCore/GS/DisableDualSourceBlend` | **`false`** | GM20B má nativní HW dual-source blending |
| Skip Duplicate Frames | `EmuCore/GS/SkipDuplicateFrames` | `false` | |
| **MTVU** | `EmuCore/Speedhacks/vuThread` | `true` | VU1 na vlastní vlákno — Switch má 4 jádra |
| EE Cycle Rate | `EmuCore/Speedhacks/EECycleRate` | **`-1`** | 75% underclock — audio crackle + throttling |
| Fast CDVD | `EmuCore/Speedhacks/fastCDVD` | `true` | Rychlejší streamování assetů |
| Affinity | `EmuCore/AffinityControlMode` | `0` | Bez pinování, CFS rozloží zátěž na všechna 4 A57 |
| Orientace | `UI/EmulationActivityOrientation` | `sensor` | |

Setup Wizard tlačítko se přejmenuje na **„Switch(Tegra X1) Defaults"**.

### ⚠️ Tato větev se ve skutečnosti neshazuje — ber ji jako výzkum, ne jako ověřenou konfiguraci

`apply_switch_optimizations()` je sice zapojená do `inject_scale_multiplier()`:

```python
if is_mali:
    apply_mali_optimizations(work_dir)
elif is_switch:
    apply_switch_optimizations(work_dir)
```

…ale `inject_scale_multiplier()` se v celém `build.py` volá **jen dvakrát**:

```python
2778: inject_scale_multiplier(adreno_nethersx2_base, NETHERSX2_ADRENO_APK, ...)              # 4248
2810: inject_scale_multiplier(mali_nethersx2_base,   NETHERSX2_MALI_APK, ..., is_mali=True)  # 3668
```

**Nikdo nepředává `is_switch=True`.** Build má jen dva cíle — `build_adreno()` (4248)
a `build_mali()` (3668). Switch varianta tedy:

- existuje v kódu (někdo ji nastavil a okomentoval),
- ale **nikdy se nepostavila a nikdo ji netestoval**.

Hodnoty výš jsou proto **dobře podložený odhad autora forku, ne ověřená konfigurace**.
Použij je jako startovní bod a každou položku si otestuj. Zejména Vulkan: pro Tegra X1
dává smysl (Nvidia driver), ale pokud ti na konkrétním buildu padá, GLES (12) je záloha.

> Pokud máš celé APK (ne jen `.so`), dej přednost kompletnímu buildu přes
> `scripts/build.py` — aplikuje jak tyto XML defaulty, tak binární patche, a je to
> cesta, kterou projekt skutečně testuje. Samotné `.so` pokrývá jen řádky 1–5 z tabulky výš
> (a to jen část z nich), zbytek musíš nastavit ručně v aplikaci.

---

## 4. Použití

```bash
python3 tools/patch_tegra_x1.py 4248/arm64-v8a/libemucore.so \
                                4248/arm64-v8a/libemucore_tegrax1.so

python3 tools/patch_tegra_x1.py --check  SOUBOR.so   # stav patchů
python3 tools/patch_tegra_x1.py --list               # katalog
python3 tools/patch_tegra_x1.py VSTUP VYSTUP --with-vulkan-bypass   # + nepotvrzený patch

# ISA audit (Cortex-A57 / Tegra X1)
python3 tools/scan_tegra_compat.py 4248/arm64-v8a/libemucore_tegrax1.so
```

---

## 5. Kompatibilita s Cortex-A57 (ARMv8.0)

Z `.text` (9 402 268 B, **2 350 567 instrukcí**):

| Instrukce | Počet | Verdikt |
|---|---:|---|
| PAC/BTI v HINT prostoru | 3 956 | ✅ NOP na A57 |
| CRC32 | 58 | ✅ A57 CRC32 má |
| LSE atomiky (ARMv8.1) | 20 | ✅ všech 20 s HWCAP guardem |
| FP16 / SVE / AES / SHA | 0 | ✅ nepoužito |
| `RETAA` / `BLRAA` (nejsou v HINT prostoru) | 0 | ✅ nepoužito |

**Verdikt: binárka na Tegra X1 nespadne na `SIGILL`.** Detaily a zdroje v
[`docs/libemucore-optimization-audit.md`](libemucore-optimization-audit.md) a v docstringu
`tools/scan_tegra_compat.py`.

> **Pozor na Crypto Extension:** A57 ji v základní konfiguraci **nemá**. V této binárce
> není použita, ale pokud bys přidával kód s AES/SHA, na Tegra X1 spadne.

---

## 6. Co dál

1. **Nejlepší cesta:** celé APK přes `scripts/build.py` z upstreamu — dostaneš XML
   defaulty + binární patche + Switch preset pohromadě.
2. **Submoduly** `pcsx2`, `armsx2`, `mali_gpu` v upstream repu = zdrojové kódy.
   S nimi + Android NDK by šel udělat skutečný rebuild s `-fvisibility=hidden`
   (odstraní 51 % zbytečných PLT volání) a LTO. V tomto sandboxu NDK stáhnout nejde.
3. **Profil ze zařízení** (`simpleperf`) — bez něj se optimalizuje naslepo.

Nepotvrzená zůstává otázka, zda `apply_switch_optimizations()` je v upstreamu skutečně
volána v defaultní build cestě, nebo jde o volitelnou funkci — v `build.py` jsem našel
jejích definici, ale neprověřil jsem všechna místa volání.

---

## 7. Turnip, NVK a `libvulkad.so` — co z toho plyne pro Tegra X1

Zdroj: <https://github.com/nckstwrt/NetherSX2-Turnip>

### `libvulkad.so` NENÍ vypnutí Vulkanu — je to vstupní bod pro VÝMĚNU OVLADAČE

Z README NetherSX2-Turnip („How It Works"):

> *"libemucore.so is modified to load the supplied **libvulkad.so** instead of the
> system's libvulkan.so. Our libvulkad.so then loads libvulkan.so but **patches it in
> memory** so that instead of loading the system's ICD driver it loads whatever
> Turnip driver we want."*

Tím se vysvětluje `libvulkad.so` v `libemucore_4248_baked.so` v tomto repu: je to
**připravený háček**, ne pokus Vulkan vypnout. (Moje úplně první interpretace
„libvulkad = Vulkan vypnut" platí jen v případě, že žádný `libvulkad.so` nedodáš.)

### Turnip na Tegra X1 nepoužiješ

README to říká explicitně:

> **„THIS IS ONLY FOR QUALCOMM (i.e. Adreno) BASED SYSTEMS"**

Turnip = open-source Vulkan driver pro Adreno (freedreno/Mesa). Tegra X1 je NVIDIA
Maxwell — nesouvisející architektura, ovladač na ni nepasuje.

### NVIDIA ekvivalent Turnipu existuje: **NVK**

NVK = Mesa open-source Vulkan driver pro NVIDIA. Podporuje **Maxwell**, a od Mesa 25.1
je na Maxwell/Pascal/Volta Vulkan **1.4 conformant**
[3](https://www.gamingonlinux.com/2025/04/mesa-nvk-nvidia-vulkan-driver-now-vulkan-1-4-conformant-on-maxwell-pascal-and-volta-gpus/)[13](https://www.collabora.com/news-and-blog/news-and-events/nvk-enabled-for-maxwell,-pascal,-and-volta-gpus.html).
Tegra X1 (GM20B) je Maxwell 2. generace.

**Ale pozor:** upstream Mesa NVK *„Tegra/integrated GPUs are not currently supported"*
[5](https://deepwiki.com/bminor/mesa-mesa/2.5-nvk-nvidia-vulkan-driver). Proto existují
samostatné porty:

- `NaGaa95/mesa-switch` — Mesa pro Switch, *„NVK, built **loaderless**; aplikace
  linkuje `libvulkan.a` přímo, žádný loader, žádné ICD"*
  [14](https://github.com/NaGaa95/mesa-switch)
- `D3fau4/mesa-nvk-horizon` — nativní Horizon OS backend pro NVK na GM20B
  [7](https://github.com/D3fau4/mesa-nvk-horizon)

### Co je v `nxvk-vulkan-tegra-x1.tar.gz` (v tomto repu)

Z `lib/pkgconfig/nxvk.pc`:

```
prefix=/opt/devkitpro/portlibs/switch
Name: nxvk
Description: NVK ported to the Nintendo Switch
Version: 26.2.2
Cflags: -D__SWITCH__ -DVK_USE_PLATFORM_VI_NN
Libs: -Wl,--whole-archive -lnvk ... -Wl,-u,vk_icdGetInstanceProcAddr
```

Obsah: `libnvk.a` (5.6 MB, 182 objektů, **AArch64**), `libnvk_support.a` (44 MB),
Vulkan hlavičky, licence GPL-2.0-or-later.

**Zjištění z analýzy nedefinovaných symbolů** (`nm -u`, 4994 symbolů):

| Rozhraní | Počet odkazů |
|---|---|
| `nvGpu*` (libnx / Horizon) | **13** |
| `ioctl` / `drm_*` / `drmOpen` / `nouveau` | **0** |
| `open` / `mmap` | **0** |
| `svc*` (Horizon syscalls) | 0 |

⇒ Jde o build pro **Horizon OS (devkitPro/libnx)**, **nikoliv pro Android**. Žádné
DRM/ioctl rozhraní, které by linuxový nebo androidový Vulkan vyžadoval.

**Důsledek:** tento tarball nelze připojit k Android APK (= k našemu
`libemucore_tegrax1.so`). Potřeboval bys NVK sestavený pro Android/Linux na Tegra X1
(Nouveau kernel driver + Mesa NVK pro aarch64 Linux), ne devkitPro/Horizon build.

### Jak to celé zapadá

| Krok | Adreno (Turnip) | Tegra X1 (ekvivalent) |
|---|---|---|
| Otevřený Vulkan driver | Turnip (freedreno) | **NVK** (Mesa) |
| Jak se dostane do hry | `libvulkad.so` shim | stejný mechanismus |
| Sestavení | Mesa pro Android | Mesa pro **Android/Linux**, ne devkitPro |

### Co s tím nástroj dělá

`--with-vulkan-shim-hook` přidá přejmenování `libvulkan.so` → `libvulkad.so`
(3 místa: `0x10728e`, `0x1264cb`, `0x1264f3`). **Je vypnutý implicitně** — aktivuj ho
jen pokud skutečně dodáváš vlastní `libvulkad.so`. Jinak Vulkan rozbiješ.

---

## 8. NXVK — zdroj `nxvk-vulkan-tegra-x1.tar.gz`

Zdroj: <https://github.com/PalindromicBreadLoaf/nxvk> (výchozí větev `switch`)

### Co to je

> *„NXVK is a downstream fork that ports the **NVK** Vulkan driver and **Zink** Gallium
> driver to the Nintendo Switch (Tegra X1/GM20B)."*

Je to fork **celé Mesa** (227 548 commitů) — ne samostatný projekt. Větve:

| Větev | Poznámka |
|---|---|
| `switch` | hlavní vývojová větev |
| `switch-mesa-26.2.2` | **odpovídá našemu tarballu** (`Version: 26.2.2`) |
| `switch-mesa-26.1.4` | |
| `switch-mesa-25.0.7` | |
| `26.1.4-perf-improv` | větev s vylepšeními výkonu |
| `zink` | |

Kromě Vulkanu dává i OpenGL (přes Zink nad NVK): **OpenGL 4.5 core** a **OpenGL ES 3.2**.

### Je to Horizon OS homebrew — NE Android

Z `switch/README.md`, důkazy jsou jednoznačné:

```c
#include <switch.h>                                 // libnx (Horizon SDK)
u32    __nx_applet_type = AppletType_Application;   // libnx applet model
size_t __nx_heap_size   = 0;                        // libnx heap
setenv("NVK_I_WANT_A_BROKEN_VULKAN_DRIVER", "1", 1);// driver je experimentální
vkCreateViSurfaceNN(... NWindow)                    // VK_NN_vi_surface
```

```
-specs=$DEVKITPRO/libnx/switch.specs ... -lnx -lc -lm -lstdc++ -pthread
Výstup: .nro   (homebrew spustitelný formát)
```

- Prezentace: **EGL over libnx `NWindow`**, rozšíření `VK_NN_vi_surface`
- Ovladač se **linkuje staticky** do `.nro` (žádný loader, žádné ICD)
- Jediný exportovaný symbol: **`vk_icdGetInstanceProcAddr`**
- Build vyžaduje docker/podman + devkitPro

To přesně souhlasí s mou analýzou tarballu: 13× `nvGpu*` (libnx), **0×** `ioctl`/`drm_*`.

### ⇒ S NetherSX2 to nejde použít

| | NXVK | NetherSX2 |
|---|---|---|
| Cílový OS | **Horizon OS** (homebrew) | **Android** |
| Formát | statické `.a` do `.nro` | dynamické `.so` v APK |
| Okno/prezentace | libnx `NWindow` | Android `ANativeWindow` / EGL |
| Přístup k GPU | libnx `nvGpu*` | Android Vulkan loader |
| Toolchain | devkitPro (`aarch64-none-elf-*`) | Android NDK (`aarch64-linux-android*`) |

Rozdílný kernel rozhraní, rozdílný libc, rozdílný windowing. **Nelze zkombinovat.**
Z `libnvk.a` nepostavíš `libvulkad.so` pro Android APK.

### Co si z toho vzít

1. **Pro Android na Switchi (Switchroot) je NXVK k ničemu.** Použij stock NVIDIA
   Vulkan driver — což je přesně předpoklad našeho výstupu (`libvulkan.so` 3×, bez shimu).
2. **Pro nativní běh na Horizon OS** bys nepotřeboval NetherSX2, ale port PCSX2 do `.nro`,
   který by si `libnvk.a` nalinkoval. To je jiný projekt.
3. **Licencování:** *„Because Horizon links `libnvk.a` **statically**, an application
   linking the driver forms a **combined work covered by the GPL**. You may ship binaries
   freely, however, the application's source must be available to whoever receives them."*
   Odpovídá `licenses/nxvk/GPL-2.0-or-later` v tarballu. Pokud bys to někdy distribuoval,
   je to závazek.
4. **Ovladač je explicitně nedokončený** — bez `NVK_I_WANT_A_BROKEN_VULKAN_DRIVER=1`
   NVK odmítne vytvořit device.

### Zajímavý vedlejší poznatek pro náš audit

Oficiální build flags nxvk pro Switch:

```
-march=armv8-a+crc+crypto -mtune=cortex-a57 -mtp=soft
```

- Potvrzuje **`-mtune=cortex-a57`** jako správný target pro Tegra X1
- `+crc` souhlasí s mým zjištěním (A57 CRC32 má)
- `+crypto` — autor předpokládá přítomné AES/SHA; `libemucore.so` je ale nepoužívá (0 nálezů),
  takže pro nás bez dopadu

### Otevřená otázka

Nevím, na čem NetherSX2 na Switchi **reálně provozuješ**:

- **Android (Switchroot / LineageOS)** → náš výstup je správný, NXVK ignoruj
- **Horizon OS** → NetherSX2 (Android APK) tam vůbec nespustíš; potřebuješ nativní port

Podle toho se odvíjí, co má smysl dělat dál.

---

## 9. Cílová platforma: NetherSX2_nx (Horizon OS), ne Android

Původní sekce 1–8 předpokládaly Android + stock NVIDIA Vulkan. To je **špatně**.
Cílem je [NaGaa95/NetherSX2_nx](https://github.com/NaGaa95/NetherSX2_nx) (MIT, 293 ★):

> *"A wrapper/port of NetherSX2 to the Nintendo Switch. It loads the original
> Android emulator core `libemucore.so`, **patches it**, and runs it inside a
> minimal Android-like environment natively."*

Jeden `NetherSX2.nro`, v sobě obě jádra (patched 4248 + Classic 3668) a tři
renderery: **native Deko3D**, **OpenGL**, **Vulkan/NVK**.

### 9.1 Jak port detekuje jádro — kritická podmínka

`source/hooks/patches.c`:

```c
static void detect_core_version(void) {
  g_core_version = CORE_VER_UNKNOWN;
  if (in_range(0xd4436, 24) &&
      !memcmp((const char *)(emu_mod.load_base + 0xd4436), "v2.2n-4248", 10))
    g_core_version = CORE_VER_V22N_4248;
  else if (in_range(0xff01f, 24) && ... "v2.2n-3668" ...)
    g_core_version = CORE_VER_V22N_3668;
}

void patch_game(void) {
  detect_core_version();
  if (g_core_version == CORE_VER_UNKNOWN)
    return;                 // <-- neaplikuje se VŮBEC NIC
  ...
}
```

Náš soubor tento řetězec má — ověřeno:

| soubor | bajty na `0xd4436` | výsledek |
|---|---|---|
| `4248/arm64-v8a/libemucore.so` | `v2.2n-4248 (Patched)` | detekováno |
| `4248/arm64-v8a/libemucore_tegrax1.so` | `v2.2n-4248 (Patched)` | detekováno |

Nepřepsali jsme ho ⇒ jádro je rozpoznáno jako `CORE_VER_V22N_4248`.

### 9.2 Runtime patche portu a kolize s našimi

`g_patches_4248[]` obsahuje **16** patchů (zde označených jako JNI/string-match:
s1, s2, s3, s4, vm; gamedb cache verze; center display X/Y; GS upscale minimum):

```c
{0x83a3d0, 0x5400c3cb, INSN_NOP,      "s1 b.lt(len)"},
{0x83a3e8, 0x940c7546, INSN_NOP,      "s1 bl memchr"},
{0x83a418, 0xaa0b0129, INSN_MOV_W9_1, "s1 force match"},
... (s2 na 0x83a774/0x83a78c/0x83a7bc) ...
{0x83b8c0, 0x34001c58, INSN_NOP,      "s3 class-name match (cbz w24)"},
{0x83bbd0, 0x340003d7, INSN_NOP,      "s4 string match (cbz w23)"},
... (vm na 0x83ce74/0x83ce8c/0x83ceb8) ...
{0x2e3fc8, 0x528c86ea, 0x528cad0a,    "gamedb cache ver lo"},
{0x2e3fcc, 0x72a726ca, 0x72a52c8a,    "gamedb cache ver hi"},
{0x61c924, 0x54000141, INSN_NOP,      "center display X"},
{0x61c964, 0x54000221, INSN_NOP,      "center display Y"},
{0x4bab84, 0x1e2c1002, 0x1e2a1002,    "GS upscale minimum 0.25x"},
```

Aplikace má **strážní podmínku** (řádek 292):

```c
if (*p != pt->expect) {
  continue;                 // tiché přeskočení, ne pád
}
```

Tj. **neshodný `expect` není fatální** — port patch mlčky vynechá. Přesto by
přepsání kteréhokoli z těch 16 míst našimi patchi znamenalo **ztrátu funkce**
(např. ztracené JNI string-match patche ⇒ rozbité ovládání).

**Výsledek kontroly: 0 kolizí.** Žádný z našich 5 patchů se nedotkl bajtu,
který port testuje přes `expect`. Všech 16 `expect` hodnot v našem výstupu
stále sedí ⇒ port aplikuje vše svých 16 patchů normálně:

```
VADDR     EXPECT      VÝSTUP      CO
0x83a3d0  0x5400c3cb  0x5400c3cb  s1 b.lt(len)                 OK
0x83a3e8  0x940c7546  0x940c7546  s1 bl memchr                 OK
...
0x4bab84  0x1e2c1002  0x1e2c1002  GS upscale minimum 0.25x     OK

Kolizí: 0
```

### 9.3 Rozsahový překryv na `0x4bab84` — není konflikt

Náš rozsah `0x4bab80+16` (`gs-max-upscale-unclamp`) formálně překrývá adresu
`0x4bab84`, kterou patchuje port. **Není to problém**, měníme jiné slovo:

| offset | kdo | původní | nové |
|---|---|---|---|
| `0x4bab80` | — | `fmin s1, s0, s1` | beze změny |
| `0x4bab84` | **port** | `fmov s2, #0.5` | `fmov s2, #0.25` |
| `0x4bab88` | — | `fcmp s0, s2` | beze změny |
| `0x4bab8c` | **my** | `fcsel s0, s2, s1, mi` | `fmov s0, s1` |

Portův patch jen **snižuje** spodní mez 0.5× → 0.25×; náš ji **odstraňuje
úplně**. Náš je nadmnožina — po obou je výsledek `s0 = min(s0, 50.0)`, přesně
jak jsme chtěli, a `s2 = 0.25` zůstane nevyužité. Oba koexistují.

### 9.4 Automatická kontrola

```bash
python3 tools/verify_nx_compat.py 4248/arm64-v8a/libemucore_tegrax1.so \
        --base 4248/arm64-v8a/libemucore.so
```

Skript načte `g_patches_4248` přímo z klonu portu, ověří detekční řetězec na
`0xd4436`, porovná všech 16 `expect` a vrátí exit 0/1. Spouštět po každé změně
patchovacího skriptu.

### 9.5 Důsledky pro předchozí sekce

| sekce | platnost | poznámka |
|---|---|---|
| 1–2 (původ patchů, tabulka) | ✅ platí | binární patche jsou nezávislé na platformě |
| 3 (Tegra profil v APK) | ✅ platí | |
| 4–6 (použití, A57, co dál) | ✅ platí | |
| 7 (Turnip / `libvulkad.so`) | ❌ **nepoužitelné** | Turnip je Adreno-only; port `libvulkad` vůbec nepoužívá (0 výskytů ve zdrojích) |
| 8 (NXVK) | ✅ **posíleno** | NXVK je přesně ten balíček, který port žádá do `vulkan/lib` + `vulkan/include` |

Patch `vulkan-shim-hook` (`libvulkan.so` → `libvulkad.so`) je proto pro tento
cíl **irelevantní** — zůstává volitelný a vypnutý.

### 9.6 Doporučené nastavení rendereru na Switchi

1. **Deko3D** (nativní, nejlepší výkon) — výchozí volba.
2. **Vulkan/NVK** — přes NXVK; vyžaduje `NVK_I_WANT_A_BROKEN_VULKAN_DRIVER=1`.
3. OpenGL — nouzová fallback cesta.

Naše patche jsou renderer-agnostické (týkají se GS upscale clampu, texture
preload a `preserve-user-data`), takže fungují se všemi třemi.

### 9.7 Má cenu přidat `libvulkad.so` jako u Turnipu? → **Ne, je to no-op**

Častá otázka: na Androidu se pro Turnip dodává vedle `libemucore.so` ještě
`libvulkad.so`. Má to přínos i na Switchi? **Ne.** Čtyři důvody, ověřené ve
zdrojích portu:

**1. Mechanismus na Horizon OS neexistuje.** Turnip shim funguje proto, že na
Androidu *je* dynamický loader a adresář s vyměnitelnými ovladači
(`/system/vendor/lib64/`). Na Switchi se žádné externí `.so` nenačítá — port
`dlopen` kompletně emuluje (`source/dl_emu.c`).

**2. Název souboru se zahodí.** To je ten rozhodující důkaz:

```c
void *dlopen_fake(const char *filename, int flags) {
  (void)flags;
  // any name (libEGL.so, libaaudio.so, self) -> the same pseudo handle
  return HANDLE_DEFAULT;   // vždy 0x444C4F50 ("DLOP")
}
```

`src/imports.c:295` přesměruje import `dlopen` jádra na tuhle funkci. Ta vrací
**vždy tentýž sentinel handle**, ať ptáš po `libvulkan.so`, `libvulkad.so` nebo
čemkoli jiném; `dlsym_fake` pak stejně hledá jen v importní tabulce a exportech
modulu. Přejmenování řetězce v binárce proto nemá **žádný** efekt — ani dobrý,
ani špatný.

**3. Vulkan je staticky zalinkovaný.** `build_all.sh` odkazuje
`$MESA_SDK_ROOT/lib/libvulkan.a` a `libEGL.a` — statické archívy vlinkované do
`NetherSX2.nro` už při překladu. Neexistuje samostatný `.so`, který by šel
přiložit vedle jádra. (Přesně tohle je náš `nxvk-vulkan-tegra-x1.tar.gz` — ta
`libvulkan.a`.)

**4. Není za co měnit.** Smysl Turnip shimu je „OEM dodal starý ovladač, my
dodáme novější Turnip". Na Tegra X1 existuje právě jeden Vulkan ovladač — NVK
přes NXVK. Stock NVIDIA Android ovladač na Horizon neběží (NVIDIA nikdy
nevydala Horizon Vulkan driver). Turnip je navíc **Adreno/Qualcomm only**.

#### Ekvivalent na Switchi: překlad, ne přiložení souboru

Výměna ovladače se tu dělá v **build-time** — postavíš `NetherSX2.nro` s jinou
verzí NXVK (obsah `vulkan/lib/libvulkan.a`). Stejný efekt, jiná fáze.

#### Je patch `vulkan-shim-hook` škodlivý?

**Není** — jen zbytečný. Mění pouze `libvulkan` → `libvulkad` (obojí 9 bajtů),
takže zachovává délku, a `dlopen_fake` název ignoruje. Zůstává vypnutý.

| platforma | `libvulkad.so` | proč |
|---|---|---|
| Android + Adreno | ✅ smysl | vymění starý OEM ovladač za novější Turnip |
| Android + Tegra (Switchroot) | ❌ ne | Turnip je Qualcomm-only |
| **Horizon OS (NetherSX2_nx)** | ❌ **no-op** | `dlopen` je falešný, název se zahodí |

### 9.8 Jak nasadit patchnuté jádro na Switch (ověřeno ve zdrojích launcheru)

Jádro **není** na SD kartě volně — launcher si ho tahá z romfs uvnitř `.nro`.
Celá cesta, krok za krokem:

**1. Build vyžaduje neporušené jádro.** `tools/prepare_build_inputs.py`
ověřuje sha256 a při neshodě spadne:

```python
CORE_HASHES = {
    "4248": "6f4473845483fa2e7be9d1e8aeac17cd12561d8153d51201037826b9c1b5ffde",
    "3668": "4e378da548984dc0208ff2240aae003942ae9c5a6eec3a36c838c65ac6a37a63",
}
if hashlib.sha256(core).hexdigest() != CORE_HASHES[version]:
    raise ValueError(...)
```

Náš **nepatchnutý** základ tento hash má (`6f447384…`), patchnutý výstup
(`be64362a…`) by build odmítl. Patchujeme proto **až po** extrakci, ne před ní.

**2. Launcher kopíruje jádro z romfs na SD a nastaví `Wrapper/CoreSo`:**

```cpp
std::string coreSource      = "romfs:/cores/emucore_" + build + ".so";
std::string coreDestination = std::string(CORES_DIR) + "/libemucore_" + build + ".so";
bool haveCore = ensureCore(coreSource.c_str(), coreDestination.c_str(), build);
...
if (haveCore) {
  std::string corePath = "/switch/nethersx2/cores/libemucore_" + build + ".so";
  storeSet(g_global, "Wrapper/CoreSo", corePath.c_str());
  storeSet(effective, "Wrapper/CoreSo", corePath.c_str());
}
```

`main.c` pak načte právě tuhle cestu (`so_load(&emu_mod, g_core_so, …)`).

⚠️ **Ruční editace `Wrapper/CoreSo` v `nethersx2.ini` nefunguje** — launcher ten
klíč při každém startu přepíše (`storeSet`).

**3. Ale `ensureCore` kontroluje jen marker, ne obsah:**

```c
static bool ensureBundledFile(const char *src, const char *dst, const std::string &marker) {
  char cur[48] = {0};
  FILE *f = fopen(marker.c_str(), "r");
  if (f) { if (!fgets(cur, sizeof(cur), f)) cur[0] = 0; fclose(f); }
  struct stat st;
  if (trim(cur)==BUILD_STAMP && stat(dst,&st)==0 && S_ISREG(st.st_mode)) return true;  // přeskočí kopii
  if (!extractFromRomfs(src,dst,true)) return false;
  ...
}
```

Marker je `/switch/nethersx2/cores/.core_build_4248` (obsahuje `BUILD_STAMP`).
Sedí-li stamp **a** cílový soubor existuje → **nekopíruje se nic**.

#### ⇒ Postup

1. Spusť launcher **jednou**, ať jádro rozbalí.
2. Zkopíruj `libemucore_tegrax1.so` na
   **`/switch/nethersx2/cores/libemucore_4248.so`** — **přepiš, zachovej jméno**.
3. Spusť znovu. Launcher vidí platný marker + existující soubor → přeskočí
   kopii → `Wrapper/CoreSo` ukáže na tentýž soubor → načte se **náš** patchnutý
   core.

Marker nech být — na něm závisí, že se náš soubor nepřepíše.

#### Kontrola a nástrahy

- Načtení selže → `fatal_error("Could not load\n%s.", g_core_so)`, tj. hláška s
  cestou. Není to tiché selhání.
- **Při přechodu na novější `NetherSX2.nro`** se změní `BUILD_STAMP`, marker
  přestane sedět a launcher jádro znovu rozbalí → **náš patchnutý soubor
  přepíše**. Po každé aktualizaci je nutné krok 2 zopakovat.
- Cesta platí pro build **4248**. Klasické jádro 3668 je
  `libemucore_3668.so` — naše patche jsou pro něj neplatné.
- Runtime patche portu (`g_patches_4248`, 16 položek) se aplikují **navrch**;
  ověřeno 0 kolizí (§9.2).

---

## 10. Kandidáti na další Tegra X1 patche (a kde to naráží)

Nástroj: `tools/find_tegra_candidates.py`.

### 10.1 První pokus selhal, a proč

Hrubý sken (`ldrsb` + registrový shift po celém `.text`) dal **1123 zásahů** —
k ničemu. Binárka je **stripped** (žádné `.symtab`, jen 330 importů v
`.dynsym`), takže bez profilu ze zařízení nelze poznat, který zásah je horká
cesta a který se zavolá jednou za běh. Nástroj proto nedělá „najdi patch",
ale „udělej pořádek a ověř kolize".

### 10.2 Co se našlo: 27 spin smyček

`sched_yield` je importován a má **89** volání; **27** z nich je uvnitř
zpětné větve, tedy skutečný spin. Na 4jádrovém Cortex-A57 bez SMT spinující
vlákno sežere celé jádro — to je ten správný druh cíle.

| | |
|---|---|
| `sched_yield` volání | 89 |
| z toho uvnitř smyčky | **27** |
| kolize s applied/hlídanými místy | **0** |

Všechny jsou mimo rozsah našich 5 patchů i mimo `0x4b2500` (VU steal) a
`0x4bab84` (port).

### 10.3 Konfigurační struktura

Z `VU_Thread::ExecuteVU` (0x4b24b0–0x4b2530):

```
x21 = ADRP 0x2604000 + 0xf20  ->  0x2604F20     (EmuConfig.Speedhacks)
  +0  = příznaky       (bit 5 testován tbnz na 0x4b252c)
  +5  = EECycleSkip    (ldrb w10,[x21,#5] -> MUL na 0x4b2500)
```

To je kotva pro případné další knoby ze stejné struktury.

### 10.4 Kde to naráží — a proč jsem zatím nic neaplikoval

**Který spin je horký, z binárky poznat nejde.** Patching studené smyčky
není k ničemu; patching horké smyčky špatně (např. odebráním potřebného
yieldu) může naopak uškodit. Obojí bez dat ze zařízení.

Fork už diagnostiku má — commit `b7a18c1` „počítat sched_yield per vlákno,
rozlišit spin od práce". **Správné pořadí se tedy musí vzít z toho logu,
ne odhadem.** Navrhovaný postup:

1. Spustit na Switchi s diagnostikou.
2. Vytáhnout `sched_yield` počty per vlákno.
3. Spárovat s 27 kandidáty podle toho, která smyčka patří kterému vláknu.
4. Teprve pak vybrat.

### 10.5 Co už je hotovo jinde — neopakovat

| věc | stav |
|---|---|
| VU cycle steal (`0x4b2500`) | má fork, ověřeno kompatibilní (§9.8) |
| `EECycleRate` | v jádře existuje, ale jde o **nastavení**, ne o patch |
| upscale clamp, texture preload, preserve-user-data | naše 5 patchů |
| pinování vláken, `sched_yield` diagnostika, LSFG | fork |

`EECycleRate` stojí za zmínku zvlášť: řetězec je v binárce přítomen, takže
jde o existující knob vystavený přes UI — není důvod ho patchovat.

### 10.6 Shrnutí

Katalog je **podklad pro rozhodnutí, ne rozhodnutí**. Bez logu ze zařízení
by další patch byl střelba naslepo, a u jádra, které port kontroluje přes
16+1 `expect` hodnot, je střelba naslepo zbytečně riskantní.


## 11. `spin-relax` — `isb` → `yield` ve spin smyčkách semaforu (EXPERIMENTÁLNÍ)

Dosud jsme spin smyčky jen spočítali (§10), nevěděli jsme ale, **ve které funkci
jsou** a co dělají. To vyřešila analýza pořízená náhradou za Ghidru — viz
§11.1 — a díky ní je tento patch **strukturně ověřený**.

### 11.1 Jak jsme zjistili, co ty smyčky jsou (bez Ghidry)

Ghidra ani žádný jiný dekompilátor není v tomto sandboxu dostupný
(release assety na `release-assets.githubusercontent.com` jsou síťově
blokované, chybí Rust/Java toolchain). Místo toho:

1. **`angr` 9.2.213 z PyPI** — plná `CFGFast` analýza 12 MB binárky na 3 GB RAM
   **nedoběhla** (narostla na ~3 GB a musela být zastavena).
2. Fungovala **levná náhrada**: začátky funkcí z cílových adres všech `bl`
   instrukcí + detekce prologů `stp x29,x30,[sp,#..]!` (celkem 10 406 začátků),
   a **jména externích funkcí z `.rela.plt`** (685 PLT stubů → skutečná jména
   dynamických symbolů, i když je binárka stripped).

Výsledek: **86 spin smyček leží v 40 funkcích**, z nich **37 volá `sem_wait`**
(pokrývá 79 smyček). Zbylé 3: jedna kalibrační funkce (`0x8a3384`, 5 smyček,
volá `clock_gettime`), jedna producentská (`0x8058f4`, `usleep`+`sem_post`) a
jedna bez PLT volání.

Z toho plyne identifikace: jde o **PCSX2 `Semaphore::Wait()`**.

### 11.2 Přesná struktura (MTVU instance, funkce `0x4b22a0`)

```
  0x4b22c0: ldar  w21,[x19]        ; atomic acquire load počítadla
  0x4b22c4: tbnz  w21,#0x1f, exit  ; sign bit -> rovnou blokovat
  0x4b22cc: mov   w22,wzr          ; total_spin = 0
  0x4b22d4: ldr   w23,[x8,#0xc0c]  ; spin budget
  outer:
  0x4b22dc: cmp   w22,w23
  0x4b22e0: b.ls  #0x4b22fc        ; ještě máme rozpočet -> spinuj
  0x4b22f0: bl    #0x2f7760        ; atomic CAS (zkus odečíst)
  0x4b22fc: ldr   w8,[x24,#0xc08]  ; g_spin_cycles
  0x4b2300: cbz   w8,#0x4b2344     ; == 0 -> pomalá cesta (nanosleep 1 s!)
  0x4b2304: mov   w9,wzr
  blok:
  0x4b2308: isb   x8               ; <-- ZDRŽENÍ (8 instrukcí)
  0x4b2328: add   w9,w9,w8
  0x4b232c: cmp   w9,#0x1f4        ; 500
  0x4b2330: b.lo  blok
  0x4b2334: add   w22,w22,w9
  0x4b2338: ldar  w21,[x19]        ; <-- ZNOVU NAČTENO, ACQUIRE
  0x4b233c: tbz   w21,#0x1f, outer ; podmínka ukončení
```

### 11.3 Proč je výměna za `yield` paměťově bezpečná

**Řazení paměti zajišťuje `ldar` na `0x4b2338`, nikoli `isb`.** Podle ARM ARM
ISB *neuspořádává datové přístupy* — je to instrukční bariéra (spláchnutí
pipeline), datovou bariérou je `dmb`/`dsb`. `isb` je zde tedy čisté zdržení
a jeho výměna za `yield` (`0xD503203F` — přesně to, co používá linuxový
arm64 `cpu_relax()`) mění jen **délku** zdržení, ne sémantiku.

Varování do budoucna: **nekódovat `yield` jako `0xD503205F`** — to je `wfe`.
Správně: `nop`=`0xD503201F`, `yield`=`0xD503203F`, `wfe`=`0xD503205F`,
`wfi`=`0xD503207F`, `isb`=`0xD50330DF`/`0xD5033FDF`.

### 11.4 Uniformita a rozsah

Všech **81** míst má identický tvar (ověřeno strojově):

| kontrola | výsledek |
|---|---|
| délka souvislého běhu ISB | 8 instrukcí u **všech 86** |
| `add w9,w9,w8` | `0x0B080129` (shodné) |
| `cmp w9,#0x1f4` | `0x7107D13F` (shodné) |
| `b.lo` cíluje na začátek bloku | **81/81** |
| rozdíl `isb` vs `yield` | jen 2 z 4 bajtů (`DF 3F` → `3F 20`, `03 D5` shodné) |

**Vyloučeno záměrně:** 5 kalibračních smyček na
`0x8a3414 / 0x8a3494 / 0x8a3518 / 0x8a35a0 / 0x8a3618` — ty mají za `isb`
místo toho `subs w8,w8,#1 ; b.ne`, takže je podpisová kontrola
`add w9,w9,w8 / cmp w9,#0x1f4 / b.lo` automaticky přeskočí. Ověřeno, že
zůstaly nedotčeny.

### 11.5 Ověření výsledku

```
počet změněných bajtů : 1296  (= 81 míst x 16 B)
8x isb -> 8x yield    : 81/81
bajtů mimo očekávané pozice : 0
zbytek binarky        : identický
velikost              : 12 162 984 B (délkově zachovné)
kolize s 5 našimi patchi + VU steal (0x4b2500) : 0
verify_nx_compat.py   : VERDIKT KOMPATIBILNI, 16/16 patchů portu, 0 kolizí
```

Nejbližší spin smyčka k VU steal adrese `0x4b2500` je `0x4b2308` (MTVU) —
tedy **500 bajtů pod** ní, žádný překryv.

### 11.6 PROČ JE VYPNUTÝ — směr výkonu nebyl změřen

Tohle je důležité a je to důvod, proč patch **není** v hlavním deliverable:

- `isb` na Cortex-A57 splachuje pipeline a je řádově **desítky cyklů**;
  `yield` je hint za ~1 cyklus. Spin se proto zkrátí v čase zhruba **20–50×**.
- Počet *iterací* se nezmění (pořád `w9` do 500), takže se nezmění ani počet
  průchodů vnější smyčkou. Změní se jen to, **jak často se v čase ptáme na
  semafor**.
- Rychlejší dotazování = **nižší latence** probuzení, ale také **plné
  vytížení jádra** po dobu čekání.
- Na 4jádrovém Tegra X1, kde fork připíná EE→0, GS→1, MTVU→2, driver→3
  (každé vlákno vlastní jádro), je tight spin pravděpodobně **v pořádku až
  prospěšný**. Pokud by jádra byla sdílená, čekající vlákno by naopak
  **kradlo cykly producentovi** a výkon by klesl.

Bez měření (FPS + 1 % low) nelze říct, kterým směrem se to vydá. Navíc
podle §6 je při cílovém rozlišení 2× úzkým hrdlem GPU (kopírování render
targetů), takže CPU-side změna pravděpodobně ani nebude dominantní.

### 11.7 Jak to odzkoušet (A/B)

```bash
# experimentální varianta (5 ověřených patchů + spin-relax)
python3 tools/patch_tegra_x1.py 4248/arm64-v8a/libemucore.so \
    4248/arm64-v8a/libemucore_tegrax1_spinrelax.so --with-spin-relax

# kontrola, že je aplikováno (idempotentní)
python3 tools/patch_tegra_x1.py --check 4248/arm64-v8a/libemucore_tegrax1_spinrelax.so
```

Na konoli nahraj `libemucore_tegrax1_spinrelax.so` jako
`/switch/nethersx2/cores/libemucore_4248.so` (jméno musí zůstat),
změř, pak vrať `libemucore_tegrax1.so` a změř znovu. Teprve podle výsledku
se rozhodni. **Hlavní deliverable `libemucore_tegrax1.so` je beze změny**
(sha256 `be64362a...`).
