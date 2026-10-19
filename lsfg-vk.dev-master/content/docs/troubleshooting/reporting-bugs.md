---
title: Reporting bugs
description: "How to report bugs and what information to include."
type: docs
weight: 3
---

When opening a bug report, please include the following information to help us diagnose and fix your issue:
- A detailed description of the issue you are experiencing.
- Details about the system you are running on (OS, GPU, relevant drivers, etc.).
- The game or application you are trying to run (and through what platform: e.g., Steam Proton, native Linux, etc.).
- The relevant section of your lsfg-vk configuration file.
- Which of the steps in the [Basic Troubleshooting Steps](../basic-troubleshooting-steps) you have tried and what the results were.

Ideally, also include a log file with the environment variables `VK_INSTANCE_LAYERS=VK_LAYER_KHRONOS_validation` and `VK_LOADER_DEBUG=layer` set. You might need to install the Vulkan validation layers package for your distribution to do this.

If you're running the game through Steam, this log file is located at `~/.steam/steam/logs/console-linux.txt`. Please clear it before launching the game to ensure it only contains relevant information.

Report bugs in a forum post on the [Discord server](https://discord.gg/5cCP6aACgT) or create a [GitHub discussion](https://github.com/PancakeTAS/lsfg-vk/discussions).
