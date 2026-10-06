/* prodos_claims.h -- does a ProDOS volume's bitmap call USED every block its
 * directories and files name?
 *
 * A writer that takes blocks the bitmap calls free is trusting the bitmap
 * with other people's data. A bitmap can be wrong in the one direction that
 * matters: a block a file still names, marked free. ProDOS would hand it
 * out and so did IMGPUT -- measured: the data block of a file marked free
 * went to the new file, and "Copied" was the answer; the key block of the
 * very directory being added to, marked free, was overwritten with the new
 * file's bytes and the directory's entries were gone.
 *
 * So before a free bit is believed, everything the volume references is
 * walked once: every block of every directory chain from block 2 down,
 * every key block, every index block of a sapling or a tree, both forks of
 * an extended file, and every data pointer those hold. Each must be inside
 * the volume and marked used. One that is not, a block that cannot be read,
 * a storage type this does not know how to follow, a chain that loops, a
 * tree more than sixteen directories deep, the volume's included (the
 * limit FIXIT and VOLINFO know as ProDOS's): the walk says 0 and the caller
 * writes NOTHING. A volume in that state is FIXIT's to look at first.
 *
 * It needs no map of its own. The question is not "who owns this block"
 * but "is this referenced block marked used", and the bitmap answers that
 * one page at a time. A walk reads every directory and index block of the
 * volume and no data block; on a big volume that is minutes, which is why
 * claims_read is expected to give a sign of life and to honour ESC.
 *
 * The includer provides, before including this:
 *
 *   static unsigned char claims_used(unsigned int b);
 *       1 when block b may be named by a directory or a file: inside the
 *       volume, not a boot block, not one of the bitmap's own pages, and
 *       marked used. 0 otherwise, and 0 when the bitmap cannot be read.
 *   static unsigned char claims_read(unsigned int b, unsigned char* to);
 *       1 when block b passed claims_used and was read into `to`; 0 on a
 *       read error or when the user stopped the walk.
 *   CLAIMS_DIR, CLAIMS_IDX
 *       two 512-byte buffers. CLAIMS_DIR holds a directory block, or the
 *       key block of an extended file, or the master index of a tree;
 *       CLAIMS_IDX an index block. Both are scratch when the walk returns.
 *   CLAIMS_WORD(p)
 *       the 16-bit little-endian word at p.
 *   CLAIMS_BLOCKS
 *       the number of blocks of the volume: no walk enters more directory
 *       blocks than that, so a chain that loops ends.
 *   CLAIMS_TARGET (optional)
 *       the key block of a directory the caller is about to write into.
 *       The walk then also demands to MEET it, as the key block of a live
 *       directory: a key kept from an earlier look at the volume may by now
 *       be a deleted directory's block, or a file's.
 *
 * What it does not prove: that no two files share a block, that the counts
 * and lengths are right, that a block marked used is referenced by anyone.
 * None of those can make a free block somebody's; FIXIT checks them.
 */
#ifndef PRODOS_CLAIMS_H
#define PRODOS_CLAIMS_H

#define CLAIMS_DEPTH 16
#define CLAIMS_ENTRY 0x27
#define CLAIMS_FIRST (4 + CLAIMS_ENTRY)                 /* past a header */
#define CLAIMS_END   (4 + 13 * CLAIMS_ENTRY)            /* past the last entry */

/* Where the walk stood in each directory above the one it is in: the
 * block, and the offset of the next entry in it. Four arrays of bytes and
 * not two of words: cc65 indexes a byte array with one instruction and a
 * word array with a dozen. */
static unsigned char claims_bl[CLAIMS_DEPTH - 1], claims_bh[CLAIMS_DEPTH - 1];
static unsigned char claims_ol[CLAIMS_DEPTH - 1], claims_oh[CLAIMS_DEPTH - 1];
/* The directory block CLAIMS_DIR holds; 0, which no directory is, when a
 * tree or an extended file borrowed the buffer and the block must be read
 * again. Reading it again for every entry, as a first version did, made
 * thirteen reads of each directory block. */
static unsigned int claims_held;

/* Index block b, and every block it names. A zero pointer is a sparse
 * hole, at any level. */
