/* goto.c -- favourite directories: jump to one in two keys, add the
 * current one, remove one. A service-table overlay.
 *
 * From the ! menu. The favourites live in a text file next to the program:
 * api->cfg_path is "/VOL/A2FILE/A2FILE.CFG", cut after its last slash and
 * followed by "GOTO.CFG" -- up to nine lines "PATH\r", type $04, the very
 * shape A2FILE.CFG has, so the file stays readable and editable by hand.
 * The overlay clears the screen, lists what it read, one numbered row each,
 * and reads one key:
 *
 *   1-9  the active panel jumps to that favourite;
 *   P    type an absolute ProDOS directory path (63 characters maximum);
 *        Return opens it, Delete/Left edits, ESC cancels. It is not saved
 *        as a favourite; lowercase is normalized and trailing slashes removed.
 *   A    the active panel's path is appended and the file rewritten --
 *        unless it is the volume list, an image or a DOS 3.3 panel, a path
 *        already listed, or the list already holds nine;
 *   M    source digit then destination digit: reorder the saved list;
 *        ESC or an unavailable number cancels without writing.
 *   D    then a digit: that favourite is dropped and the file rewritten;
 *   ESC  nothing.
 *
 * One key, one action: the screen is shown once and the overlay returns to
 * the panels with its message; running it again shows the new list.
 *
 * A BIG overlay, and not by taste: the small window is 1,280 bytes all
 * told, and this -- reading, parsing and rewriting a file, a nine-row
 * screen, three commands with their guards and a dozen messages -- comes to
 * some 1,500 bytes of cc65 code and 280 of strings. The small overlays
 * around it (volname, fixtypes) do one thing each, with no screen and no
 * file. Being big has one consequence worth stating: the entry tables of
 * the two panels live at $2000-$3FDC, which a big overlay covers, so
 * api->read_panel MUST NOT be called from here -- it would write directory
 * entries straight into this code. The core rereads and redraws both panels
 * on its own when a big overlay returns, so a jump only has to set the
 * panel's path; to tell a favourite that has been deleted or unmounted from
 * a good one, the path is opened with api->dir_open first (it reads the
 * core's own buffer, not ours) and the panel is left where it is if that
 * fails. For the same reason the last word goes through api->note, which
 * the core writes on line 22 after its redraw, and not through
 * api->message, which the redraw would wipe.
 *
 * Memory: the file is under 5,376 bytes, so $3000-$3FFF is ours (README).
 * The nine paths sit at $3000 in slots of 65 bytes (PATH_LEN and the zero,
 * 585 bytes in all): a whole ProDOS path fits, where api->copy_buf's 512
 * bytes would have forced 55 characters. $3400 upward holds the file as
 * read, then as written. api->copy_buf is left to the core, which uses it
 * for the directory block dir_open reads.
 *
 * Every service is reached through a stub -- a fastcall function whose body
 * puts the service's offset in Y and jumps to one trampoline, which drops
 * the argument its prologue pushed, fetches the pointer from the table and
 * jumps there with A/X and the C stack as the service expects them (the
 * trick volname.c explains: cc65 spends some 35 bytes on a call through a
 * pointer held in a variable, three on a call to a stub). It keeps the file
 * near two kilobytes, which is what makes $3000 legal to use. Plain 6502,
 * compiled without the optimiser (which would drop the ldy as dead before a
 * jmp); the last parameter of each stub is 16 bits so that the prologue
 * always pushes two bytes. */
#include <stddef.h>
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
    "Favourite directories: jump in two keys, add, del"
};
#pragma rodata-name (pop)

#define MAXFAV  9
#define SLOT    (PATH_LEN + 1)          /* 65: a whole ProDOS path and its zero */
#define LIST    ((char*)0x3000)         /* 9 x 65 = 585: $3000-$3248 */
#define TEXT    ((char*)0x3400)         /* GOTO.CFG as read, then as written */
#define MAXTEXT 2000                    /* of the 3 KB there: nine lines need 594 */
#define NONE    0xFF                    /* save(): no slot left out */
#define TAIL(s) (sizeof (s) - 1)        /* where the path goes after a heading */

