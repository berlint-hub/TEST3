---
title: Configuration Options
description: "Documentation for every configuration option available in lsfg-vk."
type: docs
weight: 1
---

There are two types of configuration options. Global options apply to all profiles and profile options only apply to a single profile.

### Global / `[global]`
- **Path to Lossless Scaling / `dll`**: By default, lsfg-vk will search certain hardcoded directories for Lossless Scaling. If you have Lossless Scaling installed to a custom location, you can specify the full path to the "lsfg-vk.dll" file inside of it here.
- **Allow half-precision / `allow_fp16`**: If enabled, this will allow lsfg-vk to take advantage of half-precision shader operations if supported by the GPU. This has a giant performance uplift on AMD GPUs, but does not affect NVIDIA GPUs (GTX 1000-series will actually see a performance **decrease**). This option **does not** influence quality. (Default: `true`)
- **(Hidden) / `log_level`**: The level of logging to output. Can be either `debug`, `info`, `warning` or `error`. (Default: `info`)
- **(Hidden) / `log_file`**: An optional file path to write logs to. Can be useful in case stderr is swallowed by the application.

Please note that the Steam runtime may hide other partitions from the game, so it is recommended to have lsfg-vk.dll on your main partition.

### Profile / `[[profile]]`
- **Profile Name / `name`**: The name of the profile, displayed in the graphical interface. Additionally, this is used when selecting a profile through the `LSFGVK_PROFILE` environment variable.
- **Active In / `active_in`**: A list of 1) linux binary names, such as `mpv`, 2) windows executables, such as `GenshinImpact.exe` and 3) process names, such as `GameThread`. It is also possible to specify the last part of a path (e.g., `Ghostrunner2/Binaries/Win64/Ghostrunner2-Win64-Shipping.exe`). When a process matching one of these rules is detected, this profile will be activated.
- **Multiplier / `multiplier`**: The frame generation multiplier. A value of `3` means that for every frame rendered by the application, lsfg-vk will generate 2 additional frames. (Default: `2`)
- **Flow Scale / `flow_scale`**: The resolution scale at which the motion vectors are calculated. A lower value means better performance, but worse quality. (Default: `1.0`)
- **Performance Mode / `performance_mode`**: When enabled, a significantly lighter frame generation model is used. This has a minor quality impact, but greatly improves performance.
(Default: `false`)
- **Pacing Mode / `pacing`**: Change how lsfg-vk handles frame pacing. See [here](../pacing-modes) for details. (Default: `vsync`).
- **Quirks: Override Present Mode / `override_present_mode`**: When enabled, lsfg-vk will override the present mode to Vsync/FIFO, as required for frame pacing to function correctly. Do not turn this option off, unless you know what you are doing. (Default: `true`)
- **Quirks: Preserve Swapchain Image Count / `preserve_swapchain_image_count`**: When enabled, lsfg-vk will preserve the swapchain image count of the application. This prevents a crash in some Vulkan games, but it may cause stuttering and slowdown in other games. (Default: `false`)

The "Multiplier", "Flow Scale" and "Performance Mode" options can be **hot-reloaded**, meaning that changes to these options will take effect immediately without needing to restart the application.
