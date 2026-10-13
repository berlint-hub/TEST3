# Jak postavit launcher (`NetherSX2.nro`)

Launcher je **samostatná homebrew aplikace**, ne součást emulátoru. Emulátor
(`NetherSX2_nx_vk.nro`) se do něj **zabalí do RomFS**, spolu s jádry. Proto se
launcher builduje **až po** emulátoru — bez hotového `.nro` emulátoru nemá co
zabalit.

```
NetherSX2.nro            ← launcher (tohle instaluješ na SD)
└── romfs/
    ├── emu/NetherSX2_nx_vk.nro     ← emulátor
    ├── cores/emucore_4248.so       ← jádro
    ├── logo.png, bios-cover.png, forwarder-icon.jpg   (v gitu)
    └── res/                         (generované, před buildem se maže)
```

---

## 1. Doporučená cesta: `build_all.sh`

```sh
CORES=4248 RENDERERS=VK MESA_FLAVOR=nxvk ./build_all.sh
```

Skript udělá čtyři fáze ve správném pořadí:

### 1a. Storage závislosti (CMake + Ninja)

```sh
cmake -S launcher/dependencies \
      -B launcher/dependencies/build \
      -G Ninja \
      -DCMAKE_TOOLCHAIN_FILE="$DEVKITPRO/cmake/Switch.cmake" \
      -DCMAKE_BUILD_TYPE=Release
cmake --build launcher/dependencies/build --parallel "$JOBS"
```

- Stahuje **libsmb2** a **libusbhsfs** přes FetchContent.
- **Offline build:** nastav `LIBSMB2_SOURCE` / `LIBUSBHSFS_SOURCE` na lokální
  cestu → skript je předá jako `-DFETCHCONTENT_SOURCE_DIR_*`.
- Skript **smaže** `dependencies/build`, pokud v něm leží `CMakeCache.txt` od
  jiného generátoru než Ninja. Jinak by CMake odmítl pokračovat.
- `launcher/dependencies/` obsahuje tři patche pro libusbhsfs
  (`0001-add-uasp-transport-hooks`, `0002-fallback-to-bot-interface`,
  `0003-cleanup-after-uasp-reset`) a `usbhsfs_uasp.c/.h`.

### 1b. Emulátor (musí být hotový dřív)

```sh
make clean TARGET=NetherSX2_nx
make -j"$JOBS" RENDERER=VK TARGET=NetherSX2_nx
cp -f NetherSX2_nx.nro NetherSX2_nx_vk.nro
```

**`TARGET=NetherSX2_nx` je povinné.** `Makefile` má
`TARGET := $(notdir $(CURDIR))`, takže checkout pojmenovaný jinak vyrobí
`<jmeno-adresare>.nro` a další krok spadne na
`cp: cannot stat 'NetherSX2_nx.nro'`. Tohle už jeden build stálo.

### 1c. Sbalení do RomFS

```sh
rm -rf launcher/romfs/cores launcher/romfs/emu launcher/romfs/res
mkdir -p launcher/romfs/cores launcher/romfs/emu

cp -f "$CORES_DIR/NetherSX2-v2.2n-4248/lib/arm64-v8a/libemucore.so" \
      launcher/romfs/cores/emucore_4248.so
cp -f NetherSX2_nx_vk.nro launcher/romfs/emu/NetherSX2_nx_vk.nro
```

**Ten `rm -rf` na začátku je záměrný.** Bez něj by předchozí full build nechal
v RomFS staré jádro nebo starý `.nro` a launcher by nabízel payload, který se
ve skutečnosti nebuildoval.

### 1d. Forwarder stub + build launcheru

```sh
# forwarder stub, builduje se in-tree z launcher/fwd/
make -C launcher/fwd clean
make -j"$JOBS" -C launcher/fwd

# launcher (v logu jako "launcher (SDL2 addon)")
cd launcher
make clean
make -j"$JOBS" ONLY_CORE_4248=1 VULKAN_ONLY=1
cd ..

mv -f launcher/NetherSX2.nro NetherSX2.nro
rm -f NetherSX2_nx.nro NetherSX2_nx_vk.nro NetherSX2_nx_gl.nro
```

Výstup: `launcher/NetherSX2.nro` → přesunuto do kořene jako `NetherSX2.nro`,
mezivýstupy emulátoru se mažou.

V logu to poznáš podle:

```
Writing .../launcher/romfs/emu/NetherSX2_nx_vk.nro to RomFS image...
built ... NetherSX2.nro
```

---

## 2. Co launcher linkuje

Z `launcher/Makefile`:

| Položka | Hodnota |
|---|---|
| `TARGET` (ř. 16) | `NetherSX2` — **pevně dané**, ne z `$(notdir $(CURDIR))` |
| `SOURCES` (ř. 18) | `source ../source/switch` — **sdílí kód s hlavním stromem** |
| `INCLUDES` (ř. 20) | `include ../source/switch` |
| `ROMFS` (ř. 23) | `romfs` |
| `APP_TITLE` (ř. 25) | `NetherSX2` |
| `CXXFLAGS` (ř. 53) | `-fno-rtti -std=gnu++20` |
| `LIBS` (ř. 64) | `$(STORAGE_LIBS)` + pkg-config + `-lturbojpeg -lz -lGLESv2 -lnx` |
| `LIBDIRS` (ř. 67) | `$(PORTLIBS) $(LIBNX)` |

`STORAGE_LIBS` (ř. 61–63) ukazuje na výstup z kroku 1a plus portlib:

```
launcher/dependencies/build/_deps/libsmb2-build/lib/libsmb2.a
$(PORTLIBS)/lib/libntfs-3g.a
```

**`-lGLESv2` vyžaduje portlib `switch-mesa`.** Bez něj launcher nezlinkuje, i
když sám nic nevykresluje přes GL.

