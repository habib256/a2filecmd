/* move.c -- move a file or a whole directory WITHOUT copying it: the
 * directory entry is rewritten from one directory into another on the same
 * volume, and not one block of data is touched. A tree of 400 blocks moves
 * in the time it takes to write three blocks.
 *
 * From the ! menu, on the entry under the cursor of the active panel; it
 * goes into the directory the OTHER panel shows.
 *
 * Why not just RENAME. ProDOS 8's RENAME ($C2) is the obvious candidate and
 * it does not work: asked to rename /VOL/A/X to /VOL/B/X it answers $40,
 * invalid pathname syntax. Measured under ProDOS 8 2.4 in the emulator, not
 * assumed. So the entry has to be carried by hand, and that means knowing
 * exactly what points at what:
 *
 *   - an entry's header_pointer (+$25) holds the KEY block of the directory
 *     that contains it -- not the block the entry happens to sit in;
 *   - a subdirectory's own header holds, at +$23, the block that contains
 *     ITS entry (that one IS the block, not the key), at +$25 the entry's
 *     number in that block counting from ONE, and at +$26 the entry length;
 *   - each directory header counts its live entries at +$21.
 *
 * All three were read off a real volume before a line of this was written
 * (/IMG/EXTASIE of the reference disk: entry in block 22 slot 2, key block
 * 2869, header_pointer 22, parent_pointer 22, parent_entry 3).
 *
 * The order of the writes is the one thing that decides what a power cut
 * costs. The target entry is written FIRST and the source entry cleared
 * after: interrupted in between, the file is listed in two directories,
 * which VOLINFO reports as shared blocks and which loses nothing. The other
 * order would leave the blocks allocated and named by nobody -- the file
 * would be gone. Every block written is read back and compared before the
 * move is called done.
 *
 * Two volumes have no entry that can point from one to the other, so there
 * the move is what it has always been: the file is COPIED and the original
 * removed. The copy is read back and compared in full before anything is
 * deleted -- a move that loses the file because the copy came up short is
 * not a move. Only a file: a whole tree across volumes is what the core's V
 * command already walks and copies.
 *
 * What it refuses, and why:
 *
 *   - a directory into its own subtree: the moved branch would name itself
 *     and be lost to the root, exactly what copy_one refuses in the core;
 *   - a name already used in the target directory;
 *   - a target directory with no free entry: growing a directory means
 *     allocating a block and rewriting its own entry's size, a different
 *     and riskier job. It says so instead;
 *   - anything in the program's own A2FILE directory: moving A2FILE.CODE or
 *     a .PLG out from under a running A2FC breaks it.
 *
 * One entry per run, the one under the cursor. A big overlay's code covers
 * the panels' entry tables at $2000, so the tags -- which are indexes INTO
 * that table -- can no longer be turned into names. api->selected is the
 * one entry the core copies out for us.
 *
 * A big overlay: the graphics page is its own, the core sets the tags aside,
 * rereads both panels and redraws. The block being rewritten lives in
 * api->copy_buf; the readback needs a second 512 bytes of its own. */
#define UTIL_VOLUME
#define UTIL_WRITE
#include "util.h"

void __fastcall__ plugin_entry(const struct A2fcApi* api);
struct Header {
    unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*);
    unsigned char r[3]; char desc[52];
};
#pragma rodata-name (push, "OVLHDR")
const struct Header __plugin_header = {
    PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry, {0,0,0},
    "Move without copying: rewrite the directory entry"
};
#pragma rodata-name (pop)

#define ENTRY_LEN   39
#define PER_BLOCK   13
#define E_HDRPTR    0x25            /* in an entry: the key block of its directory */
#define H_COUNT     0x21            /* in a header: how many live entries */
#define H_PARENT    0x23            /* in a subdirectory header: the block of its entry */
#define H_PARENTNUM 0x25            /* ... the entry's number there, counting from one */
#define H_PARENTLEN 0x26            /* ... and the entry length */

