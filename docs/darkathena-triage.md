# DarkAthena.exe — proč nejde spustit (triage 2026-10-26)

Soubor: `DarkAthena.exe`, 5 140 336 B,
sha256 `27adac97c5f59612c899c8fac614f6a29fe60f4620bcb9a8fa5889eda712556f`
Verze z resources: Starbreeze Studios, *The Chronicles of Riddick —
Assault on Dark Athena*, FileVersion 1.0.0.1, linker timestamp 2009,
PDB `s:\Source\PBHD_PC\...\DarkAthena.pdb`. Soubor **není poškozený**.

## Zjištění: EXE je zabalené ochranou Tages/SolidShield

Důkazy ze statické analýzy (pefile):

- Sekce `.text`, `.rdata`, `.data`, `.tls` mají **raw size 0** —
  vlastní kód a data hry v souboru vůbec nejsou; jsou zašifrované
  v **overlayi (4 810 096 B)** za poslední sekcí.
- Entry point leží v miniaturní stub sekci `.init` (RWX) — startuje
  dekryptor ochrany, ne hra.
- Importní tabulka je návnada: z každé DLL přesně **1 funkce**;
  skutečné importy si ochrana řeší až za běhu.
- Importuje **`dvm.dll!VMCALL`** — komponenta Tages/SolidShield
  („driver VM"), komunikuje s kernelovým ovladačem ochrany a řeší
  aktivace. To je jednoznačný otisk této ochrany (retail Dark Athena
  je Tagesem historicky známá).
- Soubor je podepsaný (Security directory 5 360 B), manifest je
  v pořádku (asInvoker vykomentovaný) — problém není v oprávněních.

## Proč to nejde spustit

- **Ve Wine (autorun):** Tages potřebuje nainstalovat a spustit
  Windows **kernel-mode ovladač** a službu. Wine tohle neumí —
  stub umře dřív, než se hra vůbec dešifruje. Žádný winetricks ani
  DLL override to neopraví.
- **Na moderních Windows:** ovladače Tagesu jsou na Win10/11
  nefunkční (podpisy/podpora) a aktivační infrastruktura je dávno
  za zenitem — retail build je prakticky mrtvý i tam.

## Dá se to opatchovat jako Vampire?

Ne. U Vampire byl problém v logice hry samotné. Tady je samotné
tělo hry zašifrované VM ochranou napojenou na ovladač v jádře —
„oprava" by znamenala prolomit DRM (unpacking SolidShield VM),
což dělat nebudu a ani to není realistické záplatou na bajty.

## Praktická cesta

Použít **GOG verzi** *Assault on Dark Athena* — prodává se bez DRM,
její `DarkAthena.exe` je čisté a pod Wine běžně funguje. Do prefixu
pak typicky patří DirectX 9 (`d3dx9`) a legacy PhysX (winetricks
`physx`), protože hra používá softwarový PhysX. Po nahrání GOG
EXE sem do repa ho projdu stejně jako Vampire (ověřit build,
závislosti, případné portable záplaty).
