# Review: `neon_opt/` (NXVK compute shaders + NEON)

**Datum:** 2026-10-20
**Předmět:** 10 souborů přidaných do `neon_opt/` (5× `.h` s NEON, 4× `.comp`, 1× `OPTIMIZATION_SUMMARY.md`)
**Otázka:** lze to použít pro optimalizaci `4248/arm64-v8a/libemucore.so` na Tegra X1?

## Verdikt

**Nelze aplikovat na náš deliverable.** Kód je po řemeslné stránce v pořádku
(čisté ARMv8.0-A NEON), ale míří na vrstvu, kterou nemáme k dispozici, a
optimalizuje operace, které se v PS2 emulaci takto neodehrávají.

Nejde o odsudek kvality — jde o **architektonickou nekompatibilitu**
s binárním patchováním.

---

## 1. Co je na tom dobře (férově)

| Kontrola | Výsledek |
|---|---|
| NEON ISA vs Cortex-A57 | ✅ čisté ARMv8.0-A — **žádné** `vdotq`/FP16/`float16xN_t`/SVE/bfloat |
| Použité typy | `float32x4_t` (208×), `uint8x16_t` (28×), `uint32x4_t` (18×) |
| Závislosti | jen `arm_neon.h` + `vulkan/vulkan.h` + STL — žádné externí knihovny |
| Čitelnost | strukturované, komentované, vlastní `neon::` namespace |

Kód by se na A57 zkompiloval. **Nepodařilo se mi to ověřit překladem** —
v sandboxu není aarch64 cross-compiler (jen `x86_64-linux-gnu`), takže jde
o statickou kontrolu ISA, ne o compile-test.

---

## 2. Zádrhel A: `nxvk` zdrojáky neexistují

`OPTIMIZATION_SUMMARY.md` popisuje integraci do:

```
src/vulkan/runtime/meson.build
src/vulkan/runtime/nvk_compute_shaders.{c,h}
```

Náš artefakt `nxvk-vulkan-tegra-x1.tar.gz` obsahuje:

```
include/vulkan/  include/vk_video/   (headery)
lib/libnvk.a          5 589 226 B
lib/libnvk_support.a 44 558 926 B
lib/pkgconfig/  licenses/  BUILDINFO.txt
*.md
```

**Žádné `src/`.** Ověřeno: `tar tzf … | grep -c 'src/'` → 0.
Jde o distribuci přeložených statických knihoven, ne zdrojový strom.
`src/vulkan/runtime/` tedy **neexistuje** a nelze do něj nic přidat.
Zdrojáky nxvk navíc nelze stáhnout — `release-assets.githubusercontent.com`
je odtud síťově neprůchozí (ověřeno dříve).

## 3. Zádrhel B: compute shader do ovladače nepatří

NXVK je **Vulkan ICD — vrstva pod aplikací**. Dostává `vkCmdDraw`,
`vkCmdCopyBufferToImage` atd. Nikdy neuvidí `Frustum`, `AABB4`, `BVHNode`,
`RenderObject`, `OBB`, `Cone` — to jsou typy, které `neon_opt` sám definuje
a které existují jen **uvnitř rendereru emulátoru**.

Ovladač nemůže "přesunout skinning na GPU" nebo "dělat frustum culling",
protože neví, co je kost nebo kamera.

**Důkaz z vlastního repozitáře:** když fork potřeboval GPU compute práci
(LSFG — frame generation), dal shadery do

```
third_party/lsfg-vk/lsfg-vk-backend/shaders/nvk_mipmap_downsample.comp
third_party/lsfg-vk/lsfg-vk-backend/shaders/nvk_beta1_finalize_quality.comp
```

a volá je **z aplikační vrstvy** přes veřejné Vulkan API
(`lsfg-vk-common/src/vulkan/shader.cpp` → `vkCreateShaderModule`).

To je správné místo. `neon_opt` míří o vrstvu níž.

## 4. Zádrhel C: my jsme o úroveň výš, než kód čeká

Kód předpokládá **zdrojáky emulátoru** (C++ s `vkCreateShaderModule`,
VBO, scénou). Náš stav:

- zdrojáky pro build 4248 **nemáme** (uživatel potvrzeno) → pouze binární patch
- fork `berlint-hub/NetherSX2_nx` **taky nemá** zdrojáky PCSX2
  ( struktura `source/ launcher/ third_party/ tools/`, žádné `pcsx2/GS/` );
  je to kompatibilní vrstva, která `libemucore.so` patchuje **za běhu**

