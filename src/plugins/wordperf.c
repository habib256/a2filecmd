/* Apple II WordPerfect documents: read-only MAIN/text, no AUX or disk writes. */
#define RT_FORMAT 17
#define RT_LABEL "WordPerfect"
#define RT_DESCRIPTION "Read Apple II WordPerfect text and notes"
#include "retrotext.h"
#pragma rodata-name(push,"OVLHDR")
const struct RtHeader __plugin_header={PLUGIN_MAGIC,OVERLAY_BIG,plugin_entry,{0,0,0},RT_DESCRIPTION};
#pragma rodata-name(pop)
