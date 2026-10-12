/* x1perf.c -- Tegra X1 (Nintendo Switch) performance control
 *
 * This software may be modified and distributed under the terms
 * of the MIT license.  See the LICENSE file for details.
 */

#include <stdio.h>
#include <string.h>
#include <strings.h>
#include <stdlib.h>

#include <switch.h>

#include "x1perf.h"
#include "prefs.h"
#include "util.h"

/* ------------------------------------------------------------------------- */
/* configuration                                                             */
/* ------------------------------------------------------------------------- */

/* "performance" profile: every value is a rate from the official Tegra X1 DVFS
 * table (the same frequencies HOS itself picks in its boost performance
 * configurations), just pinned permanently instead of on demand:
 *   CPU 1785 MHz  (stock 1020, +75%)
 *   GPU  921 MHz  (stock handheld 307/384, docked 768)
 *   EMC 1862 MHz  (stock 1331, +40% -- memory bandwidth is the real limit)
 */
#define X1_PERF_CPU_MHZ 1785
#define X1_PERF_GPU_MHZ  921
#define X1_PERF_EMC_MHZ 1862

typedef enum { X1_CLOCK_STOCK = 0, X1_CLOCK_PERFORMANCE, X1_CLOCK_CUSTOM } X1ClockProfile;

static X1CpuBoostMode s_boost_mode = X1_CPU_BOOST_STARTUP;
static int s_boost_applied;

/* ------------------------------------------------------------------------- */
/* clock plumbing (clkrst, HOS 8.0.0+)                                       */
/* ------------------------------------------------------------------------- */

typedef struct {
  const char *name;
  PcvModuleId id;
  ClkrstSession session;
  int open;
  u32 original_hz;   /* rate before we touched it */
  u32 applied_hz;    /* rate we set (0 = untouched) */
} X1Clock;

static X1Clock s_cpu = { "CPU", PcvModuleId_CpuBus, {{0}}, 0, 0, 0 };
static X1Clock s_gpu = { "GPU", PcvModuleId_GPU,    {{0}}, 0, 0, 0 };
static X1Clock s_emc = { "EMC", PcvModuleId_EMC,    {{0}}, 0, 0, 0 };

static int s_clkrst_ready;

/* Pick the highest rate the DVFS table offers that does not exceed `want`.
 * Requesting a rate the table does not contain makes clkrst reject the whole
 * call, so clamping is what makes hand-typed MHz values usable. */
static u32 clamp_rate(ClkrstSession *session, u32 want_hz) {
  u32 rates[32];
  s32 count = 0;
  PcvClockRatesListType type = PcvClockRatesListType_Invalid;

  if (R_FAILED(clkrstGetPossibleClockRates(session, rates, 32, &type, &count)) || count <= 0)
    return want_hz; /* table unavailable: let the service validate our value */

  u32 best = 0;
  for (s32 i = 0; i < count; i++) {
    const u32 r = rates[i];
    if (r <= want_hz && r > best)
      best = r;
  }
  if (best == 0) {
    /* requested below the lowest entry -- take the lowest */
    best = rates[0];
    for (s32 i = 1; i < count; i++)
      if (rates[i] < best)
        best = rates[i];
  }
  return best;
}

static int clock_open(X1Clock *clk) {
  if (clk->open)
    return 1;

  if (R_FAILED(clkrstOpenSession(&clk->session, clk->id, 3)))
    return 0;

  clk->open = 1;
  if (R_FAILED(clkrstGetClockRate(&clk->session, &clk->original_hz)))
    clk->original_hz = 0;
  return 1;
}

static void clock_apply(X1Clock *clk, u32 mhz) {
  if (!mhz || clk->applied_hz)
    return;
  if (!clock_open(clk))
    return;

  u32 want = mhz * 1000000u;
  /* never exceed 3 GHz: guards against a fat-fingered ini value */
  if (want > 3000000000u)
    want = 3000000000u;

  const u32 rate = clamp_rate(&clk->session, want);
  if (R_FAILED(clkrstSetClockRate(&clk->session, rate)))
    return;
  clk->applied_hz = rate;
}

static void clock_restore(X1Clock *clk) {
  if (!clk->open)
    return;

  if (clk->applied_hz && clk->original_hz)
    clkrstSetClockRate(&clk->session, clk->original_hz);
  clkrstCloseSession(&clk->session);
  clk->open = 0;
  clk->applied_hz = 0;
}

/* ------------------------------------------------------------------------- */
/* public API                                                                */
/* ------------------------------------------------------------------------- */

