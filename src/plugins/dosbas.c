/* Direct read-only DOS Applesoft listing. PLUGIN_MAGIC, OVERLAY_BIG.
 * Writes MAIN overlay/BSS/copy_buf/text only; no AUX, source or temporary. */
#include <string.h>
#define INTEGER_DOS
#define APPLESOFT_DOS
#include "intbasic.c"
