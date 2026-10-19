---
title: Environment Variables
description: "Environment variables that affect lsfg-vk."
type: docs
weight: 3
---

The following environment variables affect lsfg-vk and lsfg-vk-ui:
- `DISABLE_LSFGVK`: If set, lsfg-vk will be completely disabled.
- `LSFGVK_CONFIG`: Path to configuration file.
- `LSFGVK_PROFILE`: Name of the profile to use. If set, this will override automatic profile detection.

If you do not wish to use a configuration file, you can also set configuration options through environment variables. To do this, set `LSFGVK_ENV=1` and then any of the following variables:
- `LSFGVK_DLL_PATH`: Path to the lsfg-vk.dll file.
- `LSFGVK_NO_FP16`: If set to `1`, half-precision will be disabled.
- `LSFGVK_LOG_LEVEL`: The level of logging to output.
- `LSFGVK_LOG_FILE`: Path to the log file.
- `LSFGVK_MULTIPLIER`: Frame generation multiplier.
- `LSFGVK_FLOW_SCALE`: Flow scale value.
- `LSFGVK_PERFORMANCE_MODE`: If set to `1`, performance mode will be enabled.
- `LSFGVK_PACING_MODE`: Pacing mode to use.
- `LSFGVK_OVERRIDE_PRESENT_MODE`: If set to `0`, present mode override will be disabled.
- `LSFGVK_PRESERVE_SWAPCHAIN_IMAGE_COUNT`: If set to `1`, the swapchain image count will be unchanged.
