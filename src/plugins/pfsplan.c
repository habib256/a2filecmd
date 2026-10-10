/* Read-only PFS:Plan B00 profile. MAIN and text screen only. */
#define RT_FORMAT 16
#define RT_LABEL "PFS:Plan"
#define RT_DESCRIPTION "Read PFS:Plan labels, values and formulas"
#include "retrotext.h"
#pragma rodata-name(push,"OVLHDR")
const struct RtHeader __plugin_header={PLUGIN_MAGIC,OVERLAY_BIG,plugin_entry,{0,0,0},RT_DESCRIPTION};
#pragma rodata-name(pop)
