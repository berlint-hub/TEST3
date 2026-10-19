---
title: Performance Overlays
description: "Known issues with performance overlays."
type: docs
weight: 2
---

If you are using performance overlays like Steam's built-in overlay, there is a good chance that they will not display the correct frame rate.

This is a known limitation of Vulkan layers, and without directly working with the overlay developers, there is little that can be done to fix this.

### Background
A vulkan layer is a library that sits inbetween the application and the Vulkan driver. It can intercept and modify Vulkan API calls, which is how lsfg-vk implements frame generation.

Performance overlays such as MangoHud or Steam's built-in overlay also use a Vulkan layer.

When multiple Vulkan layers are used, they are loaded in a (kind of) random order. If the performance overlay is loaded before lsfg-vk, it will not be able to see the frame generation and will display the wrong data. This can vary from game to game, distro to distro and is sometimes related to when you last updated a package on your system.
