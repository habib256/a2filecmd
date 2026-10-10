/* Read-only PFS:Write ProDOS documents. MAIN/text only, no AUX /RAM writes. */
#define RT_FORMAT 14
#define RT_LABEL "PFS:Write"
#define RT_DESCRIPTION "Read PFS:Write documents (text and controls)"
#include "retrotext.h"
#pragma rodata-name(push,"OVLHDR")
const struct RtHeader __plugin_header={PLUGIN_MAGIC,OVERLAY_BIG,plugin_entry,{0,0,0},RT_DESCRIPTION};
#pragma rodata-name(pop)
