---
title: Building from Source
description: "Step-by-step instructions on building lsfg-vk from source."
type: docs
weight: 2
---

This guide provides step-by-step instructions on how to build lsfg-vk from source code.

### Prerequisites
Before you begin, ensure you have the required packages installed on your system.

You will need the following dependencies:
- Common build tools, such as git, curl, etc.
- A C++ compiler that supports the C++20 standard or later
- CMake (version 3.10 or higher)
- Ninja build system (other build systems may work, but Ninja is recommended)
- Vulkan SDK
- Qt6 and Qt6Quick (only needed when building lsfg-vk-ui)

The list of required packages may vary depending on your operating system. Below are the installation commands for some common Linux distributions.

{{< details title="Arch Linux" closed="true" >}}
  Install the required packages using pacman:
  ```sh
  sudo pacman -S --needed \
    git curl \
    llvm clang \
    cmake ninja \
    vulkan-headers vulkan-icd-loader \
    qt6-base qt6-declarative
  ```
{{< /details >}}

{{< details title="Ubuntu / Debian / Mint" closed="true" >}}
  Install the required packages using apt:
  ```sh
  sudo apt install -y \
    git curl \
    llvm clang clang-tools clang-tidy \
    cmake ninja-build pkg-config \
    libvulkan-dev \
    mesa-common-dev \
    qt6-base-dev qt6-base-dev-tools \
    qt6-tools-dev qt6-tools-dev-tools \
    qt6-declarative-dev qt6-declarative-dev-tools
  ```
{{< /details >}}

{{< details title="Fedora" closed="true" >}}
  Install the required packages using dnf:
  ```sh
  sudo dnf install -y \
    git curl \
    llvm clang clang-tools-extra \
    cmake ninja-build pkgconf-pkg-config \
    vulkan-loader-devel \
    mesa-libGL-devel \
    qt6-qtbase-devel \
    qt6-qttools-devel \
    qt6-qtdeclarative-devel
  ```
{{< /details >}}

### Building and Installing lsfg-vk

1. **Clone the Repository**

Clone the lsfg-vk repository from git.lsfg-vk.dev:
```sh
git clone https://git.lsfg-vk.dev/lsfg-vk.git
cd lsfg-vk
```

Optionally, you can checkout a specific release tag:
```sh
git ls-remote --tags # List all available tags
git checkout tags/<desired-tag>
```

2. **Configure the Build With CMake**

The recommended way to configure lsfg-vk is:
```bash
cmake -B build -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DCMAKE_INTERPROCEDURAL_OPTIMIZATION=ON \
    -DCMAKE_INSTALL_PREFIX=/usr/local \
    -DCMAKE_CXX_COMPILER=clang++ \
    -DLSFGVK_BUILD_UI=ON
```

However, lsfg-vk provides several CMake options to customize the build process:
- `CMAKE_BUILD_TYPE`: Set to `Release` for optimized builds or `Debug` to build for debugging.
- `CMAKE_INTERPROCEDURAL_OPTIMIZATION`: Set to `ON` to enable link-time optimization (LTO) for slightly better performance.
- `CMAKE_INSTALL_PREFIX`: Specify the installation directory (default is `/usr/local`).
- `LSFGVK_BUILD_LAYER`: Set to `ON` to build the Vulkan layer (default is `ON`).
- `LSFGVK_BUILD_UI`: Set to `ON` to build the user interface (default is `OFF`).
- `LSFGVK_BUILD_CLI`: Set to `ON` to build the command-line interface (default is `ON`).
- `LSFGVK_INSTALL_LIBRARIES`: Set to `ON` to install the development libraries (default is `OFF`).
- `LSFGVK_LAYER_LIBRARY_PATH`: Override the path to the Vulkan layer library (by default, Vulkan will search the systems library path).
- `LSFGVK_LAYER_MULTILIB_X86`: When compiling the 32-bit layer in a multilib environment, set to `ON` to append `_x86` to the Vulkan layer name and `.x86` to the library and manifest files.
- `LSFGVK_MANAGED`: Set to `ON` to make lsfg-vk skip checking missing files and assume a package manager is managing the installation. Please enable when packaging lsfg-vk for your distribution.

Please keep in mind that installing to non-system paths will require `LSFGVK_LAYER_LIBRARY_PATH` to be set accordingly (e.g. `../../../lib/liblsfg-vk-layer.so`).

3. **Build the Project**

Build the project using Ninja:
```bash
cmake --build build
```

4. **Install the Project**

Install the built files to the specified installation prefix:
```bash
sudo cmake --install build
```

Keep track of installed files in case you wish to uninstall them later.
