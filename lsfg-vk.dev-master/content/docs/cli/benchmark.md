---
title: Benchmarking
description: "How to benchmark system performance with lsfg-vk."
type: docs
weight: 2
---

The `benchmark` subcommand of lsfg-vk-cli measures how fast lsfg-vk can generate frames on your system. This can be used to get a performance estimate, and it is recommended to have a game running in the background while benchmarking.

### Basic usage

At its simplest, the benchmark command can be run without any arguments:
```sh
lsfg-vk-cli benchmark
```
This runs a 10-second benchmark at 1920x1080 using the default flow scale and multiplier.

The benchmark subcommands accepts various arguments to customize the benchmark:
- `-d, --dll <PATH>`: Path to the `lsfg-vk.dll` file.
- `-a, --no-fp16`: Disable FP16 acceleration.
- `-w, --width <INT>` / `-h, --height <INT>`: Width and height of the input frames.
- `-f, --flow <FLOAT>`: Flow scale.
- `-m, --multiplier <INT>`: Multiplier.
- `-p, --performance-mode`: Use performance mode.
- `-g, --gpu <STRING>`: GPU to use.
- `-t, --duration <SECONDS>`: Benchmark duration in seconds.

### Example usage

For instance, to run a 5-second benchmark at 3840x2160 with a flow scale of 0.85 and a multiplier of 2, you would use the following command:
```sh
$ lsfg-vk-cli benchmark -w 3840 -h 2160 -f 0.85 -m 2 -t 5
Benchmark results for lsfg-vk
-----------------------------
Iterations           : 4433
Images per iteration : 1
Total images         : 4433

Elapsed time         : 5.00 seconds
Throughput           : 886.56 images per second
Time per iteration   : 1.13 ms

Base FPS             : 886.56 fps
Output FPS           : 1773.13 fps
```

In the benchmark results, you can see how many iterations were completed and the total number of images generated. The throughput indicates how many images were generated per second and the "Base FPS" & "Output FPS" numbers indicate which output framerate you can expect given the base framerate.
