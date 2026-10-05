# models/

Drop ESRGAN-family checkpoints (`.pth`, `.safetensors`) here – TexUp lists every file in this
folder in its model dropdown. Any architecture supported by
[spandrel](https://github.com/chaiNNer-org/spandrel) works: ESRGAN / RealESRGAN (RRDB),
Real-ESRGAN Compact (SRVGGNet), SPAN, OmniSR, DAT, HAT, SwinIR, …

Where to get them: **<https://openmodeldb.info>** (filter by *scale* and *architecture*).

Tips for real-time PS2 textures on an RTX 4080:

| Need | Pick |
|---|---|
| Max quality, classic look | `4x-UltraSharp`, `4x_foolhardy_Remacri`, `4x_NMKD-Siax_200k` (RRDB/ESRGAN, ~20–60 ms per 256² texture in FP16) |
| Fastest (10× quicker, great for busy scenes) | any **Compact** or **SPAN** model, e.g. `4x-ClearRealityV1`, `2x-AnimeSharpV4` |
| 2D / anime-style games | `2x-AnimeSharpV4`, `4x-AnimeSharp` |

Files are ignored by git (see `.gitignore`) – they are big and licensed separately.
