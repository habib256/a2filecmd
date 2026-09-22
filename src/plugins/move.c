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
 *   - a FULL volume directory: a subdirectory with no free entry is grown
 *     by a block, but the volume directory's four are fixed and it has no
 *     entry of its own to rewrite;
 *   - anything in the program's own A2FILE directory, or that directory
 *     itself or one of its parents: moving A2FILE.CODE or a .PLG out from
 *     under a running A2FC breaks it, and so does renaming its path;
 *   - a disk that changed while the question was on screen: everything
 *     the move was decided on is read again and compared after the answer;
 *   - a directory that cannot be read, or whose block chain does not end:
 *     a failed read is never taken for a free name or a free entry.
 *
 * One entry per run, the one under the cursor. A big overlay's code covers
 * the panels' entry tables at $2000, so the tags -- which are indexes INTO
 * that table -- can no longer be turned into names. api->selected is the
 * one entry the core copies out for us.
 *
 * A big overlay: the graphics page is its own, the core sets the tags aside,
 * rereads both panels and redraws. The block being rewritten lives in
 * api->copy_buf; the readback needs a second 512 bytes of its own. */
#define UTIL_STUBS
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
#define H_BITMAP    0x23            /* in the VOLUME header: the first bitmap block */
#define H_TOTAL     0x25            /* ... and how many blocks the volume has */
#define E_BLOCKS    0x13            /* in an entry: blocks used */
#define E_EOF       0x15            /* ... and the length in bytes, three of them */
/* No directory is longer: its header counts 65,535 entries at most, 13 to a
 * block. With the volume's own size, the bound on any walk of a chain, so
 * a chain that loops back on itself ends in a refusal, not a hang. */
#define DIR_MAX     5042

/* BSS: nothing zeroes it; everything below is written before it is read. */
static unsigned char unit;              /* the ProDOS unit of the volume */
static unsigned int srckey, dstkey;     /* the two directories, by key block */
static unsigned int dirmax;             /* the longest chain a walk follows */
/* Where the move reads and writes, as examine() found it. */
static struct Plan {
    unsigned int sblk, dblk, subkey, blocks;
    unsigned char sslot, dslot, isdir, room;
} plan;
/* Every block examine() reads goes into a Fletcher sum (two 16-bit halves):
 * one byte changed anywhere in them always changes it. */
static unsigned int sum1, sum2, asked1, asked2;
static unsigned int hit_blk;            /* where locate/free_slot found it */
static unsigned char hit_slot;
static const struct Entry* sel;         /* api->selected */
static unsigned char ent[ENTRY_LEN];    /* the entry being carried across */
static unsigned char scratch[512];      /* the readback */
/* Lookups finish before ent carries the moved entry or scratch is used for
 * write verification. Reuse those buffers for the two lookup names. */
#define seek ((char*)ent)
#define found ((char*)scratch)
/* The resident provides a destination path buffer outside this overlay. */
#define target a.other_full
/* The shared exclusive CREATE, its Pascal path in the readback buffer,
 * which is free until copying starts. */
#define FC_PATH scratch
#define FC_PREPARE(p) (scratch[0] = RF(strlen)(p), RF(strcpy)((char*)scratch + 1, p))
#include "file_create.h"

