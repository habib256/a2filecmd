/* sciibin.c -- decode BinSCII text (.BSC, .BSQ) into the ProDOS file it
 * carries, in the other panel. From Return on a .BSC or .BSQ, or the !
 * menu, on the selected file -- and, while the file is not complete, on
 * the files that follow it in the directory: the parts of a file posted in
 * several messages, ZLINK.01.BSQ, ZLINK.02.BSQ...
 *
 * The format, and the reference this overlay is tested against, are in
 * tools/binscii_ref.py (after CiderPress II's BinSCII notes). A file comes
 * in chunks of 12,288 bytes, each with its own header -- the name, the
 * ProDOS type, the total length, where the chunk goes -- and a CRC of its
 * header and of its data. Chunks are written as they are met: each must
 * start where the previous one ended, so the parts must follow one another
 * in the directory, in order; a file after them that is not one of them
 * ends the search.
 *
 * The file follows the one contract of the file services: created
 * exclusively (an existing name is refused, never replaced), written,
 * closed, and read back -- each chunk's data against its CRC -- and removed
 * if anything fails: a damaged line, a missing part, a short write.
 *
 * A big overlay: the core rereads the panels on return. The names of the
 * following files are listed before any is read: the directory reader and
 * the file reader share the core's 512-byte buffer. */
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
    "BinSCII: decode .BSC/.BSQ text, and its next parts"
};
#pragma rodata-name (pop)

#pragma static-locals (on)

#define SEGMENT   12288
#define MAXSEGS   256                   /* 3 MB: more than any floppy holds */
#define MAXPARTS  32

#ifdef PLUGIN_HOST                      /* tools/test_sciibin.py: the same sum in C */
static unsigned int bs_sum;
static unsigned int bs_table[256];
static void bs_init(void)
{
    unsigned int i, c;
    unsigned char b;
    for (i = 0; i < 256; ++i) {
        c = i << 8;
        for (b = 0; b < 8; ++b) c = (c & 0x8000 ? (c << 1) ^ 0x1021 : c << 1) & 0xFFFF;
        bs_table[i] = c;
    }
}
static void bs_crc(const unsigned char* p)
{
    unsigned char i;
    for (i = 0; i < 48; ++i) bs_sum = ((bs_sum << 8) & 0xFFFF) ^ bs_table[(bs_sum >> 8) ^ p[i]];
}
#else
void bs_init(void);                     /* sciibin.s */
void __fastcall__ bs_crc(const unsigned char* p);
extern unsigned int bs_sum;
#endif

/* BSS: nothing zeroes it; everything below is written before it is read. */
static FILE* in;
static FILE* out;
static unsigned int have, at;
static unsigned char eof, was_cr;
static char line[81];                   /* the line read, blanks and high bits off */
static unsigned char llen;
static unsigned char table[256];        /* alphabet index + 1, 0 outside it */
static unsigned char bytes[48];
static unsigned char attrs[27];
static char fname[16], name[16];
static unsigned long total, written;
static unsigned int segs, crcs[MAXSEGS], lens[MAXSEGS];
static unsigned char type, created;
static unsigned int aux;
static char path[PATH_LEN + 1];         /* the file written */
static char src[PATH_LEN + 1];          /* the part being read */
static const char* why;
static char parts[MAXPARTS * 16];       /* the selected file, then those after it */
static unsigned char nparts, more;      /* more: the file seen is a later part */

/* The next line of the input, into line: CR, LF or CRLF ends it, blanks
 * around it are dropped, and so is the high bit. 0 at the end of the file. */
