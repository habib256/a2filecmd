/* Teach text data fork, without resource-fork styles. */
#define RT_FORMAT 6
#define RT_LABEL "Teach"
#define RT_DESCRIPTION "Read Teach text data fork (without resource styles)"
#include "retrotext.h"
#pragma rodata-name(push,"OVLHDR")
const struct RtHeader __plugin_header={PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry,{0,0,0},RT_DESCRIPTION};
#pragma rodata-name(pop)
