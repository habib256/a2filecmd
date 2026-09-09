/* find.c -- finds files by name pattern, or by a text they contain, in
 * the whole volume of the active panel, and jumps to the one chosen.
 *
 * From the ! menu. A pattern is typed on line 22 (the core's prompt
 * refuses `=` and `?`, so the keys are read here): Copy II Plus wildcards,
 * `=` for any run of characters, `?` for one, upper-cased. A pattern that
 * starts with `"` is a TEXT search: the rest is looked for inside every
 * file of the volume, case-insensitive and high bit ignored, 512 bytes at
 * a time through api->copy_buf with an overlap of the last bytes of the
 * previous read, so a text astride two reads is found too.
 *
 * The volume is the first component of the panel's path ("/VOL"), or the
 * selected volume in the volume list. It is walked breadth-first with one
 * directory open at a time: a queue of directory paths in the scratch
 * area, the current directory read to its end (its subdirectories
 * queued, its files matched), then the next of the queue. In a text
 * search the files cannot be read while the directory is open (both go
 * through copy_buf), so the names of a directory are pooled, the
 * directory closed, and the pool searched; a directory with more files
 * than the pool holds is reread from where the pool stopped.
 *
 * The matches, full paths, are listed on a full screen: up and down to
 * choose, Return sets the active panel on the directory of the chosen
 * file with the cursor on it (the core rereads and redraws after a big
 * overlay), Escape leaves. Escape during the walk aborts it. "Nothing
 * found." when there is no match.
 *
 * A big overlay under 5,376 bytes: $3000-$3FFF is its scratch memory --
 * the queue (32 paths of 64), the matches (20 paths of 80) and the name
 * pool (28 names of 16). api->full carries the path being built (and
 * the line being written), api->other_full the directory being read --
 * not a pointer into the queue, which is packed when it fills up. The
 * service table is copied into a static: a call through it costs half
 * of one through api->. */

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
    "Find files by name pattern or text in the volume"
};
#pragma rodata-name (pop)

#define KBD     (*(volatile unsigned char*)0xC000)
#define KBDSTRB (*(volatile unsigned char*)0xC010)

#define QMAX   32                          /* directories waiting, 64 bytes each */
#define QLEN   64
#define RMAX   20                          /* matches kept, 80 bytes each */
#define RLEN   80
#define PMAX   28                          /* names pooled per directory read, 16 each */
#define PLEN   16
#define PATMAX 32                          /* the pattern, or the text */
#define ROW0   2                           /* the first row of the list */

#define QUEUE   ((char*)0x3000)            /* 32 x 64 = 2048: $3000-$37FF */
#define RESULTS ((char*)0x3800)            /* 20 x 80 = 1600: $3800-$3E3F */
#define POOL    ((char*)0x3E40)            /* 28 x 16 =  448: $3E40-$3FFF */

/* BSS: nothing zeroes it; everything below is written before it is read. */
static struct A2fcApi a;                   /* the service table, copied */
static struct Panel* pan;
static char* path;                         /* a.full: the path being built, or the line written (80) */
static char* dir;                          /* a.other_full: the directory being read (80) */
static char* root;                         /* a.input: the volume, "/VOL" (17) */
static char pat[PATMAX + 1];               /* the pattern, or the text, upper case */
static unsigned char plen;
static unsigned char text;                 /* 1: a text search */
static unsigned char nres, qhead, qtail;
static unsigned char aborted, cut;         /* cut: queue or list overflow, or a path too long */

static void msg(const char* s) { a.message(s); }

/* Escape pressed? Any other key waiting is dropped. */
static unsigned char abort_key(void)
{
    if (KBD & 0x80) {
        unsigned char k = KBD & 0x7F;
        KBDSTRB = 0;
        if (k == KEY_ESC) aborted = 1;
    }
    return aborted;
}

/* Copy II Plus wildcards, without recursion: `=` backtracks to the last
 * one seen. Both strings are upper case. */
