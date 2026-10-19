---
title: Validating
description: "Validating and healthchecking your lsfg-vk installation."
type: docs
weight: 1
---

The `validate` and `healthcheck` subcommands of lsfg-vk-cli check the configuration file and your installation of lsfg-vk for errors.

### Validating the configuration file

Simply run the `validate` command without any arguments:
```sh
$ lsfg-vk-cli validate
Validating configuration file: "/home/pancake/.config/lsfg-vk/conf.toml"
The configuration file is valid.
```

Should there be any errors in the configuration file, they will be displayed in the output:
```sh
$ lsfg-vk-cli validate
Validating configuration file: "/home/pancake/.config/lsfg-vk/conf.toml"
Unknown key in profile section: acbbtive_in
```

Add `-p` to the command to print the parsed configuration file into the console.

### Legacy, duplicate and missing files

The `healthcheck` command will check for legacy, duplicate and missing files on your system.

Legacy files are files left over from a previous installation of lsfg-vk. These files should be deleted to ensure no conflicts with the main installation:
```sh
$ lsfg-vk-cli healthcheck
Healtcheck was able to find files from old lsfg-vk installations:
- /home/pancake/.local/lib/liblsfg-vk.so
```

Should you have accidentally installed lsfg-vk in multiple locations, the subcommand will also warn you about duplicate files:
```sh
$ lsfg-vk-cli healthcheck
Healtcheck was able to find duplicate lsfg-vk installations:
- /home/pancake/.local/lib/liblsfg-vk-layer.so
  - /usr/lib/liblsfg-vk-layer.so
- /home/pancake/.local/share/vulkan/implicit_layer.d/VkLayer_LSFGVK_frame_generation.json
  - /usr/share/vulkan/implicit_layer.d/VkLayer_LSFGVK_frame_generation.json
```

And finally, should any files be missing from your installation, the subcommand will also warn you about that:
```sh
$ lsfg-vk-cli healthcheck
Healtcheck encountered files missing from the lsfg-vk installation:
- liblsfg-vk-layer.so
```

A clean installation should look like this:
```sh
$ lsfg-vk-cli healthcheck
Healthcheck did not find any issues with the lsfg-vk installation.

Installed lsfg-vk-cli version:   2.0.0
Installed lsfg-vk-layer version: 2.0.0
```

### Listing installed files

If you want to uninstall lsfg-vk, you can append `-l` to the `healthcheck` subcommand to list all manually installed files. This will allow you to delete them manually:
```sh
$ lsfg-vk-cli healthcheck -l
Listing all files from the lsfg-vk installation (may be inaccurate due to managed installation):
- /usr/lib/liblsfg-vk-pipeline.a
- /usr/lib/liblsfg-vk-config.a
- /data/Development/C++/lsfg-vk/build/lsfg-vk-layer/liblsfg-vk-layer.so
- /usr/lib/liblsfg-vk-layer.x86.so
- /usr/include/lsfg-vk
- /usr/include/lsfg-vk-utils
- /usr/share/vulkan/implicit_layer.d/VkLayer_LSFGVK_frame_generation.json
- /usr/share/vulkan/implicit_layer.d/VkLayer_LSFGVK_frame_generation.x86.json
- /usr/share/applications/gay.pancake.lsfg-vk-ui.desktop
- /usr/share/icons/hicolor/256x256/apps/gay.pancake.lsfg-vk-ui.png
- /usr/bin/lsfg-vk-cli
- /usr/bin/lsfg-vk-ui

Healthcheck did not find any issues with the lsfg-vk installation.

Installed lsfg-vk-cli version:   2.0.0
Installed lsfg-vk-layer version: 2.0.0
```

Please note `-l` should not be used when a package manager was used to install lsfg-vk. In that case, you should use your package manager to uninstall lsfg-vk instead of deleting the files manually.
