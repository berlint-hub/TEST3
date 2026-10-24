# libemucore.so — optimalizační audit

**Cíl:** `4248/arm64-v8a/libemucore.so` (12 162 984 B → 11.60 MiB)
**Branch:** `arena/8b264db8-test3`
**Metoda:** ELF/binutils statická analýza (`readelf`, `nm`, `objdump`) + symbolová analýza
nestripnuté sourozenecké buildu `libemucore.so` (repo root).

---

## 0. Proč ne Ghidra (a proč by to stejně nestačilo)

Ghidra se v tomto sandboxu **nedá nainstalovat** – ověřeno měřením, ne odhadem:

| Požadavek | Stav | Důkaz |
|---|---|---|
| Stažení Ghidry (569 MB) | ✗ | asset přesměrovává na `objects.githubusercontent.com` / `release-assets.githubusercontent.com` → `curl` vrací `000` (spojení odmítnuto) |
| JDK 21+ (Ghidra 12 ho vyžaduje) | ✗ | `java`/`javac` chybí; `repo1.maven.org`, `api.adoptium.net`, `deb.debian.org` → vše `000` |
| Build ze zdrojáků (github.com) | ✗ | Gradle by stahoval závislosti z Maven Central → blokováno |
| Hardware | ✗ | 2 CPU / 3 GB RAM (Ghidra chce 4 GB+); dekompilace 9 MB arm64 by trvala hodiny |

Povolený výstup je pouze `github.com`, `codeload.github.com`, `api.github.com`,
`registry.npmjs.org`, `pypi.org`, `files.pythonhosted.org`. Žádná z nich Ghidru ani JDK nenese.

**Důležitější věc:** Ghidra **není optimalizátor**. Je to nástroj na *reverse engineering* –
disassembluje, dekompiluje a umožňuje patchovat jednotlivé instrukce. Nemá žádnou funkci
„optimalizuj binárku“. Reálná optimalizace nativní knihovny znamená:

1. najít slabé místo (profilování / statická analýza) → **tento dokument**
2. změnit zdroják nebo build flags
3. **znovu zkompilovat** ze zdrojových kódů (PCSX2/AetherSX2 + Android NDK)

Krok 3 nejde udělat bez zdrojáků a NDK, a už vůbec ne na 2-jádrovém sandboxu.
Níže je proto to nejcennější, co jde udělat *bez* Ghidry: **naměřený audit s konkrétními
nápravami**, které pak lze aplikovat při rebuildu.

> Poznámka: data označená **[sibling]** pocházejí z nestripnuté varianty `libemucore.so`
> v rootu repa (build-id `abf3eaff…`, jiný build než 4248). Slouží k pojmenování kódu,
> protože 4248 je stripnutá a jména funkcí nemá. Absolutní velikosti se mohou lišit,
> rozložení kódu je však reprezentativní.

---

## 1. Základní identifikace binárky (4248)

| Vlastnost | Hodnota |
|---|---|
| Architektura | AArch64, ELF64, little-endian, `DYN` |
| Toolchain | **Android clang 14.0.6** (NDK **r25b**, API 26), linker **LLD 14.0.6** |
| Build ID | `2b4fe70fd5c1bc92ae3ca7a01d9e8cdd8eebd71e` |
| Symboly | stripnuto (chybí `.symtab`) |
| `.text` | 9 400 732 B (8.97 MiB) |
| Align `.text` | 0x10000 (64 KiB) – kompatibilní s Android 15 / 16K stránkami |
| `BIND_NOW` + úplný RELRO | ✅ zapnuto (dobře) |
| `NEEDED` | libdl, libEGL, liblog, libaaudio, libandroid, libjnigraphics, libm, libc |

Rozložení sekcí (top):

