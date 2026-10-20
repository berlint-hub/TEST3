# Log: GT3 pod NetherSX2_nx / NVK — co z něj plyne

Zdroj: zachycená konzole jádra (corelog) + Vulkan diagnostika.
Sestavení: `NetherSX2 Vulkan diagnostic 1.4.0`, renderer=14 (Vulkan).
Hra: Gran Turismo 3 – A-Spec, `SCES_502.94`, CRC `0xB590CE04`, PAL.
Jádro: `/switch/nethersx2/cores/libemucore_4248.so` (= náš `libemucore_tegrax1.so`).

Plný log nebyl uložen do repa (je dlouhý a obsahuje cesty k ROM).
Tenhle soubor je analýza — ta část, ze které plynou závěry.

## 1. Naše jádro na zařízení běží ✅

```
configuration core=/switch/nethersx2/cores/libemucore_4248.so bios_boot=0 fastmem=hybrid
core image loaded base=0x5343e00000 size=208453632
core constructors completed
gpu[0]=NVIDIA Tegra X1 (NVK gm20b) api=4211042 driver=0x6802002
Elf entry point @ 0x01000008 about to get recompiled.
  Name: Gran Turismo 3 - A-Spec / Serial: SCES-50294 / CRC: B590CE04
```

GT3 naběhne a běží. Nasazení přes přepsání
`/switch/nethersx2/cores/libemucore_4248.so` (§9.8) funguje.

## 2. Spin smyčky — ⚠️ OPRAVA: předchozí závěr byl ŠPATNĚ

> **Tahle sekce původně tvrdila „žádné spin smyčky". Bylo to špatně a fork to
> vyvrátil měřením. Nechávám tu chybu i opravu, protože důvod je poučný.**

### 2.1 Co jsem tvrdil a proč to byla chyba

Uvažoval jsem takhle: fork počítá `sched_yield` per vlákno
(`source/pthr.c`), ale hroutí to do logu až při prahu:

```c
return n == 100 || n == 1000 || n == 10000 || (n % PTHR_YIELD_REPORT_EVERY) == 0;
```

V logu jsou `Wrapper:` řádky, takže logování funguje, ale žádný
`sched_yield:` řádek tam není ⇒ usoudil jsem „žádné vlákno nevolalo
sched_yield ani 100× ⇒ žádné spin smyčky".

**Chyba: `sched_yield` je až poslední krok, ne spin samotný.** Fork to
naměřil a opravil v commitu `b3aa5ca7`:

> *„Závěr ‚žádné vlákno nevolalo sched_yield → žádné spin smyčky' neplatí:
> **PCSX2 ShortSpin()/WorkSema spinuje na AArch64 `yield`/`isb` v userspace**
> a `sched_yield` volá až po vyčerpání spin budgetu."*

Skenovat `sched_yield` volání tedy nemohlo horké spiny najít — ty se
`sched_yield` vůbec nedotknou, dokud se nevyčerpá rozpočet.

### 2.2 Druhá chyba: hledal jsem špatný instrukční kód

Když jsem pak hledal `yield`/`isb` v binárce, našel jsem **nula** — protože
jsem měl špatně kódovanou konstantu. `0xD5033FDF` jsem si označil jako
„DSB sy", ale ve skutečnosti je to **`isb`**. Správně:

| kód | instrukce | počet v `.text` |
|---|---|---|
| `0xD503201F` | `nop` | 17 352 |
| `0xD5033FDF` | **`isb`** | **707** |
| `0xD503205F` | `yield`/`wfe` | 0 |
| `0xD50330DF` | (neplatný CRm) | 0 |

Tohle jádro `yield` nepoužívá — spinuje čistě na **`isb`**.

### 2.3 Správný výsledek: 86 spin smyček

707 `isb` tvoří **105 souvislých bloků**, z toho **86** je skutečných spin
smyček (blok + zpětná větev). Každá má stejný tvar — `ShortSpin()`
rozvinutý 8×:

```
0x4b2304: mov  w9, wzr            ; počítadlo = 0
0x4b2308: isb                     ; ┐
   …      isb   (celkem 8×)       ; │ ShortSpin() × 8
0x4b2324: isb                     ; ┘
0x4b2328: add  w9, w9, w8         ; += spin budget (ldr w8,[x24,#0xc08])
0x4b232c: cmp  w9, #0x1f4         ; 500  <- SPIN BUDGET
0x4b2330: b.lo #0x4b2308          ; dokud < 500
0x4b2344: bl   #0x8a3380          ; až pak blokovací cesta
```

Blokovací cesta `0x8a3380` je `nanosleep` na **1 s**
(`w20 = 0x3b9aca00` = 1 000 000 000 ns). Tedy: nejdřív 8 `isb` až do 500,
teprve pak skutečné uspání.

**Jedna z nich (`0x4b2308`) je přímo v MTVU vlákně**, pár instrukcí od
VU cycle steal patche (`0x4b2500`).

**0 kolizí** s našimi 5 patchi i s hlídanými místy (`0x4b2500`, `0x4bab84`,
`0xd4436`).

### 2.4 Co z toho plyne

Závěr „nepatchovat naslepo" platí dál, ale z **jiného** důvodu: spin smyčky
jsou reálné a horké kandidáty existují — jen pořád nevíme, která z 86 je ta
pravá. Snížit `SPIN BUDGET` (500) by vrátilo jádro dřív ostatním vláknům, ale
zase za cenu častějších přepnutí kontextu. Bez CPU-času per vlákno je to
pořád odhad.

