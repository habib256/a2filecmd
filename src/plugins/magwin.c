/* Magic Window BIN documents, ProDOS/extracted or direct DOS 3.3. */
#define RT_FORMAT 11
#define RT_DOS
#define RT_LABEL "Magic Window"
#define RT_DESCRIPTION "Read Magic Window documents (plain text)"
#include "retrotext.h"
#pragma rodata-name(push,"OVLHDR")
const struct RtHeader __plugin_header={PLUGIN_MAGIC,OVERLAY_BIG,plugin_entry,{0,0,0},RT_DESCRIPTION};
#pragma rodata-name(pop)