| Sekce | Velikost | Poznámka |
|---|---:|---|
| `.text` | 8.97 MiB | kód |
| `.bss` | **187.4 MiB** (virtuální, NOBITS) | ⚠️ viz nález #7 |
| `.rodata` | 951 KiB | konstanty |
| `.rela.dyn` | 508 KiB | 21 655 relokací |
| `.eh_frame` | 472 KiB | unwind tabulky |
| `.data.rel.ro` | 223 KiB | |
| `.eh_frame_hdr` | 113 KiB | |
| `.gcc_except_table` | 118 KiB | |
| `.dynstr` | 116 KiB | jména dynamických symbolů |
| `.dynsym` | 64 KiB | 2 710 položek |
| `.plt` | 10.7 KiB | 685 PLT stubů |

---

## 2. Nálezy, seřazené podle dopadu

### 🔴 #1 – 1 556 zbytečně exportovaných funkcí (95 % exportů je vnitřních)

`readelf --dyn-syms` na 4248:

```
exportovaných FUNC   : 1635
  ├─ JNI vstupy (Java_*/JNI_*) : 79     ← to jediné, co musí být vidět
  ├─ C++ manglované (_Z…)       : 1351  ← vnitřní implementace
  └─ C symboly                  : 205
```

Exportováno je kompletní vnitřek knihovny včetně celé libc++ internals:
`std::__ndk1::moneypunct`, `messages`, `codecvt_utf8_utf16`, `num_put`, `basic_istream`,
`__throw_length_error`, `ZSTD_*`, `chd_get_codec_name` …

**Náprava**

```cmake
set(CMAKE_CXX_VISIBILITY_PRESET hidden)
set(CMAKE_C_VISIBILITY_PRESET   hidden)
set(CMAKE_VISIBILITY_INLINES_HIDDEN ON)
# + version script:
# { global: JNI_OnLoad; Java_*; local: *; };
```

**Přínos:** menší `.dynsym`/`.dynstr`/`.gnu.hash` (≈ 233 KiB režie dohromady), rychlejší
`dlopen()` (méně symbolů v gnu-hash), a hlavně odemčení LTO a dead-strippingu
(linker nemůže vyhodit nic, co je exportované).

---

### 🔴 #2 – 51 % volání jde zbytečně přes PLT/GOT místo přímého `bl`

Tohle je nejzajímavější výkonnostní nález. Z 685 `R_AARCH64_JUMP_SLOT` relokací:

```
→ importované funkce (PLT nutný)      : 334
→ funkce DEFINOVANÉ V TÉTO KNIHOVNY   : 351   ← zbytečná indirekce
```

Příklady volání, která dnes končí v PLT, přestože cíl je o pár KB dál v téže `.so`:

```
_ZNSt6__ndk112basic_stringIcNS_11char_traitsIcEENS_9allocatorIcEEE6appendEPKcm
_ZdlPv   _Znwm   __cxa_throw   __cxa_begin_catch   _ZSt9terminatev
_ZNKSt6__ndk121__basic_string_commonILb1EE20__throw_length_errorEv
```

Bez hidden visibility **nesmí** kompilátor předpokládat, že globální symbol je lokální
(kdokoliv by ho mohl interponovat), takže každé takové volání generuje:

```asm
bl  plt_stub          ; místo: bl  real_target
; plt_stub: adrp x16, GOT ; ldr x17,[x16,#off] ; add x16,… ; br x17
```

= +2–3 instrukce, extra load z paměti, riziko branch mispredict a tlak na i-cache/BTB.

**Náprava:** stejná jako u #1 (`-fvisibility=hidden`). Kompilátor pak vygeneruje přímé `bl`.

---

### 🟠 #3 – Zalinkovaná celá C++ locale/iostream mašinérie **[sibling]**

V exportech i v `.text` se nachází kompletní `<locale>`/`<iostream>` infrastruktura:
`moneypunct`, `numpunct_byname`, `messages`, `codecvt_utf8_utf16`, `time_get_c_storage`,
`num_put`, `basic_istream::sync` a `wxLocale::InitLanguagesDB` (13 KiB v jednom kuse).

Na Androidu je locale DB prakticky nevyužitá – jde o klasický „iostreams bloat“.

