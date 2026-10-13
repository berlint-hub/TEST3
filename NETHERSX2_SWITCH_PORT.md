# NetherSX2 na Nintendo Switch — úplný záznam portu

Stav k releasu `vk-4248-r31`. Hra běží. Tohle je jeden dokument se vším, co bylo
během portu zjištěno: architektura, build, a kompletní pitva selhání Vulkan bootu.

Cílové zařízení: **NVIDIA Tegra X1 (GM20B / Maxwell)**. Renderer: **Vulkan přes
nxvk**, bez OpenGL. Jádro: **4248**.

---

# Část 1 — Architektura portu

## 1.1 Co se vlastně děje

Jádro emulátoru je **Android `.so`** (`libemucore_4248.so`), které se na Switchi
načítá do vlastní paměťové oblasti a běží pod vrstvou, která mu předstírá Android.
Není to emulace CPU — je to překlad prostředí (libc, JNI, AAudio, EGL/Vulkan).

```
libemucore_4248.so   (Android/bionic, arm64)
        │  volá bionic/JNI/AAudio/EGL/Vulkan symboly
        ▼
source/imports.c     tabulka importů jádra → ukazuje na naše implementace
        │
        ├── source/libc_shim.c      bionic ↔ newlib (největší soubor portu)
        ├── source/nxvk_libc.c      POSIX symboly, které nxvk chce a newlib nedává
        ├── source/hooks/egl.c      EGL → přesměrováno na Vulkan cestu
        ├── source/egl_vk_stubs.c   egl* symboly, které musí existovat, ale nic nedělají
        └── source/hooks/vk.c       Vulkan bridge (viz 1.3)
                │
                ▼
        source/vk_icd_shim.c        ICD-only Vulkan, bez loaderu
                │
                ▼
        libnvk.a / libnvk_support.a (nxvk, staticky)
                │
                ▼
        libnx → nvdrv → GPU
```

## 1.2 Klíčové soubory

| Soubor | Řádků | Role |
|---|---|---|
| `source/main.c` | 2 232 | Entrypoint, `__libnx_initheap`, hlavní smyčka, JNI fake prostředí |
| `source/libc_shim.c` | 2 105 | bionic ↔ newlib kompatibilita pro `libGame.so` / `libc++_shared.so` |
| `source/hooks/vk.c` | 1 112 | Vulkan bridge + diagnostika |
| `source/imports.c` | 621 | Tabulka importů jádra (`dynlib_functions[]`) |
| `source/hooks/egl.c` | 362 | EGL vrstva |
| `source/vk_icd_shim.c` | 240 | ICD-only Vulkan entry pointy |
| `source/nxvk_libc.c` | 166 | POSIX shimy pro nxvk |
| `source/crash.c` | 174 | CPU exception handler |
| `source/egl_vk_stubs.c` | 70 | Neškodné `egl*` stuby |
| `source/error.c` | 60 | `fatal_error()` |

## 1.3 Vulkan bez loaderu

`source/vk_icd_shim.c` je celý pod guardem:

```c
#if defined(USE_VULKAN) && defined(NETHERSX2_VK_ICD_ONLY)
```

Na Switchi **není žádný Vulkan loader**. Shim proto deklaruje ICD entry point
přímo z `libnvk.a` a obaluje ho:

```c
extern PFN_vkVoidFunction VKAPI_CALL vk_icdGetInstanceProcAddr(VkInstance instance,
                                                              const char *pName);
static VkInstance icd_instance = VK_NULL_HANDLE;   // single-instance emulator
```

**Důsledek, na který se naráží:** každý Vulkan symbol, na který kód odkáže, musí
v tomhle shimu existovat, jinak link spadne na undefined reference. Viz past v
§3.3.

## 1.4 Překlad surface — bez toho není obraz

