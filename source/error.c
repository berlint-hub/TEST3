/* error.c -- error handler
 *
 * Copyright (C) 2021 fgsfds, Andy Nguyen
 *
 * This software may be modified and distributed under the terms
 * of the MIT license.  See the LICENSE file for details.
 */

#include <switch.h>
#include <stdlib.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>

#include "util.h"
#include "error.h"

#ifdef NETHERSX2_VK_DIAGNOSTIC
// Defined in hooks/vk.c. Declared here rather than including hooks/vk.h, which
// would pull the Vulkan headers into this translation unit for a single call.
extern void vk_diag_note(const char *format, ...)
   __attribute__((format(printf, 1, 2)));
#endif

void fatal_error(const char *fmt, ...) {
  // format once so we can both log it and show it on screen
  char msg[1024];
  va_list list;
  va_start(list, fmt);
  vsnprintf(msg, sizeof(msg), fmt, list);
  va_end(list);

#ifdef NETHERSX2_VK_DIAGNOSTIC
  // The message below was only ever readable by photographing the console: this
  // function wrote nothing to a file, so a fatal error left no trace in the
  // diagnostic log and the trace just stopped. Mirror it before displaying.
  vk_diag_note("fatal_error: %s", msg);
#endif

  PadState pad;
  padConfigureInput(1, HidNpadStyleSet_NpadStandard);
  padInitializeDefault(&pad);

  consoleInit(NULL);

  printf("NetherSX2 - fatal error\n\n%s", msg);

  printf("\n\nPress A to exit.");

  consoleUpdate(NULL);

  while (appletMainLoop()) {
    padUpdate(&pad);
    const u64 keys = padGetButtonsDown(&pad);
    if (keys & HidNpadButton_A) break;
  }

  consoleExit(NULL);
  exit(1);
}