**Náprava:** nahradit `std::stringstream`/`std::locale`/`operator<<` za `fmt::format`
nebo `std::to_string`; odstranit wx locale z Android buildu.

---

### 🟠 #4 – glslang + SPIR-V + glad loader ≈ 1.47 MB kódu **[sibling]**

Z mapy 7.72 MiB `.text` nestripnuté varianty podle jmenných prostorů:

| Skupina | Velikost | % `.text` |
|---|---:|---:|
| glslang (GLSL parser/kompilátor) | 1 019 KiB | **12.9 %** |
| fmt / std / libc++ | 935 KiB | 11.8 % |
| ImGui / ImFont | 404 KiB | 5.1 % |
| glad (GL entry-point loader) | 333 KiB | 4.2 % |
| audio (dr_flac, drwav, …) | 152 KiB | 1.9 % |
| png / jpeg | 141 KiB | 1.8 % |
| SPIRV | 117 KiB | 1.5 % |
| zlib / lzma | 100 KiB | 1.3 % |
| wxWidgets | 25 KiB | 0.3 % |

Největší jednotlivé funkce:

| Funkce | Velikost |
|---|---:|
| `gladLoadGL` | **235 KiB** |
| `yyparse(glslang::TParseContext*)` | 114 KiB |
| `IPUWorker()` | 70 KiB |
| `glslang::TBuiltIns::identifyBuiltIns(...)` | 68 KiB |
| `gladLoadGLLoader` | 63 KiB |
| `GSApp::Init()` | 32 KiB |
| `drflac__decode_samples_with_residual__rice__scalar` | 16 KiB |
| `drflac__decode_samples_with_residual__rice__neon` | 14 KiB |

**Náprava:**
- **glslang/SPIRV** – pokud se používá jen pro překlad fixed-function shaderů, předkompilovat
  shader cache do assetů a kompilátor z buildu vyřadit (největší jednotlivá úspora).
- **glad** – pro GLES-only target nechat vygenerovat jen `gladLoadGLES2` (ušetří ~300 KiB);
  `gladLoadGL`/`gladLoadGLLoader` jsou na Tegra X1 mrtvý kód.
- **cold code** (`glslang`, `glad`, `ImGui`, `lzma`, `png`) kompilovat `-Os`/`-Oz`,
  hot path (recompilery, VU, GS) `-O3`.

---

### 🟡 #5 – Obě varianty dr_flac (scalar + NEON) **[sibling]**

`drflac__decode_samples_with_residual__rice__scalar` (16 KiB) i `..._neon` (14 KiB) jsou
v binárce zároveň. Na arm64 je scalar varianta mrtvý kód.

**Náprava:** vynutit pouze NEON větev (`-DDR_FLAC_NO_SCALAR_FALLBACK` nebo obdobné makro).

---

### 🟡 #6 – Unwind/exception tabulky: 703 KiB (5.9 % souboru)

`.eh_frame` 472 KiB + `.eh_frame_hdr` 113 KiB + `.gcc_except_table` 118 KiB.
Na AArch64 přidává clang unwind tabulky implicitně.

**Náprava:** pokud se v dané komponentě nepoužívají výjimky, `-fno-exceptions -fno-unwind-tables`
(pozor: bez `.eh_frame` přestane fungovat Android crash unwinding – aplikovat jen selektivně,
např. na C části a third-party knihovny).

---

### 🟡 #7 – `.bss` zabírá 187.4 MiB virtuální paměti

`0xbb306c8` bajtů. Jde o demand-zero stránky, takže reálná RAM se alokuje až při zápisu,
ale na zařízení s 2–3 GB RAM (Tegra X1) je to riziko a zhoršuje to TLB/VM pressure.

**Náprava:** projít velké statické pole (pravděpodobně recompiler code cache, GS buffery)
a převést je na `mmap`/`malloc` alokované podle potřeby.

---

### 🟡 #8 – Žádné známky LTO

