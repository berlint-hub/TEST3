# `assets_4248` — dá se tu něco vylepšit?

*Zapsáno 2026-10-24. Otázka uživatele k adresáři `assets_4248`
(81 souborů, 5,9 MB, v repu od commitu `5defa08`).*

**Krátká odpověď: skoro ne.** Jediná výkonnostně živá část jsou GLSL
shadery — a ty jsou upstream PCSX2, permutačně ořezávané při kompilaci,
a naměřené bottlenecky (kopie, bariéry, acquire) v nich nevznikají.
Zbytek je studená data nebo na Horizonu mrtvá váha po Androidu.

---

## 1. Co to je a odkud se to bere za běhu

`assets_4248` je strom `assets/` vytažený z APK buildu 4248. Na Switchi
se tytéž soubory používají živě z SD karty:

```
RESOURCES_DIR = DATA_ROOT "/resources"  =  /switch/nethersx2/resources
(source/config.h:34-35 ve forku)
```

Fork je jádru servíruje přes JNI shim (`source/filehelper.c:8`:
*„resources (shaders, GameIndex.yaml, fonts) from RESOURCES_DIR"*) a
Deko3D backend je čte přímo (`read_resource()`, `dk_device.cpp:23`;
chybějící soubor = výjimka `Missing shader resource`).

Úprava souboru v tomto repu tedy sama o sobě nic nenasadí — platí až po
překopírování do `/switch/nethersx2/resources/` se zachováním struktury
a jmen entry pointů.

## 2. Inventura podle toho, kdo to za běhu skutečně čte

Důkazy: řetězce v `libemucore.so` (počet výskytů) + grep ve forku.

| položka | velikost | čte | evidence |
|---|---|---|---|
| `shaders/vulkan/*.glsl` | ~70 KB | **jádro** (GS Vulkan renderer, kompilace do SPIR-V za běhu) | `shaders/vulkan/tfx.glsl` ×2 v jádře |
| `shaders/opengl/*.glsl` | ~110 KB | **fork Deko3D** (`dk_device.cpp:415-420…`) + jádro při GL backendu | `read_resource("shaders/opengl/tfx_fs.glsl")`; `shaders/opengl` ×16 v jádře |
| `shaders/common/{ffx_a.h,ffx_cas.h,fxaa.fx}` | 244 KB | includy obou cest (fork je inlinuje, `dk_device.cpp:231-235`) | — |
| `GameIndex.yaml` | 1,85 MB | **jádro** při načtení hry | `GameIndex.yaml` ×1 |
| `cheats_ws.zip` / `cheats_ni.zip` | 1,92 MB | **jádro** (widescreen / no-interlacing pnach) | `cheats_ws` ×4, `cheats_ni` ×4; uvnitř 4181 + 647 .pnach |
| `fonts/` (Roboto, fa-solid) | 592 KB | **jádro** (OSD/overlay) | `Roboto` ×2, `fa-solid` ×1 |
| `sounds/achievements/*.wav` | 192 KB | **jádro** (achievementy) | `unlock.wav` ×1 |
| `shaders/dx11/*` | ~60 KB | **nikdo** (DirectX 11 na Switchi neexistuje) | — |
| `dexopt/*.prof(m)` | 4,5 KB | **nikdo** (profily Android ART) | `dexopt` ×0 |
| `3rdparty.html`, `faq.html` | 104 KB | **nikdo** (WebView Android frontendu) | `3rdparty.html` ×0 |
| `icons/` (vlajky, AppIcon) | 248 KB | **nikdo** na NX (Android frontend) | `icons/flags` ×0 |
| `game_controller_db.txt` | 586 KB | **nikdo** na NX (SDL mapování Android frontendu) | ×0 v jádře i ve forku/launcheru |

## 3. Shadery — jediná horká plocha, a už je ořezaná

Hlavní GS fragment shader (`tfx_fs.glsl`, 1010 řádků; vulkan `tfx.glsl`
1302) se nekompiluje „celý". Jádro i fork před něj vkládají hlavičku s
permutací — desítky direktiv `PS_TEX_FMT`, `PS_BLEND_HW`, `PS_DATE`,
`PS_LTF`, `PS_ATST`, `PS_CHANNEL_FETCH`… (fork: `dk_device.cpp:237-251`,
cachuje se per `soubor|entry|stage|defines`). Nepoužité cesty tedy ve
výsledném shaderu vůbec nejsou; ruční „odlehčení" mazáním větví by
duplikovalo to, co už dělá preprocesor.

Co jsem v shaderech hledal a nenašel jako bezpečný zisk:

- **Přesnost:** nikde není zbytečné `precision highp` navíc; jde o
  desktopové GLSL 450 (FP32). Explicitní `highp` je jen u uint konverzí,
  kde je potřeba. Komentáře upstreamu varují, že snížení přesnosti láme
  konkrétní hry (`convert.glsl:65` Spider-Man 3, Dogs Life;
  `tfx_fs.glsl:171` Xenosaga). Jestli by GM20B z FP16 vůbec těžila,
  staticky prokázat nejde — záleží na tom, co s tím udělá glslang→SPIR-V
  a NVK/Deko3D kompilátor; bez profilování na zařízení je to spekulace.
- **Texturování:** manuální bilineární filtrování indexovaných textur
  (`sample_4_index`, 4 fetch patche) existuje kvůli korektnosti —
  komentář výslovně: *„texture gather can't be used because of special
  clamping/wrapping"*. Zjednodušení = vizuální artefakty.
- **Kopie:** `convert.glsl` (`ps_copy` aj.) je triviální 1 fetch →
  1 zápis. Forkem naměřená cena kopií (67,3/snímek v závěru závodu) je
  šířka pásma + synchronizace, ne ALU. Kopie vznikají vzorci používání
  render targetů v jádře; fork je už řeší nastaveními
  (`UserHacks_TextureInsideRt`, `OverrideTextureBarriers`), ne shaderem.

Jediné reálně pohnutelné kvalitativní kompromisy (FXAA z `common/fxaa.fx`,
CAS z `ffx_cas.h`) jsou post-procesy, které jdou v menu prostě vypnout —
fork navíc u FXAA opravil mrtvý ini klíč (`4c78d90`), takže vypnutí
konečně funguje. Sahat do jejich zdrojáků nedává oproti vypnutí nic navíc.

**Závěr pro shadery: žádné prokazatelné zlepšení tu bez zařízení
nenavrhnu.** Kdyby existovalo per-shader profilování z GT3 při 2×,
dalo by se cílit; fork ale měří režii na úrovni kopií/bariér/acquire
a tam fragment ALU jako viník nefiguruje.

## 4. Data — živá, ale studená

- **GameIndex.yaml:** jádro ho parsuje, ale pro GT3 (`SCUS-97102`)
  obsahuje jen `compat: 5` — žádné gameFixes ani gsHWFixes. Přidat
  vlastní záznam (např. skipdraw) lze, jenže totéž umí launcher per-game
  nastavením a patří to upstreamu. Ořezání YAML jen na vlastněné hry by
  zkrátilo parsování při startu hry; fork naměřil SD I/O za jízdy
  0,6–0,8 ms (žádné záseky), takže to není měřený problém.
- **cheats_ni.zip** (no-interlacing, 647 her): zapnutí pro podporovanou
  hru může ušetřit deinterlace pass — to je ale uživatelské nastavení
  v jádře, ne úprava souboru.
- **cheats_ws.zip** (4181 widescreen patchů): čistě vizuální, výkonově
  neutrální až mírně negativní (víc vykreslované plochy).

## 5. Mrtvá váha — jediná bezriziková „optimalizace"

Na Horizonu se nikdy neotevře (evidence v §2):

```
shaders/dx11/*          ~60 KB   DirectX
dexopt/*                  4 KB   Android ART
3rdparty.html, faq.html 104 KB   Android WebView
game_controller_db.txt  586 KB   Android SDL frontend
icons/*                 248 KB   Android frontend
                              ≈ 1,0 MB z 5,9 MB
```

Smazání z SD karty je bezpečné jen u položek, které nečte nikdo —
pozor: chybějící shader hází výjimku a jádro bez GameIndex/cheats přijde
o funkce. Přínos je ~1 MB a o něco rychlejší prvotní kopírování na kartu.
**Žádný FPS přínos netvrdím.**

## 6. Verdikt

| část | vylepšitelnost |
|---|---|
| `shaders/vulkan` + `shaders/opengl` + `common` | živé a horké, ale upstream-optimální; bez profilu ze zařízení žádná poctivá úprava |
| `GameIndex.yaml`, `cheats_*.zip` | funkční data; případné zásahy patří do nastavení, ne do souborů |
| `fonts`, `sounds` | OSD/achievementy; výkonově neutrální |
| dx11, dexopt, html, icons, game_controller_db | mrtvé; smazatelné (~1 MB), bez vlivu na FPS |

Skutečné páky tedy zůstávají tam, kde byly: nastavení ve forku
(`OverrideTextureBarriers`, low-latency cesta dle reportu §13.3) —
ne v assetech.
