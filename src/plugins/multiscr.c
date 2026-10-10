/* Read-only legacy word processor document. */
#define RT_FORMAT 9
#define RT_LABEL "MultiScribe"
#define RT_DESCRIPTION "Read MultiScribe TXT/WPF text (plain fonts)"
#include "retrotext.h"
#pragma rodata-name(push,"OVLHDR")
const struct RtHeader __plugin_header={PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry,{0,0,0},RT_DESCRIPTION};
#pragma rodata-name(pop)
