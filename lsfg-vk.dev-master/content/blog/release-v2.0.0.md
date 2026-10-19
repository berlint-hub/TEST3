---
title: Release v2.0.0
type: blog
weight: -4
date: 1788623421
tags:
  - Announcement
  - Release Notes
---

The long-awaited v2.0.0 release of lsfg-vk is finally here. This release brings a lot of new features, performance improvements and bug fixes.

<!--more-->

## Changelog

- An entirely new bindless pipeline has been written. This pipeline brings a bunch of new features with it.
  - FP16 acceleration: On systems with a 2:1 FP16 ratio, such as most AMD laptops and handhelds, performance will be 2x-3x as fast as before, without losing any quality at all.
  - Memory reuse: The new bindless pipeline reuses memory wherever possible, using only 30% as much memory as before. This beats even the Windows version by a landslide!
  - Dropping Vulkan to 1.2: This might seem like a downgrade at first, but dropping the required Vulkan version from 1.3 to 1.2 actually has no effect on lsfg-vk itself. Instead, it enables support for lsfg-vk to (as far as I know) every single Vulkan-capable GPU ever!
- Processes can be identified via Linux binary, Windows executable and Steam App ID, meaning it's easier than ever to set up a profile for your game.
- A new tool `lsfg-vk-cli` can be used for various tasks.
  - Benchmarking: `lsfg-vk-cli benchmark` can be used to benchmark lsfg-vk and see how well it performs on your system.
  - Validation: `lsfg-vk-cli validate` can be used to validate the configuration file and check for errors.
  - Healthcheck: `lsfg-vk-cli healthcheck` can be used to check for legacy, duplicate and missing files on your system.
- The user interface is now Qt6-based, no longer GTK+Rust. This brings the filesize down from 70 MB to just a few kilobytes. It will also integrate neatly into the KDE desktop.
- Prebuilt lsfg-vk now also contains a layer for 32-bit games, which works seamlessly.
- Various bug fixes and minor quality improvements.
- Compatibility fixes for many, many games and applications.

## Installation
Follow the [getting started guide](/docs/getting-started) to install lsfg-vk v2.0.0 on your system. Please don't forget to switch to the "lsfg-vk" branch of Lossless Scaling on Steam.

If upgrading from lsfg-vk v1, make sure to uninstall it first. If you don't remember which files you installed, then simply install lsfg-vk v2.0.0 and follow the [validation guide](/docs/cli/validation/#legacy-duplicate-and-missing-files) to check for leftover files.

Also keep in mind that the configuration file layout has changed since v1 and will be incompatible with lsfg-vk v2.0.0.

### Quick look at performance

1. Comparing 4x, 2560x1440, 100% flow scale without performance mode on a desktop RTX 5080:

```sh
# lsfg-vk v1 (193 MiB)
$ LSFG_BENCHMARK=2560x1440 vkcube
...
lsfg-vk: Benchmark completed in 8582 ms
  Time taken per real frame: 2.15 ms
  Generated 12000 frames in total at 1398.28 FPS
  Total of 16000 frames presented at 1864.37 FPS

# lsfg-vk v2 (100 MiB)
$ lsfg-vk-cli benchmark -w 2560 -h 1440 -m 4
Benchmark results for lsfg-vk
-----------------------------
Iterations           : 6267
Images per iteration : 3
Total images         : 18801

Elapsed time         : 10.00 seconds
Throughput           : 1880.08 images per second
Time per iteration   : 1.60 ms

Base FPS             : 626.69 fps
Output FPS           : 2506.78 fps
```

Resulting in around a ~34% increase in performance, while using only ~51% as much VRAM.

2. Comparing 2x, 1280x800, 100% flow scale without performance mode on a laptop Radeon 680M:

```sh
# lsfg-vk v1 (100 MiB)
$ LSFG_BENCHMARK=1280x800 vkcube
...
lsfg-vk: Benchmark completed in 46229 ms
  Time taken per real frame: 11.56 ms
  Generated 4000 frames in total at 86.53 FPS
  Total of 8000 frames presented at 173.05 FPS

# lsfg-vk v2 (26 MiB)
$ lsfg-vk-cli benchmark -w 1280 -h 800 -m 2
(lsfg-vk) [ERROR]: Failed to initialize global info:
(lsfg-vk) [ERROR]: - Unknown key in profile section: gpu
Benchmark results for lsfg-vk
-----------------------------
Iterations           : 3027
Images per iteration : 1
Total images         : 3027

Elapsed time         : 10.00 seconds
Throughput           : 302.67 images per second
Time per iteration   : 3.30 ms

Base FPS             : 302.67 fps
Output FPS           : 605.33 fps
```

Resulting in around a ~3.5x increase in performance, while using only ~26% as much VRAM.

3. Users have reported a similar ~3-4x performance increase on a Steam Deck, due to the eliminated bottlenecks.

### Changelog (since v2.0.0-rc1)
- enhancement: `Lossless.dll` is automatically corrected to `lsfg-vk.dll` in the configuration file.
- enhancement: Global properties can now be overriden with environment variables without requiring `LSFGVK_ENV=1` to be set.
- enhancement: `lsfg-vk-cli validate` has been split into `validate` / `healthcheck`.
- enhancement: `lsfg-vk-cli healthcheck` will show the version of lsfg-vk detected on your system.
- fix: `lsfg-vk-ui` now properly launches on older versions of Qt6.
- fix: `lsfg-vk-ui` now lets you select a multiplier of 1 (for bypass).
- fix: Vulkan layers and applications which query `vkGetDeviceProcAddr("vkGetDeviceProcAddr")` will now work properly with lsfg-vk.
- fix: Disabling FIFO or running a compositor with `wp_fifo_v1` will no longer cause lsfg-vk to crash.
- fix: Windows which were put into the background for too long will no longer crash.
- fix: Applications using `VkAllocationCallbacks` will no longer crash.
- fix: A workaround for Vulkan games which incorrectly fetch swapchain images has been added, which should fix crashes in some games.
