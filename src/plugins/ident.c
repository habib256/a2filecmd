/* ident.c -- say what the selected file is from its content, like file(1).
 *
 * From the ! menu, on the entry under the cursor (a file in a ProDOS
 * directory: a directory, the volume list, a disk image or a DOS 3.3 disk
 * are refused). The first 512 bytes are read into api->copy_buf and one
 * line goes on the message line, "NAME (12345 bytes): what it is", the
 * tests in this order:
 *
 *   ShrinkIt        "NuFile" or "NuFX" at 0 (high bits ignored: the real
 *                   signatures alternate them, $4E $F5 $46 $E9 $6C $E5)
 *   Binary II       $0A $47 $4C at 0 and $02 at 18
 *   2IMG            "2IMG" at 0
 *   140K image      143,360 bytes: ProDOS if block 2 carries a volume
 *                   directory header (storage type $F), DOS 3.3 if the VTOC
 *                   at track 17 says so, a ProDOS volume in DOS order
 *                   (block 2 at sector 11), else just "disk image"
 *   AppleWorks      type $1A word processor, $19 data base, $1B spreadsheet
 *   Applesoft       type $FC, or tokenised: the first line's link points
 *                   just past its terminating zero from $0801, its number
 *                   is 63999 at most and it holds a token ($80 and up)
 *   Integer BASIC   type $FA
 *   RLE pictures    "HGRR" / "DHRR" at 0 (the .RLE flow of the demo)
 *   DHGR / HGR      16,384 bytes; 8,192 bytes, or 8,184..8,192 as a BIN at $2000
 *   FOT             type $08
 *   Mockingboard    "MB1" at 0
 *   6502 code       type $FF, or a BIN with an auxtype and a JMP, JSR or
 *                   LDA# ($4C $20 $A9) among the first eight bytes
 *   text            every byte, high bit off, is printable, CR, LF or TAB:
 *                   "Text[ (UTF-8)], CR|LF|CRLF|mixed ends[, high bit
 *                   set|clear|mixed], N lines in M B[, tabs]" -- UTF-8 when
 *                   a lead byte $C2-$EF is followed by a continuation byte
 *                   and some bytes have the high bit off
 *   otherwise       "Binary data"
 *
 * A big overlay, for want of room: the twenty-odd descriptions alone
 * come to some 700 bytes, and cc65's code for the byte scan, the chain
 * of tests and the eight calls through the table to 1,900 more -- a
 * variant stripped to the bare list above still linked at 2,400 bytes,
 * nearly twice the small window. Being big, the core clears the screen and
 * redraws the panels on return: the line goes through api->note (79
 * characters, cut here so that nothing spills), and api->reselect keeps
 * the cursor on the file. Only api->selected (a copy) and the panel's
 * path and fs are read: the entry table under $2000 is covered. */
#include "../a2fc_plugin.h"

void __fastcall__ plugin_entry(const struct A2fcApi* api);

struct PluginHeader {
    unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*);
    unsigned char r0, r1, r2; char desc[52];
};
#pragma rodata-name (push, "OVLHDR")
const struct PluginHeader __plugin_header = {
    PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry, 0, 0, 0,
    "Say what a file is from its content, like file(1)"
};
#pragma rodata-name (pop)

/* BSS: nothing zeroes it; every one of these is written before it is read. */
static const struct A2fcApi* A;
static const struct Entry* e;
static unsigned char* b;            /* api->copy_buf: the first 512 bytes, then the message */
static unsigned int n;              /* how many were read */
static FILE* f;
/* The size as two words, copied once: no long compare (cc65 would link its
 * runtime), and no cast of &e->size, which cc65 2.19 compiles as a read at
 * offset 0 of the entry -- the name -- rather than at the member. */
static union { unsigned long l; unsigned int w[2]; } sz;
#define SZ sz.w

static const char* const ends_name[8] = { "no", "CR", "LF", "mixed", "CRLF", "mixed", "mixed", "mixed" };
static const char m_text[] = "Text%s, %s ends%s, %u lines in %u B%s";
static const char m_line[] = "%s (%lu bytes): %s";
static const char s_image[] = "ProDOS disk image, 140K";

/* `m` at the start of the file, the high bits ignored. */
static unsigned char magic(const char* m)
{
    unsigned char i = 0;
    while (m[i]) {
        if ((b[i] & 0x7F) != m[i]) return 0;
        ++i;
    }
    return 1;
}

/* 512 bytes at `pos` of the file (still open) into b; 1 if a ProDOS
 * volume directory header stands at their byte 4 (storage type $F). */
static unsigned char prodos_at(long pos)
{
    A->fseek(f, pos, SEEK_SET);                   /* SEEK_SET is 2 in cc65, not 0 */
    A->fread(b, 1, 512, f);
    return b[4] >> 4 == 0xF;
}