/* BSS: nothing zeroes it; everything below is written before it is read. */
static unsigned char unit;              /* the ProDOS unit of the volume */
static unsigned int srckey, dstkey;     /* the two directories, by key block */
static unsigned char ent[ENTRY_LEN];    /* the entry being carried across */
static unsigned char scratch[512];      /* the readback */
static char seek[NAME_LEN];             /* the name being looked for */
static char found[NAME_LEN];            /* a name read out of a directory */
static char target[PATH_LEN];           /* where a cross-volume copy goes */

static const char m_dirs[]  = "Open a real ProDOS directory in each panel.";
static const char m_same[]  = "Both panels show the same directory.";
static const char m_tree[]  = "A tree across volumes: V copies it, this cannot.";
static const char m_here[]  = "%s is already in the other panel.";
static const char m_cask[]  = "Another volume: copy %s there and remove it here?";
static const char m_cbad[]  = "Copy failed: %s was NOT removed.";
static const char m_vbad[]  = "The copy reads back different: %s was NOT removed.";
static const char m_del[]   = "%s copied across, but it could not be removed here.";
static const char m_cok[]   = "%s copied to the other volume and removed here.";
static const char m_prog[]  = "That is the program's own A2FILE directory: refused.";
static const char m_pick[]  = "Put the cursor on what should move.";
static const char m_self[]  = "A directory cannot move inside itself.";
static const char m_walk[]  = "The directories cannot be walked from the volume root.";
static const char m_taken[] = "The other panel already has a %s.";
static const char m_gone[]  = "%s is no longer in this directory.";
static const char m_full[]  = "The target directory has no free entry left.";
static const char m_io[]    = "Block %u failed: the move is INCOMPLETE, run VOLINFO.";
static const char m_ok[]    = "%s moved: %u block%s untouched, nothing copied.";
static const char m_ask[]   = "Move %s into %s without copying it?";

/* One block into api->copy_buf. */
static unsigned char rd(unsigned int b)
{
    return !readblk(unit, b, buf);
}

/* copy_buf back to block `b`, then read back and compare: a drive that
 * accepts the write and keeps its old contents must not pass for done. */
static unsigned char wr(unsigned int b)
{
    unsigned int i;
    if (writeblk(unit, b, buf)) return 0;
    if (readblk(unit, b, scratch)) return 0;
    for (i = 0; i < 512 && buf[i] == scratch[i]; ++i) ;
    return i == 512;
}

/* The name of entry `k` of the block in copy_buf, into `found`. */
static void name_of(unsigned char k)
{
    unsigned char* e = buf + 4 + (unsigned int)k * ENTRY_LEN;
    unsigned char n = e[0] & 15;
    a.memcpy(found, e + 1, n);
    found[n] = 0;
}

/* Walk the directory whose key block is `key` looking for `seek`. On
 * success the block that holds it is left in copy_buf and *blk / *slot say
 * where it is. Storage types 14 and 15 are headers, never entries. */
static unsigned char locate(unsigned int key, unsigned int* blk, unsigned char* slot)
{
    unsigned int b = key;
    unsigned char k, kind;
    while (b) {
        if (!rd(b)) return 0;
        for (k = 0; k < PER_BLOCK; ++k) {
            kind = buf[4 + (unsigned int)k * ENTRY_LEN] >> 4;
            if (!kind || kind >= 14) continue;
            name_of(k);
            if (!a.strcmp(found, seek)) { *blk = b; *slot = k; return 1; }
        }
        b = rd16(buf + 2);
    }
    return 0;
}

/* The first free entry of that directory, a deleted one included. Entry 0
 * of the first block is the header and is never free. */
static unsigned char free_slot(unsigned int key, unsigned int* blk, unsigned char* slot)
{
    unsigned int b = key;
    unsigned char k, first = 1;
    while (b) {
        if (!rd(b)) return 0;
        for (k = first; k < PER_BLOCK; ++k)
            if (!(buf[4 + (unsigned int)k * ENTRY_LEN] >> 4)) { *blk = b; *slot = k; return 1; }
        first = 0;
        b = rd16(buf + 2);
    }
    return 0;
}

