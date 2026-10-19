---
title: Important changes to lsfg-vk
type: blog
weight: -3
date: 1787865558
tags:
  - Announcement
---

In preparation for the v2.0.0 release of lsfg-vk, I have decided to make a few changes to lsfg-vk. I hope these changes are well-received, but I understand if you disagree with some of the decisions.

<!--more-->

## Moving from GitHub to self-hosted infrastructure
GitHub as a platform has been getting increasingly worse over the past few years. The platform constantly shoves AI and Copilot in your face, all while having worse uptime than ever before. While features such as GitHub Actions and Pages are nice, they are nothing I can't replace with my own.

I decided to move lsfg-vk's git repository to my own infrastructure and remove lsfg-vk's source code from GitHub entirely. You can find the new repository at [git.lsfg-vk.dev](https://git.lsfg-vk.dev). ~~In case my infrastructure ever goes down, I have also set up a mirror to [Codeberg](https://codeberg.org/PancakeTAS/lsfg-vk).~~

I am still working on a replacement for GitHub Issues, so for the time being I will be using [Codeberg Issues](https://codeberg.org/PancakeTAS/lsfg-vk/issues) for tracking development.
 Please do not create any issues on there, as this exists purely for tracking the development of lsfg-vk.

 Feature requests, bug reports and help requests will remain on GitHub and Discord for the time being, but I am considering alternatives as well.

 As for GitHub Actions, I have set up my own runner which will autobuild each commit and publish it to [builds.lsfg-vk.dev](https://builds.lsfg-vk.dev). You can always find a pre-built version of the latest lsfg-vk there, alongside archived builds.

tl;dr:
- Git repository moved to [git.lsfg-vk.dev](https://git.lsfg-vk.dev) ~~mirrored to [Codeberg](https://codeberg.org/PancakeTAS/lsfg-vk)~~
- Issues will be tracked on [Codeberg Issues](https://codeberg.org/PancakeTAS/lsfg-vk/issues) for now
- Pre-built versions of lsfg-vk will be available at [builds.lsfg-vk.dev](https://builds.lsfg-vk.dev)
- Feature requests, bug reports and help requests will remain on GitHub and Discord for the time being

## Starting a new git repository
As part of the move to self-hosted infrastructure, I have decided to empty out the git repository.

The original lsfg-vk v1 source code was more of a "proof-of-concept", than a proper implementation. As mentioned in my old blog posts, this was the first time working with Vulkan and I haven't had much C++ experience either.

It has been nearly 1.5 years since I started writing lsfg-vk v2 from scratch, and the source code is different in every way. That's why I decided to combine the move to self-hosted infrastructure, license change (upcoming) and major rewrite of the source code into a new git repository.

Even over the past few months, the source code has changed so significantly to the point where I never even updated the GitHub repository.

I also decided to significantly expand the documentation (and homepage), which is now hosted at [lsfg-vk.dev](https://lsfg-vk.dev) and whose source code resides in a separate git repository. I hope my changes make it easier to get into lsfg-vk and use all of its features.

The archived GitHub repository will always be available [here](https://git.lsfg-vk.dev/lsfg-vk-archive).

tl;dr:
- The git repository is new, it doesn't contain lsfg-vk v1 source code anymore.
- The documentation and homepage are now hosted at [lsfg-vk.dev](https://lsfg-vk.dev).. you're reading it right now!

## Changes to the lsfg-vk license
The original source code of lsfg-vk v1 was licensed under MIT. While rewriting lsfg-vk for v2, I switched the license to GPLv3. With the move to self-hosted infrastructure, I decided to change the license again.

I love open-source software and I love software freedom, but in current times it seems to be abused more often than not.

Especially with GitHub shoving AI and Copilot into every corner, it is no surprise that **over 87%** of all forks (not including lsfg-vk v1 or plain mirrors) are AI-generated, most of which abandoned after a few commits that never worked in the first place.

There have also been way too many cases of people making an AI slop fork with the sole intention of either misleading users or making money off of it.

This is not what open-source software is about to me. It drains my time, energy and most importantly motivation to keep working on lsfg-vk. At the end of the day, lsfg-vk is my personal passion project.

I don't want to have to deal with all of this, I just want to write code and make it available for everyone to use. This is why I decided to change the license of lsfg-vk to *CC BY-NC-ND 4.0*. This new license prevents any commercial use and all derivative works, while still allowing everyone to use/reupload lsfg-vk, read the source code, and learn from it.

If you want to contribute to lsfg-vk, you can still do so by contacting me directly. See [this](/docs/contributing) page for more information. If you want to integrate lsfg-vk, perhaps maintain a fork, reach out to me and we can discuss it.

tl;dr:
- The license of lsfg-vk has been changed to *CC BY-NC-ND 4.0*.
- This prevents commercial use and derivative works.
- If you want to contribute, contact me directly. See [here](/docs/contributing) for more information.
- The decision was made to protect my time, energy and motivation from malicious AI slop forks.

## Release v2.0.0-rc1
The v2.0.0 release of lsfg-vk has been in the works for nearly 1.5 years now. Originally I wanted to release version 2 of lsfg-vk with at least newer frame pacing, possibly adaptive frame generation and dual-GPU.

As you can probably tell, it turns out these features are harder to implement than they seem at first. I will probably write another blog post entirely about the entire journey of getting there. While most of the details are figured out by now, it will take me a while to implement them.

It's been 1.5 years since the rewrite has begun and so many new features have been added already, meanwhile most users are on a version that doesn't even have FP16 acceleration.

This is why I decided to release v2 now, with all of the features that are ready so far. I hope this isn't too disappointing, and I'll try to get new updates out more frequently, rather than build up big updates.

With that out of the way, what are the new features anyways?
- An entirely new bindless pipeline has been written. This pipeline brings a bunch of new features with it.
  - FP16 acceleration: On systems with a 2:1 FP16 ratio, such as most AMD laptops and handhelds, performance will be 2x-3x as fast as before, without losing any quality at all.
  - Memory reuse: The new bindless pipeline reuses memory wherever possible, using only 30% as much memory as before. This beats even the Windows version by a landslide!
  - Dropping Vulkan to 1.2: This might seem like a downgrade at first, but dropping the required Vulkan version from 1.3 to 1.2 actually has no effect on lsfg-vk itself. Instead, it enables support for lsfg-vk to (as far as I know) every single Vulkan-capable GPU ever!
- Processes can be identified via Linux binary, Windows executable and Steam App ID, meaning it's easier than ever to set up a profile for your game.
- A new tool `lsfg-vk-cli` can be used to benchmark lsfg-vk and validate the configuration file.
- The user interface is now Qt6-based, no longer GTK+Rust. This brings the filesize down from 70 MB to just a few kilobytes. It will also integrate neatly into the KDE desktop.
- Prebuilt lsfg-vk now also contains a layer for 32-bit games, which works seamlessly.
- Various bug fixes and minor quality improvements.

You can install this version of lsfg-vk right now by following [this guide](/docs/getting-started)! Make sure to uninstall lsfg-vk v1 properly first and keep in mind that the config layout of v2 has been changed. More details on this can be found in the documentation.

Version 2.0.0 will release shortly after this one, including any last minute bug fixes. A full changelog will be released alongside it as well.

UPDATE: Codeberg's TOS prohibits uploading source code under the new license, therefore I have removed the mirror.
