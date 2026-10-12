/* unsq.c -- SQueezed files (.QQ) and AppleLink ACU archives ("fZink"),
 * extracted into the other panel. From the ! menu, on the selected file.
 *
 * The formats, and the reference this overlay is tested against, are in
 * tools/squeeze_ref.py (after CiderPress II's Squeeze and AppleLink notes):
 * a Huffman code, its tree first, over a run-length code ($90 n). A .QQ
 * file names what it holds and ends its header with a checksum of it; a
 * .QQ taken out of a Binary II archive by BINARY2 keeps its ProDOS type,
 * which the result gets. An ACU archive is a list of records, each stored
 * or squeezed, with its type and plain length; directories are skipped,
 * so is a plain record typed $0F (counted, named in the note: the panels
 * would walk it as a folder), and partial paths flattened to their last
 * name.
 *
 * Every file follows the one contract of the file services: created only
 * under a free name (a taken one is skipped and counted), written, closed,
 * read back byte for byte against a second decode, and removed if
 * anything fails -- a damaged stream stops the extraction.
 *
 * A big overlay: the core rereads the panels on return. */
#define UTIL_STUBS
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
    "SQueeze .QQ files and ACU archives: extract"
};
#pragma rodata-name (pop)

#pragma static-locals (on)

#define DLE      0x90
#define EOFSYM   256
#define MAXNODES 256

/* BSS: nothing zeroes it; everything below is written before it is read. */
static FILE* in;
static FILE* out;
static unsigned long base, limit;       /* the file offset of buf[0]; where the stream must end */
static unsigned long source_size;       /* current stream length, not the panel's cached size */
static unsigned int have, at;
static unsigned char eof;
static short nodes[MAXNODES * 2];      /* 16 bits, signed, on the host too */
static unsigned int nnodes;
static unsigned char bits, bpos;
static unsigned char obuf[512];
static unsigned int olen, verify_have;
static unsigned short osum;             /* the sum of the bytes written, 16 bits */
static unsigned char comparing;
/* Source restart offset; after rewinding, the verification byte count. */
static unsigned long restart;
static unsigned long ocount;
static unsigned long expected;          /* ACU's maximum output length */
static unsigned char hdr[0x36];
static char name[16];
static char dest[PATH_LEN + 1];
static unsigned char type, bad, checked, kept, folder;
/* Counts of files, 16 bits: an ACU archive holds up to 65,535 records. */
static unsigned int made, skipped;
static unsigned int aux;

/* -- reading ------------------------------------------------------------- */

static unsigned long tell(void) { return base + at; }

static unsigned char getb(void)
{
    if (at == have) {
        base += have;
        have = RF(fread)(buf, 1, 512, in);
        at = 0;
        /* A successful byte count does not override an I/O error or ESC
         * delivered by the read. Do not decode any of this refill. */
        if (!have || ferror(in) || stop()) { eof = 1; return 0; }
    }
    if (base + at >= limit) { eof = 1; return 0; }
    return buf[at++];
}

static unsigned int get16(void)
{
    unsigned char lo = getb();
    return lo | ((unsigned int)getb() << 8);
}

static unsigned char seek(unsigned long off)
{
    if (RF(fseek)(in, off, SEEK_SET)) { eof = 1; return 0; }
    base = off;
    have = at = 0;
    return 1;
}

static unsigned char grab(unsigned char* p, unsigned int n)
{
    while (n--) *p++ = getb();
    return !eof;
}

static unsigned long le32(const unsigned char* p)
{
    return p[0] | ((unsigned int)p[1] << 8) | ((unsigned long)p[2] << 16) | ((unsigned long)p[3] << 24);
}

/* -- writing ------------------------------------------------------------- */

static void flush(void)
{
    if (olen && RF(fwrite)(obuf, 1, olen, out) != olen) bad = 1;
    olen = 0;
}

