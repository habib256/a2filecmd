/* MouseWrite fixed-width documents: read-only MAIN/text, no AUX. */
#define RT_FORMAT 18
#define RT_LABEL "MouseWrite"
#define RT_DESCRIPTION "Read MouseWrite text and visible controls"
#include "retrotext.h"
#pragma rodata-name(push,"OVLHDR")
const struct RtHeader __plugin_header={PLUGIN_MAGIC,OVERLAY_BIG,plugin_entry,{0,0,0},RT_DESCRIPTION};
#pragma rodata-name(pop)