static unsigned char claims_index(unsigned int b)
{
    unsigned char i = 0;
    unsigned int ref;
    if (!claims_read(b, CLAIMS_IDX)) return 0;
    do {
        ref = (CLAIMS_IDX)[i] | ((unsigned int)((CLAIMS_IDX) + 256)[i] << 8);
        if (ref && !claims_used(ref)) return 0;
        ++i;
    } while (i);
    return 1;
}

/* One fork: a seedling's only block, a sapling's index and what it names,
 * a tree's master index and its index blocks. Anything else is a storage
 * type this cannot follow, and what cannot be followed is refused. */
static unsigned char claims_fork(unsigned char kind, unsigned int b)
{
    unsigned char i = 0;
    unsigned int ref;
    if (kind == 1) return claims_used(b);
    if (kind == 2) return claims_index(b);
    if (kind != 3) return 0;
    claims_held = 0;
    if (!claims_read(b, CLAIMS_DIR)) return 0;
    do {
        ref = (CLAIMS_DIR)[i] | ((unsigned int)((CLAIMS_DIR) + 256)[i] << 8);
        if (ref && !claims_index(ref)) return 0;
        ++i;
    } while (i);
    return 1;
}

static unsigned char claims_walk(void)
{
    /* blk and off: the directory block the walk is in and the offset of
     * the next entry in it. Offset 0 is a key block not yet entered, whose
     * first entry must be a header. */
    unsigned char depth = 0, kind;
    unsigned int blk = 2, off = 0, b, budget = CLAIMS_BLOCKS;
#ifdef CLAIMS_TARGET
    unsigned char met = 0;
#endif
    const unsigned char* e;
    claims_held = 0;
    for (;;) {
        if (claims_held != blk) {
            if (!claims_read(blk, CLAIMS_DIR)) return 0;
            claims_held = blk;
        }
        if (!off) {
            /* A key block: no block before it, and its first entry is the
             * header -- $F for the volume, $E for a subdirectory -- of a
             * directory of thirteen 39-byte entries a block. */
            kind = (CLAIMS_DIR)[4] >> 4;
            if (depth) ++kind;
            if (kind != 15 || CLAIMS_WORD(CLAIMS_DIR) ||
                (CLAIMS_DIR)[0x23] != CLAIMS_ENTRY || (CLAIMS_DIR)[0x24] != 13) return 0;
#ifdef CLAIMS_TARGET
            if (blk == (CLAIMS_TARGET)) met = 1;
#endif
            off = CLAIMS_FIRST;
        }
        if (off == CLAIMS_END) {
            /* Past the last entry: the next block of the chain, or back
             * to the directory this one was an entry of. */
            blk = CLAIMS_WORD((CLAIMS_DIR) + 2);
            off = 4;
            if (blk) {
                --budget;
                if (!budget) return 0;
            } else {
#ifdef CLAIMS_TARGET
                if (!depth) return met;
#else
                if (!depth) return 1;
#endif
                --depth;
                blk = claims_bl[depth] | ((unsigned int)claims_bh[depth] << 8);
                off = claims_ol[depth] | ((unsigned int)claims_oh[depth] << 8);
            }
            continue;
        }
        e = (CLAIMS_DIR) + off;
        off += CLAIMS_ENTRY;
        kind = e[0] >> 4;
        if (!kind) continue;                            /* a free slot */
        b = CLAIMS_WORD(e + 0x11);
        if (kind == 13) {
            --budget;
            if (depth == CLAIMS_DEPTH - 1 || !budget) return 0;
            claims_bl[depth] = (unsigned char)blk;
            claims_bh[depth] = (unsigned char)(blk >> 8);
            claims_ol[depth] = (unsigned char)off;
            claims_oh[depth] = (unsigned char)(off >> 8);
            ++depth;
            blk = b;
            off = 0;
        } else if (kind == 5) {
            /* An extended file: its key block holds two mini-entries, the
             * data fork at +$000 and the resource fork at +$100, each a
             * storage type and a key. The second is taken out before the
             * first is followed: a tree fork borrows this buffer. */
            claims_held = 0;
            if (!claims_read(b, CLAIMS_DIR)) return 0;
            kind = (CLAIMS_DIR)[256];
            b = CLAIMS_WORD((CLAIMS_DIR) + 257);
            if (!claims_fork((CLAIMS_DIR)[0], CLAIMS_WORD((CLAIMS_DIR) + 1)) ||
                !claims_fork(kind, b)) return 0;
        } else if (!claims_fork(kind, b)) return 0;
    }
}
#endif