static void putb(unsigned char c)
{
    /* Refuse the first excess byte, including inside an RLE run. Only
     * the exclusively created output is writable; no source/AUX writes. */
    if (ocount >= expected) { bad = 1; return; }
    osum += c;
    ++ocount;
    if (comparing) {
        /* Only read our closed exclusive output. A sum cannot detect
         * permuted bytes; compare against the source decoded again.
         * No source or AUX writes, and cleanup still owns only dest. */
        if (olen == verify_have) {
            verify_have = RF(fread)(obuf, 1, sizeof obuf, out); olen = 0;
            if (!verify_have || ferror(out)) { bad = 1; return; }
        }
        if (obuf[olen++] != c) bad = 1;
        if (!(ocount & 511)) {
            a.progress_bar(name, ocount, restart);
            if (stop()) bad = 1;
        }
        return;
    } else {
        obuf[olen++] = c;
        if (olen == sizeof obuf) flush();
    }
    if (!(ocount & 1023)) {
        /* measured on the archive: a .QQ does not say how long it grows */
        a.progress_bar(name, tell(), source_size);
        if (stop()) bad = 1;
    }
}

/* -- the stream ---------------------------------------------------------- */

/* The next symbol, or 0xFFFF on a broken stream. */
static unsigned int symbol(void)
{
    unsigned int node = 0, steps = 0;
    int child;
    for (;;) {
        if (bpos == 8) {
            bits = getb();
            if (eof) return 0xFFFF;
            bpos = 0;
        }
        if (node >= nnodes || ++steps > MAXNODES) return 0xFFFF;
        child = nodes[node * 2 + ((bits >> bpos) & 1)];
        ++bpos;
        if (child < 0) return (unsigned int)(-(child + 1));
        node = (unsigned int)child;
    }
}

/* A squeezed stream from the file position, into out. 1 when it ended well. */
static unsigned char unsqueeze(void)
{
    unsigned int i, c, k;
    int last = -1;
    nnodes = get16();
    if (eof || nnodes > MAXNODES) return 0;
    for (i = 0; i < nnodes * 2; ++i) nodes[i] = (short)get16();
    if (eof) return 0;
    if (!nnodes) return 1;
    bpos = 8;
    for (;;) {
        c = symbol();
        if (c == EOFSYM) return 1;
        if (c > EOFSYM || bad) return 0;
        if (c != DLE) {
            putb((unsigned char)c);
            last = c;
            continue;
        }
        k = symbol();
        if (k > 255) return 0;
        if (!k) {
            putb(DLE);
            last = DLE;
            continue;
        }
        if (last < 0) return 0;
        while (--k != 0) putb((unsigned char)last);
    }
}

/* n stored bytes into out. */
static unsigned char copy(unsigned long n)
{
    unsigned char c;
    while (n--) {
        c = getb();
        if (eof || bad) return 0;
        putb(c);
        if (bad) return 0;
    }
    return 1;
}

/* Read back against the same source decoded a second time. */
static unsigned char read_back(unsigned char squeezed, unsigned long n)
{
    unsigned char ok;
    if (stop() || ferror(in) || !seek(restart) ||
        !(out = RF(fopen)(dest, "rb"))) return 0;
    comparing = 1;
    restart = ocount;
    olen = verify_have = osum = 0; ocount = 0; eof = 0;
    ok = squeezed ? unsqueeze() : copy(n);
    if (bad || ferror(in) || olen != verify_have || RF(fread)(obuf, 1, 1, out) || ferror(out)) ok = 0;
    if (ok && !bad) a.progress_bar(name, ocount, ocount);
    if (RF(fclose)(out)) ok = 0;
    comparing = 0;
    if (stop()) ok = 0;
    return ok;
}

/* One file: created under name, filled by squeezed (1) or stored bytes
 * (n); its length must be want (unless ~0), its sum check (when checked).
 * 0 stops the extraction (bad says so). */