static unsigned char match(const char* s)
{
    const char* p = pat;
    const char* star = 0;
    const char* ss = 0;
    while (*s) {
        if (*p == '?' || *p == *s) { ++p; ++s; }
        else if (*p == '=') { star = p++; ss = s; }
        else if (star) { p = star + 1; s = ++ss; }
        else return 0;
    }
    while (*p == '=') ++p;
    return *p == 0;
}

/* Does the file at `path` contain the text? Reads of 512 bytes into
 * copy_buf, the first plen-1 bytes of the buffer being the tail of the
 * previous read, normalised: high bit off, upper case. */
static unsigned char file_has(void)
{
    unsigned char* buf = a.copy_buf;
    unsigned char keep = plen - 1, i, c;
    unsigned int n, end, j;
    FILE* f = a.fopen(path, "rb");
    if (!f) return 0;
    n = 0;                                 /* nothing kept yet: the first read starts at 0 */
    for (;;) {
        unsigned char* p = buf + n;
        end = a.fread(p, 1, 512 - n, f);
        if (!end) break;
        for (j = end; j; --j, ++p) {
            c = *p & 0x7F;
            if (c >= 'a' && c <= 'z') c -= 32;
            *p = c;
        }
        end += n;                          /* bytes valid in buf */
        if (end >= plen) {
            for (j = 0; j <= end - plen; ++j) {
                if (buf[j] != (unsigned char)pat[0]) continue;
                for (i = 1; i < plen && buf[j + i] == (unsigned char)pat[i]; ++i) ;
                if (i == plen) { a.fclose(f); return 1; }
            }
        }
        if (end < 512) break;
        for (j = 0; j < keep; ++j) buf[j] = buf[512 - keep + j];
        n = keep;
        if (abort_key()) break;
    }
    a.fclose(f);
    return 0;
}

/* The path in a.full becomes a match, if the list has room. */
static void add_result(void)
{
    if (nres >= RMAX) { cut = 1; return; }
    a.strcpy(RESULTS + nres * RLEN, path);
    ++nres;
}

/* "dir/name" into a.full; 0 if it does not fit. */
static unsigned char join(const char* dir, const char* name)
{
    unsigned char dl = a.strlen(dir), nl = a.strlen(name);
    if (dl + 1 + nl >= RLEN) return 0;
    a.memcpy(path, dir, dl);
    path[dl] = '/';
    a.strcpy(path + dl + 1, name);
    return 1;
}

/* Queues the directory `dir/name`; the queue is packed first if its
 * consumed head leaves room (nothing points into it: the directory
 * being read is a copy). */
static void enqueue(const char* name)
{
    unsigned char i;
    if (qtail >= QMAX && qhead) {
        for (i = 0; qhead + i < qtail; ++i)
            a.memcpy(QUEUE + i * QLEN, QUEUE + (qhead + i) * QLEN, QLEN);
        qtail -= qhead;
        qhead = 0;
    }
    if (qtail >= QMAX || !join(dir, name) || a.strlen(path) >= QLEN) { cut = 1; return; }
    a.strcpy(QUEUE + qtail * QLEN, path);
    ++qtail;
}

/* One directory of the queue: its subdirectories queued, its files
 * matched by name, or pooled then read for the text. */
static void walk_dir(void)
{
    unsigned char skip = 0, seen, n, more, i;
    const struct DirEntry* de = a.dir_entry;
    a.sprintf(path, "Searching %s...", dir);
    msg(path);
    for (;;) {
        if (!a.dir_open(dir)) return;
        n = 0; seen = 0; more = 0;
        while (a.dir_next()) {
            if (abort_key()) break;
            if (de->type == 0x0F) { if (!skip) enqueue(de->name); continue; }
            if (!text) { if (match(de->name) && join(dir, de->name)) add_result(); continue; }
            if (seen++ < skip) continue;
            if (n >= PMAX) { more = 1; break; }
            a.strcpy(POOL + n * PLEN, de->name);
            ++n;
        }
        a.dir_close();
        for (i = 0; i < n && !aborted && nres < RMAX; ++i)
            if (join(dir, POOL + i * PLEN) && file_has()) add_result();
        if (!more || aborted || nres >= RMAX) return;
        skip += n;
    }
}