NVK na Switchi **nemá** `VK_KHR_android_surface`. Jeho skutečné WSI je
`VK_NN_vi_surface`. Jádro ale volá Android cestu. Bridge v `source/hooks/vk.c` to
překládá na třech místech:

| Kde | Co dělá |
|---|---|
| ~998–1012 | V enumeraci instancových rozšíření **inzeruje** `VK_KHR_android_surface`, které NVK nemá — aby prošla kontrola dostupnosti v jádře |
| ~1018–1044 | V `vkCreateInstance` to rozšíření **přepíše** na skutečné `VK_NN_vi_surface` |
| ~350–365 | `vkCreateAndroidSurfaceKHR` → `vkCreateViSurfaceNN` |

Funguje to proto, že `ANativeWindow*` v tomhle portu **už je** `NWindow` z libnx
(`ANativeWindow_fromSurface_fake` → `nwindowGetDefault`), takže převod není
potřeba.

## 1.5 Paměť

`__libnx_initheap()` v `source/main.c` nafukuje haldu téměř na všechnu dostupnou
paměť, minus rezervy:

- `SO_REGION_MB` (`source/config.h`) — oblast pro načtené `.so`; v logu jako
  `so_base` / `so_limit`
- `GPU_RESERVE_MB` — **záměrně nemapovaná** část; NVK/nvmap alokuje mimo tuhle
  haldu a jeho `VK_EXT_memory_budget` report je to, čemu VMA věří
- `DATA_ROOT` = `/switch/nethersx2` (`source/config.h`)

Tuning pro Tegra X1 je v samostatném `TEGRA_X1_TUNING.md`:
`-march=armv8-a+crc+crypto -mtune=cortex-a57`, `X1_FAST_MEM ?= 1`,
`source/x1mem.c`, `source/x1perf.c`, testy v `tests/x1mem_logic_test.c`.

---

# Část 2 — nxvk (Vulkan ovladač)

Zdroj: **https://github.com/PalindromicBreadLoaf/nxvk**, branch `switch`.
Mesa 26.2.2 upravená pro Tegra X1. **GPL-2.0-or-later**, linkovaná staticky →
výsledný `.nro` je kombinované GPL dílo.

## 2.1 Co nxvk produkuje

`make package: driver` (v nxvk) připraví:

```
lib/libnvk.a           ~5 314 016 B
lib/libnvk_support.a  ~43 065 254 B
lib/pkgconfig/nxvk.pc         460 B
```

`SUPPORT_LIBS` (nxvk `Makefile` ř. 43–53) — musí být všechny:

```
libmesa_util.a  libmesa_util_simd.a  blake3/libblake3.a  libmesa_util_c11.a
nak/libnak.a  nak_rs.a  libcompiler_c_helpers.a  libnvidia_headers_c.a
nil/libnil.a  liblibnil_format_table.a  nir/libnir.a  libcompiler.a
nouveau_mme/libnouveau_mme.a  nouveau_ws/libnouveau_ws.a
vulkan/util/libvulkan_util.a  spirv/libvtn.a  libxmlconfig.a
```

Bundlování přes `$(AR) -M < $(2).mri`.

## 2.2 Dvě věci, které nxvk **nemá**

- **Žádné EGL** — builduje se s `-Degl=disabled`. Nedá se „doplnit", proto
  `source/egl_vk_stubs.c`.
- **Žádné `rust_switch_stubs`** — neexistují. Nepokoušet se o EGL vrstvu ani o
  přebalování nxvk kvůli ní.

## 2.3 Build prostředí nxvk

`switch/docker/Dockerfile` v nxvk: `FROM devkitpro/devkita64` + python3-pip,
bison, flex, cmake, llvm-15, rustup nightly-2026-07-02. **Neinstaluje žádné
switch portlibs.**

---

# Část 3 — Build

## 3.1 Invokace

```sh
CORES=4248 RENDERERS=VK MESA_FLAVOR=nxvk ./build_all.sh
```

