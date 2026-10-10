/* Read-only ProDOS PFS:File records. MAIN buffers/text screen only. */
#define RT_FORMAT 15
#define RT_LABEL "PFS:File"
#define RT_DESCRIPTION "Read PFS:File forms and active records"
#include "retrotext.h"
#pragma rodata-name(push,"OVLHDR")
const struct RtHeader __plugin_header={PLUGIN_MAGIC,OVERLAY_BIG,plugin_entry,{0,0,0},RT_DESCRIPTION};
#pragma rodata-name(pop)