static const char m_dirs[]  = "ProDOS directories in both panels.";
static const char m_same[]  = "Both panels: same directory.";
static const char m_btree[] = "\2";   /* a tree across volumes: the core walks it itself, marked or not */
static const char m_here[]  = "%s is already in the other panel.";
static const char m_cask[]  = "Another volume: copy %s there and remove it here?";
static const char m_cbad[]  = "Copy failed: %s was NOT removed.";
static const char m_vbad[]  = "Copy differs: %s was NOT removed.";
static const char m_kept[]  = "%s NOT removed; its partial copy stays there too.";
static const char m_del[]   = "%s copied, but not removed here.";
static const char m_cok[]   = "%s copied to the other volume and removed here.";
static const char m_prog[]  = "Cannot move the program's A2FILE files.";
static const char m_pick[]  = "Select an entry to move.";
static const char m_locked[] = "Source is locked.";
static const char m_self[]  = "Cannot move inside itself.";
static const char m_walk[]  = "The directories cannot be walked.";
static const char m_taken[] = "Other panel already has %s.";
static const char m_gone[]  = "%s is no longer here.";
static const char m_full[]  = "Volume directory full: cannot grow.";
static const char m_grew[]  = "Move %s into %s? Its directory must grow a block.";
static const char m_nogrow[] = "Target directory could not be made longer.";
static const char m_changed[] = "Disk changed: nothing written.";
static const char m_ok[]    = "%s moved: %u block%s untouched, nothing copied.";
static const char m_ask[]   = "Move %s into %s without copying it?";

/* One block into api->copy_buf, added to the sum. */
static unsigned char rd(unsigned int b)
{
    unsigned int i;
    if (readblk(unit, b, buf)) return 0;
    for (i = 0; i < 512; ++i) { sum1 += buf[i]; sum2 += sum1; }
    return 1;
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
    RF(memcpy)(found, e + 1, n);
    found[n] = 0;
}

/* Walk the directory whose key block is `key` looking for `seek`. 1: found,
 * the block that holds it is left in copy_buf and hit_blk / hit_slot say
 * where it is; 0: not there; 2: a block could not be read or the chain does not end
 * -- never proof that the name is free. Storage types 14 and 15 are
 * headers, never entries. */
static unsigned char locate(unsigned int key)
{
    unsigned int b = key, n = 0;
    unsigned char k, kind;
    while (b) {
        if (++n > dirmax || stop() || !rd(b)) return 2;
        for (k = 0; k < PER_BLOCK; ++k) {
            kind = buf[4 + (unsigned int)k * ENTRY_LEN] >> 4;
            if (!kind || kind >= 14) continue;
            name_of(k);
            if (!RF(strcmp)(found, seek)) { hit_blk = b; hit_slot = k; return 1; }
        }
        b = rd16(buf + 2);
    }
    return 0;
}

/* The first free entry of that directory, a deleted one included. Entry 0
 * of the first block is the header and is never free. 1: found, 0: the
 * directory is full, 2: unreadable or endless, as for locate. */
static unsigned char free_slot(unsigned int key)
{
    unsigned int b = key, n = 0;
    unsigned char k, first = 1;
    while (b) {
        if (++n > dirmax || !rd(b)) return 2;
        for (k = first; k < PER_BLOCK; ++k)
            if (!(buf[4 + (unsigned int)k * ENTRY_LEN] >> 4)) { hit_blk = b; hit_slot = k; return 1; }
        first = 0;
        b = rd16(buf + 2);
    }
    return 0;
}

/* The first free block of the volume, marked used. The bitmap is one bit a
 * block, SET meaning free, 4,096 blocks to a bitmap block; blocks 0 to 5 are
 * already spoken for, so a plain first-fit scan never offers them. Taken
 * before anything points at it: a crash then leaks a block, which VOLINFO
 * reports and FIXIT will mend, where the other order would leave a directory
 * pointing at a block the volume thinks is free. */
static unsigned int alloc_block(void)
{
    unsigned int total, bitmap, base, i;

    if (!rd(2)) return 0;
    bitmap = rd16(buf + 4 + H_BITMAP);
    total = rd16(buf + 4 + H_TOTAL);
    for (base = 0; base < total; base += 4096) {
        if (!rd(bitmap + base / 4096)) return 0;
        for (i = 0; i < 4096 && base + i < total; ++i)
            if (buf[i >> 3] & (0x80 >> (i & 7))) {
                buf[i >> 3] &= ~(0x80 >> (i & 7));
                if (!wr(bitmap + base / 4096)) return 0;
                return base + i;
            }
        /* Stop before the final increment: on cc65, $F000 + $1000 wraps
         * to zero and a full volume larger than 61,440 blocks loops forever. */
        if (total - base <= 4096) break;
    }
    return 0;
}