static unsigned char next_line(void)
{
    unsigned char c, started = 0;
    llen = 0;
    for (;;) {
        if (at == have) {
            have = RF(fread)(buf, 1, 512, in);
            at = 0;
            if (!have) { eof = 1; line[llen] = 0; return started; }
        }
        c = buf[at++] & 0x7F;
        if (c == 10 && was_cr) { was_cr = 0; continue; }
        was_cr = c == 13;
        if (c == 13 || c == 10) break;
        started = 1;
        if (!llen && (c == ' ' || c == 9)) continue;
        if (llen < 80) line[llen++] = c;
    }
    while (llen && (line[llen - 1] == ' ' || line[llen - 1] == 9)) --llen;
    line[llen] = 0;
    return 1;
}

/* n characters of line from `from`, 3 bytes for every 4, into bytes. */
static unsigned char unpack(unsigned char from, unsigned char n)
{
    unsigned char i, k, v[4], *o = bytes;
    for (i = 0; i < n; i += 4) {
        for (k = 0; k < 4; ++k) {
            v[k] = table[(unsigned char)line[from + i + k]];
            if (!v[k]) return 0;
            --v[k];
        }
        *o++ = v[3] << 2 | v[2] >> 4;
        *o++ = (v[2] & 15) << 4 | v[1] >> 2;
        *o++ = (v[1] & 3) << 6 | v[0];
    }
    return 1;
}

/* CRC-16/XMODEM of n bytes (the header), bitwise: 24 bytes are cheap. */
static unsigned int crc_small(const unsigned char* p, unsigned char n)
{
    unsigned int c = 0;
    unsigned char b;
    while (n--) {
        c ^= (unsigned int)*p++ << 8;
        for (b = 0; b < 8; ++b) c = (c & 0x8000 ? (c << 1) ^ 0x1021 : c << 1) & 0xFFFF;
    }
    return c;
}

static unsigned long le24(const unsigned char* p)
{
    return p[0] | ((unsigned int)p[1] << 8) | ((unsigned long)p[2] << 16);
}

/* One chunk, the signature line just read. 1 when it went. */
static unsigned char chunk(void)
{
    unsigned char i, n;
    unsigned int seglen, left, k;
    why = "BinSCII damaged";
    /* the alphabet */
    if (!next_line() || llen < 64) return 0;
    a.memset(table, 0, 256);
    for (i = 0; i < 64; ++i) {
        if (table[(unsigned char)line[i]]) return 0;
        table[(unsigned char)line[i]] = i + 1;
    }
    /* the header */
    if (!next_line() || llen < 52) return 0;
    n = line[0] - 0x40;
    if (n < 1 || n > 15) return 0;
    RF(memcpy)(fname, line + 1, n);
    fname[n] = 0;
    if (!unpack(16, 36)) return 0;
    RF(memcpy)(attrs, bytes, 27);
    if (crc_small(attrs, 24) != (attrs[24] | (unsigned int)attrs[25] << 8)) return 0;
    seglen = (unsigned int)le24(attrs + 21);
    if (!seglen || seglen > SEGMENT || attrs[23]) return 0;
    if (le24(attrs + 3) != written || segs == MAXSEGS) { why = "Parts out of order or missing"; return 0; }
    if (!created) {
        total = le24(attrs);
        type = attrs[7];
        aux = attrs[8] | (unsigned int)attrs[9] << 8;
        if (type == 0x0F || attrs[10] == 5 || attrs[10] == 0x0D) { why = "Not a plain file"; return 0; }
        RF(strcpy)(name, fname);
        if (!join(path, other->path, name)) { why = "Path too long"; return 0; }
        if (newfile(path, type, aux, 1)) {
            a.sprintf(a.note, "%s exists or cannot be created.", name);
            why = 0;
            return 0;
        }
        created = 1;
        out = RF(fopen)(path, "wb");
        if (!out) { why = "Open"; return 0; }
    } else if (RF(strcmp)(fname, name) || le24(attrs) != total) {
        why = more ? "Parts missing" : "Parts of another file";
        return 0;
    }
    /* the data: whole lines of 48 bytes, the CRC over all of them */
    bs_sum = 0;
    for (left = seglen; left; left -= k) {
        if (!next_line() || llen < 64 || !unpack(0, 64)) return 0;
        bs_crc(bytes);
        k = left > 48 ? 48 : left;
        if (RF(fwrite)(bytes, 1, k, out) != k) { why = "Write"; return 0; }
        if (stop()) { why = "Stopped"; return 0; }
    }
    if (!next_line() || llen < 4 || !unpack(0, 4)) return 0;
    if (bs_sum != (bytes[0] | (unsigned int)bytes[1] << 8)) return 0;
    crcs[segs] = bs_sum;
    lens[segs++] = seglen;
    written += seglen;
    return 1;
}

