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
V **tomto artefaktu** tedy `src/vulkan/runtime/` není.

> ### ⚠️ OPRAVA (2026-10-20) — tento odstavec byl špatně
>
> Původní text končil tvrzením *„Zdrojáky nxvk nelze stáhnout"*. **To byla
> moje chyba, ne síťový fakt.** Ověřoval jsem jen release assety
> (`release-assets.githubusercontent.com`, skutečně neprůchozí) a **nezkusil
> jsem `git clone`** — což je mezera v postupu, ne důkaz.
>
> `git clone https://github.com/berlint-hub/nxvk.git` (větev
> `arena/92b2b9eb-nxvk`) projde a doručí **plný zdrojový strom**
> (499 MB, HEAD `9786622`). `src/vulkan/runtime/` v něm **existuje**,
> včetně `meson.build`.
>
> Tvrzení výše platí tedy jen pro náš `.tar.gz`, ne o dostupnosti zdrojáků.
> **Zádrhel A tím odpadá.** Zádrhely B a C (níže) platí dál — viz §11.

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


---

## 10. Dodatek: „a nejde vylepšit ty NEON funkce, co tam jsou?"

Změřeno 2026-10-20. Otázka míří na NEON, který binárka **už obsahuje**
(54 542 instrukcí, 140 mnemonik), ne na přidání nového.

### 10.1 Co by šlo teoreticky zlepšit — a kolik toho je

| kandidát | počet | poznámka |
|---|---|---|
| `fmul`+`fadd` → `fmla` (FP fúze) | **0** | překladač už fúzoval |
| `mul`+`add` → `mla` (celočíselná fúze) | **0** | překladač už fúzoval |
| `ins` (element insert, cross-lane, pomalé) | **0** | už se nepoužívá |
| `tbl`/`tbx` (na A57 mikrokódované) | **598** | z toho 567 = 1 tabulkový registr |
| `ext` | 2 141 | permutace |
| `zip1`/`zip2`/`uzp1`/`uzp2`/`trn` | 5 231 | transpozice |

**Fúze jsou vyčerpané.** Překladač odvedl práci — není tam jediný pár
`fmul`+`fadd` ani `mul`+`add`, který by šel sloučit.

### 10.2 Proč `tbl` nejde nahradit

567 z 598 je `tbl vD.16b, {vS.16b}, vI.16b` — permutace bajtů s **jedním**
tabulkovým registrem. Index `vI` se ale načítá **za běhu**:

```
adrp  x9, #0x12f000
ldr   q1, [x9, #0xf20]        ; index z konstanty v .rodata
tbl   v0.16b, {v0.16b}, v1.16b
```

nebo je výsledkem předchozích výpočtů. Statickou permutaci (a tedy náhradu
za `rev16`/`rev32`/`xtn`/`zip`) by šlo zvolit jen kdyby byl index konstantní
**na každém místě volání** — a i pak by šlo o ~598 instrukcí, tedy
**1,1 % NEON kódu**.

### 10.3 Kde ten NEON je (73 % na jednom místě)

Hustota po 64KB blocích — jinak než rovnoměrně být nemůže:

| blok | NEON | % |
|---|---|---|
| `0x680000` | 5 895 | **36,0 %** |
| `0x670000` | 4 297 | 26,2 % |
| `0x5d0000` | 4 180 | 25,5 % |
| `0x5e0000` | 4 134 | 25,2 % |
| `0x5c0000` | 4 105 | 25,1 % |
| `0x5f0000` | 3 814 | 23,3 % |
| `0x600000` | 3 454 | 21,1 % |
| zbylých 128 bloků | — | **0–5 %** |

**TOP 15 bloků (pás `0x5b0000`–`0x6a0000`) nese 39 833 z 54 542, tedy 73 %
veškerého NEON kódu.**

### 10.4 Co ten kód dělá — a proč to pravděpodobně není horké

