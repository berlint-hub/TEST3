/* nxvk_libc.c -- the POSIX functions Mesa's util layer expects and Horizon's
 * newlib does not provide.
 *
 * Linking libnvk_support.a pulls in Mesa code written for a POSIX host. The
 * undefined references are not guesses; they are what the devkitA64 15.2.0 link
 * reported:
 *
 *   disk_cache_os.c   sysconf getuid geteuid getgid getegid getpwuid_r fstatat dirfd
 *   mesa_cache_db.c   fstatat dirfd flock
 *   u_cpu_detect.c    sysconf
 *   u_thread.c        pthread_sigmask writev
 *   xmlconfig.c       regcomp regexec regfree posix_memalign
 *   nvkmd_nvgpu_mem.c posix_memalign regcomp
 *   sparse_array.c    posix_memalign
 *   log.c             flock
 *   libsmb2/socket.c  writev
 *
 * Horizon has no users, no signals, no advisory file locks and no on-disk shader
 * cache, so the uid/gid, sigmask, flock and regex entries are deliberately
 * degenerate: they link, they do not crash, and the Mesa paths that depend on
 * them (the disk cache, driconf option matching) simply find nothing. The ones
 * with real semantics -- posix_memalign, writev, fstatat, sysconf -- are real.
 *
 * Gated on NETHERSX2_VK_ICD_ONLY (MESA_FLAVOR=nxvk) so the OpenGL and vendored
 * Vulkan builds are untouched.
 *
 * This software may be modified and distributed under the terms
 * of the MIT license. See the LICENSE file for details.
 */
#if defined(__SWITCH__) && defined(NETHERSX2_VK_ICD_ONLY)

#define _GNU_SOURCE
#include <errno.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <fcntl.h>
#include <dirent.h>
#include <malloc.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <pwd.h>

#if defined(__has_include)
#  if __has_include(<sys/uio.h>)
#    include <sys/uio.h>
#    define NETHERSX2_HAVE_SYS_UIO_H 1
#  elif __has_include(<sys/_iovec.h>)
     /* devkitA64's newlib has no <sys/uio.h>, which is why writev is an
      * undefined reference. It does have <sys/_iovec.h>, and that is where
      * libsmb2's socket.c gets struct iovec from, so take it from the same
      * place rather than redefining a type the TU may already have. */
#    include <sys/_iovec.h>
#    define NETHERSX2_HAVE_SYS_UIO_H 1
#  endif
#endif
#ifndef NETHERSX2_HAVE_SYS_UIO_H
struct iovec { void *iov_base; size_t iov_len; };
#endif

/* Tegra X1: 4x Cortex-A57, 4 GB of LPDDR4 shared between the CPU and the GPU.
 * Only Mesa's disk-cache sizing and CPU detect read these, and there is no
 * writable shader cache on the Switch, so a fixed answer is enough. */
#ifndef _SC_NPROCESSORS_ONLN
#define _SC_NPROCESSORS_ONLN 84
#endif
#ifndef _SC_PAGESIZE
#define _SC_PAGESIZE 30
#endif
#ifndef _SC_PHYS_PAGES
#define _SC_PHYS_PAGES 85
#endif

long sysconf(int name) {
  switch (name) {
    case _SC_NPROCESSORS_ONLN: return 4;
    case _SC_PAGESIZE:         return 4096;
    case _SC_PHYS_PAGES:       return (4L * 1024 * 1024 * 1024) / 4096;
    default:                   errno = EINVAL; return -1;
  }
}

/* Single-user homebrew: every process is uid/gid 0. */
uid_t getuid(void)  { return 0; }
uid_t geteuid(void) { return 0; }
gid_t getgid(void)  { return 0; }
gid_t getegid(void) { return 0; }

int getpwuid_r(uid_t uid, struct passwd *pwd, char *buf, size_t buflen, struct passwd **result) {
  if (!pwd || !buf || buflen < 32) return ERANGE;
  memset(pwd, 0, sizeof(*pwd));
  strcpy(buf, "switch");
  pwd->pw_name  = buf;
  pwd->pw_dir   = "/tmp";
  pwd->pw_shell = "/bin/sh";
  pwd->pw_uid   = uid;
  pwd->pw_gid   = uid;
  if (result) *result = pwd;
  return 0;
}

int posix_memalign(void **memptr, size_t alignment, size_t size) {
  if (!memptr) return EINVAL;
  /* Must be a power of two and a multiple of sizeof(void *). */
  if (alignment < sizeof(void *) || (alignment & (alignment - 1)) != 0) return EINVAL;
  void *p = memalign(alignment, size);
  if (!p) return ENOMEM;
  *memptr = p;
  return 0;
}

ssize_t writev(int fd, const struct iovec *iov, int iovcnt) {
  ssize_t total = 0;
  for (int i = 0; i < iovcnt; i++) {
    ssize_t n = write(fd, iov[i].iov_base, iov[i].iov_len);
    if (n < 0) return total > 0 ? total : -1;
    total += n;
    if ((size_t)n < iov[i].iov_len) break; /* short write: the rest would block */
  }
  return total;
}

int fstatat(int dirfd, const char *path, struct stat *st, int flags) {
  if (dirfd != AT_FDCWD) { errno = ENOTSUP; return -1; }
  if (flags & AT_SYMLINK_NOFOLLOW) return lstat(path, st);
  return stat(path, st);
}

/* No advisory locking on Horizon's filesystems, and nothing to lock: the shader
 * cache is not shared between processes. Pretend the lock was taken. */
int dirfd(DIR *dirp) { (void)dirp; errno = ENOSYS; return -1; }
int flock(int fd, int operation) { (void)fd; (void)operation; return 0; }

/* No signals are delivered under Horizon. */
int pthread_sigmask(int how, const void *set, void *oldset) {
  (void)how; (void)set; (void)oldset;
  return 0;
}

/* Mesa only reaches regcomp/regexec when a driconf file supplies option-match
 * patterns. None is installed on the Switch, so matching is a no-op rather than
 * a reimplementation of POSIX regex. The regex_t layout is deliberately not
 * touched: this file must link against whatever <regex.h> the Mesa objects were
 * compiled with, so the opaque handle is left alone. */
#ifndef REG_NOMATCH
#define REG_NOMATCH 1
#endif
typedef struct { size_t re_nsub; } nsx_regex_t;
typedef struct { long rm_so, rm_eo; } nsx_regmatch_t;

int regcomp(nsx_regex_t *preg, const char *pattern, int cflags) {
  (void)preg; (void)pattern; (void)cflags;
  return 0;
}
int regexec(const nsx_regex_t *preg, const char *string, size_t nmatch,
            nsx_regmatch_t pmatch[], int eflags) {
  (void)preg; (void)string; (void)nmatch; (void)pmatch; (void)eflags;
  return REG_NOMATCH;
}
void regfree(nsx_regex_t *preg) { (void)preg; }

#endif /* __SWITCH__ && NETHERSX2_VK_ICD_ONLY */
