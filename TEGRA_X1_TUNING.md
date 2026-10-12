# NetherSX2_nx — audit a optimalizace pro NVIDIA Tegra X1 (Nintendo Switch)

Tenhle dokument je výsledek kompletního průchodu repozitářem (emulátor
`source/`, launcher `launcher/`, build systém) s jediným cílem: **dostat z
Tegry X1 v přenosném/dokovaném Switchi maximum**. Níže je jednak to, co už je
v kódu dobré, jednak nalezené slabiny — a u každé z nich konkrétní změna, která
je v tomto repu už implementovaná, nebo doporučení k doplnění.

---

## 1. Co přesně je Tegra X1 zač (a proč na tom záleží)

| Blok | Parametr | Důsledek pro PS2 emulaci |
|---|---|---|
| CPU | 4× Cortex-A57 (ARMv8-A), 1020 MHz (boost 1581 / 1785 MHz), 3-wide out-of-order, 2× 64-bit L/S pipes | EE + VU rekompilery jsou čistě CPU. Na 4 slabých jádrech bez SMT je **každé procento CPU drahé**. |
| GPU | Maxwell GM20B, 256 CUDA jader (2 SM), 307–921 MHz | GS rendering, upscaling, blending. |
| RAM | 4 GB LPDDR4 **sdílená CPU+GPU**, ~25,6 GB/s | **Hlavní úzké hrdlo.** GS texturové nahrávání, EE/VU RAM provoz, SPU2 mix a IPU/MPEG kopie jedou přes jednu sběrnici. |
| Cache | L1 32+32 KiB/jádro, L2 2 MB (sdílená s GPU) | Migrace vlákna mezi jádry = studená L1/L2. Pinning má na X1 měřitelný efekt. |

Praktický závěr: na X1 se vyplatí v tomto pořadí (1) paměťová propustnost,
(2) CPU takt, (3) stabilní afinita vláken, (4) teprve potom GPU.

---

## 2. Co už je v upstreamu správně

Není to celé špatně — naopak, spousta věcí je udělaná velmi dobře a nebylo
důvod je měnit:

* **Afinita jader** (`source/pthr.c`): EE/VM vlákno je hard-pinované na vlastní
  jádro, ostatní emulační vlákna rotují po pracovním poolu a nikdy neskočí na
  EE jádro; audio má vlastní jádro. Commit „Use all four CPU cores when the NPDM
  grants them“ je správný krok.
* **Vlastní AAudio→audren shim** (`source/aaudio.c`) místo OpenSL/SDL: méně
  vrstev, méně wakeupů.
* **Vypnuté logování core** (`Logging/*` seednuté na 0): formátování EE/IOP
  konzole stálo FPS.
* **Rozdělení heapu** (`__libnx_initheap` v `main.c` + `config.h`): rezervace
  pro GPU (`GPU_RESERVE_MB`) i pro image `.so` (`SO_REGION_MB`) — obojí je
  správný instinkt na sdílené paměti.
* Renderer se volí už při buildu (GL vs VK), takže se nelinkuje mrtvý kód.

---

## 3. Nálezové body auditu (seřazeno podle očekávaného dopadu)

### A1 – `memcpy`/`memset`/`memmove` core = generické newlib verze 🔴

`source/imports.c` mapoval `memcpy`, `memset`, `memmove`, `memcmp`, `strlen` z
Android binárky rovnou na newlib. newlib je psaný na přenositelnost, ne na
4-issue A57: jde o byte/word smyčky s jedním L/S párem v letu, žádné 128-bitové
přístupy, žádná práce po celých cache řádcích. bionic (proti kterému byl core
stavěný a profilovaný) je NEON implementace po 64bytech.

Tudy teče úplně všechno: GS texturové uploady, kopie EE/VU/IOP RAM, SPU2 mix,
IPU/MPEG snímky, CDVD sektory.