/* The file written, read back: each chunk's bytes, padded, against its CRC. */
static unsigned char read_back(void)
{
    unsigned int s, left, k, n;
    FILE* f = RF(fopen)(path, "rb");
    if (!f) return 0;
    for (s = 0; s < segs; ++s) {
        bs_sum = 0;
        for (left = lens[s]; left; left -= k) {
            k = left > 48 ? 48 : left;
            n = RF(fread)(bytes, 1, k, f);
            if (n != k) { RF(fclose)(f); return 0; }
            if (k < 48) a.memset(bytes + k, 0, 48 - k);
            bs_crc(bytes);
        }
        if (bs_sum != crcs[s]) { RF(fclose)(f); return 0; }
    }
    n = RF(fread)(bytes, 1, 1, f);
    return !RF(fclose)(f) && !n;
}

/* The selected file's name, then those of the files after it in the
 * directory, into parts. */
static void list_parts(const char* first)
{
    unsigned char seen = 0;
    const struct DirEntry* de = a.dir_entry;
    RF(strcpy)(parts, first);
    nparts = 1;
    if (!a.dir_open(pan->path)) return;
    while (nparts < MAXPARTS && a.dir_next()) {
        if (!seen) { seen = !RF(strcmp)(de->name, first); continue; }
        if (de->type != 0x0F) RF(strcpy)(parts + 16 * nparts++, de->name);
    }
    a.dir_close();
}

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    unsigned char i, ok = 1, found;
    init(api);
    if (!pan->path[0] || pan->fs || !a.selected->name[0] || a.selected->type == 0x0F) {
        note("Select a BinSCII file in a ProDOS directory.");
        return;
    }
    if (!other->path[0] || other->fs) { note("Other panel: open a ProDOS directory."); return; }
    list_parts(a.selected->name);
    bs_init();
    created = 0;
    written = 0;
    total = 1;
    segs = 0;
    why = "Not BinSCII text";
    for (i = 0; i < nparts && ok && (!created || written != total); ++i) {
        more = i != 0;
        if (!join(src, pan->path, parts + 16 * i) || !(in = RF(fopen)(src, "rb"))) {
            why = "Open";
            ok = 0;
            break;
        }
        have = at = eof = was_cr = 0;
        found = 0;
        while (ok && (!created || written != total) && next_line()) {
            if (llen == 18 && !RF(strcmp)(line, "FiLeStArTfIlEsTaRt")) {
                ok = chunk();
                found = 1;
            }
        }
        if (RF(fclose)(in)) ok = 0;
        if (!created && ok) break;          /* the selected file holds no BinSCII */
        if (more && !found) break;          /* not a part: the parts end here */
    }
    if (ok && created && written != total) { why = "Parts missing"; ok = 0; }
    if (!created) {
        if (why) note(why);
        return;
    }
    if (out && RF(fclose)(out)) { why = "Close"; ok = 0; }
    if (ok && !read_back()) { why = "Read-back"; ok = 0; }
    if (!ok) {
        if (!discard(path)) return;
        a.sprintf(a.note, "%s: %s removed.", why, name);
        return;
    }
    a.sprintf(a.note, "%s: %lu bytes, $%02X/$%04X, %u chunks.", name, written, type, aux, segs);
}
