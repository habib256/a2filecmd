/* Header: PLUGIN_MAGIC, OVERLAY_BIG, inherited from goto.c.
 * Favourite SYS/BIN/BAS/INT programs. Share GOTO's bounded list and
 * recoverable save; hand an explicit resident program entry to RUN.
 * Writes only FAVRUN.CFG/TMP/BAK in MAIN, never AUX or /RAM. RUN performs
 * its usual confirmation, metadata/runtime checks and configuration save. */
#define FAVRUN
#include "goto.c"