Výchozí hodnoty v `build_all.sh`: `CORES="${CORES:-4248 3668}"`,
`RENDERERS="${RENDERERS:-VK GL}"`, `MESA_FLAVOR="${MESA_FLAVOR:-vendored}"`.

Diagnostika: `NETHERSX2_VK_DIAGNOSTIC=1` (Makefile ř. 34–35 přidá
`-DNETHERSX2_VK_DIAGNOSTIC`; `build_all.sh` ř. 112 to přeposílá).

## 3.2 Jádro

**Musí být `libemucore_4248_baked.so` z `main` repa**, ne z APK třetí strany.
Workflow má krok „Prefer the baked core from main":

```sh
git fetch --depth 1 origin main
git show "FETCH_HEAD:libemucore_${CORE}_baked.so" > "$dir/lib/arm64-v8a/libemucore.so"
```

**Proč přes git a ne přes contents API:** GitHub contents API odmítá soubory nad
1 MB a jádro má 12 MB.

Ověření v build logu: `using the baked core from main: libemucore_4248_baked.so`
a `Bundled cores: 4248 | renderers: VK | MESA_FLAVOR: nxvk`.

Jádra v `main`: `libemucore_3668_baked.so` (12 094 744 B),
`libemucore_4248_baked.so` (12 162 984 B). Jsou **striplá** — žádné `.symtab` ani
`.debug_info`, ale `.dynsym` mají (2 713 symbolů), takže adresu jde přeložit na
nejbližší exportovaný symbol.

## 3.3 Pasti, které stály buildy

| Past | Projev | Řešení |
|---|---|---|
| `TARGET := $(notdir $(CURDIR))` (`Makefile:13`) | Build projde, pak `cp: cannot stat 'NetherSX2_nx.nro'` | `TARGET=NetherSX2_nx` |
| **Zapnutí `NETHERSX2_VK_DIAGNOSTIC` mění, jaké symboly link potřebuje** | `undefined reference to vkQueueSubmit / vkQueueSubmit2 / vkAcquireNextImageKHR` | `#ifdef` větve v `hooks/vk.c` odkazují symboly, kterých se nedagnostický build nedotkne. Při přidání define-gated kódu **vždy**: `grep -oE "\bvk[A-Z][A-Za-z0-9]*\b" source/hooks/*.c` proti exportům ve `vk_icd_shim.c` |
| Release vyžaduje **dvě** podmínky | Run je „skipped" | (a) push se dotkne cesty v `push.paths`; (b) commit message obsahuje `[release-vk]` (workflow ř. 90: `contains(github.event.head_commit.message, '[release-vk]')`) |
| `concurrency: cancel-in-progress: true` | Push zruší běžící run | Nepushovat, dokud běží run, na kterém záleží |
| devkitA64 newlib deklaruje POSIX funkce, které nedefinuje | `conflicting types` | Lokální definice musí přesně sedět na newlib prototyp. `pthread_sigmask(int, const sigset_t *, sigset_t *)`. **`<sys/uio.h>` neexistuje** — použít `<sys/_iovec.h>`, a `struct iovec` definovat jen podmíněně přes `__has_include` |
| Vnořená definice funkce | `error: invalid storage class for function` | Edit ukotvený na řádek **uvnitř** `main()` vloží definici do těla funkce |

## 3.4 CI a proč je diagnostika taková, jaká je

Kontejner `devkitpro/devkita64:latest`, `--user root`.

**Z toho sandboxu ani z Actions UI se logy a artifacty stáhnout nedají**
(`objects.githubusercontent.com`, `release-assets.githubusercontent.com` →
`SSL_ERROR_SYSCALL`). Proto workflow **commituje log zpět do větve** jako
`.ci-logs/release-build-<run_number>.log`, oříznutý na 1 200 řádků
(head 200 + tail 1 000). To je jediný kanál zpětné vazby z buildu.

## 3.5 devkitPro