static unsigned char one(unsigned char squeezed, unsigned long n, unsigned long want, unsigned int check)
{
    unsigned char ok;
    /* ESC during header reads or seeks must precede CREATE, including a
     * colliding name or an empty file. Previously verified outputs stay;
     * no current output is owned, and source/AUX remain read-only. */
    if (stop()) return 0;
    /* A stored fork's exact output size is already known. Reject a
     * contradiction before CREATE, even if its name is taken. */
    if (!squeezed && n != want) return 0;
    if (!name[0] || !join(dest, other->path, name)) {
        /* A name/path failure is not a collision. No output is owned:
         * stop before CREATE and preserve prior files, source and AUX. */
        bad = 3;
        return 0;
    }
    ok = newfile(dest, type, aux, 1);
    if (ok) {
        /* Failed CREATE grants no ownership. Only a duplicate is a skip;
         * other errors stop before opening or cleaning this destination. */
        if (ok != 0x47) { bad = 2; return 0; }
        ++skipped;
        return 1;
    }
    restart = tell(); comparing = 0; expected = want;
    out = RF(fopen)(dest, "wb");
    olen = osum = 0;
    ocount = 0;
    ok = out != 0 && (squeezed ? unsqueeze() : copy(n));
    if (out) {
        flush();
        if (ferror(out)) ok = 0;
        if (RF(fclose)(out)) ok = 0;
    }
    if (ok && (bad || (want != 0xFFFFFFFFUL && ocount != want) || (checked && osum != check)))
        ok = 0;
    if (ok && !read_back(squeezed, n)) ok = 0;
    if (!ok) {
        bad = 1;
        kept = !discard(dest);          /* its note, then, is the last word */
        return 0;
    }
    ++made;
    return 1;
}

static void wrapper_name(void)
{
    unsigned char k;
    RF(strcpy)(name, a.selected->name);
    k = RF(strlen)(name);
    if (k > 3 && !RF(strcmp)(name + k - 3, ".QQ")) name[k - 3] = 0;
}

/* A ProDOS name from n bytes of a name, its last component: upper case,
 * anything but letters, digits and periods a period, no leading
 * non-letter, 15 characters at most. */