static const char f_name[] = "GOTO.CFG";
static const char f_rb[]   = "rb";
static const char f_wb[]   = "wb";
static const char m_title[] = "GOTO -- favourite directories";
static const char m_keys[]  = "1-9 Go,P Path,A Add,M Move,D Delete,ESC Back";
static const char m_none[]  = "No favourites yet: A adds this directory";
static const char m_dir[]   = "Not a ProDOS directory: nothing to add.";
static const char m_room[]  = "The list is full: nine favourites.";
static const char m_dup[]   = "Already in the list.";
static const char m_gone[]  = "Gone: ";
static const char m_which[] = "Delete which one? 1-9";
static const char m_err[]   = "GOTO.CFG cannot be written.";
static const char m_jump[]  = "Jumped to ";
static const char m_add[]   = "Added ";
static const char m_del[]   = "Removed ";
static char num[] = "1 ";               /* DATA: the row number, rewritten in place */

/* Nothing here is read before being written at entry. */
static const struct A2fcApi* A;
static struct Panel* P;                 /* the active panel */
static char* N;                         /* api->note: what line 22 will say */
static FILE* fh;
static unsigned char count;
static char temp[PATH_LEN], backup[PATH_LEN];
static struct { unsigned char n; char* path; unsigned char fields[15]; } info;
static struct { unsigned char n; char* from; char* to; } ren;
static char cfg[PATH_LEN];              /* "/VOL/A2FILE/GOTO.CFG" */

/* The stubs into the service table (see above). */
#pragma optimize (push, off)
static void tramp(void)
{
    asm("sta tmp1");
    asm("stx tmp2");
    asm("jsr incsp2");              /* the argument the stub's prologue pushed */
    asm("lda %v", A);
    asm("sta ptr1");
    asm("lda %v+1", A);
    asm("sta ptr1+1");
    asm("lda (ptr1),y");
    asm("sta jmpvec+1");
    asm("iny");
    asm("lda (ptr1),y");
    asm("sta jmpvec+2");
    asm("lda tmp1");
    asm("ldx tmp2");
    asm("jmp jmpvec");
}
#define STUB(field) { asm("ldy #%b", offsetof(struct A2fcApi, field)); asm("jmp %v", tramp); }
static unsigned char __fastcall__ mli(unsigned char cmd,void* params) STUB(mli)
static void __fastcall__ msg(const char* s) STUB(message)
static void __fastcall__ cls(unsigned int unused) STUB(clrscr)
static void __fastcall__ at(unsigned char x, unsigned int y) STUB(gotoxy)
static void __fastcall__ put(const char* s) STUB(cputs)
static void __fastcall__ kbar(unsigned char x, const char* spec) STUB(keys_bar)
static char __fastcall__ getkey(unsigned int unused) STUB(cgetc)
static unsigned char __fastcall__ dopen(const char* path) STUB(dir_open)
static void __fastcall__ dclose(unsigned int unused) STUB(dir_close)
static char* __fastcall__ scpy(char* d, const char* s) STUB(strcpy)
static int __fastcall__ scmp(const char* a, const char* b) STUB(strcmp)
static unsigned char __fastcall__ slen(const char* s) STUB(strlen)
static FILE* __fastcall__ fopn(const char* path, const char* mode) STUB(fopen)
static unsigned int __fastcall__ frd(void* p, unsigned int sz, unsigned int n, FILE* f) STUB(fread)
static unsigned int __fastcall__ fwr(const void* p, unsigned int sz, unsigned int n, FILE* f) STUB(fwrite)
static int __fastcall__ fcls(FILE* f) STUB(fclose)
#pragma optimize (pop)

/* Slot `i` of the list, without a multiplication. */
static char* __fastcall__ slot(unsigned char i)
{
    char* p = LIST;
    while (i--) p += SLOT;
    return p;
}

/* A favourite is an absolute ProDOS path.  Check its component boundaries
 * before presenting it: otherwise a malformed line could be shown as a
 * favourite and only fail much later when the user tries to jump. */
static unsigned char valid_path(const char* p)
{
    unsigned char n = 0;
    if (*p++ != '/') return 0;
    if (!*p) return 1;                  /* the volume list root */
    while (*p) {
        if (*p == '/') {
            if (!n) return 0;           /* empty component */
            n = 0;
        } else {
            if (*p < ' ' || *p >= 127 || n == 15) return 0;
            ++n;
        }
        ++p;
    }
    return n != 0;                      /* no trailing slash in saved paths */
}