/* The key block of `path`, walked from the volume directory: the first
 * component is the volume, whose directory is block 2, and each one after
 * it is an entry to step into. 0 if any of it is missing. */
static unsigned int key_of(const char* path)
{
    unsigned int b = 2, blk;
    unsigned char i, n, slot;
    if (path[0] != '/') return 0;
    for (i = 1; path[i] && path[i] != '/'; ++i) ;
    while (path[i]) {
        ++i;                                    /* past the slash */
        for (n = 0; path[i] && path[i] != '/'; ++i)
            if (n < NAME_LEN - 1) seek[n++] = path[i];
        seek[n] = 0;
        if (!n) break;                          /* a trailing slash */
        if (!locate(b, &blk, &slot)) return 0;
        b = rd16(buf + 4 + (unsigned int)slot * ENTRY_LEN + 0x11);   /* its key block */
        if (!b) return 0;
    }
    return b;
}

/* Add `delta` to the live-entry count in a directory's header. */
static unsigned char count_add(unsigned int key, unsigned int delta)
{
    if (!rd(key)) return 0;
    wr16(buf + 4 + H_COUNT, rd16(buf + 4 + H_COUNT) + delta);
    return wr(key);
}

/* Is `path` the directory the program keeps itself in? api->cfg_path is
 * "/VOL/A2FILE/A2FILE.CFG", so that directory is cfg_path up to its last
 * slash. Moving A2FILE.CODE or a .PLG out from under a running A2FC is not
 * something to find out about afterwards. */
static unsigned char program_dir(const char* path)
{
    unsigned char i;
    for (i = 0; path[i] && path[i] == a.cfg_path[i]; ++i) ;
    return !path[i] && a.cfg_path[i] == '/';
}

/* `dst` is `entry` itself or something under it: moving a directory there
 * would cut it off from the root. The same test copy_one makes in the core. */
static unsigned char into_itself(const char* entry, const char* dst)
{
    unsigned char i;
    for (i = 0; entry[i] && entry[i] == dst[i]; ++i) ;
    return !entry[i] && (!dst[i] || dst[i] == '/');
}

/* No entry can point from one volume to another, so across volumes a move
 * is a copy followed by a removal. The copy is verified against the original
 * BEFORE the original goes: the whole point of a move is that the file still
 * exists afterwards. `buf` reads the source, `scratch` the copy. */
