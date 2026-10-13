#---------------------------------------------------------------------------------
.SUFFIXES:
#---------------------------------------------------------------------------------

ifeq ($(strip $(DEVKITPRO)),)
$(error "Please set DEVKITPRO in your environment. export DEVKITPRO=<path to>/devkitpro")
endif

TOPDIR ?= $(CURDIR)
include $(DEVKITPRO)/libnx/switch_rules

#---------------------------------------------------------------------------------
TARGET		:=	$(notdir $(CURDIR))
APP_TITLE	:=	NetherSX2
APP_AUTHOR	:=	naga
APP_VERSION	:=	1.3.0
BUILD		:=	build
SOURCES		:=	source source/hooks source/switch
DATA		:=	data
INCLUDES	:=	source source/switch \
			launcher/dependencies/build/_deps/libsmb2-src/include \
			launcher/dependencies/build/_deps/libusbhsfs-src/include

#---------------------------------------------------------------------------------
# options for code generation
#---------------------------------------------------------------------------------
ARCH	:=	-march=armv8-a+crc+crypto -mtune=cortex-a57 -mtp=soft -fPIE
LTOFLAGS := -flto=auto -fuse-linker-plugin

# __SWITCH__ for libnx; NETHERSX2 gates the port-specific shim branches.
DEFINES	:=	-D__SWITCH__ -DNETHERSX2 -DCURL_STATICLIB \
			-DNETHERSX2_VERSION='"$(APP_VERSION)"'

ifneq ($(strip $(NETHERSX2_VK_DIAGNOSTIC)),)
DEFINES += -DNETHERSX2_VK_DIAGNOSTIC
endif

# Tegra X1 tuned memcpy/memset/memmove/memcmp/strlen (source/x1mem.c) are wired
# into the core's import table. Set X1_FAST_MEM=0 to fall back to the newlib
# implementations for A/B benchmarking on device.
X1_FAST_MEM ?= 1
ifeq ($(strip $(X1_FAST_MEM)),0)
DEFINES += -DX1_FAST_MEM=0
endif

# --- renderer select: GL (default) or VK (Mesa NVK) ------------------------
# GL and Vulkan are mutually exclusive (switch-mesa's libEGL/GLES and the NVK
# archives both bundle mesa util/nir/compiler object code -> can't co-link).
#   make             -> OpenGL (switch-mesa GLES, unchanged)
#   make RENDERER=VK -> Vulkan (Mesa NVK, vendored flat under vulkan/)
RENDERER ?= GL
MESA_SDK_ROOT ?=
# Which Vulkan driver archive set to link against:
#   vendored (default): the 23 Mesa NVK archives staged under vulkan/lib. That
#                       bundle is NaGaa95's private NVK build, so it is not in
#                       this repository and CI cannot fetch it.
#   nxvk:               the public NVK port -- PalindromicBreadLoaf/nxvk,
#                       Mesa 26.2.2 for Tegra X1/GM20B. `make` there stages a
#                       devkitPro-style portlib: libnvk.a + libnvk_support.a,
#                       described by lib/pkgconfig/nxvk.pc.
#   sdk:                the unified Mesa SDK pointed at by MESA_SDK_ROOT.
MESA_FLAVOR ?= vendored
# Staged nxvk package (nxvk/switch/build/pkg) when it is not installed into
# $DEVKITPRO/portlibs/switch.
NXVK_ROOT ?=
ifneq ($(strip $(MESA_SDK_ROOT)),)
DEFINES += -DUSE_UNIFIED_MESA
endif
ifeq ($(strip $(MESA_FLAVOR)),nxvk)
NXVK_LIBDIR	:= $(if $(strip $(NXVK_ROOT)),$(NXVK_ROOT)/lib,$(PORTLIBS)/lib)
NXVK_INCDIR	:= $(if $(strip $(NXVK_ROOT)),$(NXVK_ROOT)/include,$(PORTLIBS)/include)
INCLUDES	+=	$(NXVK_INCDIR)
# Let nxvk.pc drive the link line when pkg-config is available. The fallback
# mirrors that .pc exactly: nxvk merges the 23 vendored archives into two, so
# the long -l:lib*.a group is neither valid nor needed here.
NXVK_PC	:= $(PREFIX)pkg-config --libs nxvk
NXVK_LIBS	:= $(shell PKG_CONFIG_PATH="$(NXVK_LIBDIR)/pkgconfig$${PKG_CONFIG_PATH:+:$$PKG_CONFIG_PATH}" $(NXVK_PC) 2>/dev/null)
ifeq ($(strip $(NXVK_LIBS)),)
NXVK_LIBS	:= -Wl,--whole-archive -lnvk -Wl,--no-whole-archive -Wl,--start-group -lnvk_support -lz -lexpat -Wl,--end-group -Wl,-u,vk_icdGetInstanceProcAddr
endif
endif
ifeq ($(RENDERER),VK)
DEFINES	+=	-DUSE_VULKAN -DGS_RENDERER=14 -DVK_USE_PLATFORM_VI_NN
SOURCES	+=	source/lsfg \
			third_party/lsfg-vk/lsfg-vk-common/src/helpers \
			third_party/lsfg-vk/lsfg-vk-common/src/vulkan \
			third_party/lsfg-vk/lsfg-vk-backend/src \
			third_party/lsfg-vk/lsfg-vk-backend/src/extraction \
			third_party/lsfg-vk/lsfg-vk-backend/src/helpers \
			third_party/lsfg-vk/lsfg-vk-backend/src/shaderchains