/* A tokenised Applesoft line from $0801: link, number, tokens, zero. */
static unsigned char applesoft(void)
{
    unsigned int k;
    unsigned char tok = 0;
    if (n < 6 || b[3] > 0xF9) return 0;           /* the number: 63999 at most */
    for (k = 4; k < n; ++k) {
        if (!b[k]) break;
        if (b[k] & 0x80) tok = 1;
    }
    return tok && k < n && (b[0] | (b[1] << 8)) == 0x0802 + k;
}

/* Text, or binary data: the line written at b + 256. */
static const char* text(void)
{
    unsigned int i, lines = 0;
    unsigned char c, k, hi = 0, lo = 0, utf = 0, tabs = 0, pend = 0, ends = 0;
    const char* hb;
    for (i = 0; i < n; ++i) {
        c = b[i];
        k = c & 0x7F;
        if (c & 0x80) hi = 1; else lo = 1;
        if (k == 13) { ++lines; pend = 1; continue; }
        if (k == 10) {
            if (pend) ends |= 4; else { ends |= 2; ++lines; }
            pend = 0;
            continue;
        }
        if (pend) { ends |= 1; pend = 0; }
        if (k == 9) tabs = 1;
        else if (k < 32 || k == 127) return "Binary data";
        if (c >= 0xC2 && c < 0xF0 && i + 1 < n && (b[i + 1] & 0xC0) == 0x80) utf = 1;
    }
    if (pend) ends |= 1;
    if (!lo) utf = 0;                             /* all high: Apple text, not UTF-8 */
    hb = utf ? "" : hi ? (lo ? ", high bit mixed" : ", high bit set") : ", high bit clear";
    A->sprintf((char*)b + 256, m_text, utf ? " (UTF-8)" : "", ends_name[ends], hb, lines, n, tabs ? ", tabs" : "");
    return (const char*)b + 256;
}

static const char* identify(void)
{
    unsigned char t = e->type, i;
    if (!n) return "Empty file";
    if (magic("NuFile") || magic("NuFX")) return "ShrinkIt archive (NuFX)";
    if (magic("\x0A\x47\x4C") && b[18] == 2) return "Binary II archive";
    if (magic("2IMG")) return "2IMG disk image";
    if (SZ[1] == 2 && SZ[0] == 0x3000) {          /* 143,360 bytes: a 5.25 image */
        if (prodos_at(1024)) return s_image;
        prodos_at(69632L);                        /* the VTOC, DOS order: track 17 sector 0 */
        if (b[1] == 17 && b[3] == 3) return "DOS 3.3 disk image, 140K";
        if (prodos_at(2816)) return "ProDOS disk image, 140K, DOS order";   /* block 2 = sector 11 */
        return "Disk image, 140K";
    }
    if (t == 0x1A) return "AppleWorks word processor";
    if (t == 0x19) return "AppleWorks data base";
    if (t == 0x1B) return "AppleWorks spreadsheet";
    if (t == 0xFC || applesoft()) return "Applesoft BASIC program";
    if (t == 0xFA) return "Integer BASIC program";
    if (magic("HGRR")) return "HGR picture, RLE";
    if (magic("DHRR")) return "DHGR picture, RLE";
    if (!SZ[1]) {
        if (SZ[0] == 16384) return "DHGR picture, 16K (two planes)";
        if (SZ[0] == 8192 || (SZ[0] >= 8184 && SZ[0] < 8192 && t == 6 && e->aux == 0x2000))
            return "HGR picture, 8K";
    }
    if (t == 0x08) return "Hi-res picture (FOT)";
    if (magic("MB1")) return "Mockingboard music (MB1)";
    if (t == 0xFF) return "ProDOS system program, 6502 code";
    if (t == 6 && e->aux)
        for (i = 0; i < 8; ++i) {
            t = b[i];
            if (t == 0x4C || t == 0x20 || t == 0xA9) return "Binary, maybe 6502 code";
        }
    return text();
}

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    const struct Panel* pan = api->panels;
    const char* what;
    A = api;
    e = api->selected;
    b = api->copy_buf;
    sz.l = e->size;
    if (*api->active) ++pan;
    if (!e->name[0] || e->type == 0x0F || !pan->path[0] || pan->fs) {
        A->strcpy(A->note, "Select a file in a ProDOS directory.");
        return;
    }
    A->strcpy(A->reselect, e->name);              /* the cursor stays on it after the redraw */
    f = A->fopen(A->full, "rb");
    if (!f) { A->strcpy(A->note, "Cannot open it."); return; }
    n = A->fread(b, 1, 512, f);
    if (n < 512) A->memset(b + n, 0, 512 - n);    /* no magic read out of the last call's bytes */
    what = identify();
    A->fclose(f);
    A->sprintf((char*)b, m_line, e->name, e->size, what);
    b[79] = 0;                                    /* one line of note: nothing spills */
    A->strcpy(A->note, (char*)b);                 /* written by the core after its redraw */
}