/* One more block on the end of a directory, and its own entry told that it
 * is a block longer. The volume directory cannot grow: its four blocks are
 * fixed and it has no entry of its own to rewrite -- the caller checks that
 * before asking.
 *
 * The block is allocated first, then filled, then linked, then accounted
 * for. Interrupted anywhere in there the volume stays readable: at worst a
 * block is lost, never a directory cut in two. */
static unsigned char grow_dir(unsigned int key)
{
    unsigned int last, next, nb, pblk, n = 0;
    unsigned char* p;
    unsigned char pslot;

    if (!rd(key)) return 0;
    pblk = rd16(buf + 4 + H_PARENT);
    pslot = buf[4 + H_PARENTNUM];
    if (!pblk || !pslot || pslot > PER_BLOCK ||
        buf[4 + H_PARENTLEN] != ENTRY_LEN) return 0;
    --pslot;                                    /* it is counted from one */

    /* Validate the backlink before allocating or linking anything. A bad
     * parent slot must not rewrite another file, or escape the block buffer. */
    if (!rd(pblk)) return 0;
    p = buf + 4 + (unsigned int)pslot * ENTRY_LEN;
    if ((p[0] >> 4) != 13 || rd16(p + 0x11) != key) return 0;
    if (!rd(key)) return 0;

    last = key;                                 /* the end of the chain */
    for (;;) {
        next = rd16(buf + 2);
        if (!next) break;
        if (++n >= dirmax) return 0;            /* a chain that loops */
        last = next;
        if (!rd(last)) return 0;
    }

    nb = alloc_block();
    if (!nb) return 0;

    a.memset(buf, 0, 512);                      /* every entry free, pointing back */
    wr16(buf, last);
    if (!wr(nb)) return 0;

    if (!rd(last)) return 0;                    /* and the chain points forward */
    wr16(buf + 2, nb);
    if (!wr(last)) return 0;

    if (!rd(pblk)) return 0;                    /* one more block, 512 more bytes */
    p = buf + 4 + (unsigned int)pslot * ENTRY_LEN;
    wr16(p + E_BLOCKS, rd16(p + E_BLOCKS) + 1);
    if ((p[E_EOF + 1] += 2) < 2) ++p[E_EOF + 2];    /* 512 more bytes: 2 in the middle one */
    return wr(pblk);
}

/* The key block of `path`, walked from the volume directory: the first
 * component is the volume, whose directory is block 2, and each one after
 * it is an entry to step into. 0 if any of it is missing. */
