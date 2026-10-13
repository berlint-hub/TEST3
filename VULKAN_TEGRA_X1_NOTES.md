# Vulkan na Tegra X1 — proč to nešlo a kde přesně byla chyba

Stav k `vk-4248-r31`. Hra běží. Tohle je záznam toho, co bylo rozbité, proč to
trvalo ~30 buildů, a čemu se příště vyhnout.

---

## 1. TL;DR — ta jedna řádka

```c
setenv("NVK_I_WANT_A_BROKEN_VULKAN_DRIVER", "1", 1);   // source/main.c:1931
```

Musí být nastavené **před** tím, než jádro zavolá `vkCreateInstance`. V tomhle
repo je na začátku `main()` pod `#ifdef USE_VULKAN` — **ne** pod diagnostickým
guardem (viz §7).

---

## 2. Příznak

Launcher naběhl, hra se vybrala, jádro se načetlo — a pak nic. Návrat do
launcheru / crash do Horizon menu. Diagnostický log končil takto:

```
[.] vkCreateInstance end result=0 instance=0x... lsfg_prepared=0
[.] vkEnumeratePhysicalDevices result=0 count=0 querying=0
[.] core VM sequence returned vm_running=1
[.] host heartbeat polls=300 vm_running=0 presents=0
```

Klíčové: **`result=0` a zároveň `count=0`.** Ne chyba — „úspěch" nad prázdným
seznamem. A `nethersx2-mesa-stderr.log` byl **prázdný**, `nethersx2-exception.log`
**neexistoval**.

To znamená: žádný CPU exception, žádná fatal error, žádná zalogovaná chyba NVK.
Jádro korektně zjistilo „tento stroj nemá Vulkan" a samo se vypnulo
(`vm_running` 1 → 0 během 0,6 s), hostitel pak prošel graceful shutdownem.

---

## 3. Kořenová příčina

### 3a. NVK odmítá Tegra X1

`nxvk` → `src/nouveau/vulkan/nvk_physical_device.c:1508-1518`,
funkce `nvk_physical_device_create()`:

```c
   /* We don't support anything pre-Kepler */
   if (nvkmd->dev_info.cls_eng3d < KEPLER_A) {
      result = VK_ERROR_INCOMPATIBLE_DRIVER;        // tiché, bez logu
      goto fail_nvkmd;
   }

   if (!nvk_is_conformant(&nvkmd->dev_info) &&
       !debug_get_bool_option("NVK_I_WANT_A_BROKEN_VULKAN_DRIVER", false)) {
#ifdef NDEBUG
      result = VK_ERROR_INCOMPATIBLE_DRIVER;        // ← TOHLE. release build,
                                                    //    varování zkompilované pryč
#else
      result = vk_errorf(instance, VK_ERROR_INCOMPATIBLE_DRIVER,
                         "WARNING: NVK is not well-tested on %s, pass ...");
#endif
```

**Tegra X1 (GM20B / Maxwell) není na seznamu `nvk_is_conformant()`.**
První podmínka (`< KEPLER_A`) projde — Maxwell je novější než Kepler. Selhává až
ta druhá.

### 3b. Mesa tu chybu záměrně polyká

Mesa → `src/vulkan/runtime/vk_instance.c:445-463`:

```c
static VkResult
enumerate_physical_devices_locked(struct vk_instance *instance)
{
   if (instance->physical_devices.enumerate) {
      VkResult result = instance->physical_devices.enumerate(instance);
      if (result != VK_ERROR_INCOMPATIBLE_DRIVER)   // ← spolknutá
         return result;
   }
   VkResult result = VK_SUCCESS;
   if (instance->physical_devices.try_create_for_drm) {   // na Horizonu NULL
      result = enumerate_drm_physical_devices_locked(instance);
      ...
   }
   return result;
}
```

`VK_ERROR_INCOMPATIBLE_DRIVER` je **jediný** kód, který se polyká. Jakýkoli jiný
by se vrátil do `vk_common_EnumeratePhysicalDevices` a odtud ven — viděli bychom
`result != 0` v logu.

Na Horizonu je `try_create_for_drm` NULL, protože `nvk_instance.c:192-198`
používá vlastní cestu:

```c
#if DETECT_OS_HORIZON
   instance->vk.physical_devices.enumerate = nvk_enumerate_physical_device;
#else
   instance->vk.physical_devices.try_create_for_drm = nvk_create_drm_physical_device;
#endif
```

**Výsledek:** `VK_SUCCESS` nad prázdným seznamem zařízení, `count=0`, a protože
selhání šlo `NDEBUG` větví, **nikde ani řádek logu**.

### 3c. Proč to bylo tak těžké najít

Tři nezávislé vrstvy mlčení se sešly najednou:

1. `NDEBUG` → varování se zkompiluje pryč (jinak by tam byl text
   `"WARNING: NVK is not well-tested on ..."`).
2. Mesa spolkne zrovna ten kód, který NVK vrátí.
3. `VK_SUCCESS` + `count=0` vypadá jako legitimní odpověď, ne jako chyba.

---

## 4. Tři slepé uličky — NEOPAKOVAT

Všechny tři vypadaly věrohodně a všechny byly **vyvráceny měřením**:

| Hypotéza | Jak byla vyvrácena |
|---|---|
| **`abort()` → tichý exit.** `abort` je v importní tabulce jádra (`source/imports.c:301`) a `abort_fake()` (`source/imports.c:201`) jde přímo na `__libnx_exit(134)` — bez logu, bez handleru. | Do `abort_fake` bylo přidáno logování. V logu žádný řádek `abort()` není → nikdy se nezavolal. |
| **`__nx_nv_transfermem_size = 16 MB`** (`source/main.c`) se nealo­kuje, protože `__libnx_initheap()` už nafoukne haldu téměř na všechnu paměť. | Sonda (`nv_probe()`) volá `nvInitialize/nvGpuInit/nvMapInit/nvFenceInit/nvGpuGetCharacteristics` přímo z hostitele. **Všech pět vrátilo `rc=0x0`**, včetně těch 16 MB, a `chars` byl platný ukazatel. |
| **`DETECT_OS_HORIZON` není definované**, takže se použila DRM cesta. | `nvk_instance.c:16` includeuje `util/detect_os.h` a `detect_os.h:97-98` mapuje `__SWITCH__` → `DETECT_OS_HORIZON 1`. Cesta zapnutá je. |

**Co to rozhodlo:** prázdný `nethersx2-mesa-stderr.log`. Kdyby selhalo cokoli, co
NVK loguje přes `vk_errorf`, na úrovni ERROR by to prošlo filtrem a bylo by to
tam. Prázdný soubor ⇒ selhání jde cestou, která neloguje ⇒ `vk_error()` bez
formátovacího řetězce ⇒ §3a.

---

## 5. Diagnostika, která už v repu je

Zapíná se `NETHERSX2_VK_DIAGNOSTIC=1` (Makefile ř. 34-35, `build_all.sh` ř. 112).
Píše tři soubory do `/switch/nethersx2/`:

| Soubor | Co v něm je |
|---|---|
| `nethersx2-vulkan.log` | `vk_diag_note` — `fflush` + `fsync` na každý řádek. Hooky v `source/hooks/vk.c`: `vkCreateInstance`, `vkEnumeratePhysicalDevices`, `vkCreateDevice`, swapchain, present. Heartbeat z hlavní smyčky (`source/main.c`). |
| `nethersx2-exception.log` | Píše **jen** `vk_diag_exception()` z `source/crash.c:169`. **Když neexistuje, nedošlo k CPU exception** — to je důkaz, ne absence dat. |
| `nethersx2-mesa-stderr.log` | `stderr` je přesměrovaný sem, protože Mesa fallback píše do `stderr` a ten na Horizonu nikam nejde. |

Dvě věci, které stály za to vědět:

- **`fatal_error()` do souboru nepsala.** Jen `consoleInit` + `printf` + čekání
  na A + `exit(1)`. Text chyby byl čitelný jedině vyfocením obrazovky. Teď se
  loguje (`source/error.c`).