static X1ClockProfile clock_profile_from_string(const char *v) {
  if (!v || !*v)
    return X1_CLOCK_STOCK;
  if (!strcasecmp(v, "performance") || !strcasecmp(v, "perf"))
    return X1_CLOCK_PERFORMANCE;
  if (!strcasecmp(v, "custom"))
    return X1_CLOCK_CUSTOM;
  return X1_CLOCK_STOCK;
}

static X1CpuBoostMode boost_mode_from_string(const char *v) {
  if (!v || !*v)
    return X1_CPU_BOOST_STARTUP;
  if (!strcasecmp(v, "always") || !strcasecmp(v, "on") || !strcasecmp(v, "game"))
    return X1_CPU_BOOST_ALWAYS;
  if (!strcasecmp(v, "off") || !strcasecmp(v, "never") || !strcasecmp(v, "false"))
    return X1_CPU_BOOST_OFF;
  return X1_CPU_BOOST_STARTUP;
}

static int mhz_pref(const char *key) {
  const int v = prefs_get_int(key, 0);
  return (v >= 100 && v <= 3000) ? v : 0;
}

void x1_perf_init(void) {
  s_boost_mode = boost_mode_from_string(prefs_get_string("Wrapper/CpuBoostMode", "startup"));

  if (s_boost_mode == X1_CPU_BOOST_OFF) {
    cpu_boost(0);
    s_boost_applied = 0;
  } else {
    cpu_boost(1);
    s_boost_applied = 1;
  }

  const X1ClockProfile profile =
      clock_profile_from_string(prefs_get_string("Wrapper/ClockProfile", "stock"));

  u32 cpu_mhz = 0, gpu_mhz = 0, emc_mhz = 0;
  if (profile == X1_CLOCK_PERFORMANCE) {
    cpu_mhz = X1_PERF_CPU_MHZ;
    gpu_mhz = X1_PERF_GPU_MHZ;
    emc_mhz = X1_PERF_EMC_MHZ;
  } else if (profile == X1_CLOCK_CUSTOM) {
    cpu_mhz = (u32)mhz_pref("Wrapper/ClockCpuMhz");
    gpu_mhz = (u32)mhz_pref("Wrapper/ClockGpuMhz");
    emc_mhz = (u32)mhz_pref("Wrapper/ClockEmcMhz");
  }

  if (!cpu_mhz && !gpu_mhz && !emc_mhz)
    return; /* stock: nothing to do, no service needed */

  if (R_FAILED(clkrstInitialize()))
    return; /* no clock control (plain hbmenu launch on <8.0.0, or blocked) */
  s_clkrst_ready = 1;

  /* Order matters: raise EMC (memory) before the clients that hammer it, and
   * drop it last. */
  clock_apply(&s_emc, emc_mhz);
  clock_apply(&s_gpu, gpu_mhz);
  clock_apply(&s_cpu, cpu_mhz);
}

X1CpuBoostMode x1_cpu_boost_mode(void) {
  return s_boost_mode;
}

int x1_perf_status(char *out, size_t size) {
  if (!out || !size)
    return 0;
  out[0] = '\0';

  if (!s_cpu.applied_hz && !s_gpu.applied_hz && !s_emc.applied_hz)
    return 0;

  size_t used = 0;
  int n;

#define APPEND(...)                                                            \
  do {                                                                         \
    if (used >= size)                                                          \
      return used > 0;                                                         \
    n = snprintf(out + used, size - used, __VA_ARGS__);                        \
    if (n < 0)                                                                 \
      return used > 0;                                                         \
    used += (size_t)n;                                                         \
    if (used >= size) {                                                        \
      out[size - 1] = '\0';                                                    \
      return 1;                                                                \
    }                                                                          \
  } while (0)

  if (s_cpu.applied_hz)
    APPEND("CPU %u", s_cpu.applied_hz / 1000000u);
  if (s_gpu.applied_hz)
    APPEND("%sGPU %u", used ? " / " : "", s_gpu.applied_hz / 1000000u);
  if (s_emc.applied_hz)
    APPEND("%sEMC %u", used ? " / " : "", s_emc.applied_hz / 1000000u);
#undef APPEND

  return used > 0;
}

void x1_perf_shutdown(void) {
  if (s_clkrst_ready) {
    clock_restore(&s_cpu);
    clock_restore(&s_gpu);
    clock_restore(&s_emc);
    clkrstExit();
    s_clkrst_ready = 0;
  }
  if (s_boost_applied) {
    cpu_boost(0);
    s_boost_applied = 0;
  }
}