Region **neodkazuje na jediný řetězec** (ověřeno dvěma způsoby vazby
`adrp`+`add`). PLT volání z něj jsou téměř výhradně STL
(`_ZdlPv` 837×, `basic_string::append` 77×, `__next_prime` 44×) — žádná
grafika, žádné logování.

Vzorek z `0x5718fc` ukazuje surový výpočet:

```
sqadd   v26.8h, v20.8h, v23.8h      ; saturující sčítání
add     v25.8h, v25.8h, v17.8h
sshr    v25.8h, v25.8h, #1          ; průměr dvou hodnot
sqxtun  v30.8b, v25.8h              ; 16h -> 8b s balením
sqxtun2 v30.16b, v26.8h
tbl     v24.16b, {v29.16b, v30.16b}, v18.16b
```

`sqadd` + `sshr #1` + `sqxtun` = **průměrování pixelů a balení 16→8 bitů**.
To je obrazové/video zpracování — tedy buď **IPU (MPEG-2 dekodér PS2)**,
nebo softwarový renderer.

**Ani jedno není na horké cestě hry:**

- IPU běží jen při **FMV/videu**, ne během hraní;
- softwarový renderer se nepoužívá, když běží **hardwarový** backend
  (Deko3D / Vulkan-NVK), což je náš případ;
- navíc podle měření forku je při cílových 2× úzkým hrdlem **GPU**
  (kopírování render targetů), ne CPU.

Přesnou identifikaci subsystému **si netroufám tvrdit** — binárka je
stripped a region nemá žádné řetězce. Jde o závěr z tvaru kódu.

### 10.5 Proč binární patch na tohle nestačí

Binární patch bez symbolů umí jen **1:1 náhradu instrukce se stejnými
registry** — registr alokovat znovu nemůžeme. Na ARMv8.0-A / Cortex-A57:

- řetězy `zip`/`uzp`/`trn` jsou pro transpozici **už optimální**; levnější
  varianta neexistuje (bez SVE);
- fúze jsou vyčerpané (10.1);
- `tbl` má dynamický index (10.2);
- `ins` se už nepoužívá.

**Žádná 1:1 náhrada, která by byla prokazatelně rychlejší, neexistuje.**

### 10.6 Odpověď

Vylepšit stávající NEON binárním patchem **nejde**, a to ze dvou důvodů
zároveň:

1. **není co** — překladač už fúzoval, permutace jsou optimální pro
   ARMv8.0-A, `tbl` nelze specializovat;
2. **a stejně by to nebylo horké** — 73 % NEON kódu leží v obrazovém/video
   zpracování, které při hardwarovém renderování a při 2× (GPU-bound)
   nehraje roli.

Kdyby se někdo přesto chtěl pokusit, jediná smysluplná cesta vede přes
**zdrojáky a překlad s profilem** (`-fprofile-use`) nebo ruční přepis
konkrétního jádra s měřením — ne přes patch binárky.


---

## 11. `berlint-hub/nxvk` — zdrojáky jsou k dispozici (a co z toho plyne)

### 11.1 Co je k dispozici

| věc | hodnota |
|---|---|
| repozitář | `berlint-hub/nxvk`, fork `PalindromicBreadLoaf/nxvk` (`isFork: true`) |
| velikost | 576 MB (shallow clone 499 MB) |
| větve | `switch`, `arena/92b2b9eb-nxvk`, `arena/068e6f2f-nxvk` |
| HEAD zkoumané větve | `9786622` — *tegra wsi: opt-in low latency* |
| `src/vulkan/runtime/` | **existuje**, vč. `meson.build` |

Takže integrační cesta z `OPTIMIZATION_SUMMARY.md` je **technicky
průchozí**. To ale neznamená, že je správná — viz 11.3.

### 11.2 `NVK_LOW_LATENCY=1` — míří přesně na naměřený bottleneck