INCLUDES	+=	source/lsfg \
			third_party/lsfg-vk/lsfg-vk-common/include \
			third_party/lsfg-vk/lsfg-vk-backend/include \
			third_party/lsfg-vk/lsfg-vk-backend/src
else
DEFINES	+=	-DGS_RENDERER=12
endif

CFLAGS	:=	-g -Wall -O3 -ffunction-sections -fno-omit-frame-pointer $(LTOFLAGS) \
			$(ARCH) $(DEFINES)
CFLAGS	+=	$(INCLUDE)
CXXFLAGS	:= $(CFLAGS) -std=gnu++20

ASFLAGS	:=	-g $(ARCH)
LDFLAGS	=	-specs=$(DEVKITPRO)/libnx/switch.specs -g $(ARCH) $(LTOFLAGS) -Wl,-Map,$(notdir $*.map)

STORAGE_LIBS := $(TOPDIR)/launcher/dependencies/build/_deps/libsmb2-build/lib/libsmb2.a \
				$(TOPDIR)/launcher/dependencies/build/_deps/libusbhsfs-build/liblibusbhsfs.a \
				$(PORTLIBS)/lib/libntfs-3g.a

# nx: libnx (audren for the AAudio shim, HID, applet, fs). m: libm. No SDL2/
# OpenSL ES -- audio is the in-tree AAudio->audren shim (source/aaudio.c).
ifeq ($(RENDERER),VK)
ifeq ($(strip $(MESA_FLAVOR)),nxvk)
# nxvk: the public Mesa 26.2.2 NVK port for Horizon. It ships two archives
# (libnvk.a + libnvk_support.a) and lib/pkgconfig/nxvk.pc, so the flags come
# from pkg-config (NXVK_LIBS, above) instead of the 23 vendored -l:lib*.a
# entries. -lexpat (driconf) replaces the vendored -lzstd.
LIBDIRS	:= $(NXVK_LIBDIR) $(PORTLIBS) $(LIBNX)
LIBS	:= $(NXVK_LIBS) $(STORAGE_LIBS) -lcurl -lz -lnx -lstdc++ -lm
else
ifneq ($(strip $(MESA_SDK_ROOT)),)
# Unified Mesa SDK: the Vulkan driver and all private Mesa dependencies are
# packaged in one archive. External dependencies stay in devkitPro portlibs.
LIBDIRS	:= $(MESA_SDK_ROOT) $(PORTLIBS) $(LIBNX)
LIBS	:= -Wl,--start-group -lvulkan -lEGL -lGLESv2 -lglapi \
		-lmesa_util_c11 -lblake3 -lmesa_util -lmesa_util_simd -lxmlconfig \
		-Wl,--end-group $(STORAGE_LIBS) -lcurl -lelf -lexpat -lz -lzstd \
		-lnx -lstdc++ -lm