static unsigned int key_of(const char* path)
{
    unsigned int b = 2;
    unsigned char i, n;
    unsigned char* entry;
    if (path[0] != '/') return 0;
    for (i = 1; path[i] && path[i] != '/'; ++i) ;
    while (path[i]) {
        ++i;                                    /* past the slash */
        for (n = 0; path[i] && path[i] != '/'; ++i)
            if (n < NAME_LEN - 1) seek[n++] = path[i];
        seek[n] = 0;
        if (!n) break;                          /* a trailing slash */
        if (locate(b) != 1) return 0;
        entry = buf + 4 + (unsigned int)hit_slot * ENTRY_LEN;
        /* A cached panel path does not guarantee this entry is still a
         * directory. Never walk a file's data/index blocks as directory records. */
        if ((entry[0] >> 4) != 13) return 0;
        b = rd16(entry + 0x11);                  /* the directory's key block */
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

/* `p` as a whole-component prefix of `q`: the index in q just past it
 * (q[i] is 0 or '/'), or 0 if it is not one. `p` is never empty. */
static unsigned char prefix(const char* p, const char* q)
{
    unsigned char i;
    for (i = 0; p[i] && p[i] == q[i]; ++i) ;
    return !p[i] && (!q[i] || q[i] == '/') ? i : 0;
}

/* Where is `path` from the directory the program keeps itself in?
 * api->cfg_path is "/VOL/A2FILE/A2FILE.CFG", so that directory is cfg_path
 * up to its last slash. 1: that directory; 2: one of its parents, the
 * volume root included; 0: neither. Moving A2FILE.CODE or a .PLG out from
 * under a running A2FC, or the directory that holds them, is not something
 * to find out about afterwards -- but the volume root is only a parent: its
 * other entries may come and go. */
static unsigned char program_dir(const char* path)
{
    unsigned char i = prefix(path, a.cfg_path);
    if (!i || !a.cfg_path[i]) return 0;
    for (++i; a.cfg_path[i] && a.cfg_path[i] != '/'; ++i) ;
    return a.cfg_path[i] ? 2 : 1;
}

/* Everything the move is decided on, read from the disk into `plan` and
 * `ent`, every block of it summed. 0 if the move may go ahead, otherwise
 * the refusal (written with the entry's name). */
static const char* examine(void)
{
    unsigned char k;

    sum1 = sum2 = 0;
    if (!rd(2) || (buf[4] >> 4) != 15) return m_walk;
    dirmax = rd16(buf + 4 + H_TOTAL);
    if (dirmax > DIR_MAX) dirmax = DIR_MAX;

    srckey = key_of(pan->path);
    dstkey = key_of(other->path);
    if (!srckey || !dstkey || srckey == dstkey) return m_walk;

    RF(strcpy)(seek, sel->name);
    k = locate(dstkey);
    if (k == 1) return m_taken;
    if (k) return m_walk;
    k = locate(srckey);
    if (k == 2) return m_walk;
    if (!k) return m_gone;
    plan.sblk = hit_blk; plan.sslot = hit_slot;
    RF(memcpy)(ent, buf + 4 + (unsigned int)hit_slot * ENTRY_LEN, ENTRY_LEN);
    /* Raw directory writes bypass ProDOS DESTROY's access check. Use the
     * freshly read entry, not a possibly stale panel access flag. */
    if (!(ent[30] & 0x80)) return m_locked;
    k = ent[0] >> 4;
    plan.isdir = k == 13;
    plan.subkey = rd16(ent + 0x11);
    plan.blocks = rd16(ent + 0x13);
    if (!plan.isdir && (k < 1 || k > 3)) return m_walk;
    if (plan.isdir && (!rd(plan.subkey) || (buf[4] >> 4) != 14 ||
        rd16(buf + 4 + H_PARENT) != plan.sblk || buf[4 + H_PARENTNUM] != plan.sslot + 1 ||
        buf[4 + H_PARENTLEN] != ENTRY_LEN)) return m_walk;
    /* A target with no free entry is grown by a block -- but only after the
     * user has said yes, and never the volume directory, whose four blocks
     * are fixed and which has no entry of its own to rewrite. */
    plan.room = free_slot(dstkey);
    plan.dblk = hit_blk; plan.dslot = hit_slot;
    if (plan.room == 2) return m_walk;
    if (!plan.room && dstkey == 2) return m_full;
    return 0;
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
    unsigned char bad = 0, err, check;
    const char* m = m_cbad;

    if (e->type == 0x0F) { note(m_btree); return; }
    if (!join(target, other->path, e->name)) { note(m_walk); return; }

    a.sprintf((char*)scratch, m_cask, e->name);
    if (a.arg != 'B' && !RF(confirm)((char*)scratch)) { note(""); return; }

    /* CREATE must grant us a new entry before fopen("wb") or failure
     * cleanup can touch this path. */
    err = newfile(target, e->type, e->aux, 1);
    if (err) {
        a.sprintf(a.note, err == 0x47 ? m_here : m_cbad, e->name);
        return;
    }
    *a.filetype = e->type;
    *a.auxtype = e->aux;
    /* Two passes over the same loop: the copy, then both files read back
     * and compared BEFORE the original is touched. The bar restarts at 0
     * for the check, which is as long as the copy. */
    for (check = 0; check < 2; ++check) {
        if (check) m = m_vbad;
        in = RF(fopen)(a.full, "rb");
        out = RF(fopen)(target, check ? "rb" : "wb");
        if (!in || !out) bad = 1;
        for (left = e->size, done = 0; left && !bad; left -= n) {
            a.progress_bar(e->name, done, e->size);
            n = left > 512 ? 512 : (unsigned int)left;
            if (stop() || RF(fread)(buf, 1, n, in) != n) bad = 1;
            else if (!check) { if (RF(fwrite)(buf, 1, n, out) != n) bad = 1; }
            else if (RF(fread)(scratch, 1, n, out) != n) bad = 1;
            else for (i = 0; i < n; ++i) if (buf[i] != scratch[i]) { bad = 1; break; }
            done += n;
        }
        /* The panel's size can be stale. Matching that prefix is not enough:
         * deleting a longer source would silently discard its remaining bytes.
         * Both streams must end at the size we copied, including empty files. */
        if (check && !bad && (RF(fread)(buf, 1, 1, in) || RF(fread)(scratch, 1, 1, out))) bad = 1;
        /* A zero-byte probe is EOF only if neither stream has an I/O error.
         * Keep the source until both verification handles have closed too. */
        if (in) { if (ferror(in)) bad = 1; if (RF(fclose)(in)) bad = 1; }
        if (out) { if (ferror(out)) bad = 1; if (RF(fclose)(out)) bad = 1; }
        if (bad) goto drop;
    }

    if (RF(remove)(a.full)) { a.sprintf(a.note, m_del, e->name); return; }
    RF(strcpy)(a.reselect, e->name);
    a.sprintf(a.note, m_cok, e->name);
    return;
drop:
    /* Only the entry newly created above is removed. If it stays, the note
     * says so: a retry's exclusive CREATE refuses it, nothing overwrites it. */
    a.sprintf(a.note, RF(remove)(target) ? m_kept : m, e->name);
}

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    unsigned char restored;
    unsigned int src_count, dst_count;
    const char* why;

    init(api);
    sel = a.selected;

    if (pan->fs || other->fs || !pan->path[0] || !other->path[0]) { note(m_dirs); return; }
    if (!RF(strcmp)(pan->path, other->path)) { note(m_same); return; }
    if (program_dir(pan->path) == 1 || program_dir(other->path) == 1) { note(m_prog); return; }
    if (!sel->name[0] || (sel->name[0] == '.' && sel->name[1] == '.')) { note(m_pick); return; }
    if (!a.full[0]) { note(m_pick); return; }
    if (program_dir(a.full)) { note(m_prog); return; }
    /* The other panel is the entry itself or under it: moving a directory
     * there would cut it off from the root, as copy_one refuses in the core. */
    if (prefix(a.full, other->path)) { note(m_self); return; }

    /* The same volume, compared by UNIT: two names can be the same drive.
     * Anything else has to be copied -- no entry points across a volume. */
    unit = unit_of(pan->path, 0);
    if (!unit || unit != unit_of(other->path, 0)) { copy_across(sel); return; }

    why = examine();
    if (!why && a.arg != 'B') {
        asked1 = sum1; asked2 = sum2;
        a.sprintf((char*)scratch, plan.room ? m_ask : m_grew, sel->name, other->path);
        if (!RF(confirm)((char*)scratch)) { note(""); return; }
        /* The same guard as DOSWRITE's: a floppy swapped, or a directory
         * changed, while the question was on screen must not receive block
         * numbers read from the disk that was there before. Everything is
         * read again; the writes below use this second reading, and only if
         * every block of it matches the first -- the volume header in
         * block 2 included, so another disk in the drive does not pass. A
         * sum, not a copy: MOVE has no room for one. It misses no single
         * changed byte; several changes cancelling out is left to a chance
         * of about one in 2^32. */
        why = examine();
        if (!why && (sum1 != asked1 || sum2 != asked2)) why = m_changed;
    }
    if (why) { a.sprintf(a.note, why, sel->name); return; }

    if (!plan.room) {
        if (!grow_dir(dstkey) || free_slot(dstkey) != 1) { note(m_nogrow); return; }
        plan.dblk = hit_blk; plan.dslot = hit_slot;
    }

    if (!rd(srckey)) { note(m_walk); return; }
    src_count = rd16(buf + 4 + H_COUNT);
    if (!rd(dstkey)) { note(m_walk); return; }
    dst_count = rd16(buf + 4 + H_COUNT);

    /* 1. The entry into the target directory, its header pointer put right.
     *    This one first: interrupted after it, the file is in two places,
     *    which is recoverable; the other way round it would be in none. */
    wr16(ent + E_HDRPTR, dstkey);
    if (!rd(plan.dblk)) { goto fail; }
    RF(memcpy)(buf + 4 + (unsigned int)plan.dslot * ENTRY_LEN, ent, ENTRY_LEN);
    if (!wr(plan.dblk)) { goto fail; }

    /* 2. A moved subdirectory says where its own entry now lives. */
    if (plan.isdir) {
        if (!rd(plan.subkey)) { goto fail; }
        wr16(buf + 4 + H_PARENT, plan.dblk);
        buf[4 + H_PARENTNUM] = plan.dslot + 1;           /* counted from one */
        buf[4 + H_PARENTLEN] = ENTRY_LEN;
        if (!wr(plan.subkey)) { goto fail; }
    }

    /* 3. The old entry goes. Storage type 0 is what DESTROY leaves. */
    if (!rd(plan.sblk)) { goto fail; }
    buf[4 + (unsigned int)plan.sslot * ENTRY_LEN] = 0;
    if (!wr(plan.sblk)) { goto fail; }

    /* 4. Both counts. */
    if (!count_add(srckey, 0xFFFF)) { goto fail; }
    if (!count_add(dstkey, 1)) { goto fail; }

    RF(strcpy)(a.reselect, sel->name);
    a.sprintf(a.note, m_ok, sel->name, plan.blocks, plan.blocks == 1 ? "" : "s");
    return;
fail:
    /* A reported I/O failure may have committed its write. Restore the
     * source FIRST, then its backlink, then remove the duplicate entry.
     * Never destroy the destination if restoring the source failed. */
    restored = 0;
    wr16(ent + E_HDRPTR, srckey);
    if (rd(plan.sblk)) {
        RF(memcpy)(buf + 4 + (unsigned int)plan.sslot * ENTRY_LEN, ent, ENTRY_LEN);
        restored = wr(plan.sblk);
    }
    if (restored && plan.isdir) {
        restored = rd(plan.subkey);
        if (restored) {
            wr16(buf + 4 + H_PARENT, plan.sblk);
            buf[4 + H_PARENTNUM] = plan.sslot + 1;
            restored = wr(plan.subkey);
        }
    }
    if (restored && rd(plan.dblk)) {
        buf[4 + (unsigned int)plan.dslot * ENTRY_LEN] = 0;
        restored = wr(plan.dblk);
    } else restored = 0;
    if (restored && rd(srckey)) { wr16(buf + 4 + H_COUNT, src_count); restored = wr(srckey); }
    else restored = 0;
    if (restored && rd(dstkey)) { wr16(buf + 4 + H_COUNT, dst_count); restored = wr(dstkey); }
    else restored = 0;
    if (restored) note("Move failed; original restored.");
    else note("Move incomplete: delete neither entry; run VOLINFO.");
}
