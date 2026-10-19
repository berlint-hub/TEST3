---
title: Porting LSFG to native Vulkan
type: blog
date: 1751752800
weight: -1
tags:
  - Technical
  - Outdated
---

This document details the process of getting LSFG to work in a native Vulkan environment. It is not a guide. It is not a tutorial for doing this yourself. It simply describes the psychological torture I went through to make this project work

<!--more-->

### Figuring out how LSFG works
The first thing I did was open Lossless Scaling in dnSpy, which quickly revealed that all the magic was in Lossless.dll file.\
Then I opened up Lossless.dll in IDA... and quickly found out that this is a D3D11 program.

I closed dnSpy and IDA. What this teaches you is that throwing IDA at something is not always the right move.

### Getting D3D11 to run on Linux
_"The first step to translating D3D11 to Vulkan, is to not translate D3D11 to Vulkan. Instead, it is to translate D3D11 to D3D11, and then to Vulkan."_ - Me (after not sleeping for 2 days)

It's true!

When you're trying to translate something that utilizes the GPU, it often comes in multiple parts:\
The **shaders** that run on the actual GPU and the **pipeline** used to coordinate the shaders

Like I said, I didn't translate D3D11 to Vulkan just yet. Instead I used what the Steam Deck, Proton, and native Linux titles from Valve use: DXVK.

DXVK is a project that pretends to be D3D11 and provides just enough methods to run most if not all Windows games written in D3D8 through D3D11 on Linux. It can also be used natively without proton/wine! And that's what I did.

#### Step 1: The shaders
The first step to translating everything to D3D11 was to get the shaders to work.
Vulkan uses SPIR-V and D3D11 uses DXBC. Thankfully DXVK can translate the shaders just fine.

I wrote a hook for Lossless Scaling that intercepted all D3D11 calls and dumped the shader files to my computer. Then I took those shader files and copied them over to Linux. I wrote a really small D3D11 app that loaded one shader, loaded a texture that I dumped into it, and dumped the outputs. Voila, WinMerge tells me the files are identical!

I did this to a few other shaders until I moved on to actually translating the pipeline.

#### Step 2: The pipeline
Translating the shader pipeline is the fun part of all of this. Attaching RenderDoc to LS on Windows is near impossible because it isn't a game by itself. Current RenderDoc simply does not detect anything and older versions crash immediately. NVIDIA Nsight Graphics also crashed when taking a capture.

The solution is a mix of IDA to get the dispatch math, self written C++ programs to dump the D3D11 commands, and a heck ton of WinMerge to compare my shader pipeline with the original.

Step by step I rewrote the shader pipeline in D3D11, just like Valve did with Portal 2, until I was done.
This process took a huuuge amount of time and there were many barricades in the way like when stuff just wouldn't work for no reason.

### Translating D3D11 to Vulkan
Having a working pipeline on Linux now means I can attach RenderDoc and get the exact Vulkan calls in a neatly organized manner.

This was my first time writing something in Vulkan, so I had to do quite a bit of research on Vulkan and read quite a bit of it. Originally my plan was to keep the DXVK pipeline and simply use Vulkan to hook the game. This plan was cut short however, because D3D11 does not have any synchronization primitives and Vulkan exclusively works with synchronization primitives. Since that didn't work, I had to translate the entire pipeline to Vulkan.

This process was fairly smooth and I did it in 27 hours. Twenty seven.. consecutive.. hours.. with no sleep.

_"Sometimes, no sleep is all you ne-"_ Okay I'm gonna stop with these stupid quotes, lol.

And there we have it, the Vulkan pipeline is completed. What follows is a bit of PE parsing to extract shaders from the exe at runtime, so that not everyone using the project needs to go through my painful process. And also a statically linked subset of DXVK is now used to translate the shaders without actually using DXVK.

### Credits
Huge thanks to [0xNULLderef](https://github.com/0xNULLderef) who sat through this with me. They were the first to suggest native DXVK and taught me how to use IDA and RenderDoc. This project would not have worked without them!