else
# Mesa NVK: 23 vendored static archives (vulkan/lib) linked in one --start-group
# (circular NVK<->runtime<->nir<->compiler deps). -l:libX.a links by exact file
# name (avoids the -lvulkan GROUP-script + the double-prefixed liblibnil...a).
# -lz/-lzstd resolve crc32/ZSTD_*; the DRM/nouveau_ws path is dead-stripped so no
# -ldrm_nouveau. -lstdc++/libgcc unwinder are needed by NAK's bundled Rust.
LIBDIRS	:= $(TOPDIR)/vulkan $(PORTLIBS) $(LIBNX)
LIBS	:= -Wl,--start-group \
		-l:libnvk.a -l:libvulkan_lite_runtime.a -l:libvulkan_runtime.a \
		-l:libvulkan_lite_instance.a -l:libvulkan_instance.a \
		-l:libvulkan_util.a -l:libvulkan_wsi.a \
		-l:libnak.a -l:libnak_rs.a -l:libvtn.a -l:libxmlconfig.a \
		-l:libnil.a -l:liblibnil_format_table.a -l:libnouveau_mme.a \
		-l:libnouveau_ws.a -l:libnvidia_headers_c.a \
		-l:libnir.a -l:libcompiler.a -l:libcompiler_c_helpers.a \
		-l:libmesa_util.a -l:libmesa_util_simd.a -l:libblake3.a -l:libmesa_util_c11.a \
		-Wl,--end-group $(STORAGE_LIBS) -lcurl -lz -lzstd -lnx -lstdc++ -lm
endif
endif
else
ifneq ($(strip $(MESA_SDK_ROOT)),)
# The unified EGL archive contains both native NVC0 and Zink. Keep Vulkan in
# the same rescan group so the GL host can select either driver at runtime.
LIBDIRS	:= $(MESA_SDK_ROOT) $(PORTLIBS) $(LIBNX)
LIBS	:= -Wl,--start-group -lvulkan -lEGL -lGLESv2 -lglapi \
		-lmesa_util_c11 -lblake3 -lmesa_util -lmesa_util_simd -lxmlconfig \
		-Wl,--end-group $(STORAGE_LIBS) -lcurl -lelf -lexpat -lz -lzstd \
		-lnx -lstdc++ -lm
else
# EGL/GLESv2/glapi/drm_nouveau: switch-mesa/nouveau GL.
LIBDIRS	:= $(PORTLIBS) $(LIBNX)
LIBS	:= $(STORAGE_LIBS) -lcurl -lz -lEGL -lGLESv2 -lglapi -ldrm_nouveau -lnx -lm
endif
endif

#---------------------------------------------------------------------------------
ifneq ($(BUILD),$(notdir $(CURDIR)))
#---------------------------------------------------------------------------------

export OUTPUT	:=	$(CURDIR)/$(TARGET)
export TOPDIR	:=	$(CURDIR)

export VPATH	:=	$(foreach dir,$(SOURCES),$(CURDIR)/$(dir)) \
			$(foreach dir,$(DATA),$(CURDIR)/$(dir))

export DEPSDIR	:=	$(CURDIR)/$(BUILD)