HEAD commit přidává opt-in proměnnou prostředí `NVK_LOW_LATENCY=1`.
Ověřeno v kódu `src/vulkan/wsi/wsi_switch.c`:

```c
#define WSI_SWITCH_IMAGE_COUNT_LOW_LATENCY 2          /* ř. 60  */
...
const uint64_t timeout = chain->low_latency ? 0 : info->timeout;   /* ř. 615 */
if (chain->low_latency) {
   /* Never fall into the blocking libnx dequeue; report NOT_READY. */
   result = wsi_switch_dequeue_nonblocking(chain, 0, &slot);       /* ř. 625 */
}
```

a `caps->minImageCount = caps->maxImageCount = wsi_switch_image_count()`
(ř. 120–121), present mode `VK_PRESENT_MODE_MAILBOX_KHR` (ř. 95).
Soubor se builduje pro Switch: `src/vulkan/wsi/meson.build:41`
`if host_machine.system() == 'horizon'`.

**Proč je to důležité:** fork naměřil, že v GPU-bound úseku (posledních 7
oken) je prezentující vlákno **zaparkované ve `vkAcquireNextImageKHR` na
37–86 % délky okna** (2251–5968 ms), zatímco CPU má rezervu. Přesně tohle
`NVK_LOW_LATENCY` odstraňuje — acquire nebude blokovat, vrátí `NOT_READY`.

**Výslovné varování z commitu:** *„This is a latency/bandwidth knob, not an
FPS claim; no hardware A/B recorded yet."* Výchozí stav je vypnuto a
3-image cesta je bez proměnné bit-identická.

**⚠️ Riziko:** acquire teď může vrátit `VK_NOT_READY`. Aplikace to musí
obsloužit (přeskočit snímek). Z naší binárky **nelze prokázat**, že to
PCSX2 dělá — řetězec `VK_NOT_READY` v jádře existuje (offset `0xcb761`),
ale leží vedle `vkCreateFence failed:` a dalších chybových hlášek, tedy
jde spíš o tabulku jmen výsledků než o důkaz obsluhy. **Vyžaduje test na
zařízení.**

### 11.3 Co se tím NEMĚNÍ: architektonický zádrhel B platí dál

`src/vulkan/runtime/` skutečně hostuje interní compute shadery:

```
src/vulkan/runtime/bvh/lbvh_main.comp
src/vulkan/runtime/bvh/leaf.comp
src/vulkan/runtime/bvh/hploc_internal.comp
src/vulkan/runtime/vk_texcompress_astc.c
```

Jenže to všechno jsou operace, které **vlastní ovladač** a které odstartuje
nějaký Vulkan příkaz: BVH se staví uvnitř
`vkCmdBuildAccelerationStructuresKHR`, ASTC komprese uvnitř texcompress.

**Vertex skinning a frustum culling žádný takový příkaz nemají.** Žádné
`vkCmdSkinVertices` ani `vkCmdCullObjects` neexistuje — ovladač tyto koncepty
nikdy neuvidí, protože mu je nikdo nepředá. Shodou okolností existuje
adresář `runtime/bvh/`, ale ten je pro **ray-tracingové
akcelerační struktury**, ne pro scénový BVH hry — není to táž věc.

Zdrojáky tedy odstraňují **praktickou** překážku (kde psát kód), ne
**architektonickou** (že by tam ten kód neměl být).

### 11.4 Doporučení

1. **Odměřit `NVK_LOW_LATENCY=1`** — je to jediná nová páka, která míří na
   změřený GPU-bound úsek, a zatím nemá žádné A/B. Riziko `VK_NOT_READY`
   otestovat na GT3.
2. `neon_opt` do nxvk **nedávat** — patří do rendereru emulátoru
   (aplikační vrstva), viz §3 a precedens `third_party/lsfg-vk`.
3. Pokud někdo přesto chce GPU práci v nxvk, legitimní jsou jen operace,
   které ovladač vlastní (blit/clear/copy/komprese formátů).
