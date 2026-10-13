/* vk_icd_shim.c -- loader entry points for a loader-less NVK link.
 *
 * The public nxvk port (PalindromicBreadLoaf/nxvk, branch `switch`) configures
 * Mesa with -Dvulkan-drivers=nouveau only, so it produces the NVK *ICD* and the
 * Mesa support archives. It does not produce the Vulkan loader/runtime archives
 * that NaGaa95's private 23-archive bundle carries, so the plain `vkFoo` names
 * that hooks/vk.c falls back to (`real_X ? real_X : vkX`) have no definition and
 * the link fails with ~20 undefined references.
 *
 * What the ICD does export is vk_icdGetInstanceProcAddr (nvk_instance.c), which
 * resolves every global, instance, physical-device and device entry point. So
 * each name below is a thin wrapper over that lookup. hooks/vk.c populates its
 * real_* pointers from the intercepted GIPA, so these are a fallback in
 * practice -- but they are also correct if the fallback is ever taken.
 *
 * Compiled only when NETHERSX2_VK_ICD_ONLY is set (MESA_FLAVOR=nxvk). Under the
 * vendored/sdk flavors the real loader archives are linked and defining these
 * again would be a duplicate-symbol error.
 *
 * This software may be modified and distributed under the terms
 * of the MIT license. See the LICENSE file for details.
 */
#if defined(USE_VULKAN) && defined(NETHERSX2_VK_ICD_ONLY)

#include <stddef.h>
#include <vulkan/vulkan.h>

/* The ICD entry point provided by libnvk.a. Declared here rather than pulled
 * from a loader header: there is no loader in this link. */
extern PFN_vkVoidFunction VKAPI_CALL vk_icdGetInstanceProcAddr(VkInstance instance,
                                                              const char *pName);

/* Single-instance emulator: remember the instance so device-level entry points
 * can be resolved after vkCreateInstance. */
static VkInstance icd_instance = VK_NULL_HANDLE;

static PFN_vkVoidFunction icd_get(const char *name) {
  return vk_icdGetInstanceProcAddr(icd_instance, name);
}

#define ICD_FN(name) ((PFN_##name)icd_get(#name))

/* ---- global (instance == NULL) ---- */

VkResult vkCreateInstance(const VkInstanceCreateInfo *pCreateInfo,
                          const VkAllocationCallbacks *pAllocator,
                          VkInstance *pInstance) {
  PFN_vkCreateInstance fn = (PFN_vkCreateInstance)vk_icdGetInstanceProcAddr(NULL, "vkCreateInstance");
  if (!fn) return VK_ERROR_INITIALIZATION_FAILED;
  VkResult r = fn(pCreateInfo, pAllocator, pInstance);
  if (r == VK_SUCCESS && pInstance) icd_instance = *pInstance;
  return r;
}

VkResult vkEnumerateInstanceExtensionProperties(const char *pLayerName,
                                               uint32_t *pPropertyCount,
                                               VkExtensionProperties *pProperties) {
  PFN_vkEnumerateInstanceExtensionProperties fn =
      (PFN_vkEnumerateInstanceExtensionProperties)
          vk_icdGetInstanceProcAddr(NULL, "vkEnumerateInstanceExtensionProperties");
  if (!fn) { if (pPropertyCount) *pPropertyCount = 0; return VK_ERROR_INITIALIZATION_FAILED; }
  return fn(pLayerName, pPropertyCount, pProperties);
}

VkResult vkEnumerateInstanceLayerProperties(uint32_t *pPropertyCount,
                                           VkLayerProperties *pProperties) {
  PFN_vkEnumerateInstanceLayerProperties fn =
      (PFN_vkEnumerateInstanceLayerProperties)
          vk_icdGetInstanceProcAddr(NULL, "vkEnumerateInstanceLayerProperties");
  if (!fn) { if (pPropertyCount) *pPropertyCount = 0; return VK_ERROR_INITIALIZATION_FAILED; }
  return fn(pPropertyCount, pProperties);
}

