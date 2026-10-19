---
title: Contributing
description: "Guidance on how to contribute to lsfg-vk"
type: docs
weight: 6
---

>[!INFO]
>For financial contributions, you can donate to me over at [GitHub Sponsors](https://github.com/sponsors/PancakeTAS) or [Ko-fi](https://ko-fi.com/pancaketas). Thank you!

There are a few things you need to be aware of before contributing code to lsfg-vk.

### License
As part of the recent switch from GitHub to a self-hosted infrastructure (and the accompanied rewrite), I decided to change the license of lsfg-vk from MIT / GPLv3 to **CC BY-NC-ND 4.0**.

This new license prohibits any commercial use of lsfg-vk (NC), and it also prohibits any and all derivatives (ND). This means you **cannot** create a "fork" (modified reupload) of the source code or binaries produced from it. Read the LICENSE.txt file in the repository root for the full license details.

My reason for this change is detailed in [this blog post](/blog/important-changes-to-lsfg-vk).

Regardless, I still appreciate any contribution to lsfg-vk.

### Contributing
If you wish to contribute to lsfg-vk, you must format your patch into an Email and send it to me at patches@lsfg-vk.dev. Please keep your Email in plain text and don't use any formatting.

Example workflow for formatting a patch:
```bash
$ git commit
[master a5d8b4b] fix: Do not respect XDG_CONFIG_HOME inside of Flatpak
 2 files changed, 4 insertions(+), 1 deletion(-)

$ git format-patch -1 HEAD
0001-fix-Do-not-respect-XDG_CONFIG_HOME-inside-of-Flatpak.patch
```

Ideally align your commit names and code-style with mine, but I will likely edit the contribution anyways, so don't worry about it too much.

Here is an example patch file:
```patch
From a5d8b4b81ae425bd983030c83b19833d8756d2ac Mon Sep 17 00:00:00 2001
From: PancakeTAS <pancake@mgnet.work>
Date: Sat, 1 Aug 2026 03:58:43 +0200
Subject: [PATCH] fix: Do not respect XDG_CONFIG_HOME inside of Flatpak

---
 dist/flatpak/lsfg-vk-ui/gay.pancake.lsfg-vk-ui.yml | 1 +
 lsfg-vk-config/src/config.cpp                      | 4 +++-
 2 files changed, 4 insertions(+), 1 deletion(-)

diff --git a/dist/flatpak/lsfg-vk-ui/gay.pancake.lsfg-vk-ui.yml b/dist/flatpak/lsfg-vk-ui/gay.pancake.lsfg-vk-ui.yml
index 79097c3..6bc98a1 100644
--- a/dist/flatpak/lsfg-vk-ui/gay.pancake.lsfg-vk-ui.yml
+++ b/dist/flatpak/lsfg-vk-ui/gay.pancake.lsfg-vk-ui.yml
@@ -12,6 +12,7 @@ finish-args:
   - --socket=wayland
   - --device=dri
   - --filesystem=xdg-config
+  - --env=LSFGVK_FLATPAK=1

 modules:
   - name: lsfg-vk-ui
diff --git a/lsfg-vk-config/src/config.cpp b/lsfg-vk-config/src/config.cpp
index 30188a2..05b724d 100644
--- a/lsfg-vk-config/src/config.cpp
+++ b/lsfg-vk-config/src/config.cpp
@@ -39,8 +39,10 @@ std::filesystem::path lsfgvk::defaultConfigPath() {
         path = std::filesystem::path(home) / ".config" / "lsfg-vk" / "conf.toml";
     }

+    const bool isFlatpak{std::getenv("LSFGVK_FLATPAK") != nullptr};
+
     const char* xdgConfigHome{std::getenv("XDG_CONFIG_HOME")};
-    if (xdgConfigHome && *xdgConfigHome != '\0') {
+    if (xdgConfigHome && *xdgConfigHome != '\0' && !isFlatpak) {
         path = std::filesystem::path(xdgConfigHome) / "lsfg-vk" / "conf.toml";
     }

--
2.55.0
```

Due to the CC BY-NC-ND 4.0 license, you must either assign copyright of your contribution to me, or grant me a perpetual, worldwide, non-exclusive, royalty-free, irrevocable license to use, reproduce, distribute, sublicense, publicly display, and modify your contribution. You must also confirm that you are the rights holder of the contribution and it does not infringe on third-party rights.

This mouthful is typically seen in Contributor License Agreements in other open source software. Make sure to agree to either one of the two options and put it into the Email, else I cannot use the contribution.

### Derivatives
If you want to contribute an entirely new feature, perhaps maintain a separate branch for lsfg-vk or otherwise integrate lsfg-vk into the rest of the ecosystem, feel free to reach out at derivatives@lsfg-vk.dev.