`DEVKITPRO=/opt/devkitpro`, `PORTLIBS=/opt/devkitpro/portlibs/switch`.

- **`pkg.devkitpro.org` / pacman vrací 403 — je to IP ban, ne přechodná chyba.**
  A **není potřeba**: obraz `devkitpro/devkita64:latest` už obsahuje switch-mesa,
  curl, zlib, ntfs-3g, sdl2*, libjpeg-turbo a `libexpat.a` (251 018 B).
- **Žádné GitHub-hostované binární mirror devkitPro neexistuje** — `installer`
  má jediný asset `.exe` z roku 2018, `libctru`/`buildscripts`/`pacman-packages`/
  `wut`/`SDL` mají nula assetů.
- `switch-mesa` je **nutný** (`launcher/Makefile:64` linkuje `-lGLESv2
  -lturbojpeg`). Neodebírat.
- `actions/cache` v kontejnerovém jobu resoluje cesty na **hostiteli** →
  indirection přes tarball v `$GITHUB_WORKSPACE` je povinná.

## 3.6 Co lokální kontrola neodhalí

`gcc -fsyntax-only` na **vyextrahovaném úryvku** je užitečné (chytilo 4+ reálných
chyb), ale **neodhalí špatné umístění v souboru** — takhle prošel test a stejně
to spadlo v CI na `invalid storage class`.

Místo toho ověřovat **strukturálně na skutečném souboru**: hloubka složených
závorek, otevřené `#if` bloky, a **počkat si na CI build**.

---

# Část 4 — Vulkan boot: kompletní pitva

## 4.1 TL;DR

```c
setenv("NVK_I_WANT_A_BROKEN_VULKAN_DRIVER", "1", 1);   // source/main.c:1931
```

Musí být nastavené **před** `vkCreateInstance`. Je pod `#ifdef USE_VULKAN` —
**ne** pod diagnostickým guardem (viz §4.7).

## 4.2 Příznak

```
[.] vkCreateInstance end result=0 instance=0x... lsfg_prepared=0
[.] vkEnumeratePhysicalDevices result=0 count=0 querying=0
[.] core VM sequence returned vm_running=1
[.] host heartbeat polls=300 vm_running=0 presents=0
```

- **`result=0` a zároveň `count=0`** — ne chyba, ale „úspěch" nad prázdným seznamem
- `nethersx2-exception.log` **neexistoval** → žádný CPU exception
- `nethersx2-mesa-stderr.log` **prázdný** → NVK nic nezalogoval

Jádro korektně zjistilo „tento stroj nemá Vulkan", samo se vypnulo (`vm_running`
1 → 0 během 0,6 s) a hostitel prošel graceful shutdownem.

## 4.3 Kořenová příčina

**a) NVK odmítá Tegra X1.** `src/nouveau/vulkan/nvk_physical_device.c:1508-1518`:

```c
   /* We don't support anything pre-Kepler */
   if (nvkmd->dev_info.cls_eng3d < KEPLER_A) {
      result = VK_ERROR_INCOMPATIBLE_DRIVER;        // tiché
      goto fail_nvkmd;
   }
   if (!nvk_is_conformant(&nvkmd->dev_info) &&
       !debug_get_bool_option("NVK_I_WANT_A_BROKEN_VULKAN_DRIVER", false)) {
#ifdef NDEBUG
      result = VK_ERROR_INCOMPATIBLE_DRIVER;        // ← TOHLE, bez logu
#else
      result = vk_errorf(instance, VK_ERROR_INCOMPATIBLE_DRIVER,
                         "WARNING: NVK is not well-tested on %s, pass ...");
#endif
```

Tegra X1 (GM20B/Maxwell) **není** na seznamu `nvk_is_conformant()`. První
podmínka projde — Maxwell je novější než Kepler. Selhává druhá.

**b) Mesa tu chybu záměrně polyká.** `src/vulkan/runtime/vk_instance.c:445-463`:

```c
   if (instance->physical_devices.enumerate) {
      VkResult result = instance->physical_devices.enumerate(instance);
      if (result != VK_ERROR_INCOMPATIBLE_DRIVER)   // ← spolknutá
         return result;
   }
   VkResult result = VK_SUCCESS;
   if (instance->physical_devices.try_create_for_drm) {   // na Horizonu NULL
      result = enumerate_drm_physical_devices_locked(instance);
      ...
   }
   return result;
```

`VK_ERROR_INCOMPATIBLE_DRIVER` je **jediný** spolknutý kód. Jakýkoli jiný by se
vrátil ven a v logu by bylo `result != 0`.

`try_create_for_drm` je na Horizonu NULL, protože `nvk_instance.c:192-198`:

```c
#if DETECT_OS_HORIZON
   instance->vk.physical_devices.enumerate = nvk_enumerate_physical_device;
#else
   instance->vk.physical_devices.try_create_for_drm = nvk_create_drm_physical_device;
#endif
```

**Výsledek:** `VK_SUCCESS` nad prázdným seznamem, `count=0`, žádný log.

## 4.4 Proč to trvalo ~30 buildů

Tři nezávislé vrstvy mlčení najednou:

1. **`NDEBUG`** → varování se zkompiluje pryč (v debug buildu by ten text byl)
2. **Mesa spolkne zrovna ten kód**, který NVK vrátí
3. **`VK_SUCCESS` + `count=0` vypadá jako legitimní odpověď**, ne jako chyba

Driver selhal, ale navenek to vypadalo jako „tento stroj nemá Vulkan".

## 4.5 Tři slepé uličky — NEOPAKOVAT

Všechny vypadaly věrohodně, všechny byly **vyvráceny měřením**:

| Hypotéza | Jak byla vyvrácena |
|---|---|
| **`abort()` → tichý exit.** `abort` je v importní tabulce (`source/imports.c:301`) a `abort_fake()` (`source/imports.c:201`) jde přímo na `__libnx_exit(134)` — bez logu, bez handleru | Do `abort_fake` přidáno logování → v logu žádný řádek `abort()`, nikdy se nezavolal |
| **`__nx_nv_transfermem_size = 16 MB`** se nealo­kuje, protože `__libnx_initheap()` už haldu nafoukl | Sonda `nv_probe()` volá všech pět kroků z hostitele: **vše `rc=0x0`**, včetně 16 MB, `chars` platný ukazatel |
| **`DETECT_OS_HORIZON` není definované** → použila se DRM cesta | `nvk_instance.c:16` includeuje `util/detect_os.h`; `detect_os.h:97-98` mapuje `__SWITCH__` → `DETECT_OS_HORIZON 1` |

**Co to rozhodlo:** prázdný `nethersx2-mesa-stderr.log`. Kdyby selhalo cokoli, co
NVK loguje přes `vk_errorf`, na úrovni ERROR by to filtrem prošlo. Prázdný soubor
⇒ selhání jde cestou, která neloguje ⇒ `vk_error()` bez formátovacího řetězce.

---

# Část 5 — Diagnostika

Zapíná se `NETHERSX2_VK_DIAGNOSTIC=1`. Píše do `/switch/nethersx2/`:

| Soubor | Obsah |
|---|---|
| `nethersx2-vulkan.log` | `vk_diag_note` — **`fflush` + `fsync` na každý řádek**. Hooky: `vkCreateInstance`, `vkEnumeratePhysicalDevices`, `vkCreateDevice`, swapchain, present. Plus `nv_probe()` a heartbeat z hlavní smyčky |
| `nethersx2-exception.log` | Píše **jen** `vk_diag_exception()` ze `source/crash.c:169`. **Neexistence = důkaz, že nedošlo k CPU exception** |
| `nethersx2-mesa.log` | Přes `MESA_LOG_FILE` |
| `nethersx2-mesa-stderr.log` | Přesměrovaný `stderr` (viz 5.2) |

