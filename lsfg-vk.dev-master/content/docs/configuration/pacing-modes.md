---
title: Pacing Modes
description: "Detailed explanation of the pacing modes available in lsfg-vk."
type: docs
weight: 2
---

The pacing mode determines how lsfg-vk synchronizes frame generation with the application's render loop.

- **Vsync / `vsync`**:  No frame pacing. Frames are generated and presented as soon as they are ready. This approach **requires** Vsync, otherwise frames will be skipped.
- _There are no other pacing modes available at this time._

### Background
Traditionally, lsfg-vk did not have frame pacing and would present frames to the screen as soon as they are generated. This approach is flawed, because frames are generated and presented much quicker than your screen refreshes, causing frames to be skipped.

This effect is countered by force-enabling Vsync, as Vulkan will now only process one image per Vblank. Even though this works, it is not ideal as frame pacing only properly works if the target refresh rate is the exact monitor refresh rate. Additionally Vsync introduces latency and may cause issues with VRR in this configuration.
