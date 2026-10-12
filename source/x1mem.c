/* x1mem.c -- Cortex-A57 (Nintendo Switch / Tegra X1) tuned memory primitives
 *
 * Implementation notes for Tegra X1 (Cortex-A57, 128-bit L1, 64-byte cache
 * lines, 2 MB L2 shared with the Maxwell GPU):
 *
 *  - 64-byte blocks (4 x q-register) match one full cache line, so a store
 *    never has to fetch the line first when the destination is written in its
 *    entirety -- the A57's write-combining path turns those into full-line
 *    stores.  That is the single biggest win versus a byte/word loop.
 *  - All bulk accesses are 16-byte aligned: unaligned 16-byte accesses do not
 *    fault on AArch64, but an access crossing a 64-byte line boundary costs an
 *    extra cycle on A57.
 *  - Aligned 16-byte loads/stores are the widest the A57 issues (2x64-bit
 *    internally), so issuing them back to back keeps both load/store pipes
 *    busy without unrolling into register pressure.
 *  - Small sizes (< 16 bytes) are handled by simple loops: the overhead of
 *    setting up NEON dominates below that, and the emulator hammers memcpy
 *    with 4/8/16-byte structs too.
 *
 * This software may be modified and distributed under the terms
 * of the MIT license.  See the LICENSE file for details.
 */

#include <string.h>

#include "x1mem.h"

#if X1_FAST_MEM

#include <stdint.h>
#include <arm_neon.h>

/* bytes per bulk block: one Tegra X1 cache line */
#define X1_BLOCK 64

void *x1_memset(void *dst, int c, size_t n) {
  uint8_t *d = (uint8_t *)dst;

  if (n == 0)
    return dst;

  const uint8_t v = (uint8_t)c;

  /* Head: reach 16-byte alignment with plain stores (a NEON store here would
   * have to be unaligned anyway, and the head is at most 15 bytes). */
  if (n >= 16) {
    const size_t mis = ((size_t)16u - ((uintptr_t)d & (uintptr_t)15u)) & (size_t)15u;
    for (size_t i = 0; i < mis; i++)
      d[i] = v;
    d += mis;
    n -= mis;

    const uint8x16_t vq = vdupq_n_u8(v);

    /* full cache lines */
    while (n >= X1_BLOCK) {
      vst1q_u8(d, vq);
      vst1q_u8(d + 16, vq);
      vst1q_u8(d + 32, vq);
      vst1q_u8(d + 48, vq);
      d += X1_BLOCK;
      n -= X1_BLOCK;
    }
    /* remaining aligned 16-byte chunks */
    while (n >= 16) {
      vst1q_u8(d, vq);
      d += 16;
      n -= 16;
    }
  }

  while (n != 0) {
    *d++ = v;
    n--;
  }
  return dst;
}

void *x1_memcpy(void *dst, const void *src, size_t n) {
  uint8_t *d = (uint8_t *)dst;
  const uint8_t *s = (const uint8_t *)src;

  if (n >= X1_BLOCK) {
    /* Copy the first <=15 bytes with one (unaligned but 16-byte) NEON pair so
     * the destination is 16-byte aligned for the bulk loop.  The store may
     * write up to 15 bytes past the head; those bytes are inside the
     * destination (n >= 64) and are re-written with identical data below. */
    const size_t mis = ((size_t)16u - ((uintptr_t)d & (uintptr_t)15u)) & (size_t)15u;
    if (mis) {
      vst1q_u8(d, vld1q_u8(s));
      d += mis;
      s += mis;
      n -= mis;
    }

    while (n >= X1_BLOCK) {
      /* issue all four loads, then all four stores: A57 can overlap the
       * loads with the previous iteration's stores */
      const uint8x16_t v0 = vld1q_u8(s);
      const uint8x16_t v1 = vld1q_u8(s + 16);
      const uint8x16_t v2 = vld1q_u8(s + 32);
      const uint8x16_t v3 = vld1q_u8(s + 48);
      vst1q_u8(d, v0);
      vst1q_u8(d + 16, v1);
      vst1q_u8(d + 32, v2);
      vst1q_u8(d + 48, v3);
      d += X1_BLOCK;
      s += X1_BLOCK;
      n -= X1_BLOCK;
    }
  }

  while (n >= 16) {
    vst1q_u8(d, vld1q_u8(s));
    d += 16;
    s += 16;
    n -= 16;
  }

  switch (n) {
    /* small tails: keep them branch-light, the emulator copies 4/8/12-byte
     * headers constantly */
    case 8: *(uint64_t *)d = *(const uint64_t *)s; break;
    case 4: *(uint32_t *)d = *(const uint32_t *)s; break;
    case 1: *d = *s; break;
    case 2: *(uint16_t *)d = *(const uint16_t *)s; break;
    default:
      while (n != 0) {
        *d++ = *s++;
        n--;
      }
      break;
  }

  return dst;
}