/* The key loop on line 22: the pattern, echoed as it is typed. Returns 0
 * on Escape, or an empty pattern. */
static unsigned char read_pattern(void)
{
    char k;
    plen = 0;
    for (;;) {
        pat[plen] = 0;
        a.sprintf(path, "Find (= any run, ? one char, \"text): %s_", pat);
        msg(path);
        k = a.cgetc();
        if (k == KEY_ESC) { msg(""); return 0; }
        if (k == KEY_RETURN) { if (plen) return 1; }
        else if (k == KEY_DELETE || k == KEY_LEFT) { if (plen) --plen; }
        else if (k >= ' ' && k <= '~' && plen < PATMAX) {
            if (k >= 'a' && k <= 'z') k -= 32;
            pat[plen++] = k;
        }
    }
}

/* The list of matches, one per row from ROW0, the chosen one in
 * inverse video. Returns the index chosen, or 0xFF on Escape. */
static unsigned char choose(void)
{
    unsigned char sel = 0, i;
    char k;
    a.clrscr();
    a.gotoxy(0, 0);
    a.cprintf("%u match(es) for %s%s in %s", nres, text ? "\"" : "", pat, root);
    a.bar_begin();
    a.keys_bar(0, "UP/DN Choose,RET Go there,ESC Leave");
    for (;;) {
        for (i = 0; i < nres; ++i) {
            a.gotoxy(0, ROW0 + i);
            a.revers(i == sel);
            a.cprintf("%-79s", RESULTS + i * RLEN);
        }
        a.revers(0);
        k = a.cgetc();
        if (k == KEY_ESC) return 0xFF;
        if (k == KEY_RETURN) return sel;
        if (k == KEY_UP && sel) --sel;
        else if (k == KEY_DOWN && sel + 1 < nres) ++sel;
    }
}

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    unsigned char i, sel;
    char* s;
    api->memcpy(&a, api, sizeof a);
    pan = a.panels;
    if (*a.active) ++pan;
    path = a.full;
    dir = a.other_full;
    root = a.input;
    if (pan->fs) { msg("Not in a disk image or a DOS 3.3 disk."); return; }
    /* The volume: the first component of the path, or the selected volume. */
    s = pan->path;
    if (!s[0]) s = a.selected->name;
    if (s[0] != '/') { msg("Select a ProDOS volume first."); return; }
    for (i = 1; s[i] && s[i] != '/' && i < NAME_LEN - 1; ++i) root[i] = s[i];
    root[0] = '/';
    root[i] = 0;
    a.strcpy(QUEUE, root);
    if (!read_pattern()) return;
    text = pat[0] == '"';
    if (text) {
        for (i = 0; i < plen; ++i) pat[i] = pat[i + 1];
        --plen;
        if (!plen) { msg(""); return; }
    }
    nres = 0; qhead = 0; qtail = 1; aborted = 0; cut = 0;
    while (qhead < qtail && !aborted && nres < RMAX) {
        a.strcpy(dir, QUEUE + qhead * QLEN);
        ++qhead;
        walk_dir();
    }
    if (!nres) { a.strcpy(a.note, aborted ? "Search aborted." : "Nothing found."); return; }
    sel = choose();
    if (sel != 0xFF) {
        /* The directory of the match into the panel's path, its name reselected. */
        s = RESULTS + sel * RLEN;
        for (i = a.strlen(s); s[i] != '/'; --i) ;
        a.strcpy(a.reselect, s + i + 1);
        s[i] = 0;                          /* a file at the root: "/VOL" */
        if (a.strlen(s) < PATH_LEN) { a.strcpy(pan->path, s); pan->first = 0; }
    }
    a.sprintf(a.note, "%u match(es)%s.", nres, aborted ? ", search aborted"
              : nres >= RMAX ? ", the first ones only" : cut ? ", some directories skipped" : "");
}