/* Parse the entire bounded file before offering actions. Never turn an
 * overlong path, embedded NUL or extra favourite into a partial list that
 * a later save could silently write over the original. Missing is empty. */
static unsigned char load(void)
{
    unsigned int n;
    unsigned char j;
    char* p = TEXT;
    char* end;
    char* d;
    count = 0;
    fh = fopn(cfg, f_rb);
    if (!fh) return 1;
    n = frd(p, 1, MAXTEXT + 1, fh);
    fcls(fh);
    if (n > MAXTEXT) return 0;
    end = p + n;
    while (p < end) {
        if (*p == '\r' || *p == '\n') { ++p; continue; }
        if (count == MAXFAV) return 0;
        d = slot(count);
        j = 0;
        while (p < end && *p != '\r' && *p != '\n') {
            if (!*p || j == PATH_LEN - 1) return 0;
            d[j++] = *p++;
        }
        d[j] = 0;
        if (!valid_path(d)) return 0;
        ++count;
    }
    return 1;
}

static void pascal(char* out,const char* path)
{
    scpy(out+1,path);out[0]=slen(path);
}
static unsigned char fileop(unsigned char cmd,const char* path)
{
    pascal(A->full,path);info.path=A->full;
    info.n=cmd==0xC4 ? 10 : cmd==0xC0 ? 7 : 1;
    return mli(cmd,&info);
}
static unsigned char rename_file(const char* from,const char* to)
{
    pascal(A->full,from);pascal(A->other_full,to);
    ren.n=2;ren.from=A->full;ren.to=A->other_full;
    return mli(0xC2,&ren);
}
static void discard_temp(void)
{
    scpy(N,fileop(0xC1,temp) ? (const char*)"Save failed; GOTO.TMP kept." : m_err);
}

/* Serialize to an exclusively created GOTO.TMP. Only after successful write
 * and close do we rename CFG to BAK, then TMP to CFG. A failed install rolls
 * BAK back; if rollback fails both recovery files are retained. No existing
 * TMP or BAK is ever overwritten. This is recoverable replacement, not an
 * atomic filesystem transaction across a power failure. */
static void save(unsigned char dead)
{
    unsigned char i;
    char* p = TEXT;
    char* q;
    for (i = 0; i < count; ++i) {
        if (i == dead) continue;
        q = slot(i);
        while (*q) *p++ = *q++;
        *p++ = '\r';
    }
    /* Never truncate either recovery file. Existing ones require review. */
    i=fileop(0xC4,backup);
    if(i!=0x46) { scpy(N,i ? m_err : (const char*)"GOTO.BAK exists; check saved files.");return; }
    for(i=0;i<15;++i)info.fields[i]=0;
    info.fields[0]=0xE3;info.fields[1]=0x04;info.fields[4]=1;
    i=fileop(0xC0,temp);
    if(i) { scpy(N,i==0x47 ? (const char*)"GOTO.TMP exists; check saved files." : m_err);return; }
    *A->filetype=0x04;*A->auxtype=0;
    fh=fopn(temp,f_wb);
    if(!fh) { discard_temp();return; }
    i=fwr(TEXT,1,p-TEXT,fh)!=(unsigned int)(p-TEXT);
    if(fcls(fh) || i) { discard_temp();return; }
    /* The old list remains intact until the new file has closed cleanly. */
    i=rename_file(cfg,backup);
    if(i && i!=0x46) { discard_temp();return; }
    if(rename_file(temp,cfg)) {
        if(!i && rename_file(backup,cfg)) {
            scpy(N,"Save failed; restore GOTO.BAK. GOTO.TMP kept.");return;
        }
        discard_temp();return;
    }
    if(!i && fileop(0xC1,backup))scpy(N,"Saved; GOTO.BAK kept.");
}

/* The whole screen: the title, one numbered row per favourite, the keys. */
static void draw(void)
{
    unsigned char i;
    cls(0);
    at(2, 1);
    put(m_title);
    if (!count) { at(2, 3); put(m_none); }
    for (i = 0; i < count; ++i) {
        at(2, 3 + i);
        num[0] = '1' + i;
        put(num);
        put(slot(i));
    }
    kbar(0, m_keys);
}

