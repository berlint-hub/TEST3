"""TexUp – real-time AI upscaler for emulator texture dumps (AutoCrispy replacement).

Watches the PCSX2 ``dumps`` folder, runs every new texture through an ESRGAN-family
model on CUDA (via PyTorch + spandrel) and writes the result into ``replacements``,
preserving the PS2 alpha range so PCSX2 renders transparency correctly.
"""

__version__ = "0.1.0"