void *x1_memmove(void *dst, const void *src, size_t n) {
  uint8_t *d = (uint8_t *)dst;
  const uint8_t *s = (const uint8_t *)src;

  if (d == s || n == 0)
    return dst;

  /* Fully disjoint (or dest entirely below/above the source range): the fast
   * path is safe. */
  if (d >= s + n)
    return x1_memcpy(dst, src, n);

  if (d < s) {
    /* Overlapping with the destination BELOW the source: copy forward, but
     * WITHOUT x1_memcpy's head alignment step. That step stores a full 16
     * bytes while only consuming `mis` of them, and with an overlap smaller
     * than 16 bytes the leftover bytes land in source data that has not been
     * read yet -- the copy then re-reads its own output.
     * Unaligned blocks are fine here: after reading block i, everything it
     * writes stays below the next block's read cursor (d + 64 <= s + 64). */
    while (n >= X1_BLOCK) {
      const uint8x16_t v0 = vld1q_u8(s);
      const uint8x16_t v1 = vld1q_u8(s + 16);
      const uint8x16_t v2 = vld1q_u8(s + 32);
      const uint8x16_t v3 = vld1q_u8(s + 48);
      vst1q_u8(d, v0);
      vst1q_u8(d + 16, v1);
      vst1q_u8(d + 32, v2);
      vst1q_u8(d + 48, v3);
      d += X1_BLOCK;
      s += X1_BLOCK;
      n -= X1_BLOCK;
    }
    while (n >= 16) {
      vst1q_u8(d, vld1q_u8(s));
      d += 16;
      s += 16;
      n -= 16;
    }
    while (n != 0) {
      *d++ = *s++;
      n--;
    }
    return dst;
  }

  /* Overlapping with the destination ABOVE the source: copy backwards. */
  d += n;
  s += n;
  while (n >= 16) {
    d -= 16;
    s -= 16;
    vst1q_u8(d, vld1q_u8(s));
    n -= 16;
  }
  while (n != 0) {
    n--;
    d--;
    s--;
    *d = *s;
  }
  return dst;
}

int x1_memcmp(const void *a, const void *b, size_t n) {
  const uint8_t *p = (const uint8_t *)a;
  const uint8_t *q = (const uint8_t *)b;

  while (n >= 16) {
    const uint8x16_t va = vld1q_u8(p);
    const uint8x16_t vb = vld1q_u8(q);
    /* vminvq of the equality mask is 0xFF only when all 16 bytes match */
    if (vminvq_u8(vceqq_u8(va, vb)) != 0xFF) {
      for (size_t i = 0; i < 16; i++)
        if (p[i] != q[i])
          return (int)p[i] - (int)q[i];
    }
    p += 16;
    q += 16;
    n -= 16;
  }

  while (n != 0) {
    if (*p != *q)
      return (int)*p - (int)*q;
    p++;
    q++;
    n--;
  }
  return 0;
}

size_t x1_strlen(const char *str) {
  const char *p = str;

  /* reach 16-byte alignment first */
  while (((uintptr_t)p & (uintptr_t)15u) != 0) {
    if (*p == '\0')
      return (size_t)(p - str);
    p++;
  }

  /* An aligned 16-byte load can never cross a page boundary, so this is safe
   * as long as the caller's string is mapped -- which it is up to and
   * including the NUL. */
  for (;;) {
    const uint8x16_t v = vld1q_u8((const uint8_t *)p);
    if (vmaxvq_u8(vceqq_u8(v, vdupq_n_u8(0))) != 0) {
      for (size_t i = 0; i < 16; i++)
        if (p[i] == '\0')
          return (size_t)(p + i - str);
    }
    p += 16;
  }
}

#else /* !X1_FAST_MEM -- A/B fallback to the toolchain implementations */

void *x1_memcpy(void *dst, const void *src, size_t n) { return memcpy(dst, src, n); }
void *x1_memset(void *dst, int c, size_t n) { return memset(dst, c, n); }
void *x1_memmove(void *dst, const void *src, size_t n) { return memmove(dst, src, n); }
int x1_memcmp(const void *a, const void *b, size_t n) { return memcmp(a, b, n); }
size_t x1_strlen(const char *s) { return strlen(s); }

#endif /* X1_FAST_MEM */
