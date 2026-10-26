# DarkAthena.exe — proč nejde spustit (triage, opravená verze)

Soubor: `DarkAthena.exe`, 5 140 336 B,
sha256 `27adac97c5f59612c899c8fac614f6a29fe60f4620bcb9a8fa5889eda712556f`
Starbreeze, FileVersion 1.0.0.1, RTM 2009. Soubor **není poškozený**.

## Co EXE obsahuje (statická analýza)

- Sekce `.text`, `.rdata`, `.data`, `.tls` mají **raw size 0** —
  kód a data hry jsou zašifrované v **overlayi (4 810 096 B)**.
- Entry point v miniaturní RWX sekci `.init` (stub ochrany),
  importy jsou návnada (1 funkce z každé DLL),
  mezi nimi **`dvm.dll!VMCALL`** = Tages/SolidShield.
- Žádné GOG řetězce, podpis je původní vydavatelský řetěz
  (VeriSign 2004). **Ze samotného EXE nelze poznat retail vs. GOG** —
  obě edice sdílí stejně zabalené EXE.

## Klíč: rozhoduje soubor `dvm.dll` vedle EXE (System\Win32_x86)

GOG edice je vedená jako DRM-free, přesto obsahuje stejně
zabalené EXE [4]. Trik je v tom, že GOG ke hře přibalila
**zneškodněnou variantu `dvm.dll`**, se kterou ochrana projde bez
ovladače i aktivace. Podpora GOG doslova rozlišuje „TAGES-enabled
dvm.dll" vs. tu jejich a varuje, že typický problém je smazání
`dvm.dll` antivirem (známý false positive) [7]. Se správnou
(GOG) `dvm.dll` hra běží i ve Wine/Protonu [2].

Protože je `dvm.dll` v EXE normální (ne delay) import, **bez ní
proces vůbec nenastartuje** — přesně odpovídá „nejde to spustit".

## Co zkontrolovat (v tomto pořadí)

1. Existuje ve složce hry (`System\Win32_x86\`, vedle EXE) soubor
   `dvm.dll`? Pokud ne → přeinstalovat z GOG instalátoru, zkontrolovat
   karanténu antiviru a přidat výjimku. (Přítomnost `TagesClient.*`
   naopak značí plnotučnou Tages instalaci.)
2. Je `dvm.dll` ta GOGí? (lze ověřit analýzou souboru — velikost,
   podpis, řetězce; stačí ho sem nahrát stejně jako EXE)
3. Když dvm sedí a pořád nic: závislosti prefixu — legacy PhysX
   (winetricks `physx`), `d3dx9`, případně MSVC runtimes; a správné
   rozložení souborů (engínové DLL `MSystem.dll`, `MCCDyn.dll` ap.
   musí být u EXE).

## Co dál neumíme/nebudeme

Plnohodnotný Tages (retail `dvm.dll` + kernel ovladač) ve Wine
nerozjedeš a obal ochrany nebudu prolamovat. Cílem je dostat do hry
její vlastní, legální GOG `dvm.dll` — ta běží v user-mode a Wine
si s ní poradí.

## Zdroje

- [4] PCGamingWiki — dostupnost/DRM jednotlivých edic:
  https://www.pcgamingwiki.com/wiki/The_Chronicles_of_Riddick:_Assault_on_Dark_Athena
- [7] GOG Support — „insert CD" chyba po smazání dvm.dll antivirem:
  https://support.gog.com/hc/en-us/articles/212453089-The-Chronicles-of-Riddick-Assault-on-Dark-Athena-insert-CD-error
- [2] ProtonDB — běh s GOG soubory vč. dvm.dll:
  https://www.protondb.com/app/9860