**Oprava:** nový `source/x1mem.c` (NEON, 64bytové bloky = celá cache řádka,
16bytové zarovnání, krátké velikosti řešené jednoduchou smyčkou) zapojený do
importní tabulky i do `_chk` wrapperů. `make X1_FAST_MEM=0` vrátí newlib verze
(pro A/B měření na zařízení).

> ⚠️ Při implementaci odhalen reálný bug: `memmove` s překryvem (cíl pod
> zdrojem) používal zarovnávací „head“ store o 16 bytech, který přepsal
> zdrojová data ještě nepřečtená. Opraveno + pokryto testem
> `tests/x1mem_logic_test.c` (projde bez devkitPro na PC).

### A2 – CPU boost na Switchi **throttluje GPU** 🟠

`main.c` volá `cpu_boost(1)` (= `ApmCpuBoostMode_FastLoad`) a po 60 snímcích
zase `cpu_boost(0)`. Podle libnx:

```
ApmCpuBoostMode_FastLoad = 1  ///< Boost CPU. Additionally, throttle GPU to minimum.
```

Takže „zapnout boost natrvalo“ — první věc, kterou by člověk pro výkon udělal —
by u GPU-heavy her (vyšší upscale, blending) výkon **snížilo**. Upstream se
tomu vyhnul správně, ale nevědomky.

**Oprava:** `source/x1perf.c` — režim je volitelný (`Wrapper/CpuBoostMode`:
`startup` výchozí / `always` pro CPU-bound EE/VU hry / `off`).

### A3 – MTGS sdílí jádro s VU1 a workerama 🟠

`assign_work_core()` rotuje MTGS, VU1 i ring/texture workery přes stejný pool a
`work_mask` jim umožňuje migraci. Na 4× A57 bez SMT to znamená, že si dvě
nejžhavější vlákna vzájemně vyhazují L1/L2 a scheduler je přehazuje.

**Oprava:** `pthr_pin_render_core()` — první vlákno, které naváže render
kontext (`eglMakeCurrent` na GL, první `vkQueuePresentKHR` na Vulkan), dostane
vlastní jádro vyjmuté z rotace a prioritu nad běžnými workery. Výsledné rozložení
na 4 jádrech: **EE = jádro 0, VU1/workery = jádro 1, MTGS = jádro 2, audio/systém = jádro 3.**
EE vlákno zároveň dostává nejvyšší emulační prioritu (40), MTGS 42, audio 43,
input pump 45.

### A4 – `tls_is_render_thread` se nikde nenastavuje → dead code 🟡

`source/pthr.c` deklaruje `__thread int tls_is_render_thread` a čte ho na
třech místech (speciální chování Render vlákna: podržení GL kontextu přes park,
krátké „slice“ čekání, polling mutexu). **Nikde se ale nenastaví na 1**, takže
`pthr_is_render_thread()` vrací vždy 0 a celý tenhle mechanismus je mrtvý.

Dopad: render vlákno při každém `pthread_cond_wait` **odbindovává GL kontext**
(`eglMakeCurrent(..., EGL_NO_CONTEXT)`) a po probuzení znovu binduje. Na Mesa
není `eglMakeCurrent` zadarmo.

**Doporučení:** nechat rozhodnutí na upstreamu — zapnout to znamená změnit
sémantiku čekání (risk deadlocku vs. úspora `eglMakeCurrent` per frame).
Ideální experiment: nastavit flag tam, kde se detekuje render vlákno
(nově `pthr_pin_render_core()`), a otestovat. Prozatím **záměrně nezměněno**.

### A5 – Žádné řízení taktů (CPU/GPU/EMC) 🟠→🟢

Na X1 je největší páka. Bohužel: `apm`/FastLoad zvedá CPU a shazuje GPU (viz
A2), takže zbývá přímé DVFS přes `clkrst` (HOS 8.0.0+). To normální aplikace
nemůže (proto existuje sys-clk jako sysmodul), ale **emulátor spuštěný přes
bundlovaný forwarder má NPDM se `service_access: ["*"]`** → cesta je otevřená.

