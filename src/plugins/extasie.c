/* Extasie/Chat Mauve $F2 image viewer.  The stream is the compact format
 * used by UNPACK on the original Extasie disks: a count byte, bit 7 selecting
 * a repeated byte, with zero counts wrapping to 256. */
#include "../a2fc_plugin.h"

struct Header { unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*); unsigned char r[3];
    char desc[52]; };
void __fastcall__ plugin_entry(const struct A2fcApi*);
#pragma rodata-name (push, "OVLHDR")
#ifdef A2FC_6502
const struct Header __plugin_header = { PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry,
#else
const struct Header __plugin_header = { PLUGIN_MAGIC, 0, plugin_entry,
#endif
    {0,0,0}, "View Extasie $F2 nibble images" };
#pragma rodata-name (pop)

static FILE* in;
static unsigned char have, at;
static unsigned char row, col;
static unsigned char* dst;

static int getb(const struct A2fcApi* a)
{
    if (at == have) { have = (unsigned char)a->fread(a->copy_buf, 1, 256, in); at = 0; if (!have) return -1; }
    return a->copy_buf[at++];
}

static void putb(unsigned char v)
{
    *dst++ = v;
    if (++col == 40) { col = 0; ++row;
        dst = (unsigned char*)0x2000 + ((row & 7) << 10) + ((row & 0x38) << 4) + ((row >> 6) * 40u); }
}

static void graphics_on(void)
{
    *(unsigned char*)0xC000 = 0; *(unsigned char*)0xC00D = 0;
    *(unsigned char*)0xC05E = 0; *(unsigned char*)0xC05F = 0;
    *(unsigned char*)0xC05E = 0; *(unsigned char*)0xC05F = 0;
    *(unsigned char*)0xC00C = 0; *(unsigned char*)0xC057 = 0;
    *(unsigned char*)0xC054 = 0; *(unsigned char*)0xC052 = 0;
    *(unsigned char*)0xC050 = 0;
}

void __fastcall__ plugin_entry(const struct A2fcApi* a)
{
    unsigned int n; int t, v;
    in = a->fopen(a->full, "rb");
    if (!in) { a->note[0] = 0; a->strcpy(a->note, "Cannot open Extasie image."); return; }
    a->fseek(in, 2, SEEK_SET); have = at = 0; row = col = 0; dst = (unsigned char*)0x2000;
    while (row < 192) {
        t = getb(a); if (t < 0) break;
        n = (unsigned char)t & 0x7F; if (!n) n = 256;
        if (t & 0x80) {
            v = getb(a); if (v < 0) break;
            while (n--) putb((unsigned char)v);
        } else while (n--) { v = getb(a); if (v < 0) break; putb((unsigned char)v); }
        if (v < 0) break;
    }
    a->fclose(in);
    if (row != 192 || col) { a->note[0] = 0; a->strcpy(a->note, "Extasie image truncated."); return; }
    graphics_on();
    a->cputs("Extasie $F2  |  arrows: directory  |  ESC: return");
    while (a->cgetc() != KEY_ESC) {}
}
