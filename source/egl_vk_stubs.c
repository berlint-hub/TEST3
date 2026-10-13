/* egl_vk_stubs.c -- the few EGL/GLES symbols NVK does NOT already stub, for the
 * VULKAN build only.
 *
 * The Vulkan (NVK) build does NOT link switch-mesa's libEGL/libGLESv2 (they and
 * NVK both bundle mesa util/nir/compiler object code and can't co-link). But
 * libemucore.so has 19 undefined egl* dynamic imports and our EGL layer
 * (hooks/egl.c) still compiles and calls the raw egl and gl functions. NVK's own
 * rust_switch_stubs already provides most egl* symbols (eglGetDisplay,
 * eglSwapBuffers, ...); this file adds only the handful it does not, so the link
 * resolves. On the Vulkan renderer path the core drives GSDeviceVK and never
 * actually calls these -- they just need to exist and fail benignly. Compiled to
 * nothing in the OpenGL build (real switch-mesa symbols linked instead).
 */
#if defined(USE_VULKAN) && !defined(USE_UNIFIED_MESA)

#include <stddef.h>
#include <EGL/egl.h>
#include <GLES2/gl2.h>

EGLBoolean eglQuerySurface(EGLDisplay d, EGLSurface s, EGLint a, EGLint *v) {
  (void)d; (void)s; (void)a; if (v) *v = 0; return EGL_FALSE; }
EGLContext eglGetCurrentContext(void) { return EGL_NO_CONTEXT; }
EGLSurface eglGetCurrentSurface(EGLint rw) { (void)rw; return EGL_NO_SURFACE; }
const GLubyte *glGetString(GLenum name) { (void)name; return (const GLubyte *)""; }

/* The rest of the egl* surface, for the nxvk (ICD-only) link.
 *
 * The vendored NVK bundle above ships its own EGL, so only the three functions
 * it lacks are stubbed. The public nxvk port configures Mesa with
 * -Degl=disabled, so it provides none of them and all 18 egl* imports of
 * libemucore.so are unresolved. The Vulkan renderer path drives GSDeviceVK and
 * never calls into EGL; these only have to exist and fail benignly so the link
 * resolves. Guarded by NETHERSX2_VK_ICD_ONLY so the vendored/sdk flavors keep
 * linking the real symbols.
 */
#ifdef NETHERSX2_VK_ICD_ONLY

EGLBoolean eglBindAPI(EGLenum api) { (void)api; return EGL_FALSE; }
EGLBoolean eglChooseConfig(EGLDisplay d, const EGLint *a, EGLConfig *c, EGLint n, EGLint *out) {
  (void)d; (void)a; (void)c; (void)n; if (out) *out = 0; return EGL_FALSE; }
EGLContext eglCreateContext(EGLDisplay d, EGLConfig c, EGLContext s, const EGLint *a) {
  (void)d; (void)c; (void)s; (void)a; return EGL_NO_CONTEXT; }
EGLSurface eglCreatePbufferSurface(EGLDisplay d, EGLConfig c, const EGLint *a) {
  (void)d; (void)c; (void)a; return EGL_NO_SURFACE; }
EGLSurface eglCreateWindowSurface(EGLDisplay d, EGLConfig c, EGLNativeWindowType w,
                                  const EGLint *a) {
  (void)d; (void)c; (void)w; (void)a; return EGL_NO_SURFACE; }
EGLBoolean eglDestroyContext(EGLDisplay d, EGLContext c) { (void)d; (void)c; return EGL_FALSE; }
EGLBoolean eglDestroySurface(EGLDisplay d, EGLSurface s) { (void)d; (void)s; return EGL_FALSE; }
EGLBoolean eglGetConfigAttrib(EGLDisplay d, EGLConfig c, EGLint a, EGLint *v) {
  (void)d; (void)c; (void)a; if (v) *v = 0; return EGL_FALSE; }
EGLDisplay eglGetDisplay(EGLNativeDisplayType id) { (void)id; return EGL_NO_DISPLAY; }
EGLint eglGetError(void) { return EGL_NOT_INITIALIZED; }
__eglMustCastToProperFunctionPointerType eglGetProcAddress(const char *name) {
  (void)name; return NULL; }
EGLBoolean eglInitialize(EGLDisplay d, EGLint *maj, EGLint *min) {
  (void)d; if (maj) *maj = 1; if (min) *min = 4; return EGL_FALSE; }
EGLBoolean eglMakeCurrent(EGLDisplay d, EGLSurface dr, EGLSurface rd, EGLContext c) {
  (void)d; (void)dr; (void)rd; (void)c; return EGL_FALSE; }
const char *eglQueryString(EGLDisplay d, EGLint name) {
  (void)d; (void)name; return "nxvk-no-egl"; }
EGLBoolean eglReleaseThread(void) { return EGL_FALSE; }
EGLBoolean eglSwapBuffers(EGLDisplay d, EGLSurface s) { (void)d; (void)s; return EGL_FALSE; }
EGLBoolean eglSwapInterval(EGLDisplay d, EGLint i) { (void)d; (void)i; return EGL_FALSE; }
EGLBoolean eglTerminate(EGLDisplay d) { (void)d; return EGL_FALSE; }

#endif /* NETHERSX2_VK_ICD_ONLY */


#endif // USE_VULKAN
