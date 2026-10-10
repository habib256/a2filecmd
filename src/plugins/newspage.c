/* Actual DOS Newsroom layouts, or their BIN copies on ProDOS. */
#define RT_FORMAT 8
#define RT_DOS
#define RT_LABEL "Newsroom layout"
#include "retrotext.h"
#pragma rodata-name(push,"OVLHDR")
const struct RtHeader __plugin_header={PLUGIN_MAGIC, OVERLAY_BIG,plugin_entry,{0,0,0},"Decode Newsroom PG. page layouts"};
#pragma rodata-name(pop)
