---
title: Injecting into a Vulkan app
type: blog
date: 1751752800
weight: -2
tags:
  - Technical
  - Outdated
---

This document details the process of injecting frames into a Vulkan app. It describes the mechanism currently in use in lsfg-vk. This is not a guide, nor a tutorial. This is a technical document explaining what I did and how it works.

<!--more-->

### Injecting into a Vulkan app
There's plenty of ways to hook into a Vulkan app. At first this project used an `LD_PRELOAD` approach, where `dlopen`, `dlsym` and `dlclose` were hooked and replaced the Vulkan loader with it's own modded version.
Towards completion of the process I realized there was a better way to do this and seeing how it would fix a lot of issues I decided to implement it.

Enter: Vulkan layers.
When you link against Vulkan, statically or dynamically it does not matter, you're not linking against the actual library, but a loader. This Vulkan loader provides you with two functions called `vkDeviceGetProcAddr` and `vkInstanceGetProcAddr`. Calling these functions returns function pointers for each function requested.

This approach allows the Vulkan loader to return function pointers not to the actual driver, but an intermediate function. These intermediary functions are called layers and Vulkan stacks as many as you want ontop of each other.

lsfg-vk uses an implicit layer, which means it is implicitly enabled simply by existing in one of the many Vulkan layer folders, or by having an environment variable set. In our case, it loads when `ENABLE_LSFG` is set to 1.

### Hooking various functions
Each layer has its own `vkIntanceGetProcAddr` (and corresponding device-level) function. By default this function simply calls the _next_ layer's `vkInstanceGetProcAddr` function. If you wish to actually override a method, you simply store the next layer's function pointer and return your own method, which then eventually calls the next layer.

In order for us to inject frames into Vulkan apps, we need to add a few extensions to the Vulkan instance and each Vulkan device, as well as monitor created swapchains. We override `vkCreate{Instance,Device,SwapchainKHR}` as well as `vkDestroy{Instance,Device,SwapchainKHR}` and modify the creation info to add our own extensions, or in the case of the swapchain, add `TRANSFER_SRC` and `TRANSFER_DST` to the imageUsage flags (so that we can copy the to and from swapchain images).

### Grabbing and inserting frames into the app
This is where stuff gets interesting. First we hook `vkQueuePresentKHR`, which is the function used for presenting an image to the screen. Then we create a command buffer for copying the swapchain image in the parameters to some other image we created. That command buffer now takes the waitSemaphores from the present call and outputs its own semaphore, which is used in the original present call itself. Just like that, we've successfully grabbed a swapchain image. (I say "just like that", but this is several hundreds if not thousands of lines of code).

Inserting frames is where stuff gets interesting. If you just want to insert a frame, acquire an image from the swapchain using `vkAcquireNextImageKHR`, write or copy something to it, and call `vkQueuePresentKHR` a second time. The problem is synchronization.

### Synchronizing frame insertions
You don't know when the frame grab starts, because the waitSemaphores passed to you are GPU-only, you can not access them.
You don't know when your inserted frames are done rendering either, because that is also signaled by a semaphore on the GPU.
All of the code within `vkQueuePresentKHR` runs _immediately_, and you simply hook up one semaphore to another so that the GPU knows what to do. The GPU cant do math and go like "okay last frame took so long, so let's insert our frame once it's done rendering, plus an average time of 5 ms".

There is only two solutions to this problem. Solution one is to create a second thread and do a CPU-wait for rendering to finish, then sleep on the CPU for as long as you need to and insert the frame without a semaphore. The problem is that VkQueues are not thread safe and access needs to be synchronized on the CPU. This means you'll now be adding a mutex to each and every call using VkQueue, _and_ VkSwapchainKHR, _and_ the command buffer, etc.

The other solution is simply turning on the FIFO present mode. This mode queues up calls to vkQueuePresentKHR in order and takes a submitted frame each VBlank. This mode is more commonly known as V-Sync, but it's not exactly that. This solution only works because the amount of swapchain images is limited. Usually between 3 or 8 images can be prepared and presented (this does technically mean, that there may be up to 8 frames of latency if you do not handle this correctly.). Either way, changing the present mode is done in the swapchain creation, so we both switch to the FIFO present mode, as well as increase the amount of frames rendered by one plus the intermediate images. (Adding 1 here, because we're also delaying the rendering of one real frame).

### Integrating the frame generation
Integrating the frame generation into this is not really the target of this document, but I'll mention it anyways.

Frame generation runs in a separate Vulkan device, this is required because we need Vulkan 1.3 for DXVK's Shaders to run. We use the shared memory and shared semaphore extensions to get a file descriptor to image memory on the hook side and pass it to the frame gen side. Then we have two different VkImages on two devices which can both read and write to the same underlying memory.

From here it's a simple double buffering logic and sharing semaphores to synchronize completion and requests.

And there we have it, that's the entire application explained basically.
