/* Normal Apple II Multiplan 1.06 saved sheets, copied intact as ProDOS $F4.
 * MAIN/text only; no AUX and no disk writes or formula evaluation. */
#define RT_FORMAT 20
#define RT_LABEL "Multiplan"
#define RT_DESCRIPTION "Read Multiplan normal sheets and cached values"
#include "retrotext.h"
#pragma rodata-name(push,"OVLHDR")
const struct RtHeader __plugin_header={PLUGIN_MAGIC,OVERLAY_BIG,plugin_entry,{0,0,0},RT_DESCRIPTION};
#pragma rodata-name(pop)
