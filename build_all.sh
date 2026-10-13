#!/usr/bin/env bash
set -euo pipefail
export DEVKITPRO=${DEVKITPRO:-/opt/devkitpro}
export DEVKITARM=$DEVKITPRO/devkitARM
export DEVKITA64=$DEVKITPRO/devkitA64
JOBS=${JOBS:-18}
[[ "$JOBS" =~ ^[1-9][0-9]*$ ]] || { echo "JOBS must be a positive integer." >&2; exit 1; }

# What to bundle. Defaults keep the historical behaviour (both cores, both
# renderers); the CI release workflow narrows it down:
#   CORES=4248 RENDERERS=VK ./build_all.sh   -> Vulkan-only, single core
CORES="${CORES:-4248 3668}"
RENDERERS="${RENDERERS:-VK GL}"
# Vulkan driver archives to link: vendored (default), nxvk, or sdk.
MESA_FLAVOR="${MESA_FLAVOR:-vendored}"
export MESA_FLAVOR

APP="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$APP")"
CORES_DIR="${CORES_DIR:-$ROOT}"

required=()
for b in $CORES; do
  required+=(
    "$CORES_DIR/NetherSX2-v2.2n-$b/lib/arm64-v8a/libemucore.so"
    "$CORES_DIR/NetherSX2-v2.2n-$b/assets/GameIndex.yaml"
  )
done
wants_vulkan=no
for r in $RENDERERS; do [[ "$r" == "VK" ]] && wants_vulkan=yes; done
if [[ "$wants_vulkan" == yes ]]; then
  case "$MESA_FLAVOR" in
    nxvk)
      # PalindromicBreadLoaf/nxvk (Mesa 26.2.2 NVK for Tegra X1) installed as a
      # devkitPro portlib, or staged in NXVK_ROOT by its own `make`:
      #   lib/libnvk.a, lib/libnvk_support.a, lib/pkgconfig/nxvk.pc
      nxvk_lib="${NXVK_ROOT:-$DEVKITPRO/portlibs/switch}/lib"
      required+=("$nxvk_lib/libnvk.a" "$nxvk_lib/libnvk_support.a")
      ;;
    sdk)
      : "${MESA_SDK_ROOT:?MESA_FLAVOR=sdk requires MESA_SDK_ROOT}"
      required+=("$MESA_SDK_ROOT/include/vulkan/vulkan_core.h"
                 "$MESA_SDK_ROOT/include/EGL/egl.h"
                 "$MESA_SDK_ROOT/lib/libvulkan.a" "$MESA_SDK_ROOT/lib/libEGL.a")
      ;;
    *)
      if [[ -n "${MESA_SDK_ROOT:-}" ]]; then
        required+=("$MESA_SDK_ROOT/include/vulkan/vulkan_core.h"
                   "$MESA_SDK_ROOT/include/EGL/egl.h"
                   "$MESA_SDK_ROOT/lib/libvulkan.a" "$MESA_SDK_ROOT/lib/libEGL.a")
      else
        required+=("$APP/vulkan/include/vulkan/vulkan_core.h" "$APP/vulkan/lib/libnvk.a")
      fi
      ;;
  esac
fi
missing=0
for file in "${required[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "Missing build input: $file" >&2
    missing=1
  fi
done
if (( missing )); then
  # Naming the file alone is not enough to diagnose a bad core extraction, so
  # show what the core folder actually holds next to it.
  for b in $CORES; do
    d="$CORES_DIR/NetherSX2-v2.2n-$b"
    echo "--- contents of $d ---" >&2
    if [[ -d "$d" ]]; then find "$d" -maxdepth 3 | sort | head -40 >&2; else echo "(absent)" >&2; fi
  done
  exit 1
fi
command -v cmake >/dev/null || { echo "cmake is required." >&2; exit 1; }
command -v ninja >/dev/null || { echo "ninja is required." >&2; exit 1; }

DEPS_BUILD="$APP/launcher/dependencies/build"
if [[ -f "$DEPS_BUILD/CMakeCache.txt" ]] &&
   ! grep -q '^CMAKE_GENERATOR:INTERNAL=Ninja$' "$DEPS_BUILD/CMakeCache.txt"; then
  cmake -E rm -rf "$DEPS_BUILD"
fi

echo "==== launcher storage dependencies ===="
deps_args=(
  -S "$APP/launcher/dependencies"
  -B "$DEPS_BUILD"
  -G Ninja
  -DCMAKE_TOOLCHAIN_FILE="$DEVKITPRO/cmake/Switch.cmake"
  -DCMAKE_BUILD_TYPE=Release
)
if [[ -n "${LIBSMB2_SOURCE:-}" ]]; then
  deps_args+=( -DFETCHCONTENT_SOURCE_DIR_LIBSMB2="$LIBSMB2_SOURCE" )
fi
if [[ -n "${LIBUSBHSFS_SOURCE:-}" ]]; then
  deps_args+=( -DFETCHCONTENT_SOURCE_DIR_LIBUSBHSFS="$LIBUSBHSFS_SOURCE" )
