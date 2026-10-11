/* Cross-volume file move, loaded only after MOVE validates both paths.
 * Writes exclusively created destination; removes source only after full
 * readback, EOF/error checks and successful closes. No auxiliary RAM. */
#define UTIL_STUBS
#define UTIL_INFO
#include "util.h"
static unsigned char scratch[512];
static const char m_btree[] = "\2";
static const char m_walk[] = "The directories cannot be walked.";
#include "move_copy.h"
void __fastcall__ plugin_entry(const struct A2fcApi* api) {
    init(api);
    copy_across(a.selected);
}
struct Header {
    unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*);
    unsigned char r[3]; char desc[52];
};
#pragma rodata-name (push, "OVLHDR")
const struct Header __plugin_header = {
    PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry, {0,0,0},
    "MOVE cross-volume copy service"
};
#pragma rodata-name (pop)
