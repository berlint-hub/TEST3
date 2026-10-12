/* x1mem.h -- Cortex-A57 (Nintendo Switch / Tegra X1) tuned memory primitives
 *
 * NetherSX2_nx -- NetherSX2 (AetherSX2 / PCSX2-lineage PS2 emulator) on the
 * Nintendo Switch via a libnx so-loader.
 *
 * Why this exists
 * ---------------
 * libemucore.so is an Android (bionic) binary. Every libc import it makes is
 * resolved through our import table, and the upstream table wired
 * memcpy/memset/memmove/memcmp/strlen straight to the devkitA64 newlib
 * implementations.  newlib's versions are written for portability, not for a
 * 4-wide out-of-order core: they are byte/word loops with a single
 * load-store pair in flight, so they leave most of Cortex-A57's ~2 load/store
 * issue slots idle and never issue the 128-bit accesses the core can retire
 * every cycle.
 *
 * bionic's memcpy (the routine the core was compiled and profiled against) is
 * a NEON, 64-byte-block implementation.  On Tegra X1 the gap is large for the
 * sizes the emulator actually moves -- GS texture uploads, EE/VU/IOP RAM
 * mirrors, IPU (MPEG) frame copies, SPU2 mixing buffers, CDVD sector reads --
 * which are mostly 2 KiB..1 MiB and run every frame.
 *
 * These are drop-in replacements with C semantics (including the correct
 * memmove overlap behaviour and memcmp/strlen return values).  They only read
 * 16-byte-aligned blocks, so they never touch a page the caller did not
 * already map.
 *
 * Set X1_FAST_MEM=0 at build time (or -DX1_FAST_MEM=0) to fall back to the
 * newlib implementations for A/B benchmarking on device.
 *
 * This software may be modified and distributed under the terms
 * of the MIT license.  See the LICENSE file for details.
 */

#ifndef __X1MEM_H__
#define __X1MEM_H__

#include <stddef.h>

#if !defined(X1_FAST_MEM)
#define X1_FAST_MEM 1
#endif

void *x1_memcpy(void *dst, const void *src, size_t n);
void *x1_memset(void *dst, int c, size_t n);
void *x1_memmove(void *dst, const void *src, size_t n);
int x1_memcmp(const void *a, const void *b, size_t n);
size_t x1_strlen(const char *s);

#endif /* __X1MEM_H__ */
