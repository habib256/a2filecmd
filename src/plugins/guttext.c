/* Gutenberg extracted text, preserving missing alternate glyphs as '?'. */
#define RT_FORMAT 5
#define RT_LABEL "Gutenberg"
#define RT_DESCRIPTION "Read extracted Gutenberg text (alternate glyphs ?)"
#include "retrotext.h"
#pragma rodata-name(push,"OVLHDR")
const struct RtHeader __plugin_header={PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry,{0,0,0},RT_DESCRIPTION};
#pragma rodata-name(pop)
