/* Read-only LISA 8/16 v4/v5. MAIN/text only; preserves files and AUX /RAM. */
#define RT_FORMAT 13
#define RT_LABEL "LISA v4/v5"
#define RT_DESCRIPTION "List LISA 8/16 v4/v5 sources and symbols"
#include "retrotext.h"
#pragma rodata-name(push,"OVLHDR")
const struct RtHeader __plugin_header={PLUGIN_MAGIC,OVERLAY_BIG,plugin_entry,{0,0,0},RT_DESCRIPTION};
#pragma rodata-name(pop)
