/* unwrap.c -- the data fork of an AppleSingle or MacBinary file, extracted
 * into the other panel with its ProDOS type. From Return (type $E0/$0001,
 * or a .AS name) or the ! menu, on the selected file.
 *
 * The formats, and the reference this overlay is tested against, are in
 * tools/unwrap_ref.py (after CiderPress II's notes and Apple's File Type
 * Note $E0/0001):
 *
 *   AppleSingle, version 1 or 2: a table of entries -- 1 the data fork,
 *   3 the name, 7 (version 1, home file system "ProDOS") or 11 the ProDOS
 *   type and auxiliary type, 9 the Finder's Mac type and creator.
 *   MacBinary I, II or III: a 128-byte header -- the name, the Mac type and
 *   creator, the fork lengths -- then the data fork. MacBinary II and III
 *   are recognised by the header's CRC; MacBinary I by its zero fields.
 *
 * A Mac type and creator become a ProDOS type as AppleShare and the GS/OS
 * FSTs convert them ('pdos' 'p' $tt $aaaa, 'TEXT', 'BINA'...). The name is
 * the wrapped file's, made a ProDOS name; without one, the wrapper's name
 * less its suffix.
 *
 * The file follows the one contract of the file services: created
 * exclusively (an existing name is refused, never replaced), written,
 * closed, read back and compared, and removed if any of that fails. The
 * resource fork is left out, and the note says so.
 *
 * A big overlay: the core rereads the panels on return, and the new file
 * shows in the other one. */
#define UTIL_CREATE
#define UTIL_DISCARD
#include "util.h"

void __fastcall__ plugin_entry(const struct A2fcApi* api);

struct PluginHeader {
    unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*);
    unsigned char r0, r1, r2; char desc[52];
};
#pragma rodata-name (push, "OVLHDR")
const struct PluginHeader __plugin_header = {
    PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry, 0, 0, 0,
    "AppleSingle and MacBinary: extract the data fork"
};
#pragma rodata-name (pop)

#pragma static-locals (on)

/* BSS: nothing zeroes it; everything below is written before it is read. */
static FILE* in;
static FILE* out;
static unsigned long size, off, len, rsrc;
static unsigned char type, typed;       /* $80 a data fork; 2 a ProDOS type, 1 a Mac one */
static unsigned int aux;
static char name[16];
static char dest[PATH_LEN + 1];
static unsigned char hdr[128];
static unsigned char blk[512], cmp[512];

static unsigned long be32(const unsigned char* p)
{
    return ((unsigned long)p[0] << 24) | ((unsigned long)p[1] << 16) | ((unsigned int)p[2] << 8) | p[3];
}
static unsigned int be16(const unsigned char* p) { return ((unsigned int)p[0] << 8) | p[1]; }

/* n bytes at `at` of the input into blk; 1 when they all came. */
static unsigned char grab(unsigned long at, unsigned int n)
{
    return !RF(fseek)(in, at, SEEK_SET) && RF(fread)(blk, 1, n, in) == n;
}

/* A ProDOS name from n bytes of a Mac or Unix name: upper case, anything
 * but letters, digits and periods a period, no leading non-letter, 15
 * characters at most. */