## 5.1 `fatal_error()` do souboru nepsala

`source/error.c`: jen `consoleInit` + `printf` + čekání na A + `exit(1)`. Text
chyby byl čitelný **jedině vyfocením obrazovky**. Teď se loguje.

## 5.2 Proč je potřeba přesměrovat `stderr`

Mesa `src/util/log.c` nastaví `mesa_log_file = stderr` a soubor použije **jen**
když projdou obě podmínky:

```c
   if (__normal_user()) {                    // log.c:146
      ...
      const char *log_file = os_get_option("MESA_LOG_FILE");   // log.c:159
      if (log_file) fp = fopen(log_file, "w");
      if (fp) { mesa_log_file = fp; mesa_log_control |= MESA_LOG_CONTROL_FILE; }
   }
```

Jinak `mesa_log_file` zůstane `stderr` — a ten na Horizonu **nikam nejde**. Proto
`main.c` přesměrovává `stderr` do souboru (jen `stderr`, ne `stdout` —
`fatal_error()` vypisuje přes `stdout` a to musí zůstat na obrazovce).

## 5.3 `mesa_log_file` se zachytí jednorázově

Jediná dvě přiřazení jsou `log.c:143` (`= stderr`) a `log.c:165` (`= fp`), obojí
uvnitř `mesa_log_init_once()`. **Setter neexistuje.** První Mesa log u nás běží
na vlákně jádra, takže `main.c` volá `_mesa_log()` hned po instalaci
přesměrování — aby se ta jednorázová inicializace stihla na hlavním vlákně.

## 5.4 Výkonnostní cena

`fflush` + `fsync` na každý řádek a heartbeat každých ~5 s po celou dobu hry.
**Pro běžné hraní `NETHERSX2_VK_DIAGNOSTIC` vypnout.**

---

# Část 6 — Instalace a provoz

```
sdmc:/switch/NetherSX2.nro      hlavní .nro
sdmc:/switch/nethersx2/         data, jádra, logy
sdmc:/switch/nethersx2/cores/libemucore_4248.so
```

Spouštět s **plným memory override**, ne v applet režimu.

---

# Část 7 — Kdyby se to vrátilo

`setenv("NVK_I_WANT_A_BROKEN_VULKAN_DRIVER", ...)` byl původně vložený vedle
`setenv("MESA_LOG_FILE", ...)`, což je **uvnitř**
`#if defined(USE_VULKAN) && defined(NETHERSX2_VK_DIAGNOSTIC)`. Build bez
diagnostiky by se tiše vrátil na nula zařízení.

Teď je na `source/main.c:1931`, na začátku `main()`, pod `#ifdef USE_VULKAN`.
**Nikdy to nepřesouvat pod diagnostický guard** — je to runtime požadavek, ne
instrumentace.

```sh
grep -n "NVK_I_WANT_A_BROKEN_VULKAN_DRIVER" source/main.c
# očekáváno: jedno volání, ~1931, pod #ifdef USE_VULKAN
```

---

# Část 8 — Zdroje

- **nxvk:** https://github.com/PalindromicBreadLoaf/nxvk, branch `switch`
- **Jádro (baked, autoritativní):** `main` tohoto repa,
  `libemucore_4248_baked.so`
- **APK odkazy** (jen historicky — jádro se z nich **nepoužívá**):
  4248 → `Trixarian/NetherSX2-patch` release `2.2n`,
  `NetherSX2-v2.2n-4248.apk`, sha256
  `2029e30dcc1ba1ecb8d73313f18b429b40e6044c7785c52af08b948ef94b3ddf`;
  3668 → `Trixarian/NetherSX2-classic` release `2.2n`
- `GameIndex.yaml` se do APK vkládá přes `aapt a` (`old/scripts/patch-apk.sh`) —
  chybějící GameIndex **nebyl** příčinou boot problému