- **`mesa_log_file` se zachytí jednorázově** v `mesa_log_init_once()`; jediná dvě
  přiřazení jsou `log.c:143` (`= stderr`) a `log.c:165` (`= fp`), setter
  neexistuje. Proto `main.c` volá `_mesa_log()` hned po instalaci
  přesměrování — aby se ta jednorázová inicializace stihla na hlavním vlákně.

**Pozor:** `MESA_LOG_FILE` se v `log.c:159` sice čte, ale až uvnitř
`if (__normal_user())` a jen když `fopen()` uspěje. Jinak `mesa_log_file` zůstane
`stderr`. Proto ten `stderr` redirect — bez něj je Mesa log na Switchi neviditelný.

**Výkonnostní cena:** `fflush`+`fsync` na každý řádek + heartbeat každých ~5 s po
celou dobu hry. Pro běžné hraní `NETHERSX2_VK_DIAGNOSTIC` **vypnout**.

---

## 6. Build — co je potřeba

Přesná invokace, kterou repo podporuje:

```sh
CORES=4248 RENDERERS=VK MESA_FLAVOR=nxvk ./build_all.sh
```

- **Jádro** musí být `libemucore_4248_baked.so` z `main` tohohle repa, **ne**
  z APK třetí strany.
- **nxvk** (`PalindromicBreadLoaf/nxvk`, branch `switch`) se linkuje staticky →
  výsledný `.nro` je kombinované GPL dílo (nxvk je GPL-2.0-or-later).
- Lokální cross-compilace bez devkitPro **nejde**; produkční cesta je GitHub
  Actions (`.github/workflows/release-vulkan.yml`, kontejner
  `devkitpro/devkita64:latest`).

### Pasti, které stály buildy

| Past | Projev |
|---|---|
| `TARGET := $(notdir $(CURDIR))` (`Makefile:13`) | Build projde, pak `cp: cannot stat 'NetherSX2_nx.nro'`. Musí být `TARGET=NetherSX2_nx`. |
| Zapnutí `NETHERSX2_VK_DIAGNOSTIC` **mění, jaké symboly link potřebuje** | `#ifdef` větve v `hooks/vk.c` odkazují `vkQueueSubmit`, `vkQueueSubmit2`, `vkAcquireNextImageKHR` — undefined reference. Při přidání define-gated kódu **vždy** proskenovat: `grep -oE "\bvk[A-Z][A-Za-z0-9]*\b" source/hooks/*.c` proti exportům v `source/vk_icd_shim.c`. |
| Release vyžaduje **dvě** podmínky | (a) push se musí dotknout cesty v `push.paths`; (b) commit message musí obsahovat `[release-vk]` (workflow ř. 90). Jedna chybějící = build se přeskočí. |
| `MESA_FLAVOR=nxvk` nemůže linkovat EGL | nxvk má `-Degl=disabled` a žádné `rust_switch_stubs`. Nedělat EGL vrstvu. |
| Vnořená definice funkce | `error: invalid storage class for function` — edit ukotvený na řádek **uvnitř** `main()` vloží definici do těla funkce. |

### Co lokální kontrola neodhalí

`gcc -fsyntax-only` na **vyextrahovaném úryvku** neodhalí špatné *umístění* v
souboru — takhle prošel test a stejně to spadlo v CI. Místo toho ověřovat
strukturálně na skutečném souboru (hloubka složených závorek, otevřené `#if`
bloky) a **počkat si na CI build**.

---

## 7. Kdyby se to někdy vrátilo

`setenv("NVK_I_WANT_A_BROKEN_VULKAN_DRIVER", ...)` byl původně vložený vedle
`setenv("MESA_LOG_FILE", ...)`, což je **uvnitř**
`#if defined(USE_VULKAN) && defined(NETHERSX2_VK_DIAGNOSTIC)`. Build bez
diagnostiky by se tiše vrátil na nula zařízení.

Teď je na `source/main.c:1931`, na začátku `main()`, pod `#ifdef USE_VULKAN`.
**Nikdy to nepřesouvat pod diagnostický guard** — je to runtime požadavek, ne
instrumentace.

Kontrola jedním příkazem:

```sh
grep -n "NVK_I_WANT_A_BROKEN_VULKAN_DRIVER" source/main.c
# očekávaný výsledek: jedno volání, ~1931, POD #ifdef USE_VULKAN
```
