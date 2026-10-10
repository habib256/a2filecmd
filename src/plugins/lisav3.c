/* LISA v3 standard mnemonic dialect; v4/v5 are separate formats. */
#define RT_FORMAT 12
#define RT_LABEL "LISA v3"
#define RT_DESCRIPTION "List LISA v3 sources and packed symbols"
#include "retrotext.h"
#pragma rodata-name(push,"OVLHDR")
const struct RtHeader __plugin_header={PLUGIN_MAGIC,OVERLAY_BIG,plugin_entry,{0,0,0},RT_DESCRIPTION};
#pragma rodata-name(pop)
