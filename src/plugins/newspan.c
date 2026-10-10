/* Actual DOS Newsroom panels, or their BIN copies on ProDOS. */
#define RT_FORMAT 7
#define RT_DOS
#define RT_LABEL "Newsroom panel"
#include "retrotext.h"
#pragma rodata-name(push,"OVLHDR")
const struct RtHeader __plugin_header={PLUGIN_MAGIC, OVERLAY_BIG,plugin_entry,{0,0,0},"Decode Newsroom PN. text panels"};
#pragma rodata-name(pop)
