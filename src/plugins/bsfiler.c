/* Read-only Bank Street Filer: no disk/AUX writes. */
#define RT_FORMAT 19
#define RT_LABEL "Bank Street Filer"
#define RT_DESCRIPTION "Read Bank Street Filer records and fields"
#include "retrotext.h"
#pragma rodata-name(push,"OVLHDR")
const struct RtHeader __plugin_header={PLUGIN_MAGIC,OVERLAY_BIG,plugin_entry,{0,0,0},RT_DESCRIPTION};
#pragma rodata-name(pop)
