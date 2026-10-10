/* Read-only legacy word processor document. */
#define RT_FORMAT 10
#define RT_LABEL "Apple Writer"
#define RT_DESCRIPTION "Read Apple Writer text and layout commands"
#define RT_DOS
#include "retrotext.h"
#pragma rodata-name(push,"OVLHDR")
const struct RtHeader __plugin_header={PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry,{0,0,0},RT_DESCRIPTION};
#pragma rodata-name(pop)
