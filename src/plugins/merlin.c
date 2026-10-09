/* Merlin / DOS Toolkit ED/ASM source columns. */
#define RT_FORMAT 3
#define RT_LABEL "Merlin"
#define RT_DESCRIPTION "Read Merlin/ED-ASM sources in aligned columns"
#include "retrotext.h"
#pragma rodata-name(push,"OVLHDR")
const struct RtHeader __plugin_header={PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry,{0,0,0},RT_DESCRIPTION};
#pragma rodata-name(pop)
