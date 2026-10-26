# DarkAthena.exe + dvm.dll — proč nejde spustit (triage)

Soubory od uživatele (GOG verze hry):

- `DarkAthena.exe`, 5 140 336 B,
  sha256 `27adac97c5f59612c899c8fac614f6a29fe60f4620bcb9a8fa5889eda712556f`
  — Starbreeze 1.0.0.1, RTM 2009, zabalené Tages/SolidShield
  (sekce s kódem raw size 0, 4,8 MB šifrovaný overlay, stub `.init`,
  návnadové importy vč. `dvm.dll!VMCALL`). Takhle vypadá EXE
  ve všech edicích včetně GOG — DRM-free z ní dělá až `dvm.dll`.
- `dvm.dll`, 72 848 B,
  sha256 `ca8fe8d6f44f7503735d7a664e3809254ba120a8b306a6fd180a5f467f62661a`

## Nález k dvm.dll: je to pravá, nepoškozená GOG kopie

- Hash souboru **sedí bajt na bajt** s `dvm.dll` z originálních
  GOG instalací — na GOG fóru k téhle hře lidé řešili, že jim
  Norton/Kaspersky soubor mažou, a odkazovali VirusTotal analýzu
  přesně tohoto sha256 (15/42 detekcí, klasický false positive) [1].
  Soubor uživatele je tedy kompletní a správný.
- Struktura: nepodepsaná DLL bez version info, jediný export
  `VMCALL`, sekce `.RLD0`/`.RLD1` (RWX, zabalené) a overlay
  s hlavičkou `RLD!` (30 352 B). GOG skutečně distribuovala
  emulátor postavený na wrapperu skupiny RELOADED — proto ji
  antiviry dodnes mažou.
- Chování při načtení (z importů a kódu): `DllMain` si přes
  `GetModuleFileNameA`+`CreateFileA`+`ReadFile` **přečte sama sebe
  z disku**, rozbalí payload z overlaye do alokované paměti,
  export `VMCALL` v `.data` ukáže na VM dispečer (0x10001580)
  a volání ochrany obslouží **čistě v user-mode** — žádné importy
  pro služby/ovladače (`ADVAPI32`, `CreateService`,
  `DeviceIoControl`) v DLL vůbec nejsou; chyby hlásí přes
  `MessageBoxA` a ukončí proces (`ExitProcess`).

## Závěr: dvojice EXE+dvm.dll je v pořádku — hledej v prostředí

1. **Pro jistotu Ověřit/opravit v GOG Galaxy** (nebo přeinstalace
   z offline instalátoru) — pak je sada souborů garantovaně
   konzistentní a žádný soubor nechybí (`MSystem.dll`, `MCCDyn.dll`,
   `RndrGL.dll` ap. musí ležet u EXE v `System\Win32_x86\`).
2. **Antivirus nesmí `dvm.dll` smazat** při instalaci/kopírování —
   výjimka na složku hry [1][3]. (Ve Wine problém není, ale pokud
   se hra připravuje pod Windows, je to past č. 1.)
3. **Závislosti Wine prefixu** — hra (Starbreeze engine) potřebuje
   mj. **legacy PhysX** (winetricks `physx`) a DirectX 9 runtime
   (`d3dx9`); chybějící PhysX je u Dark Athena klasický důvod,
   proč proces po startu tiše zemře.
4. **Diagnostika z terminálu**: jednou spustit přímo
   `wine DarkAthena.exe` ze složky `System\Win32_x86\` a zachytit
   výpis — loader tam jmenovitě vypíše chybějící DLL a objeví se
   i případný `MessageBox` z `dvm.dll`, který ve frontendovém
   rozhraní nemusí být vidět.
5. Okrajově: cesta ke hře bez diakritiky (DLL pracuje s ANSI
   cestami při čtení sama sebe).

## Zdroje

- [1] GOG fórum — mazání dvm.dll antivirem + VirusTotal odkaz
  se sha256 shodným se souborem uživatele:
  https://www.gog.com/forum/chronicles_of_riddick_the/norton_security_suite_v_kaspersky/post2
- [3] GOG Support — „insert CD" po smazání/nahrazení dvm.dll:
  https://support.gog.com/hc/en-us/articles/212453089-The-Chronicles-of-Riddick-Assault-on-Dark-Athena-insert-CD-error
- PCGamingWiki — DRM jednotlivých edic (GOG = DRM-free):
  https://www.pcgamingwiki.com/wiki/The_Chronicles_of_Riddick:_Assault_on_Dark_Athena
- ProtonDB — běh s GOG soubory ve Wine/Protonu:
  https://www.protondb.com/app/9860