**Ponaučení:** párovat statickou analýzu binárky s měřením ze zařízení, a
když si ty dva protiřečí, ověřit vlastní předpoklady (tady: co vlastně
znamená „více sched_yield").

## 2.5 Naměřená A/B série z forku (commity 5a4f2019, 70b06f5a, e0e44b4d)

A/B test, který tahle sekce navrhovala, mezitím fork **odměřil**. Výsledky
(GT3, okno 300 snímků, zarovnáno na race-start hitch):

| konfigurace | fps | rozdil |
|---|---|---|
| VU steal **Off** | 42.95 | — |
| VU steal **Off** (2. build) | 42.99 | **+0.10 %** (opakovatelnost) |
| VU steal **Level 1** | 43.34 | **+0.92 %** |
| VU steal **Level 2** | 43.51 | **+1.32 %** |
| **MTVU off** | 32.44 | **-24.46 %** |

Dva nezávislé běhy téže konfigurace na dvou různých buildech se shodly na
0.10 % => **šum je hluboko pod 1 %** a měření je důvěryhodné.

Závěry:

- **VU cycle steal NENÍ „nic"** — je to malý, ale skutečný zisk, se správnou
  dávkovou odezvou (L2 > L1). Jen silně pod úměrností: dvojnásobný kredit dá
  jen +0.4 %, což odpovídá disassembly — kredit je
  `clamp(prumer 4 VU citacu, 4, 3000)` EE cyklů proti ~1.2 M cyklů v PAL rámci.
- **MTVU je zásadní** (-24.5 % po vypnutí). Ponechat zapnuté.
- Původní čísla („43.9 / 43.3 / 43.5 = nerozlišitelné") byla **špatně**:
  závodní fáze se brala jako „okna 7+", ale race-start hitch nebyl ve všech
  bězích ve stejném okně, takže jeden běh dostal do průměru navíc okno
  patřící ještě bootu na PAL stropu. Po zarovnání se pořadí obrátilo.

### Kde ve skutečnosti mizí cas (commit e0e44b4d)

První odhad „noc v GT3 je vázaná na GPU" se **nepotvrdil**:

| | klidný závod | pomalý úsek |
|---|---|---|
| `vkCmdCopyImage` / snímek | 1.5 | **80.6** |
| barrier / snímek | 167 | **617** |
| fence čekání | — | 300x 8-9 ms za okno ~6 s = **0.1 %** |
| `queue-idle` | — | **0** |
| `copy2buf` | — | **0** |

Na GPU tedy **nikdo nečeká**. Je to **GS vlákno na 89 % CPU**, které
duplikuje render targety: driver hlásí
`VK_ARM_rasterization_order_attachment_access` jako **NOT supported**, takže
target, který se zároveň sampluje, se musí nejdřív zkopírovat.

Důsledek: CPU-sprite render / software CLUT / CPU framebuffer conversion by
práci přesunuly na **nejvytíženější** vlákno. Fork proto šel opačnou cestou a
zpřístupnil v menu `UserHacks_TextureInsideRt` (0/1/2) a
`UserHacks_GPUTargetCLUTMode` (0/1/2) — oba klíče jsou int enumy už v
připnutém jádru.

## 3. MTVU vs Instant VU1 — vyřešeno měřením, netestovat

Log třikrát opakuje varování samotného jádra:

```
[Unsafe Settings] Instant VU1 is disabled, this may reduce performance.
```

V PCSX2 se MTVU a Instant VU1 **vylučují** — zapnuté MTVU VU1 instant vynutí
vypnout. Varování je tedy důsledek MTVU, ne chyba.

Původně jsem tu navrhoval A/B test MTVU on/off vs Instant VU1. **Fork ho
odměřil dřív (§2.5): MTVU off = -24.46 %.** Verdikt je jednoznačný — MTVU
ponechat zapnuté, Instant VU1 netestovat.

Poznámka k původní úvaze „VU1 vlákno nespínuje, takže počítá": ta úvaha
stála na chybném předpokladu z §2.1. Správně je: VU1 vlákno spinuje na `isb`
(spin smyčka `0x4b2308` je přímo v MTVU), takže „95 % na jádru 2" může být
z velké části **čekání**, ne počítání. Fork to teď rozlišuje měřením CPU času
per vlákno (`pthr_cpu_time_report`, commit `b3aa5ca7`).

## 4. Co je v pořádku a neřešit

| věc | stav | proč |
|---|---|---|
| NVK + zero-copy WSI | ✅ | `nvk wsi: zero-copy ENABLED`, `compositor synced present` |
| `used=3185 MiB` | ⚠️ **kouřová clona** | `InfoType_UsedMemorySize` = rezervace procesu (heap `mb=2910`). Komentář v `nvk_libc_stubs.c`: *„heap.size on this port is an advisory figure for the caller, not a budget NVK enforces"* |
| `NVK heap = 50% = 1642 MiB` | ✅ záměr | commit `ce343cb` |
| pinování vláken | ✅ | MTVU→core 2, CPU→core 0, GS→core 1, driver→core 3 |
| `SummerTime=0` spam (~640/s) | ⚠️ známé | fork už to řeší v `corelog.c` — počítá místo zapisuje. Zbývá jen cena formátování v jádru |
| shader cache (825 položek, 1143 KiB) | ⚠️ malá | první běhy budou mít zásek při kompilaci shaderů |

## 5. Co chybí k dalšímu postupu

Log **neobsahuje žádný frame time ani FPS** — to se od té doby vyřešilo jinde
(fork přidal perf okno s fps i CPU časem per vlákno). Zbývá:

1. **CPU čas per vlákno (`pthr_cpu_time_report`)** z pomalého úseku GT3.
   Z něj se pozná, zda je úzké hrdlo EE / GS / MTVU / nic z těch tří.
   Teprve podle toho má smysl sahat na konkrétní spin smyčku z 86.
2. **Vyhodnocení `UserHacks_TextureInsideRt`** (0/1/2) — fork ho zpřístupnil
   v menu (`e0e44b4d`) právě proto, že 80.6 kopií/snímek je hlavní nález.
   Pokud to zabere, další binární patch jádra ztrácí smysl.

### Verdikt k dalším binárním patchům

Zatím **nedává smysl** žádný další aplikovat:

- Spin smyčky jsou reálné (86, viz §2.3), ale bez CPU času per vlákno nelze
  říct, kterou z nich zkrátit. Zmenšit `SPIN BUDGET` (500) je oboustranný
  obchod — dřív vrátí jádro ostatním, ale přidá přepnutí kontextu.
- MTVU, VU steal i GS hacky jsou **konfigurační** knoby a fork je už
  zpřístupnil. To je levnější a bezpečnější cesta než binární patch.
- Největší nalezený problém (80.6 kopií/snímek kvůli chybějící
  `VK_ARM_rasterization_order_attachment_access`) je **vlastnost ovladače**,
  ne jádra — binárním patchem jádra to nevyřešíme.


## 6. Dodatek: cílové rozlišení 2× — co z našich patchů platí dál

Nejnovější commit forku (`26a9bdd5`) uvádí:

> *„Hráč chce hrát na 2x interním rozlišení a níž nepůjde."*

To přímo dopadá na náš největší patch. Přesná podoba clampu
(`0x4bab6c..0x4bab8c`):

```
0x4bab78: mov  w8, #0x42480000   ; 0x42480000 = 50.0f
0x4bab7c: fmov s1, w8
0x4bab80: fmin s1, s0, s1        ; HORNÍ limit 50x
0x4bab84: fmov s2, #0.50000000   ; DOLNÍ limit 0.5x (port -> 0.25x)
0x4bab88: fcmp s0, s2
0x4bab8c: fcsel s0, s2, s1, mi   ; náš patch: fmov s0, s1  (bez dolního)
```

**2× leží uvnitř [0.25×, 50×], takže se neuplatní žádný clamp**
⇒ `gs-max-upscale-unclamp` je při 2× **inertní**. Odemýká opačný konec
rozsahu, než který se používá.

| patch | při 2× | proč |
|---|---|---|
| `gs-max-upscale-unclamp` | ❌ inertní | clamp se neuplatní |
| `texture-preload-defaults` | ✅ **důležitější** | textury jsou při 2× 4× větší |
| `texture-preload-gssettings` | ✅ totéž | |
| `preserve-user-data` ×2 | ✅ | bezpečnost, nezávislé na rozlišení |

Pozor i na přenos měření: A/B série v §2.5 (42.95 / 43.34 / 43.51 fps) běžela
na **`upscale=0.50`** (viz startup echo `settings upscale=0.50`). Na 2× se
čísla nebudou přenášet — podle forku má GPU při 2× 4× víc pixelů a každá
kopie targetu nese 16× víc bajtů než při 0,5×, takže se zed přesouvá na GPU.

### XGKick Skip: na 4248 nedělá nic

`patch_xgkick_skip()` ve forku (`source/hooks/patches.c:185`):

```c
if (!core_is_3668() || !prefs_get_bool("EmuCore/Patches/XGKickSkip", false) ||
    prefs_get_bool("Wrapper/BootBIOS", false) || ...)
  return;
...
if (*first != 0x14000012 || *second != 0x140001d7) return;
```

Tři důvody, proč na nás nedosáhne:

1. **Gate na `core_is_3668()`** — pro 4248 vrací hned.
2. **Expecty nesedí** (kontrolováno v našem jádru):

   | adresa | fork čeká | naše 4248 |
   |---|---|---|
   | `0x3cfa98` | `0x14000012` | `0x5401a561` |
   | `0x3cfad8` | `0x140001d7` | `0x0b080128` |

   Adresy patří jádru 3668 (12 094 744 B), ne našemu (12 162 984 B).
3. **Default off** a navíc vypnuto při bootu do BIOS.

Je to navíc věc z upstreamu — fork ji nepřidal. **Zapomenout.**

### Verdikt (aktualizovaný)

Při cílovém 2×:

- Další binární patch jádra **nedává smysl** — nejen že chybí měření, ale
  největší známý problém (80.6 kopií targetu/snímek kvůli chybějící
  `VK_ARM_rasterization_order_attachment_access`) je **vlastnost ovladače**,
  ne jádra.
- Nástroj, který fork už zpřístupnil: **`UserHacks_TextureInsideRt`** (0/1/2).
  Při 2× je jeho význam větší, ne menší — každá kopie nese 16× víc bajtů než
  při 0,5×.
- Zbývá GPU fill rate (4× pixelů proti nativu) — to binární patch neovlivní.
