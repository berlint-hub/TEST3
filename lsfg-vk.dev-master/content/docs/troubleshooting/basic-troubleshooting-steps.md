---
title: Basic Troubleshooting Steps
description: "Troubleshooting steps that solve common issues with lsfg-vk."
type: docs
weight: 1
---

If lsfg-vk does not seem to be doing *anything*:
- Ensure the application you are trying to run is using Vulkan (not OpenGL).
- Ensure you are running a 64-bit application (try `PROTON_USE_WOW64=1` with 32-bit applications).
- Run `lsfg-vk-cli validate` and `lsfg-vk-cli healthcheck` to check your configuration and installation.
  - You may need to run `~/.local/bin/lsfg-vk-cli` instead.
- Launch the application with the environment variable `VK_LOADER_DEBUG=layer` set.
  - Look for lines mentioning `VK_LAYER_LSFGVK_frame_generation` inbetween `<Loader>` and `<Device>`.
  - If you can't find any, try again using `LSFGVK_ENV=1`.
    - If it still doesn't show up, you may be running in a Flatpak.
    - If it does show up, the `active_in` property of your profile is misconfigured. Reconfigure it, then try again without `LSFGVK_ENV=1`.
    - Otherwise, revisit the installation steps for lsfg-vk.
- Check for warnings/errors from lsfg-vk in the terminal/log output. These will often give clues as to what is going wrong.
- If there are no errors/warnings and you have gone through all the above steps, move onto the next section.

If lsfg-vk is loaded and can't find the lsfg-vk.dll file, this might be due to Steam's sandboxing. Other partitions are typically hidden from Steam, so lsfg-vk.dll may not be found. Move lsfg-vk.dll to your main partition (somewhere in `~/`) and adjust the dll path in the configuration.

If lsfg-vk is loaded but frame generation is not working:
- (When using `pacing_mode = vsync`): Enable (or disable) V-Sync in your game settings.
- (When using `pacing_mode = vsync` on Gamescope/SteamDeck): Set `ENABLE_GAMESCOPE_WSI=0`.
- (When using `pacing_mode = vsync` on Wayland): Try running in a window.
- Disable in-game upscaling options (e.g., DLSS, FSR, etc.).
- Disable other Vulkan layers (e.g., VkBasalt or MangoHud).

Should none of the above help, move on to [this section](../reporting-bugs) to report a bug.
