---
title: lsfg-vk
description: "The lsfg-vk project brings frame generation from Lossless Scaling to Linux."
toc: false
---

# <!-- Don't ask why this is here -->

The **lsfg-vk** project ports the most popular feature from the Windows-exclusive **Lossless Scaling** program to Linux. Through the use of a Vulkan layer, it hooks into Vulkan applications and generates additional frames using **Lossless Scaling's frame generation**.

## Features

With **lsfg-vk**, you can:
- Use **Lossless Scaling Frame Generation v3.1** in every Vulkan application, including games and emulators.
- Automatically enable **lsfg-vk** in games without having to mess with launch options or environment variables.
- Configure frame generation through a convenient Qt6-based GUI.
- Benchmark your GPU's frame generation performance.

Many more things, such as **adaptive frame generation** and **dual-GPU** support are being worked on, and will be available in future releases.

## Getting Started

**lsfg-vk** is designed to work on any Linux system with Vulkan support.
 If your GPU has a Vulkan driver, you should be fine.

Read the [documentation](./docs) to learn how to get started with **lsfg-vk**.

## Source

The source code for **lsfg-vk** is available on [git.lsfg-vk.dev](https://git.lsfg-vk.dev/lsfg-vk). The project is licensed under *CC BY-NC-ND 4.0*, read more about what that means and how to contribute [here](./docs/contributing).

Issue tracking is done on [Codeberg](https://codeberg.org/PancakeTAS/lsfg-vk/issues), and you can also reach out to the developer on [Discord](https://discord.gg/3g6v7J8).