Aplikace by vyžadovala rekompilaci jádra. To je mimo rozsah tohoto úkolu.

## 5. Věcná chyba: takt CPU

`OPTIMIZATION_SUMMARY.md` uvádí **„4× ARM Cortex-A57 @ ~1.9 GHz"**.

Switch Tegra X1 (T210) běží na **1020 MHz**, a to jak handheld, tak docked.
Maximum 1,785 GHz je dosažitelné jen přetaktováním nebo krátkým boostem při
loadingu. 1,9 GHz odpovídá **SHIELD Android TV**, ne Switchi.

Rozdíl je **~86 %** a přímo ovlivňuje úvahy typu „CPU skinning je úzké hrdlo".
Chybí i GPU kontext: **307,2 MHz handheld / 768 MHz docked, 256 CUDA jader**.
GPU compute na 307 MHz je úplně jiná výkonová třída než implikuje dokument.

## 6. Modelová chyba: jak PS2 emulace skinuje a co culluje

**Vertex skinning** — na PS2 se nedělí na CPU s 4 kostmi. Dělá ho **VU1**
vektorová jednotka, a to **mikrokódem, který dodává hra** (libovolný program).
PCSX2 ho emuluje VU recompilerem (na arm64 NEON) a s MTVU na vlastním vlákně.
Fixní compute shader se 4 kostmi **nemůže** nahradit libovolný VU1 mikrokód.
Náš device log navíc ukazuje MTVU připnuté na jádro 2 a dřívější A/B ve forku
naměřilo, že vypnutí MTVU stojí **−24,46 %** — tedy VU1 je reálná a významná
zátěž, ale řešitelná jedině přes VU, ne přes GPU skinning.

**Frustum culling** — PCSX2 neprovádí objektový culling. GS nemá scénograf;
emulátor vykresluje přesně to, co mu hra pošle v GS paketech. Neexistuje
`RenderObject`/BVH, které by šlo cullovat.

**Textury** — jediná oblast, která se reálné práce emulátoru dotýká
(převod formátů, swizzle, mipy). I ta však žije uvnitř GS rendereru,
ne v ovladači.

## 7. Co s tím

Nechat `neon_opt/` v repozitáři jako referenci je v pořádku, ale je potřeba
vědět, že **není použitelná pro binární patch `libemucore.so`**.

Pokud by se měla zužitkovat, jediná cesta vede přes:

1. zdrojáky PCSX2/NetherSX2 pro Switch (nebo fork s vlastním buildem jádra),
2. úpravy v **GS rendereru**, tedy aplikační vrstvě — vzor viz `third_party/lsfg-vk`,
3. **ne** v nxvk.

Nejlépe využitelné části (kdyby se zdrojáky někdy objevily):
`neon_swizzle_rgba_bgra()`, `neon_srgb_to_linear()`,
`neon_generate_mip_level_2d_box()` — to jsou obecné rutiny bez vazby na
doménový model. `AsyncTextureStreamer` je rozumný návrh pipeline.

## 8. Shrnutí tabulkou

| Tvrzení v dokumentu | Stav |
|---|---|
| Cortex-A57 @ 1.9 GHz | ❌ je 1020 MHz |
| 256 CUDA jader (GM20B) | ✅ správně |
| Integrace do `src/vulkan/runtime/` | ❌ zdrojáky nxvk nemáme |
| „GPU compute pro skinning v ovladači" | ❌ ovladač nevidí kosti |
| „Frustum culling v ovladači" | ❌ PCSX2 nemá scénograf |
| „10–50× speedup" | ⚠️ nepodloženo, a pro VU1 mikrokód neplatí |
| NEON je čisté ARMv8.0-A | ✅ ověřeno |
| Kód je čitelný a samostatný | ✅ ověřeno |

---

*Zapsáno jako součást branch `arena/8b264db8-test3`. Napsáno bez spuštění
Ghidry nebo jiného dekompilátoru — jde o statickou analýzu ISA, obsahu
tarballe a architektury, ne o dekompilaci.*


---

## 9. Dodatek: „jde to tedy opatchovat?" (naměřeno 2026-10-20)

### 9.1 Binárka už NEON používá — změřeno

Disassembly celého `.text` (2 350 567 instrukcí), skupiny z capstone:

| skupina | počet | % z .text |
|---|---|---|
| **NEON** | **54 542** | **2,32 %** |
| FP (skalární) | 22 213 | 0,95 % |
| FP16 | 0 | 0,00 % |
| DOTPROD | 0 | 0,00 % |
| SVE / SVE2 | 0 | 0,00 % |
| MatMul / RDM / CRYPTO / AES | 0 | 0,00 % |

**140 různých NEON mnemonik**, nejčastější: `mov`, `movi`, `dup`, `ext`,
`zip1`, `add`, `and`, `uzp2`, `cmeq`, `usra`, `smax`, `smin`, `sshr`, `ushll`.
`zip1`/`uzp2`/`ushll`/`ext` jsou klasické vzorce **autovektorizace překladače**
(prokládání, rozšiřování) — tedy výstup clang/ndk, ne ruční kód.

Dva závěry:

1. **ISA audit je potvrzen daty** — SVE, FP16, dot-product, MatMul, RDM,
   CRYPTO, AES: všude 0. Binárka je čisté ARMv8.0-A.
2. **Neexistuje „NEON mezera", kterou by `neon_opt` zaplnil.** Překladač
   už NEON vygeneroval. Ruční rutiny typu `neon_swizzle_rgba_bgra()` by
   reimplementovaly kód, který tam je.

### 9.2 VU1 se generuje až za běhu

Hustota NEON v okolí MTVU/VU je **podprůměrná**:

| oblast | NEON | % |
|---|---|---|
| MTVU/VU okolí `0x4b2000–0x4b6000` | 13 | 0,32 % |
| VU steal `0x4b2000–0x4b2a00` | 0 | 0,00 % |
| MTVU semafor `0x4b22a0–0x4b2400` | 0 | 0,00 % |
| GS okolí `0x4ba000–0x4bc000` | 0 | 0,00 % |
| *(celá .text)* | *(54 542)* | *(2,32 %)* |

Není to tím, že by VU1 byl nevektorizovaný. Je to tím, že binárka obsahuje
**VU recompiler**, nikoliv VU kód — ten recompiler **vygeneruje NEON až za
běhu** (JIT) do bufferu. Staticky v `.text` proto nic neuvidíme.

Důsledek: ruční NEON v binárce VU1 práci neovlivní, a fixní GPU compute
shader nemůže nahradit **libovolný** VU1 mikrokód, který dodává hra.

### 9.3 Místo na kód by bylo — to není problém

V `.text` existuje souvislý úsek **24 228 nul** na `0x88a15c` až `0x890000`:

- končí **přesně na 64KB hranici** (`0x890000`) ⇒ linker padding
- před ním končí funkce tail-calem `b #0xb577d0` (PLT)
- za ním začíná nová funkce `mov x16, sp` / `stp x16,x30,[x0]` (ukládání
  registrů do bufferu — setjmp/ucontext typ)
- nuly se dekódují jako **`udf #0`** (permanently undefined) ⇒ nikdy se
  nevykoná

Tedy legitimní **code cave**. Prostor není překážka.

### 9.4 Skutečná překážka: chybí symboly, ne místo

I s 24 KB volného místa by injekce vyžadovala:

1. najít funkci, kterou přesměrovat — binárka je **stripped**, bez symbolů;
2. znát její ABI a datové struktury (formát textur, layout VBO);
3. upravit call sites nebo prolog bez rozbití okolí.

To nejde bezpečně udělat. `neon_opt` navíc žádný integrační bod ani
build systém nemá — je to knihovna hledající hostitele.

### 9.5 Co binární patch umí a co ne

| Umí ✅ | Neumí ❌ |
|---|---|
| změnit konstantu (rozlišení, defaulty) | přidat novou funkci |
| vypnout kontrolu (`nop`, `b`) | přidat compute shader |
| nahradit instrukci **v místě** (`isb`→`yield`) | přidat pipeline / nový průchod |
| zachovat volání funkcí | přidat datové struktury |

Našich 5 patchů + `spin-relax` jsou přesně typ „změna chování na existujícím
místě". `neon_opt` je typ „přidat novou funkcionalitu" — a ten ze své podstaty
vyžaduje zdrojáky.

### 9.6 Odpověď

- **NEON část** — technicky vložitelná, ale **zbytečná**: binárka už NEON má,
  VU1 se vektorizuje JITem za běhu.
- **Compute shadery** — **nelze**: potřebují `vkCreateShaderModule`
  z aplikační vrstvy, my máme jen přeloženou binárku.
- **Překážkou není prostor** (24 KB je k dispozici), ale **absence symbolů
  a zdrojáků**.