static void set_name(const unsigned char* s, unsigned char n)
{
    unsigned char k = 0, c;
    while (n-- && k < 15) {
        c = *s++;
        if (c >= 'a' && c <= 'z') c -= 32;
        if (!((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '.')) c = '.';
        if (!k && !(c >= 'A' && c <= 'Z')) continue;
        name[k++] = c;
    }
    name[k] = 0;
}

/* The ProDOS type of a Mac type and creator (tools/unwrap_ref.py: hfs_type). */
static void mac_type(const unsigned char* t)
{
    unsigned long mt = be32(t), cr = be32(t + 4);
    typed |= 1;
    aux = 0;
    type = 0;
    if (mt == 0x54455854UL) type = 0x04;                    /* TEXT */
    else if (mt == 0x4D494449UL) type = 0xD7;               /* MIDI */
    else if (mt == 0x41494646UL) type = 0xD8;               /* AIFF */
    else if (mt == 0x41494643UL) { type = 0xD8; aux = 1; }  /* AIFC */
    else if (mt == 0x64496D67UL && cr == 0x64437079UL) { type = 0xE0; aux = 0x8005; }
    else if (cr == 0x70646F73UL) {                          /* 'pdos' */
        if (mt == 0x50535953UL) type = 0xFF;                /* PSYS */
        else if (mt == 0x50533136UL) type = 0xB3;           /* PS16 */
        else if (t[0] == 'p') { type = t[1]; aux = be16(t + 2); }
        else if (t[2] == ' ' && t[3] == ' ') {              /* 'XY  ': $XY in hex */
            unsigned char i, c, v = 0;
            for (i = 0; i < 2; ++i) {
                c = t[i];
                if (c >= '0' && c <= '9') c -= '0';
                else if (c >= 'A' && c <= 'F') c -= 'A' - 10;
                else return;
                v = v << 4 | c;
            }
            type = v;
        }
    }
}

/* Version 1's home file system, "ProDOS" and spaces. */
static unsigned char prodos_home(void)
{
    static const char home[] = "ProDOS";
    unsigned char i;
    for (i = 0; i < 6; ++i) if (hdr[8 + i] != home[i]) return 0;
    return 1;
}

/* AppleSingle: the entries of the table. 0 when it is none, or broken. */
static unsigned char apple_single(void)
{
    unsigned int n, i;
    unsigned long id, at, l;
    unsigned char v1 = hdr[5] == 1;
    if (be32(hdr) != 0x00051600UL || (hdr[5] != 1 && hdr[5] != 2) || hdr[4] | hdr[6] | hdr[7])
        return 0;
    n = be16(hdr + 24);
    for (i = 0; i < n; ++i) {
        if (!grab(26 + 12UL * i, 12)) return 0;
        id = be32(blk);
        at = be32(blk + 4);
        l = be32(blk + 8);
        if (at > size || l > size - at) return 0;
        if (id == 1) { off = at; len = l; typed |= 0x80; }
        else if (id == 2) rsrc = l;
        else if (id == 3 && l) {
            if (!grab(at, l > 63 ? 63 : (unsigned int)l)) return 0;
            set_name(blk, l > 63 ? 63 : (unsigned char)l);
        } else if (id == 11 && l >= 8) {
            if (!grab(at, 8)) return 0;
            type = blk[3]; aux = be16(blk + 6); typed = (typed & 0x80) | 2;
        } else if (id == 7 && v1 && l >= 16 && prodos_home()) {
            if (!grab(at, 16)) return 0;
            type = blk[11]; aux = be16(blk + 14); typed = (typed & 0x80) | 2;
        } else if (id == 9 && l >= 8 && !(typed & 2)) {
            if (!grab(at, 8)) return 0;
            mac_type(blk);
        }
    }
    return 1;
}

/* MacBinary II and III: the CRC-16 (XMODEM) of the first 124 bytes. */
static unsigned int crc16(void)
{
    unsigned short c = 0;               /* 16 bits here and on the host */
    unsigned char i, b;
    for (i = 0; i < 124; ++i) {
        c ^= (unsigned short)(hdr[i] << 8);
        for (b = 0; b < 8; ++b) c = c & 0x8000 ? (unsigned short)(c << 1) ^ 0x1021 : (unsigned short)(c << 1);
    }
    return c;
}

static unsigned char mac_binary(void)
{
    unsigned char i;
    if (hdr[0] || !hdr[1] || hdr[1] > 63 || hdr[74] || hdr[82]) return 0;
    if (crc16() != be16(hdr + 124)) {
        for (i = 99; i < 128; ++i) if (hdr[i]) return 0;   /* MacBinary I: all zero */
    }
    len = be32(hdr + 83);
    rsrc = be32(hdr + 87);
    if (len > size - 128) return 0;
    off = 128;
    set_name(hdr + 2, hdr[1]);
    mac_type(hdr + 65);
    typed |= 0x80;
    return 1;
}

/* The data fork, copied to dest, or compared with it (check). 1 if all went. */
static unsigned char pass(unsigned char check)
{
    unsigned long left = len;
    unsigned int n, i;
    if (RF(fseek)(in, off, SEEK_SET)) return 0;
    while (left) {
        n = left > 512 ? 512 : (unsigned int)left;
        if (RF(fread)(blk, 1, n, in) != n) return 0;
        if (check) {
            if (RF(fread)(cmp, 1, n, out) != n) return 0;
            for (i = 0; i < n; ++i) if (cmp[i] != blk[i]) return 0;
        } else if (RF(fwrite)(blk, 1, n, out) != n) return 0;
        left -= n;
        if (stop()) return 0;
    }
    return !check || RF(fread)(cmp, 1, 1, out) == 0;
}

static const char m_pick[] = "Not an AppleSingle or MacBinary file.";
static const char m_other[] = "Other panel: open a ProDOS directory.";

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    const struct Entry* e = api->selected;
    unsigned char ok, k;
    init(api);
    size = e->size;
    name[0] = 0;
    typed = 0;
    type = 0;
    aux = 0;
    rsrc = 0;
    if (!e->name[0] || e->type == 0x0F || !a.full[0] || !(in = RF(fopen)(a.full, "rb"))) {
        note(m_pick);
        return;
    }
    ok = RF(fread)(hdr, 1, 128, in);
    if (ok >= 26) {
        if (ok < 128) RF(memset)(hdr + ok, 0xFF, 128 - ok);     /* too short for MacBinary */
        ok = apple_single() || (!(typed & 0x80) && ok == 128 && mac_binary());
    } else ok = 0;
    if (!ok || !(typed & 0x80) || type == 0x0F || len > 0xFFFFFFUL) {
        RF(fclose)(in);
        note(m_pick);
        return;
    }
    if (!name[0]) {                     /* the wrapper's name, less its suffix */
        set_name((const unsigned char*)e->name, RF(strlen)(e->name));
        for (k = RF(strlen)(name); k && name[k - 1] != '.'; --k) ;
        if (k > 1) name[k - 1] = 0;
    }
    if (!other->path[0] || other->fs) { RF(fclose)(in); note(m_other); return; }
    if (!join(dest, other->path, name)) { RF(fclose)(in); note("Path too long."); return; }
    if (newfile(dest, type, aux, 1)) {
        RF(fclose)(in);
        a.sprintf(a.note, "%s exists or cannot be created.", name);
        return;
    }
    ok = 0;
    out = RF(fopen)(dest, "wb");
    if (out) {
        ok = pass(0);
        if (ferror(out)) ok = 0;
        if (RF(fclose)(out)) ok = 0;
        if (ok) {
            out = RF(fopen)(dest, "rb");
            ok = out && pass(1);
            if (out && RF(fclose)(out)) ok = 0;
        }
    }
    RF(fclose)(in);
    if (!ok) {
        if (discard(dest))
            a.sprintf(a.note, cancelled ? "Stopped: %s removed." : "Extraction failed: %s removed.", name);
        return;
    }
    a.sprintf(a.note, "%s: %lu bytes, $%02X/$%04X.%s", name, len, type, aux,
              rsrc ? " Resource fork left out." : "");
}