VkResult vkEnumerateInstanceVersion(uint32_t *pApiVersion) {
  PFN_vkEnumerateInstanceVersion fn =
      (PFN_vkEnumerateInstanceVersion)vk_icdGetInstanceProcAddr(NULL, "vkEnumerateInstanceVersion");
  if (!fn) { if (pApiVersion) *pApiVersion = VK_API_VERSION_1_0; return VK_SUCCESS; }
  return fn(pApiVersion);
}

PFN_vkVoidFunction vkGetInstanceProcAddr(VkInstance instance, const char *pName) {
  if (instance && !icd_instance) icd_instance = instance;
  return vk_icdGetInstanceProcAddr(instance ? instance : icd_instance, pName);
}

PFN_vkVoidFunction vkGetDeviceProcAddr(VkDevice device, const char *pName) {
  PFN_vkGetDeviceProcAddr fn = ICD_FN(vkGetDeviceProcAddr);
  return fn ? fn(device, pName) : NULL;
}

/* ---- instance ---- */

void vkDestroyInstance(VkInstance instance, const VkAllocationCallbacks *pAllocator) {
  PFN_vkDestroyInstance fn = ICD_FN(vkDestroyInstance);
  if (fn) fn(instance, pAllocator);
  if (instance == icd_instance) icd_instance = VK_NULL_HANDLE;
}

VkResult vkCreateViSurfaceNN(VkInstance instance, const VkViSurfaceCreateInfoNN *pCreateInfo,
                             const VkAllocationCallbacks *pAllocator, VkSurfaceKHR *pSurface) {
  PFN_vkCreateViSurfaceNN fn = ICD_FN(vkCreateViSurfaceNN);
  if (!fn) return VK_ERROR_EXTENSION_NOT_PRESENT;
  return fn(instance, pCreateInfo, pAllocator, pSurface);
}

/* ---- physical device ---- */

VkResult vkEnumerateDeviceExtensionProperties(VkPhysicalDevice physicalDevice,
                                             const char *pLayerName, uint32_t *pPropertyCount,
                                             VkExtensionProperties *pProperties) {
  PFN_vkEnumerateDeviceExtensionProperties fn = ICD_FN(vkEnumerateDeviceExtensionProperties);
  if (!fn) { if (pPropertyCount) *pPropertyCount = 0; return VK_ERROR_INITIALIZATION_FAILED; }
  return fn(physicalDevice, pLayerName, pPropertyCount, pProperties);
}

void vkGetPhysicalDeviceFormatProperties(VkPhysicalDevice physicalDevice, VkFormat format,
                                         VkFormatProperties *pFormatProperties) {
  PFN_vkGetPhysicalDeviceFormatProperties fn = ICD_FN(vkGetPhysicalDeviceFormatProperties);
  if (!fn) { if (pFormatProperties) *pFormatProperties = (VkFormatProperties){0}; return; }
  fn(physicalDevice, format, pFormatProperties);
}

void vkGetPhysicalDeviceQueueFamilyProperties(VkPhysicalDevice physicalDevice,
                                             uint32_t *pQueueFamilyPropertyCount,
                                             VkQueueFamilyProperties *pQueueFamilyProperties) {
  PFN_vkGetPhysicalDeviceQueueFamilyProperties fn = ICD_FN(vkGetPhysicalDeviceQueueFamilyProperties);
  if (!fn) { if (pQueueFamilyPropertyCount) *pQueueFamilyPropertyCount = 0; return; }
  fn(physicalDevice, pQueueFamilyPropertyCount, pQueueFamilyProperties);
}

