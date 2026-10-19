---
title: Installing lsfg-vk
description: "Installing lsfg-vk on various Linux distributions."
type: docs
weight: 2
sidebar:
  open: true
---

>[!CAUTION]
>Before proceeding, please make sure you have [Lossless Scaling](https://store.steampowered.com/app/993090/Lossless_Scaling/) installed on Steam.
>
> **Make sure you have switched to the `lsfg-vk` branch!**

There are several different ways to install lsfg-vk.

### Packages (Recommended)
If your distribution provides packages for lsfg-vk, you can simply install them using your package manager.

{{< details title="Arch Linux (AUR)" closed="true" >}}
  Install lsfg-vk from the AUR:
  ```sh
  yay -S lsfg-vk # or lsfg-vk-bin for the pre-built binary
  ```

  Or, if you want the latest (unstable) git build:
  ```sh
  yay -S lsfg-vk-git
  ```

  Please note that these packages are not maintained by me. Always be careful when installing packages from the AUR.
{{< /details >}}

{{< details title="SteamOS" closed="true" >}}
  There is currently no official and supported convenient way to use lsfg-vk in Big Picture Mode.

  The approach that works best is to use the [Decky plugin for lsfg-vk](https://github.com/xXJSONDeruloXx/decky-lsfg-vk), which provides a convenient user interface for lsfg-vk alongside other features. Keep in mind that this is not officially supported and support queries should be directed to the plugin's repository and Discord server.

  Alternatively, the manual installation method will work.
{{< /details >}}

### Manual
If there are no packages available for your distribution, download a build from [builds.lsfg-vk.dev](https://builds.lsfg-vk.dev). These pre-built binaries are compiled on Ubuntu 22.04 and should run on most distributions.

Open a terminal in the folder where you downloaded the archive and extract it:
```sh
tar -xvf file.tar.xz -C ~/.local
```

This will extract lsfg-vk to `~/.local`. If you want to uninstall lsfg-vk later, you must delete all the files that were extracted. Please keep track of all installed files, but in the worst case you can use lsfg-vk-cli to list all known installed files.

The graphical interface optionally requires Qt6 and Qt6 Quick to run. Please make sure you have the corresponding packages installed on your system.

{{< details title="Arch Linux" closed="true" >}}
  Install `qt6-declarative` and `qt6-base` from the official repositories:
  ```sh
  sudo pacman -S qt6-declarative qt6-base
  ```
{{< /details >}}

{{< details title="SteamOS" closed="true" >}}
  The required packages are already included.
{{< /details >}}

{{< details title="Ubuntu / Debian / Mint" closed="true" >}}
  Install various Qt6 packages using apt:
  ```sh
  sudo apt install -y qt6-qpa-plugins libqt6quick6 qml6-module-qtquick-controls qml6-module-qtquick-layouts qml6-module-qtquick-window qml6-module-qtquick-dialogs qml6-module-qtqml-workerscript qml6-module-qtquick-templates qml6-module-qt-labs-folderlistmodel
  ```
{{< /details >}}

{{< details title="Fedora" closed="true" >}}
  Install `qt6-qtdeclarative` and `qt6-qtbase` from the official repositories:
  ```sh
  sudo dnf install qt6-qtdeclarative qt6-qtbase
  ```
{{< /details >}}

### Flatpak

Due to the nature of Flatpak, even if you installed lsfg-vk using one of the methods above, you will still need to install the lsfg-vk layer separately into the Flatpak runtime.

---

{{< cards cols="2" >}}
{{< card link="flatpak" title="Flatpak" icon="server" subtitle="If you wish to use lsfg-vk within Flatpak applications." >}}
{{< card link="building-from-source" icon="beaker" title="Building from Source" subtitle="A guide to building lsfg-vk yourself from source." >}}
{{< /cards >}}
