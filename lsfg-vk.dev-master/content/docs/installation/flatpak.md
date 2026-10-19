---
title: Flatpak
description: "Installing lsfg-vk for use with Flatpak applications."
type: docs
weight: 1
---

If you want to use lsfg-vk with Flatpak applications, you must also install the Vulkan layer into the Flatpak runtimes.

You can also install the graphical interface as a Flatpak application.

## Installation
There are two ways to install lsfg-vk into Flatpak. In both cases you must have `flathub` as a user-wide repository.

### Via Flathub
The Vulkan layer is available on Flathub. You can install it with the following commands (omit `--user` in a system-wide installation):

```sh
flatpak install --user org.freedesktop.Platform.VulkanLayer.lsfgvk//24.08
flatpak install --user org.freedesktop.Platform.VulkanLayer.lsfgvk//25.08
```

If you require an older runtime (23.08), you must install it manually as shown in the next section. Similarly, if you want to install the graphical interface, you must also install it manually.

### Via flatpak-builder
This method requires `flatpak-builder` to be installed on your system.

>[!NOTE]
>If you can't install `flatpak-builder`, you can use the org.flatpak.Builder flatpak instead.
>For this, you will need to edit `./dist/flatpak/build.sh` and replace `flatpak-builder` with `flatpak run org.flatpak.Builder`.

First, clone the repository and navigate into it:
```sh
git clone https://git.lsfg-vk.dev/lsfg-vk.git
cd lsfg-vk
```

By default this will build the latest unstable version. If you want to build a specific release, check out the corresponding tag:
```sh
git ls-remote --tags # List all available tags
git checkout tags/<desired-tag>
```

Then use the provided script to build all Flatpak bundles:
```sh
./dist/flatpak/build.sh
flatpak --user install build-flatpak/org.freedesktop.Platform.VulkanLayer.lsfgvk_23.08.flatpak
flatpak --user install build-flatpak/org.freedesktop.Platform.VulkanLayer.lsfgvk_24.08.flatpak
flatpak --user install build-flatpak/org.freedesktop.Platform.VulkanLayer.lsfgvk_25.08.flatpak
flatpak --user install build-flatpak/gay.pancake.lsfg-vk-ui.flatpak # For graphical interface
```

## Permissions
Before using lsfg-vk with Flatpak applications, you must grant them access to the configuration directory and Lossless Scaling.

For example, to grant access to `io.mpv.Mpv`, run the following commands:
```sh
export appid=io.mpv.Mpv
mkdir -p ~/.config/lsfg-vk
flatpak override --user --filesystem=/home/$USER/.config/lsfg-vk:rw $appid
flatpak override --user --filesystem=/home/$USER/.local/share/Steam/steamapps/common:ro $appid
flatpak override --user --env=LSFGVK_CONFIG=/home/$USER/.config/lsfg-vk/conf.toml $appid
```