static void set_name(const unsigned char* s, unsigned char n)
{
    unsigned char k = 0, c;
    while (n--) {
        c = *s++;
        if (c == '/' || c == ':') { k = 0; continue; }
        if (c >= 'a' && c <= 'z') c -= 32;
        if (!((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '.')) c = '.';
        if (!k && !(c >= 'A' && c <= 'Z')) continue;
        if (k < 15) name[k++] = c;
    }
    name[k] = 0;
}

static unsigned char standalone(void)
{
    unsigned int check;
    unsigned char raw[64], n = 0, c;
    check = get16();
    while ((c = getb()) != 0 && !eof) if (n < sizeof raw) raw[n++] = c;
    if (eof) return 0;
    set_name(raw, n);
    if (!name[0]) wrapper_name();
    type = a.selected->type;
    aux = a.selected->aux;
    checked = 1;
    return one(1, 0, 0xFFFFFFFFUL, check);
}

static unsigned char acu(void)
{
    unsigned int count, nlen;
    unsigned long rlen, dlen, fork;
    unsigned char raw[64];
    count = hdr[0] | ((unsigned int)hdr[1] << 8);   /* the archive header, read */
    while (count--) {
        if (!grab(hdr, 0x36)) return 0;
        nlen = hdr[0x32] | ((unsigned int)hdr[0x33] << 8);
        if (nlen > sizeof raw || !grab(raw, nlen)) return 0;
        rlen = le32(hdr + 0x0E);
        dlen = le32(hdr + 0x12);
        /* Subtract before adding: untrusted 32-bit lengths may wrap on
         * cc65, and SEEK_SET beyond EOF may succeed. Validate even records
         * that will be skipped, before creating any output for this record. */
        fork = tell();
        if (fork > source_size || rlen > source_size - fork) return 0;
        fork += rlen;
        if (dlen > source_size - fork) return 0;
        if (!seek(fork)) return 0;
        /* A directory record is skipped; a file typed $0F too, counted:
         * the panels would walk it as a folder. */
        if (hdr[0x20] == 0x0D || hdr[0x18] == 0x0F) {
            if (hdr[0x20] != 0x0D) { ++skipped; folder = 1; }
            if (!seek(fork + dlen)) return 0;
            continue;
        }
        if (hdr[1] != 0 && hdr[1] != 3) return 0;
        /* ProDOS EOF is 24 bits. In particular, an ACU length of $FFFFFFFF
         * must not become the standalone .QQ's unknown-length sentinel. */
        if (le32(hdr + 0x26) > 0xFFFFFFUL) return 0;
        set_name(raw, (unsigned char)nlen);
        type = hdr[0x18];
        aux = hdr[0x1A] | ((unsigned int)hdr[0x1B] << 8);
        limit = fork + dlen;
        checked = 0;                    /* ACU's data CRCs cannot be trusted */
        if (!one(hdr[1] == 3, dlen, le32(hdr + 0x26), 0)) return 0;
        limit = source_size;
        if (tell() > fork + dlen) return 0;
        if (!seek(fork + dlen) || eof) return 0;
    }
    return 1;
}

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    unsigned char ok = 0, io_bad;
    init(api);
    if (!a.selected->name[0] || a.selected->type == 0x0F || !a.full[0] || !(in = RF(fopen)(a.full, "rb"))) {
        note("Not a SQueezed file or an ACU archive.");
        return;
    }
    if (!other->path[0] || other->fs) {
        RF(fclose)(in);
        note("Other panel: open a ProDOS directory.");
        return;
    }
    /* The archive can have changed since the panel was read. No offsets
     * or fork lengths are trusted until its current length is available. */
    /* Only service-table streams share the resident's open-file state;
     * overlay-local ftell would use a different cc65 descriptor table.
     * Count actual reads instead and reject an error, not just short EOF. */
    source_size = 0;
    while ((have = RF(fread)(buf, 1, 512, in)) != 0) {
        source_size += have;
        if (source_size > 0xFFFFFFUL || stop()) break;
    }
    if (ferror(in) || source_size > 0xFFFFFFUL || cancelled ||
        RF(fseek)(in, 0, SEEK_SET)) {
        RF(fclose)(in);
        note("Archive size unreadable: nothing extracted.");
        return;
    }
    base = have = at = eof = bad = made = skipped = kept = folder = 0;
    limit = source_size;
    if (grab(hdr, 2) && hdr[0] == 0x76 && hdr[1] == 0xFF) {
        ok = standalone();
    } else if (grab(hdr + 2, 18) && hdr[4] == 'f' && hdr[5] == 'Z' && hdr[6] == 'i' && hdr[7] == 'n' && hdr[8] == 'k') {
        ok = acu();
    } else if (!cancelled) {
        io_bad = ferror(in) != 0;
        RF(fclose)(in);
        note(io_bad ? "Archive I/O error: nothing extracted." : "Not a SQueezed file or an ACU archive.");
        return;
    }
    /* The source is read-only; only exclusively created outputs were
     * written, closed and read back. Do not turn a source read/close error
     * into complete success or delete those already verified outputs.
     * No AUX is used. Always close, even when the stream has an error. */
    io_bad = ferror(in) != 0;
    if (RF(fclose)(in)) io_bad = 1;
    /* ESC may arrive during the final close, even with no files extracted.
     * Verified outputs remain owned by the user; no cleanup or AUX writes. */
    if (stop()) ok = 0;
    if (kept) return;
    if (io_bad) {
        a.sprintf(a.note, "%u extracted, %u skipped; archive I/O error, stopped.", made, skipped);
        return;
    }
    if (!ok && !bad && !made && !skipped && !cancelled) { note("Damaged archive: nothing extracted."); return; }
    a.sprintf(a.note, "%u extracted, %u skipped (name taken%s)%s", made, skipped,
              folder ? " or type $0F" : "",
              ok ? "." : cancelled ? "; stopped." : bad == 2 ?
              "; create failed, stopped." : bad == 3 ?
              "; name/path invalid, stopped." : "; damaged, stopped.");
}
