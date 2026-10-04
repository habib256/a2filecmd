/* visicalc.c -- VisiCalc worksheets (/SS files), recalculated and shown as
 * VisiCalc shows them. From Return on a text file that starts like one
 * (`>A1:`), or the ! menu. All of the overlay is visicalc.s; this file
 * gives it its header and the offsets of the services it calls. */
#include <stddef.h>
#include "../a2fc_plugin.h"

void __fastcall__ plugin_entry(const struct A2fcApi*);   /* visicalc.s */

struct Header { unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*); unsigned char r[3];
    char desc[52]; };
#pragma rodata-name (push, "OVLHDR")
const struct Header __plugin_header = { PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry,
    {0,0,0}, "VisiCalc worksheets (/SS files), recalculated" };
#pragma rodata-name (pop)

/* The fields, then the services visicalc.s calls, in the order of its
 * jtab (J_FOPEN...), then SEEK_SET. */
#define OFS(field) offsetof(struct A2fcApi, field)
const unsigned char vc_ofs[] = {
    OFS(full), OFS(copy_buf), OFS(note), OFS(selected), OFS(cfg_path),
    OFS(fopen), OFS(fread), OFS(fseek), OFS(fclose), OFS(strcpy), OFS(cgetc),
    OFS(gotoxy), OFS(cputs), OFS(revers), OFS(clrscr), OFS(bar_begin), OFS(keys_bar),
    OFS(ram_format), OFS(aux_consent), SEEK_SET
};
