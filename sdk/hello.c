/* hello.c -- an example overlay for A2 File Cmd, compiled OUTSIDE the
 * program's tree, to prove that the ABI (struct A2fcApi) holds and to
 * serve as a model for a third party.
 *
 * It knows NOTHING of A2 File Cmd but src/a2fc_plugin.h: not a single
 * address of the program, none of its functions linked in. Everything goes
 * through the service table that the core hands to its entry point. It is
 * launched with the `!` key (the overlay menu), on the entry under the cursor.
 *
 * What it does: read the selected entry in the active panel and display
 * its name, type and path on the message line -- just enough calls
 * (message, sprintf, reading panels/active/selected) to show both
 * directions of the exchange. See sdk/README.md and sdk/build.sh.
 *
 * Compiled for the apple2enh target, like A2FC; WITHOUT --all-cdecl (cprintf
 * and sprintf are variadic cdecl, everything else fastcall). */

#include "../src/a2fc_plugin.h"

/* The entry point: the core calls it with the service table. */
void __fastcall__ plugin_entry(const struct A2fcApi* api);

/* The struct Overlay header, AT THE HEAD of the overlay ($1B00). The
 * PLUGIN_MAGIC signature says "third-party overlay"; the core recognises it
 * and calls nothing except through the table. `desc` is shown in the menu. */
struct PluginHeader {
    unsigned int signature;
    unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*);
    unsigned char r0, r1, r2;
    char desc[66];      /* the menu reads 65 at most */
};

#pragma rodata-name (push, "OVLHDR")
const struct PluginHeader __plugin_header = {
    PLUGIN_MAGIC,
    0,                       /* small overlay; OVERLAY_BIG for $2000-$3FFF */
    plugin_entry,
    0, 0, 0,
    "Example third-party plugin: names the file"
};
#pragma rodata-name (pop)

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    const struct Panel* pan = &api->panels[*api->active];
    char* buf = (char*)api->copy_buf;          /* 512 bytes of scratch space on loan */

    if (api->selected->name[0])
        api->sprintf(buf, "Plugin: \"%s\", type $%02X, in %s",
                     api->selected->name,
                     (unsigned)api->selected->type,
                     pan->path[0] ? pan->path : "the volume list");
    else
        api->sprintf(buf, "Plugin: nothing selected, in %s",
                     pan->path[0] ? pan->path : "the volume list");

    api->message(buf);       /* line 22; the table did all the work */
}
