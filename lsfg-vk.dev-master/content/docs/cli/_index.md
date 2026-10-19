---
title: Using lsfg-vk-cli
description: "Learn how to use the lsfg-vk command-line interface."
type: docs
weight: 4
sidebar:
  open: true
---

Bundles with every installation of lsfg-vk is a command-line interface called lsfg-vk-cli.

Running lsfg-vk-cli is as simple as typing `lsfg-vk-cli` into a terminal. However, if you installed lsfg-vk into `~/.local` as the installation guide suggests, then you will need to specify the full path to the binary: `~/.local/bin/lsfg-vk-cli`:
```sh
$ ~/.local/bin/lsfg-vk-cli
Validate, benchmark, and debug lsfg-vk.

USAGE:
    lsfg-vk-cli <COMMAND> [OPTIONS] [ARGS]

COMMANDS:
    validate     Validate a configuration file
    healthcheck  Check the health of the lsfg-vk installation
    benchmark    Run a benchmark
    debug        Run lsfg-vk on a set of images

SUBCOMMAND OPTIONS:

    validate
        -c, --config <PATH>             Optional path to the configuration file
        -p, --print                     Print the parsed configuration file

    healthcheck
        -l, --list                      List all installed files

    benchmark & debug
        -d, --dll <PATH>                Path to lsfg-vk.dll
        -a, --no-fp16                   Disable FP16 acceleration
        -w, --width <INT>               Width of the input frames
        -h, --height <INT>              Height of the input frames
        -f, --flow <FLOAT>              Flow scale
        -m, --multiplier <INT>          Multiplier
        -p, --performance-mode          Use performance mode
        -g, --gpu <STRING>              GPU to use

    benchmark
        -t, --duration <SECONDS>        Benchmark duration in seconds

    debug
        <folder>                        Path to the debug frames
```

---

{{< cards cols="2" >}}
{{< card link="validation" title="Validation" icon="refresh" subtitle="Validating your installation and configuration" >}}
{{< card link="benchmark" title="Benchmark" icon="chip" subtitle="Using the integrated benchmark" >}}
{{< /cards >}}