/* TEXT is no longer needed once load() has parsed the favourites. */
static unsigned char path_input(void)
{
    unsigned char len=0,k;
    for(;;) {
        TEXT[len]=0;
        scpy(N,"Path: ");scpy(N+6,TEXT);N[6+len]='_';N[7+len]=0;
        msg(N);k=getkey(0);
        if(k==KEY_ESC) { N[0]=0;return 0; }
        if(k==KEY_RETURN) {
            if(TEXT[0]!='/' || !TEXT[1]) { scpy(N,"Use /VOLUME/DIRECTORY.");return 0; }
            while(len>1 && TEXT[len-1]=='/') { --len;TEXT[len]=0; }
            return 1;
        }
        if(k==KEY_DELETE || k==KEY_LEFT) { if(len)--len; }
        else if(k>=' ' && k<127 && len<PATH_LEN-1) {
            if(k>='a' && k<='z')k-=32;
            TEXT[len]=k;++len;
        }
    }
}

static void jump(const char* p)
{
    if(!dopen(p))scpy(scpy(N,m_gone)+TAIL(m_gone),p);
    else {
        dclose(0);scpy(P->path,p);P->first=P->cursor=0;P->fs=FS_PRODOS;
        scpy(scpy(N,m_jump)+TAIL(m_jump),p);
    }
}

/* Move a favourite to its final numbered position, preserving the order
 * of all the others. TEXT holds one path until the shift is complete;
 * save() can then reuse it to serialize the complete list. */
static void move_favourite(void)
{
    unsigned char from,to,i;
    msg("Move which favourite? 1-9, ESC cancels");
    from=getkey(0)-'1';if(from>=count)return;
    msg("New position? 1-9, ESC cancels");
    to=getkey(0)-'1';if(to>=count)return;
    if(from==to) { scpy(N,"Already at that position.");return; }
    scpy(TEXT,slot(from));i=from;
    while(i<to) { scpy(slot(i),slot(i+1));++i; }
    while(i>to) { scpy(slot(i),slot(i-1));--i; }
    scpy(slot(to),TEXT);
    scpy(N,"Favourite moved.");save(NONE);
}

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    unsigned char i, k, del = 0;
    char* p;

    A = api;
    N = api->note;
    P = api->panels;
    if (*api->active) ++P;

    /* "/VOL/A2FILE/A2FILE.CFG" -> "/VOL/A2FILE/GOTO.CFG" */
    scpy(cfg, api->cfg_path);
    i = slen(cfg);
    while (i && cfg[i] != '/') --i;
    scpy(cfg + i + 1, f_name);
    scpy(temp,cfg);scpy(temp+i+1,"GOTO.TMP");
    scpy(backup,cfg);scpy(backup+i+1,"GOTO.BAK");

    if (!load()) { scpy(N,"Invalid GOTO.CFG: check size, paths and nine-entry limit."); return; }
    draw();
    /* One key. Bit 5 is set on every digit, so `| 0x20` lower-cases the
     * letters and leaves 1-9 alone; and since count <= 9, i < count can
     * only be true for a digit key. */
    k = getkey(0) | 0x20;
    if(k=='p') { if(path_input())jump(TEXT);return; }
    if(k=='m' && count) { move_favourite();return; }
    if (count && k == 'd') {
        msg(m_which);
        k = getkey(0) | 0x20;
        del = 1;
    }
    i = k - '1';

    if (i < count) {
        p = slot(i);
        if (del) {                      /* dropped, and the file rewritten */
            scpy(scpy(N, m_del) + TAIL(m_del), p);
            save(i);
        } else jump(p);
    } else if (!del && k == 'a') {
        p = P->path;
        if (!*p || P->fs) scpy(N, m_dir);
        else if (count == MAXFAV) scpy(N, m_room);
        else {
            for (i = 0; i < count; ++i)
                if (!scmp(slot(i), p)) { scpy(N, m_dup); break; }
            if (i == count) {
                scpy(slot(count), p);
                ++count;
                scpy(scpy(N, m_add) + TAIL(m_add), p);
                save(NONE);             /* which says so if it fails */
            }
        }
    } else if (!count) {
        scpy(N, m_none);                /* an empty list: how to fill it */
    }
}