**Oprava:** `source/x1perf.c` umí (volitelně, defaultně vypnuto) nastavit
CPU/GPU/EMC. Hodnoty se **clamplují na nejbližší nižší položku DVFS tabulky**
(`clkrstGetPossibleClockRates`), takže ručně napsané MHz neskončí chybou. Při
ukončení se takty vrací zpět.

### A6 – Audio buffer 🟡

`DEFAULT_FRAMES_PER_CB 512` × `NUM_WAVEBUFS 3` @ 48 kHz = **~32 ms** latence.
Na CPU-bound emulátoru je velký buffer spíš výhra (méně wakeupů), ale 32 ms je
cítit u her citlivých na timing. Konstanta je compile-time; pokud chceš
experimentovat, zkus 256 (16 ms) a sleduj, jestli se neobjeví praskání.

### A7 – I/O: bufferuje se jen `.dat` 🟡

`libc_shim.c: fopen_fake()` dává 256 KiB buffer jen souborům s příponou `.dat`.
ISO/CHD jde přes `open()`/`read()` (`filehelper.c`) bez bufferu — u CHD/CSO
(dekomprese = drobné čtení) to stojí spoustu round-tripů na SD kartu.
**Doporučení:** pro CDVD přidat read-ahead buffer (256 KiB–1 MiB) do
`fh_open_fd`/čtecí cesty. Prozatím neimplementováno (vyžaduje zásah do
filehelper rozhraní, které volá core).

### A8 – Kompilátor 🟢

`-mtune=cortex-a57` + LTO + `-O3` je správně. Drobnosti:
* globální `-fno-omit-frame-pointer` (kvůli crash handleru) stojí registr x29 v
  každé funkci — pro paměťové primitivy vypnuto per-file (`x1mem.o`).
* `-march=armv8-a+crc+crypto` je pro X1 přesně správně (A57 má obojí).

### A9 – Paměťový rozpočet 🟡

`GPU_RESERVE_MB 1024` + `SO_REGION_MB 256`. Na 4 GB jednotce s game-override
(~3,2 GB pro aplikaci) zbývá pro newlib heap cca **1,9 GB** a ~1 GB pro GPU.
Na X1 je to rozumný kompromis (VMA věří NVK budgetu). Pokud tě trápí „Out of
memory“ v texturové cache u texture-replacement módů, zvedni heap (sniž
`GPU_RESERVE_MB` na 768) — a naopak.

---

## 4. Co je v tomto repu změněno

| Soubor | Změna |
|---|---|
| `source/x1mem.h`, `source/x1mem.c` | **nové** — NEON paměťové primitivy pro A57 (`memcpy/memset/memmove/memcmp/strlen`), přepínač `X1_FAST_MEM` |
| `source/imports.c` | importní tabulka core → `x1_*` (včetně `strlen`) |
| `source/libc_shim.c` | `__mem{cpy,move,set}_chk`, `__strlen_chk` → `x1_*` |
| `source/x1perf.h`, `source/x1perf.c` | **nové** — Tegra X1 politika výkonu: CPU boost režim + volitelné takty CPU/GPU/EMC přes `clkrst` (s restore) |
| `source/pthr.c`, `source/pthr.h` | `pthr_pin_render_core()` (vlastní jádro pro MTGS), priorita EE vlákna (40) a rendereru (42) |
| `source/hooks/egl.c` | detekce render vlákna → pinning (GL) |
| `source/hooks/vk.c` | detekce render vlákna → pinning (Vulkan, první present) |
| `source/main.c` | integrace `x1_perf_init/shutdown`, boost politika dle ini, OSD hláška s aplikovanými takty |
| `source/prefs.c` | seed nových `Wrapper/*` klíčů |
| `Makefile` | `X1_FAST_MEM` přepínač, `x1mem.o` bez frame pointeru |
| `tests/x1mem_logic_test.c` | **nové** — host-side logický test paměťových funkcí (bez devkitPro) |

---