CFILES		:=	$(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.c)))
CPPFILES	:=	$(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.cpp)))
SFILES		:=	$(foreach dir,$(SOURCES),$(notdir $(wildcard $(dir)/*.s)))
BINFILES	:=	$(foreach dir,$(DATA),$(notdir $(wildcard $(dir)/*.*)))

#---------------------------------------------------------------------------------
# link with g++ so mesa's C++ EGL/GLES pulls in libstdc++
export LD	:=	$(CXX)

export OFILES_BIN	:=	$(addsuffix .o,$(BINFILES))
export OFILES_SRC	:=	$(CPPFILES:.cpp=.o) $(CFILES:.c=.o) $(SFILES:.s=.o)
export OFILES 	:=	$(OFILES_BIN) $(OFILES_SRC)
export HFILES_BIN	:=	$(addsuffix .h,$(subst .,_,$(BINFILES)))

export INCLUDE	:=	$(foreach dir,$(INCLUDES),-I$(CURDIR)/$(dir)) \
			$(foreach dir,$(LIBDIRS),-I$(dir)/include) \
			-I$(CURDIR)/$(BUILD)

export LIBPATHS	:=	$(foreach dir,$(LIBDIRS),-L$(dir)/lib)

ifeq ($(strip $(ICON)),)
	icons := $(wildcard *.jpg)
	ifneq (,$(findstring $(TARGET).jpg,$(icons)))
		export APP_ICON := $(TOPDIR)/$(TARGET).jpg
	else
		ifneq (,$(findstring icon.jpg,$(icons)))
			export APP_ICON := $(TOPDIR)/icon.jpg
		endif
	endif
else
	export APP_ICON := $(TOPDIR)/$(ICON)
endif

ifeq ($(strip $(NO_ICON)),)
	export NROFLAGS += --icon=$(APP_ICON)
endif

ifeq ($(strip $(NO_NACP)),)
	export NROFLAGS += --nacp=$(CURDIR)/$(TARGET).nacp
endif

ifneq ($(APP_TITLEID),)
	export NACPFLAGS += --titleid=$(APP_TITLEID)
endif

.PHONY: $(BUILD) clean all

#---------------------------------------------------------------------------------
all: $(BUILD)

$(BUILD):
	@[ -d $@ ] || mkdir -p $@
	@$(MAKE) --no-print-directory -C $(BUILD) -f $(CURDIR)/Makefile

#---------------------------------------------------------------------------------
clean:
	@echo clean ...
	@rm -fr $(BUILD) $(TARGET).nro $(TARGET).nacp $(TARGET).elf

#---------------------------------------------------------------------------------
else
.PHONY:	all

DEPENDS	:=	$(OFILES:.o=.d)

# libnx provides a weak 1 KiB __nx_exception_stack, while crash.c supplies the
# strong 512 KiB stack used by the re-entrant fastmem/JIT fault handler. Keep
# that defining object out of LTO so the linker sees the final strong size
# before the LTO plugin materializes symbols (and does not retain/report the
# weak libnx size).
crash.o: CFLAGS += -fno-lto

# The memory primitives are the hottest code in the process (every GS texture
# upload, EE/VU RAM copy and SPU2 mix goes through them). Drop the frame
# pointer here only: x29 is then free for the copy loops, and crash.c's
# backtraces never cross these leaf functions.
x1mem.o: CFLAGS += -fomit-frame-pointer

#---------------------------------------------------------------------------------
all	:	$(OUTPUT).nro

ifeq ($(strip $(NO_NACP)),)
$(OUTPUT).nro	:	$(OUTPUT).elf $(OUTPUT).nacp
else
$(OUTPUT).nro	:	$(OUTPUT).elf
endif

# Relink when the prebuilt storage archives change, not only on source edits.
$(OUTPUT).elf	:	$(OFILES) $(STORAGE_LIBS)

$(OFILES_SRC)	: $(HFILES_BIN)

%.bin.o	%_bin.h :	%.bin
	@echo $(notdir $<)
	@$(bin2o)

-include $(DEPENDS)

#---------------------------------------------------------------------------------------
endif
#---------------------------------------------------------------------------------------
