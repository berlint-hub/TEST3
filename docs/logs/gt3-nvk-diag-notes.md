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

## 2. Spin smyčky jsou STUDENÉ — hypotéza vyvrácena ❌

Tohle je nejdůležitější výsledek.

Fork počítá `sched_yield` per vlákno (`source/pthr.c`), ale **nehroutí** to do
logu při každém volání — jen při prahu:

```c
#define PTHR_YIELD_REPORT_EVERY 100000ull
static int yield_worth_reporting(unsigned long long n) {
  return n == 100 || n == 1000 || n == 10000 || (n % PTHR_YIELD_REPORT_EVERY) == 0;
}
```

První hlášení padne při **n == 100**. V logu jsou `Wrapper:` řádky
(pinování vláken), takže Wrapper logování funguje — ale **žádný řádek
`sched_yield: thread "..." called it Nx` se neobjevil**.

⇒ **Žádné vlákno za celou relaci (~70 s) nezavolalo `sched_yield` ani 100×.**

Důsledek: 27 spin smyček katalogizovaných v §10 jsou **studené cesty**
(inicializace, shutdown, vzácné synchronizace), ne horké smyčky. Horké cesty
EE/GS/VU používají řádné blokující primitivy (`pthread_cond_wait`, `sem_wait`,
`nanosleep`) — přesně ten „hybrid wait: spin for a while, then sleep", který
komentář v `pthr.c` popisuje.

**To zpětně potvrzuje, proč jsem v §10 žádný nový patch neaplikoval.** Kdybych
byl střílel naslepo, patchoval bych studenou smyčku — nulový přínos, reálné
riziko.

⚠️ Podmínka závěru: platí, pokud je `.nro` z posledního CI běhu (`5dca62b`).
Starší build počítadlo ještě neměl — pak by absence řádků nic neznamenala.

## 3. MTVU vs Instant VU1 — skutečná další páka

Log třikrát opakuje varování samotného jádra:

```
[Unsafe Settings] Instant VU1 is disabled, this may reduce performance.
```

V PCSX2 se MTVU a Instant VU1 **vylučují** — zapnuté MTVU VU1 instant vynutí
vypnout. Takže tohle varování není samo o sobě chyba, je to důsledek MTVU.

Jenže forkův commit `e989c84` (VU cycle steal) říká opak:

> *„GT3 na zařízení: VU1 vlákno jede na 100 %, Instant VU1 musí být vypnutý,
> protože se s MTVU hádá."*

A teď víme z §2, že VU1 vlákno **nespinuje** (žádný `sched_yield`). Jestli
„jede na 100 %", pak **počítá**, ne čeká. To je jiná situace, než se čekalo.

⇒ **A/B test, který stojí za to udělat:**

| varianta | MTVU | Instant VU1 | poznámka |
|---|---|---|---|
| A (současná) | on | off (vynuceno) | výchozí |
| B | **off** | **on** | jestli VU1 počítá, nemusí MTVU pomáhat |
| C | on | off | + VU cycle steal level 1 |
| D | on | off | + VU cycle steal level 2 |

Měřit FPS / frame time, ne dojem.

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

Log **neobsahuje žádný frame time ani FPS**. Bez toho nelze A/B testy z §3
vyhodnotit jinak než dojmem. Chybí konkrétně:

1. **Frame time / FPS** — průměr + 1% low (nebo PCSX2 řádky `EE: x% GS: y%`).
2. **Potvrzení verze `.nro`** — je to z CI běhu `5dca62b`? (jinak §2 neplatí)
3. **VU cycle steal nastavení** — jaká hodnota `EmuCore/Speedhacks/vuCycleSteal`
   byla při tomto logu aktivní.

Další binární patch zatím nedává smysl: spin smyčky jsou studené, konfigurační
knoby existují (EECycleRate, VU steal) a zbývá je **změřit**, ne přidávat.