`CFLAGS` obsahují `-O3 -DNDEBUG $(LTOFLAGS)` a `-D__SWITCH__ -D_GNU_SOURCE
-D_LARGEFILE64_SOURCE -D_FILE_OFFSET_BITS=64`.

### Definice přepínačů — **nejsou** napevno

`launcher/Makefile` ř. 39 a 42 přidávají `-DONLY_CORE_4248` a `-DVULKAN_ONLY`, ale
**podmíněně**, podle make proměnných. `build_all.sh` ř. 160–163 je nastavuje z
`CORES` / `RENDERERS`:

```sh
launcher_vars=()
[[ "$CORES" == "4248" ]]   && launcher_vars+=(ONLY_CORE_4248=1)
[[ "$RENDERERS" == "VK" ]] && launcher_vars+=(VULKAN_ONLY=1)
[[ -n "${RELEASE_VERSION:-}" ]] && launcher_vars+=(RELEASE_VERSION="$RELEASE_VERSION")
make -j"$JOBS" ${launcher_vars[@]+"${launcher_vars[@]}"}
```

Takže launcher schová položky menu pro payloady, které se nesbalily. Při ručním
buildu je **musíš předat sám**, jinak launcher nabídne 3668 a OpenGL, které
v RomFS nejsou.

### RomFS a ikona

```make
ifneq (,$(findstring $(TARGET).jpg,$(icons)))
    export APP_ICON := $(TOPDIR)/$(TARGET).jpg     # ř. 105 → launcher/NetherSX2.jpg
endif
ifneq (,$(strip $(ROMFS)))
    export NROFLAGS += --romfsdir=$(CURDIR)/$(ROMFS)   # ř. 124
endif
```

`SwitchStorageBridge.cpp` je z `CPPFILES` **vyfiltrovaný** (ř. 82) — nekompiluje
se do launcheru.

---

## 3. Když chceš buildovat launcher ručně

Pořadí je závazné. `CORES_DIR` má v `build_all.sh` ř. 20 default **`$ROOT`**
(kořen repa), ne `cores/` — v CI se přepisuje na `$GITHUB_WORKSPACE/cores`.

```sh
# 0. proměnné
CORES_DIR="${CORES_DIR:-$PWD}"

# 1. storage závislosti
cmake -S launcher/dependencies -B launcher/dependencies/build -G Ninja \
      -DCMAKE_TOOLCHAIN_FILE="$DEVKITPRO/cmake/Switch.cmake" \
      -DCMAKE_BUILD_TYPE=Release
cmake --build launcher/dependencies/build --parallel 4

# 2. emulátor
make clean TARGET=NetherSX2_nx
make -j4 RENDERER=VK TARGET=NetherSX2_nx
cp -f NetherSX2_nx.nro NetherSX2_nx_vk.nro

# 3. zabalit do RomFS
rm -rf launcher/romfs/cores launcher/romfs/emu launcher/romfs/res
mkdir -p launcher/romfs/cores launcher/romfs/emu
cp -f "$CORES_DIR/NetherSX2-v2.2n-4248/lib/arm64-v8a/libemucore.so" \
      launcher/romfs/cores/emucore_4248.so
cp -f NetherSX2_nx_vk.nro launcher/romfs/emu/NetherSX2_nx_vk.nro

# 4. forwarder stub (build_all.sh ř. 154-156) — NEPŘESKOČIT
make -C launcher/fwd clean
make -j4 -C launcher/fwd

# 5. launcher (build_all.sh ř. 164-166)
cd launcher
make clean
make -j4 ONLY_CORE_4248=1 VULKAN_ONLY=1
cd ..

# 6. výsledek do kořene (build_all.sh ř. 168-169)
mv -f launcher/NetherSX2.nro NetherSX2.nro
rm -f NetherSX2_nx.nro NetherSX2_nx_vk.nro NetherSX2_nx_gl.nro
```

**Bez kroku 2 a 3 launcher sice zkompiluje, ale bude prázdný** — nabídne payload,
který v RomFS není. **Bez kroku 4** chybí forwarder stub z `launcher/fwd/`.

---

## 4. Pasti

| Past | Projev |
|---|---|
| Chybějící `TARGET=NetherSX2_nx` u emulátoru | `cp: cannot stat 'NetherSX2_nx.nro'` — build emulátoru přitom **projde** |
| Launcher buildnutý před emulátorem | Zkompiluje, ale RomFS je prázdný |
| Starý obsah `launcher/romfs/{cores,emu}` | Launcher nabídne jádro/payload z předchozího buildu |
| Chybějící `switch-mesa` portlib | Link spadne na `-lGLESv2` |
| `dependencies/build` od jiného generátoru | CMake odmítne pokračovat; `build_all.sh` to maže automaticky, ruční build ne |
| `NETHERSX2_VK_DIAGNOSTIC` | Patří **emulátoru**, ne launcheru. Launcher ho nečte. |

---

## 5. Kam s výsledkem

```
sdmc:/switch/NetherSX2.nro          ← launcher
sdmc:/switch/nethersx2/             ← data, logy
```

Launcher si jádro a emulátor vytáhne z vlastního RomFS, takže na SD **nemusíš**
kopírovat ani `emucore_4248.so`, ani `NetherSX2_nx_vk.nro` zvlášť.

Spouštět s **plným memory override**, ne v applet režimu.

---

## 6. Souvislosti

- Architektura portu, nxvk a build emulátoru: `NETHERSX2_SWITCH_PORT.md`
- Pitva selhání Vulkan bootu: `NETHERSX2_SWITCH_PORT.md`, část 4
- Tuning pro Tegra X1: `TEGRA_X1_TUNING.md`
