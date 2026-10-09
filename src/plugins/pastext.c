/* Apple Pascal PTX text, including compressed indentation. */
#define RT_FORMAT 1
#define RT_LABEL "Apple Pascal"
#define RT_DESCRIPTION "Read Apple Pascal text (PTX, compressed spaces)"
#include "retrotext.h"
#pragma rodata-name(push,"OVLHDR")
const struct RtHeader __plugin_header={PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry,{0,0,0},RT_DESCRIPTION};
#pragma rodata-name(pop)