fi
cmake "${deps_args[@]}"
cmake --build "$DEPS_BUILD" --parallel "$JOBS"

echo "==== emulator binaries ($RENDERERS, MESA_FLAVOR=$MESA_FLAVOR) ===="
cd "$APP"
for r in $RENDERERS; do
  echo "---- renderer: $r ----"
  # The Makefile defaults TARGET to $(notdir $(CURDIR)), so a checkout named
  # anything other than NetherSX2_nx produced <dirname>.nro and the cp below
  # failed. Pin it.
  emu_vars=(RENDERER="$r" TARGET=NetherSX2_nx)
  # NETHERSX2_VK_DIAGNOSTIC=1 turns on the on-device trace: every hooked
  # Vulkan call is written to /switch/nethersx2/nethersx2-vulkan.log, and a CPU
  # exception dumps pc/far/esr to nethersx2-exception.log. It fsyncs per line,
  # so it is a debugging aid, not something to ship.
  [[ -n "${NETHERSX2_VK_DIAGNOSTIC:-}" ]] && \
    emu_vars+=(NETHERSX2_VK_DIAGNOSTIC="$NETHERSX2_VK_DIAGNOSTIC")
  if [[ -n "${NETHERSX2_VK_DIAGNOSTIC:-}" ]]; then
    echo "!! diagnostic build: traces go to the SD card under /switch/nethersx2/"
    echo "     nethersx2-vulkan.log    every hooked Vulkan call (flushed per line)"
    echo "     nethersx2-exception.log CPU exception: pc/far/esr/sp/fp/lr"
    echo "     nethersx2-mesa.log      Mesa/NVK output via MESA_LOG_FILE"
  fi
  make clean TARGET=NetherSX2_nx >/dev/null 2>&1
  make -j"$JOBS" "${emu_vars[@]}"
  if [[ "$r" == "VK" ]]; then
    cp -f NetherSX2_nx.nro NetherSX2_nx_vk.nro
  else
    cp -f NetherSX2_nx.nro NetherSX2_nx_gl.nro
  fi
done

echo "==== bundle cores + emulator binaries into the launcher romfs ===="
# Wipe first: a previous full build would otherwise leave a stale core/nro in
# romfs and the launcher would happily offer a payload that is not shipped.
rm -rf "$APP/launcher/romfs/cores" "$APP/launcher/romfs/emu" "$APP/launcher/romfs/res"
mkdir -p "$APP/launcher/romfs/cores" "$APP/launcher/romfs/emu"
for b in $CORES; do
  cp -f "$CORES_DIR/NetherSX2-v2.2n-$b/lib/arm64-v8a/libemucore.so" \
        "$APP/launcher/romfs/cores/emucore_$b.so"
done
for r in $RENDERERS; do
  if [[ "$r" == "VK" ]]; then
    cp -f "$APP/NetherSX2_nx_vk.nro" "$APP/launcher/romfs/emu/NetherSX2_nx_vk.nro"
  else
    cp -f "$APP/NetherSX2_nx_gl.nro" "$APP/launcher/romfs/emu/NetherSX2_nx_gl.nro"
  fi
done

echo "==== bundle per-core resources into the launcher romfs ===="
for b in $CORES; do
  rd="$APP/launcher/romfs/res/$b"
  rm -rf "$rd"; mkdir -p "$rd"
  cp -rf "$CORES_DIR/NetherSX2-v2.2n-$b/assets/." "$rd/"
  rm -rf "$rd/dexopt"
done

echo "==== forwarder stub (built in-tree from launcher/fwd/) ===="
make -C "$APP/launcher/fwd" clean >/dev/null 2>&1
make -j"$JOBS" -C "$APP/launcher/fwd"

echo "==== launcher (SDL2 addon) ===="
# Hide menu entries for payloads that are not bundled (see launcher/Makefile).
launcher_vars=()
[[ "$CORES" == "4248" ]]     && launcher_vars+=(ONLY_CORE_4248=1)
[[ "$RENDERERS" == "VK" ]]   && launcher_vars+=(VULKAN_ONLY=1)
[[ -n "${RELEASE_VERSION:-}" ]] && launcher_vars+=(RELEASE_VERSION="$RELEASE_VERSION")
cd "$APP/launcher"
make clean >/dev/null 2>&1
make -j"$JOBS" ${launcher_vars[@]+"${launcher_vars[@]}"}

mv -f "$APP/launcher/NetherSX2.nro" "$APP/NetherSX2.nro"
rm -f "$APP/NetherSX2_nx.nro" "$APP/NetherSX2_nx_vk.nro" "$APP/NetherSX2_nx_gl.nro"

echo
echo "Done. The only file to copy:"
ls -la "$APP/NetherSX2.nro"
echo "Bundled cores: $CORES | renderers: $RENDERERS | MESA_FLAVOR: $MESA_FLAVOR"
echo
echo "SD layout: sdmc:/switch/NetherSX2.nro + sdmc:/switch/nethersx2/"