static void copy_across(const struct Entry* e)
{
    FILE *in, *out;
    unsigned long left, done = 0;
    unsigned int n, i;
    unsigned char bad = 0;

    if (e->type == 0x0F) { note(m_tree); return; }
    if (!join(target, other->path, e->name)) { note(m_walk); return; }
    in = a.fopen(target, "rb");
    if (in) { a.fclose(in); a.sprintf(a.note, m_here, e->name); return; }

    a.sprintf((char*)scratch, m_cask, e->name);
    if (!a.confirm((char*)scratch)) { note(""); return; }

    *a.filetype = e->type;
    *a.auxtype = e->aux;
    in = a.fopen(a.full, "rb");
    out = a.fopen(target, "wb");
    if (!in || !out) bad = 1;
    for (left = e->size; left && !bad; left -= n) {
        n = left > 512 ? 512 : (unsigned int)left;
        if (a.fread(buf, 1, n, in) != n || a.fwrite(buf, 1, n, out) != n) bad = 1;
        else { done += n; a.progress_bar(e->name, done, e->size); }
    }
    if (in) a.fclose(in);
    if (out && a.fclose(out)) bad = 1;
    if (bad) { a.remove(target); a.sprintf(a.note, m_cbad, e->name); return; }

    /* Read both back and compare before the original is touched. */
    in = a.fopen(a.full, "rb");
    out = a.fopen(target, "rb");
    if (!in || !out) bad = 1;
    for (left = e->size; left && !bad; left -= n) {
        n = left > 512 ? 512 : (unsigned int)left;
        if (a.fread(buf, 1, n, in) != n || a.fread(scratch, 1, n, out) != n) bad = 1;
        else for (i = 0; i < n; ++i) if (buf[i] != scratch[i]) { bad = 1; break; }
    }
    if (in) a.fclose(in);
    if (out) a.fclose(out);
    if (bad) { a.remove(target); a.sprintf(a.note, m_vbad, e->name); return; }

    if (a.remove(a.full)) { a.sprintf(a.note, m_del, e->name); return; }
    a.strcpy(a.reselect, e->name);
    a.sprintf(a.note, m_cok, e->name);
}

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    const struct Entry* e;
    unsigned int sblk, dblk, subkey, blocks, bad = 0;
    unsigned char sslot, dslot, isdir;

    init(api);
    e = a.selected;

    if (pan->fs || other->fs || !pan->path[0] || !other->path[0]) { note(m_dirs); return; }
    if (!a.strcmp(pan->path, other->path)) { note(m_same); return; }
    if (program_dir(pan->path) || program_dir(other->path)) { note(m_prog); return; }
    if (!e->name[0] || (e->name[0] == '.' && e->name[1] == '.')) { note(m_pick); return; }
    if (!a.full[0]) { note(m_pick); return; }
    if (into_itself(a.full, other->path)) { note(m_self); return; }

    /* The same volume, compared by UNIT: two names can be the same drive.
     * Anything else has to be copied -- no entry points across a volume. */
    unit = unit_of(pan->path, 0);
    if (!unit || unit != unit_of(other->path, 0)) { copy_across(e); return; }

    srckey = key_of(pan->path);
    dstkey = key_of(other->path);
    if (!srckey || !dstkey) { note(m_walk); return; }

    a.strcpy(seek, e->name);
    if (locate(dstkey, &dblk, &dslot)) { a.sprintf(a.note, m_taken, e->name); return; }
    if (!locate(srckey, &sblk, &sslot)) { a.sprintf(a.note, m_gone, e->name); return; }
    a.memcpy(ent, buf + 4 + (unsigned int)sslot * ENTRY_LEN, ENTRY_LEN);
    isdir = (ent[0] >> 4) == 13;
    subkey = rd16(ent + 0x11);
    blocks = rd16(ent + 0x13);
    if (!free_slot(dstkey, &dblk, &dslot)) { note(m_full); return; }

    a.sprintf((char*)scratch, m_ask, e->name, other->path);
    if (!a.confirm((char*)scratch)) { note(""); return; }

    /* 1. The entry into the target directory, its header pointer put right.
     *    This one first: interrupted after it, the file is in two places,
     *    which is recoverable; the other way round it would be in none. */
    wr16(ent + E_HDRPTR, dstkey);
    if (!rd(dblk)) { bad = dblk; goto fail; }
    a.memcpy(buf + 4 + (unsigned int)dslot * ENTRY_LEN, ent, ENTRY_LEN);
    if (!wr(dblk)) { bad = dblk; goto fail; }

    /* 2. A moved subdirectory says where its own entry now lives. */
    if (isdir) {
        if (!rd(subkey)) { bad = subkey; goto fail; }
        wr16(buf + 4 + H_PARENT, dblk);
        buf[4 + H_PARENTNUM] = dslot + 1;           /* counted from one */
        buf[4 + H_PARENTLEN] = ENTRY_LEN;
        if (!wr(subkey)) { bad = subkey; goto fail; }
    }

    /* 3. The old entry goes. Storage type 0 is what DESTROY leaves. */
    if (!rd(sblk)) { bad = sblk; goto fail; }
    buf[4 + (unsigned int)sslot * ENTRY_LEN] = 0;
    if (!wr(sblk)) { bad = sblk; goto fail; }

    /* 4. Both counts. */
    if (!count_add(srckey, 0xFFFF)) { bad = srckey; goto fail; }
    if (!count_add(dstkey, 1)) { bad = dstkey; goto fail; }

    a.strcpy(a.reselect, e->name);
    a.sprintf(a.note, m_ok, e->name, blocks, blocks == 1 ? "" : "s");
    return;
fail:
    a.sprintf(a.note, m_io, bad);
}
