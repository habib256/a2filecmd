/* Direct read-only DOS Integer BASIC. PLUGIN_MAGIC, OVERLAY_BIG.
 * Writes MAIN overlay/BSS/copy_buf/text only; no AUX, source or temporary.
 * The existing listing/pager uses the validated DOS stream directly. */
#include <string.h>
#define INTEGER_DOS
#include "intbasic.c"
