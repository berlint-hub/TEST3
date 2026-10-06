# AutoCrispy (fixed build)

Automatically apply AI upscaling on dumped textures.

This is a maintenance fork of **[WalkerMx/AutoCrispy](https://github.com/WalkerMx/AutoCrispy)**.
It keeps the original program, backends and behaviour, and layers a set of bug fixes on top —
mainly around model chaining, the `Threads: All` queue and CPU post-processing.
Licensed under **GPL-3.0**, see [LICENSE](LICENSE).

[![Build](https://github.com/berlint-hub/TEST3/actions/workflows/build.yml/badge.svg)](https://github.com/berlint-hub/TEST3/actions/workflows/build.yml)

---

## What is fixed here

| # | Area | Fix |
|---|------|-----|
| 1 | **Model chaining** | Models are no longer overwritten when reordering; drag & drop stays in sync with the chain; right-click **Edit**/**Delete** act on the item you actually clicked; captions show the real model name. |
| 2 | **Deadlock on `Threads: All`** | Backend output is drained asynchronously, so a process that prints more than the 4 KB pipe buffer can no longer freeze the program. |
| 3 | **Smooth queue on `Threads: All`** | All pending textures are handed to the backend in a single batch — one Python/Vulkan launch instead of a restart per batch. |
| 4 | **`Tile Size: 0` unlocked** | Range widened from `64–1024` to `0–4096`. `0` disables tiling and lets ESRGAN use the whole frame of VRAM. |
| 5 | **Fast CPU post-processing** | `Defringe` and the PS2 alpha passes now work directly on `DirectBitmap.Bits` instead of per-pixel `Color` structures. |

Full technical detail, including the root cause of each bug, is in [CHANGES.md](CHANGES.md).

---

## Building

### Visual Studio

Open `AutoCrispy/AutoCrispy.sln` in Visual Studio 2022 (or newer) with the **.NET desktop
development** workload and the **.NET Framework 4.7.2 targeting pack** installed, then build the
`Release` configuration. There are no NuGet dependencies — every reference is a framework one.

### GitHub Actions

[`.github/workflows/build.yml`](.github/workflows/build.yml) builds the solution with MSBuild on a
Windows runner and uploads `AutoCrispy.exe` as an artifact. It runs on pushes to `main`, on every
pull request, and can be started by hand from the *Actions* tab.

The job is pinned to `windows-2022` on purpose: `windows-latest` currently maps to the
Windows Server 2025 / Visual Studio 2026 image, which only ships the .NET Framework **4.8.1**
targeting pack. This project targets **v4.7.2** and would fail there with `MSB3644`. The
`windows-2022` image still installs `Microsoft.Net.Component.4.7.2.TargetingPack`.

---

## AutoCrispy features

- **Seamless upscaling** — experimental system for improving seamless texture upscales, based on
  [JoeyBallentine's](https://github.com/JoeyBallentine/ESRGAN) `upscale.py` script. Available for
  all backends. For advanced users. See the [manual](MANUAL.md).

- **Model chaining** — arbitrarily chain models for upscaling. Adding a model to a chain
  *snapshots* your current settings for the backend, so you can apply the same backend with
  different settings or models (ESRGAN), or apply any mix of backends in sequence.

- **Defringing** — basic GDI+ defringing scheme. Removes ugly halo artifacts (*fringes*) from
  textures with transparency. Works best where all textures are roughly the same size.

## Backends

Any feature listed is not necessarily the same as the features or requirements of the program. To
work, AutoCrispy requires one of the following to be downloaded, or ESRGAN to be installed.
[Comparison shots and more about the backends](COMPARE.md).

Backend|Scale Range|Denoising Support|Alpha Support|TAA|Custom Filters|Speed|VRAM Requirements|Download
:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:
Waifu2x Caffe|1-4|✔️|✔️|✔️|❌|Slow|Very High|[Link](https://github.com/lltcggie/waifu2x-caffe/releases)
Waifu2x Vulkan|1-2|✔️|✔️|✔️|❌|Average|Medium|[Link](https://github.com/nihui/waifu2x-ncnn-vulkan/releases)
RealSR Vulkan|4-4|❌|✔️|✔️|❌|*Slow*|High|[Link](https://github.com/nihui/realsr-ncnn-vulkan/releases)
SRMD Vulkan|2-4|✔️|✔️|✔️|❌|Average|Medium|[Link](https://github.com/nihui/srmd-ncnn-vulkan/releases)
Waifu2x CPP|1-8|✔️|✔️|❌|❌|Quick|Low|[Link](https://github.com/DeadSix27/waifu2x-converter-cpp/releases)
Anime4K CPP|1-8|❌|✔️|❌|✔️|Quick|Low|[Link](https://github.com/TianZerL/Anime4KCPP)
xBRZ|2-6|❌|✔️|❌|❌|*Quick*|Low|[Link](https://sourceforge.net/projects/xbrz)

### Texconv

AutoCrispy supports [Microsoft's Texconv utility](https://github.com/Microsoft/DirectXTex/wiki/Texconv)
for processing DDS textures. Most DDS formats are supported, as well as many image formats. When
chaining, ensure that the backends you have selected support the format you have chosen (PNG is
widely supported).

To use texconv, place it in the folder with AutoCrispy, or in its own folder inside AutoCrispy's
folder. To set up for DDS files, set the first item in your chain to Texconv, set to "DDS Input".
Then set the last item to Texconv, set to "DDS Output".

### ESRGAN

A PyInstaller build is provided for use with AutoCrispy:<br />
https://github.com/WalkerMx/ESRGAN_Python_Embedded/releases

This does not include any models. [They can be found here.](https://openmodeldb.info/)

Set **Tile Size** to `0` to turn tiling off and let the model run on the whole image at once —
fastest on a card with plenty of VRAM, but it will run out of memory on large textures. Raise it
(512 is a sane default) if the backend reports an out-of-memory error.

## How to use

1. Toss AutoCrispy into the folder of the backend(s) you chose, and run it.
2. Pick the folder where the textures dump.
3. Pick the folder where the new textures need to be.
4. Set your settings. The defaults should work, unless you know what you want.
5. Push the button.

As the textures dump, new upscaled textures are generated, and the originals are optionally
deleted.

Make sure you have enough VRAM if you use multithreading, especially with Caffe and ESRGAN. More
threads & higher upscales dramatically increase the memory requirements.

More info about AutoCrispy and how it works can be found in [MANUAL.md](MANUAL.md).<br />
Guides for some common programs can be found in [GUIDES.md](GUIDES.md).

---

## Credits

AutoCrispy was written by **[WalkerMx](https://github.com/WalkerMx)**; this fork only carries bug
fixes. `DirectBitmap` is by A.Konzel (StackOverflow), converted to VB.NET by WalkerMx.

### Special thanks

Some people have been unusually helpful, or have gone above and beyond to show support for this
project. With their permission, they are listed below.

- **u/devilskin**
- **fefo-dev**