VkResult vkGetPhysicalDeviceSurfaceCapabilitiesKHR(VkPhysicalDevice physicalDevice,
                                                  VkSurfaceKHR surface,
                                                  VkSurfaceCapabilitiesKHR *pSurfaceCapabilities) {
  PFN_vkGetPhysicalDeviceSurfaceCapabilitiesKHR fn = ICD_FN(vkGetPhysicalDeviceSurfaceCapabilitiesKHR);
  if (!fn) return VK_ERROR_EXTENSION_NOT_PRESENT;
  return fn(physicalDevice, surface, pSurfaceCapabilities);
}

/* ---- device ---- */

VkResult vkCreateDevice(VkPhysicalDevice physicalDevice, const VkDeviceCreateInfo *pCreateInfo,
                        const VkAllocationCallbacks *pAllocator, VkDevice *pDevice) {
  PFN_vkCreateDevice fn = ICD_FN(vkCreateDevice);
  if (!fn) return VK_ERROR_INITIALIZATION_FAILED;
  return fn(physicalDevice, pCreateInfo, pAllocator, pDevice);
}

void vkDestroyDevice(VkDevice device, const VkAllocationCallbacks *pAllocator) {
  PFN_vkDestroyDevice fn = ICD_FN(vkDestroyDevice);
  if (fn) fn(device, pAllocator);
}

void vkGetDeviceQueue(VkDevice device, uint32_t queueFamilyIndex, uint32_t queueIndex,
                      VkQueue *pQueue) {
  PFN_vkGetDeviceQueue fn = ICD_FN(vkGetDeviceQueue);
  if (!fn) { if (pQueue) *pQueue = VK_NULL_HANDLE; return; }
  fn(device, queueFamilyIndex, queueIndex, pQueue);
}

void vkGetDeviceQueue2(VkDevice device, const VkDeviceQueueInfo2 *pQueueInfo, VkQueue *pQueue) {
  PFN_vkGetDeviceQueue2 fn = ICD_FN(vkGetDeviceQueue2);
  if (!fn) { if (pQueue) *pQueue = VK_NULL_HANDLE; return; }
  fn(device, pQueueInfo, pQueue);
}

/* ---- swapchain (KHR) ---- */

VkResult vkCreateSwapchainKHR(VkDevice device, const VkSwapchainCreateInfoKHR *pCreateInfo,
                              const VkAllocationCallbacks *pAllocator, VkSwapchainKHR *pSwapchain) {
  PFN_vkCreateSwapchainKHR fn = ICD_FN(vkCreateSwapchainKHR);
  if (!fn) return VK_ERROR_EXTENSION_NOT_PRESENT;
  return fn(device, pCreateInfo, pAllocator, pSwapchain);
}

void vkDestroySwapchainKHR(VkDevice device, VkSwapchainKHR swapchain,
                           const VkAllocationCallbacks *pAllocator) {
  PFN_vkDestroySwapchainKHR fn = ICD_FN(vkDestroySwapchainKHR);
  if (fn) fn(device, swapchain, pAllocator);
}

VkResult vkGetSwapchainImagesKHR(VkDevice device, VkSwapchainKHR swapchain,
                                 uint32_t *pSwapchainImageCount, VkImage *pSwapchainImages) {
  PFN_vkGetSwapchainImagesKHR fn = ICD_FN(vkGetSwapchainImagesKHR);
  if (!fn) { if (pSwapchainImageCount) *pSwapchainImageCount = 0; return VK_ERROR_EXTENSION_NOT_PRESENT; }
  return fn(device, swapchain, pSwapchainImageCount, pSwapchainImages);
}

VkResult vkQueuePresentKHR(VkQueue queue, const VkPresentInfoKHR *pPresentInfo) {
  PFN_vkQueuePresentKHR fn = ICD_FN(vkQueuePresentKHR);
  if (!fn) return VK_ERROR_EXTENSION_NOT_PRESENT;
  return fn(queue, pPresentInfo);
}

#endif /* USE_VULKAN && NETHERSX2_VK_ICD_ONLY */
