/* x1mem_logic_test.c -- host-side logic test for source/x1mem.c
 *
 * devkitA64 is not needed (and not available on a PC): this re-implements the
 * exact control flow of the NEON routines with scalar 16-byte blocks and
 * cross-checks them against libc for every size up to 600 bytes and every
 * src/dst alignment offset, comparing the whole surrounding buffer so an
 * out-of-range store is caught too.
 *
 * A regression in the head/tail index math shows up here in seconds; the NEON
 * intrinsics themselves are one-to-one with these block copies.
 *
 * Build:  gcc -O2 -o x1mem_logic_test tests/x1mem_logic_test.c && ./x1mem_logic_test
 * Expect: "ALL PASS (0 failures)"
 *
 * This software may be modified and distributed under the terms
 * of the MIT license.  See the LICENSE file for details.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>

typedef struct { unsigned char b[16]; } q16;
static q16 ld16(const unsigned char *p) { q16 v; memcpy(v.b, p, 16); return v; }
static void st16(unsigned char *p, q16 v) { memcpy(p, v.b, 16); }
#define vld1q_u8(p) ld16((const unsigned char *)(p))
#define vst1q_u8(d, v) st16((unsigned char *)(d), (v))

#define X1_BLOCK 64

static void *x1_memcpy_t(void *dst, const void *src, size_t n) {
  uint8_t *d = (uint8_t *)dst; const uint8_t *s = (const uint8_t *)src;
  if (n >= X1_BLOCK) {
    const size_t mis = ((size_t)16u - ((uintptr_t)d & (uintptr_t)15u)) & (size_t)15u;
    if (mis) { vst1q_u8(d, vld1q_u8(s)); d += mis; s += mis; n -= mis; }
    while (n >= X1_BLOCK) {
      const q16 v0 = vld1q_u8(s), v1 = vld1q_u8(s+16), v2 = vld1q_u8(s+32), v3 = vld1q_u8(s+48);
      vst1q_u8(d, v0); vst1q_u8(d+16, v1); vst1q_u8(d+32, v2); vst1q_u8(d+48, v3);
      d += X1_BLOCK; s += X1_BLOCK; n -= X1_BLOCK;
    }
  }
  while (n >= 16) { vst1q_u8(d, vld1q_u8(s)); d += 16; s += 16; n -= 16; }
  switch (n) {
    case 8: *(uint64_t *)d = *(const uint64_t *)s; break;
    case 4: *(uint32_t *)d = *(const uint32_t *)s; break;
    case 1: *d = *s; break;
    case 2: *(uint16_t *)d = *(const uint16_t *)s; break;
    default: while (n != 0) { *d++ = *s++; n--; } break;
  }
  return dst;
}

static void *x1_memset_t(void *dst, int c, size_t n) {
  uint8_t *d = (uint8_t *)dst;
  if (n == 0) return dst;
  const uint8_t v = (uint8_t)c;
  if (n >= 16) {
    const size_t mis = ((size_t)16u - ((uintptr_t)d & (uintptr_t)15u)) & (size_t)15u;
    for (size_t i = 0; i < mis; i++) d[i] = v;
    d += mis; n -= mis;
    q16 vq; memset(vq.b, v, 16);
    while (n >= X1_BLOCK) { vst1q_u8(d, vq); vst1q_u8(d+16, vq); vst1q_u8(d+32, vq); vst1q_u8(d+48, vq); d += X1_BLOCK; n -= X1_BLOCK; }
    while (n >= 16) { vst1q_u8(d, vq); d += 16; n -= 16; }
  }
  while (n != 0) { *d++ = v; n--; }
  return dst;
}

static void *x1_memmove_t(void *dst, const void *src, size_t n) {
  uint8_t *d = (uint8_t *)dst; const uint8_t *s = (const uint8_t *)src;
  if (d == s || n == 0) return dst;
  if (d >= s + n) return x1_memcpy_t(dst, src, n);
  if (d < s) {
    while (n >= X1_BLOCK) {
      const q16 v0=vld1q_u8(s), v1=vld1q_u8(s+16), v2=vld1q_u8(s+32), v3=vld1q_u8(s+48);
      vst1q_u8(d,v0); vst1q_u8(d+16,v1); vst1q_u8(d+32,v2); vst1q_u8(d+48,v3);
      d+=X1_BLOCK; s+=X1_BLOCK; n-=X1_BLOCK;
    }
    while (n >= 16) { vst1q_u8(d, vld1q_u8(s)); d+=16; s+=16; n-=16; }
    while (n != 0) { *d++ = *s++; n--; }
    return dst;
  }
  d += n; s += n;
  while (n >= 16) { d -= 16; s -= 16; vst1q_u8(d, vld1q_u8(s)); n -= 16; }
  while (n != 0) { n--; d--; s--; *d = *s; }
  return dst;
}

static size_t x1_strlen_t(const char *str) {
  const char *p = str;
  while (((uintptr_t)p & (uintptr_t)15u) != 0) { if (*p == '\0') return (size_t)(p - str); p++; }
  for (;;) {
    q16 v = vld1q_u8((const uint8_t *)p);
    int zero = 0;
    for (int i = 0; i < 16; i++) if (v.b[i] == 0) { zero = 1; break; }
    if (zero) { for (size_t i = 0; i < 16; i++) if (p[i] == '\0') return (size_t)(p + i - str); }
    p += 16;
  }
}

#define MAXN 600
static unsigned char a[4096], b[4096], ref[4096];
static int fails = 0;

int main(void) {
  srand(12345);
  /* memcpy / memcmp: all (src,dst) alignment offsets x all sizes */
  for (size_t n = 0; n <= MAXN; n++) {
    for (int so = 0; so < 32; so++) {
      for (int dof = 0; dof < 32; dof++) {
        for (size_t i = 0; i < sizeof(a); i++) a[i] = (unsigned char)rand();
        memset(b, 0xAA, sizeof(b)); memset(ref, 0xAA, sizeof(ref));
        memcpy(ref + dof, a + so, n);
        x1_memcpy_t(b + dof, a + so, n);
        if (memcmp(ref, b, sizeof(b)) != 0) { printf("memcpy FAIL n=%zu so=%d do=%d\n", n, so, dof); if (++fails > 5) return 1; }
      }
    }
  }
  /* memset */
  for (size_t n = 0; n <= MAXN; n++)
    for (int dof = 0; dof < 32; dof++) {
      memset(b, 0x55, sizeof(b)); memset(ref, 0x55, sizeof(ref));
      memset(ref + dof, 0xC3, n);
      x1_memset_t(b + dof, 0xC3, n);
      if (memcmp(ref, b, sizeof(b)) != 0) { printf("memset FAIL n=%zu do=%d\n", n, dof); if (++fails > 5) return 1; }
    }
  /* memmove: overlapping both directions */
  for (size_t n = 0; n <= MAXN; n++)
    for (int off = 0; off < 64; off++) {
      for (size_t i = 0; i < sizeof(a); i++) a[i] = (unsigned char)rand();
      /* dest above src */
      memcpy(b, a, sizeof(a)); memcpy(ref, a, sizeof(a));
      memmove(ref + 100, ref + 100 + off, n);
      x1_memmove_t(b + 100, b + 100 + off, n);
      if (memcmp(ref, b, sizeof(b)) != 0) { printf("memmove(fwd) FAIL n=%zu off=%d\n", n, off); if (++fails > 5) return 1; }
      /* dest below src */
      memcpy(b, a, sizeof(a)); memcpy(ref, a, sizeof(a));
      memmove(ref + 100 + off, ref + 100, n);
      x1_memmove_t(b + 100 + off, b + 100, n);
      if (memcmp(ref, b, sizeof(b)) != 0) { printf("memmove(bwd) FAIL n=%zu off=%d\n", n, off); if (++fails > 5) return 1; }
    }
  /* strlen */
  for (int off = 0; off < 32; off++)
    for (size_t len = 0; len < 300; len++) {
      memset(a, 'x', sizeof(a));
      a[off + len] = '\0';
      if (x1_strlen_t((char *)a + off) != len) { printf("strlen FAIL off=%d len=%zu\n", off, len); if (++fails > 5) return 1; }
    }
  printf(fails ? "FAILURES: %d\n" : "ALL PASS (%d failures)\n", fails);
  return fails != 0;
}