## 5. Nová nastavení v `nethersx2.ini`

```ini
; CPU boost (apmSetCpuBoostMode) -- POZOR: FastLoad na Switchi zároveň
; throttluje GPU na minimum.
;   startup = boost jen při startu (výchozí, chování upstreamu)
;   always  = nechat boost zapnutý (pro CPU-bound EE/VU hry)
;   off     = nikdy
Wrapper/CpuBoostMode = startup

; Explicitní takty (vyžaduje clkrst / HOS 8.0.0+ a přístup ke službě --
; např. spuštění přes bundlovaný forwarder). Jinak se tiše přeskočí.
;   stock       = netýkat se DVFS (výchozí)
;   performance = CPU 1785 / GPU 921 / EMC 1862 MHz (vše oficiální položky
;                 DVFS tabulky Tegry X1)
;   custom      = použít Clock*Mhz níže
Wrapper/ClockProfile = stock
Wrapper/ClockCpuMhz = 0     ; 0 = ponechat
Wrapper/ClockGpuMhz = 0
Wrapper/ClockEmcMhz = 0
```

Po startu se aplikované takty ukážou v OSD (`Tegra X1 clocks: CPU … / GPU … /
EMC … MHz`) — nic se nevypíše, když jsou takty ponechány na stávajících.

> ⚠️ **Varování k taktům:** vyšší takty = víc tepla a odběru. Hodnoty profilu
> `performance` jsou v rámci oficiální DVFS tabulky (ne přetaktování mimo
> specifikaci SOC), ale Switch je pasivně chlazený v handheldu — sleduj teploty.
> Hodnoty se vrací na původní při čistém ukončení; po pádu může zůstat nastavený
> (stejně jako u sys-clk).

---

## 6. Jak to změřit na zařízení (A/B protokol)

1. Zapni FPS v OSD: `EmuCore/GS/OsdShowFPS = true` (nebo v quick menu).
2. Vyber 2–3 reprezentativní hry: CPU-bound (např. *Gran Turismo 3/4*),
   GPU/bandwidth-bound (např. hra s těžkým blendingem), a jednu FMV-heavy.
3. Měř vždy **stejné 60 s úseku** (ideálně replay/in-game demo), po teplotní
   stabilizaci.
4. Postup:
   * baseline (upstream build),
   * `make X1_FAST_MEM=0` → izoluje vliv paměťových funkcí,
   * `Wrapper/CpuBoostMode = always` vs `startup` (GPU-bound hře to uškodí,
     CPU-bound pomůže),
   * `Wrapper/ClockProfile = performance` (pouze se spuštěním přes forwarder).
5. Zapnuté `EmuCore/GS/OsdShowMessages` ti ukáže i OSD hlášku s takty.

Očekávané pořadí dopadu na X1: **EMC takt > CPU takt > paměťové funkce >
afinita MTGS > GPU takt** (u většinyher je limitem sdílená sběrnice, ne výkon
Maxwellu).

---

## 7. Další doporučené kroky (zatím neimplementováno)

1. **Read-ahead buffer pro CDVD/ISO/CHD** (viz A7) — u CHD očekávaný jasný gain.
2. **Rozhodnout A4** (dead code v render-thread handoveru) — experiment s
   zapnutím `tls_is_render_thread` a měřením počtu `eglMakeCurrent` za sekundu.
3. **`audio buffer` konfigurovatelný** z ini místo compile-time konstanty.
4. **Per-game profily taktů**: číst `Wrapper/ClockProfile` z per-game konfigu
   (`gamecfg/`), aby se CPU-bound hra mohla chovat jinak než GPU-bound.
5. **`-fomit-frame-pointer` globálně** pro release build (crash handler má vlastní
   stack; ověřit, že backtrace v `crash.c` funguje i bez FP).
6. Zvážit **měřiče**: jednoduchý počítadlo `svcGetSystemTick()` kolem MTGS
   prezentace by umožnilo ladit frame pacing přímo na zařízení.
