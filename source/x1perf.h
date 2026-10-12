/* x1perf.h -- Tegra X1 (Nintendo Switch) performance control
 *
 * NetherSX2_nx -- NetherSX2 (AetherSX2 / PCSX2-lineage PS2 emulator) on the
 * Nintendo Switch via a libnx so-loader.
 *
 * Two independent knobs, both driven from nethersx2.ini:
 *
 *  1. CPU boost mode (apm / appletSetCpuBoostMode -- always available).
 *     IMPORTANT Switch quirk: ApmCpuBoostMode_FastLoad raises the CPU clock
 *     *and throttles the GPU to its minimum*.  That is perfect for the
 *     core-load/relocation/GameIndex phase and for CPU-bound (EE/VU-heavy)
 *     games, but it is actively harmful once the Maxwell GPU becomes the
 *     bottleneck -- which is why upstream only uses it for the first 60
 *     presented frames.  We keep that default but make it selectable.
 *
 *  2. Explicit DVFS clocks (clkrst, HOS 8.0.0+; pcv as a legacy fallback).
 *     This is what actually helps a PS2 emulator: CPU + GPU + EMC raised
 *     together.  PS2 emulation on Tegra X1 is mostly limited by the shared
 *     25.6 GB/s LPDDR4 link (GS texture uploads, EE/VU RAM traffic, SPU2,
 *     MPEG/IPU frame copies), so EMC (memory) clock is usually the highest
 *     value-per-watt knob of the three.
 *
 * Everything degrades to a no-op when the service is not reachable, which is
 * the normal case for a plain .nro launched from hbmenu: clock control then
 * has to come from a sysmodule (sys-clk) and only the CPU boost applies.
 * When the emulator is started through the bundled forwarder (its NPDM grants
 * service_access "*"), the clkrst path is available.
 *
 * Ini keys (all under /switch/nethersx2/nethersx2.ini):
 *
 *   Wrapper/CpuBoostMode  = startup   ; startup | always | off
 *   Wrapper/ClockProfile  = stock     ; stock | performance | custom
 *   Wrapper/ClockCpuMhz   = 0         ; 0 = leave as-is (custom only)
 *   Wrapper/ClockGpuMhz   = 0
 *   Wrapper/ClockEmcMhz   = 0
 *
 * This software may be modified and distributed under the terms
 * of the MIT license.  See the LICENSE file for details.
 */

#ifndef __X1PERF_H__
#define __X1PERF_H__

#include <stddef.h>

typedef enum {
  X1_CPU_BOOST_STARTUP = 0,  /* boost during boot only (upstream behaviour) */
  X1_CPU_BOOST_ALWAYS,       /* keep FastLoad boost for the whole session */
  X1_CPU_BOOST_OFF,          /* never boost (use with explicit clocks) */
} X1CpuBoostMode;

/* Read the ini and apply the requested policy. Safe to call before the core is
 * loaded; every step is a no-op when the underlying service is unavailable. */
void x1_perf_init(void);

/* Policy query for main.c's frame loop. */
X1CpuBoostMode x1_cpu_boost_mode(void);

/* Restore the clocks we changed and drop the CPU boost. */
void x1_perf_shutdown(void);

/* One-line summary for the OSD ("Tegra X1: CPU 1785 / GPU 921 / EMC 1862 MHz").
 * Returns 0 and writes an empty string when nothing was changed. */
int x1_perf_status(char *out, size_t size);

#endif /* __X1PERF_H__ */