24 658 funkcí, průměrně 328 B na funkci **[sibling]** – typický obraz buildu bez
cross-TU inlinování. 1 635 exportovaných symbolů (nález #1) navíc celoprogramovou
optimalizaci aktivně blokuje: linker musí každý z nich považovat za „může být použit zvnějšku“.

**Náprava:**

```cmake
set(CMAKE_INTERPROCEDURAL_OPTIMIZATION TRUE)          # nebo -flto=thin
target_link_options(... PRIVATE "-Wl,--lto-O3" "-Wl,--gc-sections")
set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -ffunction-sections -fdata-sections")
```

Pořadí doporučuji: **nejdřív #1 → pak LTO → pak `--gc-sections`**, jinak linker nemá co vyhazovat.

---

### 🟡 #9 – 2 720 relokací vyžadujících symbol lookup při startu

Z 21 655 relokací v `.rela.dyn`:

| Typ | Počet | Cena |
|---|---:|---|
| `R_AARCH64_RELATIVE` | 18 935 | levné (jen přičtení báze) |
| `R_AARCH64_ABS64` | 2 511 | **drahé** – lookup + zápis 8 B |
| `R_AARCH64_JUMP_SLOT` | 685 | drahé |
| `R_AARCH64_GLOB_DAT` | 209 | drahé |

2 405 z těch „drahých“ jde odstranit hidden visibility (viz #1) – každá ušetřená
relokace = rychlejší `dlopen()`.

---

### ⚪ #10 – Zastaralý build-id v „baked“ souboru

`libemucore_4248_baked.so` se liší od `4248/arm64-v8a/libemucore.so` v **203 bajtech**
(stejná velikost souboru, stejné `.text`), ale má **identický build-id**
`2b4fe70f…`. Build-id se po patchi nepřepočítal.

**Důsledek:** debugger/profiler (simpleperf, `addr2line`) může k binárce přiřadit
špatné symboly. **Náprava:** po „baking“ patchi znovu vygenerovat build-id
(`llvm-strip --strip-debug` nepomůže – je potřeba relink nebo přepsání `.note.gnu.build-id`).

---

## 3. Co je naopak v pořádku ✅

- `BIND_NOW` + `FLAGS_1 NOW` + úplný `GNU_RELRO` (0x3a598) – GOT je read-only po startu.
- Binárka je stripnutá (žádné `.symtab`/`.debug_*`) – 11.6 MiB místo 18.4 MiB.
- Align 0x10000 – připraveno na 16K stránky (Android 15+).
- NEEDED seznam je minimální (8 knihoven), žádná nadbytečná závislost.
- Žádný `TEXTREL`, žádný executable stack (`GNU_STACK` RW).

---

## 4. Co bych potřeboval k realizaci

Všechny výše uvedené nápravy jsou **build-time** změny. Abych je mohl aplikovat a změřit:

1. **Zdrojové kódy** – odkaz na PCSX2/AetherSX2 fork + konkrétní tag/konfiguraci,
   ze které vznikl build 4248 (build-id `2b4fe70f…`).
2. **Android NDK** (r25b, aby seděl toolchain) – v tomto sandboxu není a přes allowlist
   ho stáhnout nejde.
3. **Profil** z reálného zařízení (`simpleperf` / perfetto) – bez něj optimalizuju velikost,
   nikoliv skutečná horká místa. Statická analýza neřekne, co žere FPS.
4. Případně **výkonnější sandbox** (8+ jader, 16+ GB RAM) na rebuild a na Ghidru, pokud
   chcete i hloubkovou RE analýzu konkrétních funkcí.

---

## 5. Reprodukce měření

```bash
F=4248/arm64-v8a/libemucore.so
readelf -h "$F"                 # architektura
readelf -n "$F" | grep -A1 'Build ID'
readelf -S -W "$F"              # sekce
readelf -d "$F"                 # NEEDED, FLAGS, RELACOUNT
readelf --dyn-syms -W "$F"      # exporty
readelf -r -W "$F"              # relokace

# nestripnutá varianta – jmenná mapa kódu
nm -SC --defined-only --size-sort -r libemucore.so | head -40
```
