/* Shared cross-volume MOVE implementation; also exercised by the host harness. */
/* The resident provides a destination path buffer outside this overlay. */
#define target a.other_full
/* The shared exclusive CREATE, its Pascal path in the readback buffer,
 * which is free until copying starts. */
#define FC_PATH scratch
#define FC_PREPARE(p) (scratch[0] = RF(strlen)(p), RF(strcpy)((char*)scratch + 1, p))
#include "file_create.h"

static const char m_here[]  = "%s is already in the other panel.";
static const char m_cask[]  = "Another volume: copy %s there and remove it here?";
static const char m_cbad[]  = "Copy failed: %s was NOT removed.";
static const char m_vbad[]  = "Copy differs: %s was NOT removed.";
static const char m_kept[]  = "%s NOT removed; its partial copy stays there too.";
static const char m_del[]   = "%s copied, but not removed here.";
static const char m_cok[]   = "%s copied to the other volume and removed here.";
/* A byte-stream copy verifies standard data files only, never both forks
 * of storage type 5. Read metadata afresh; a failed lookup cannot permit
 * creating a replacement or deleting the source. No raw or AUX writes. */
static unsigned char standard_source(const struct Entry* e)
{
    return !getinfo(a.full) && info.storage >= 1 && info.storage <= 3 &&
        (info.access & 0x80) && info.type == e->type && info.aux == e->aux;
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

    if (!standard_source(e)) { a.sprintf(a.note, m_cbad, e->name); return; }

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

    /* Metadata may change during copying or readback. At this point the
     * destination is closed and verified: retain it and the source if the
     * source is now forked, protected, unreadable, its type/aux changed,
     * or cancellation arrived. Verified bytes alone do not preserve a
     * program's type or load address; the destination uses the panel's. */
    if (stop() || !standard_source(e) || RF(remove)(a.full)) { a.sprintf(a.note, m_del, e->name); return; }
    RF(strcpy)(a.reselect, e->name);
    a.sprintf(a.note, m_cok, e->name);
    return;
drop:
    /* Only the entry newly created above is removed. If it stays, the note
     * says so: a retry's exclusive CREATE refuses it, nothing overwrites it. */
    a.sprintf(a.note, RF(remove)(target) ? m_kept : m, e->name);
}
