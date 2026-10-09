/* LISA v2 tokenized sources; later symbol-table formats are refused. */
#define RT_FORMAT 4
#define RT_LABEL "LISA v2"
#define RT_DESCRIPTION "List LISA v2 tokenized sources (alternate B)"
#include "retrotext.h"
#pragma rodata-name(push,"OVLHDR")
const struct RtHeader __plugin_header={PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry,{0,0,0},RT_DESCRIPTION};
#pragma rodata-name(pop)
