/* dirsort.c -- reorder the entries of one ProDOS directory on the disk.
 *
 * ProDOS 8 searches a directory in the order of its entries: at boot it
 * starts the first SYS file named *.SYSTEM of the volume directory, and
 * the panels' S only sorts what they show. DIRSORT reads the directory of
 * the active panel whole with READ_BLOCK, checks it, lets the entries be
 * put in another order (Space carries one, N, T and D sort), and writes the
 * blocks back after a confirmation that names the directory.
 *
 * WHAT IS WRITTEN. The occupied slots stay the occupied slots: a deleted
 * entry stays where it was (UNDELETE still finds it), the header and its
 * file count are not touched; only which entry sits in which occupied slot
 * changes. A subdirectory whose entry moves has its own header's
 * parent_pointer and parent_entry_number rewritten, which ProDOS follows
 * to update that entry. Nothing else: no bitmap, no file block.
 *
 * WHAT IS REFUSED before anything is shown. An image or a DOS 3.3 disk,
 * more than MAXBLK blocks, a header other than (39, 13), a chain of blocks
 * whose back links disagree or leave the volume, a file count that is not
 * the number of entries, a storage type that is not a file or a
 * subdirectory, an entry whose header pointer is not this directory, a
 * subdirectory header that does not point back at its entry, a directory
 * or volume that is write-disabled, including a moved child's header, or
 * a failed close of the parent listing. FIXIT says what is wrong; DIRSORT only
 * reorders a directory it can account for whole.
 *
 * HOW IT WRITES. Every block, and the header of every subdirectory that
 * moves, is read again and compared with what was checked just before the
 * first write: a disk swapped or changed meanwhile receives nothing. Each
 * block written is read back and compared. On a failure every block
 * already written is put back as it was, children first, each one read
 * back too. A power cut DURING the writes is not covered: ProDOS has no
 * multi-block atomic write, an entry may then be twice or missing, and the
 * confirmation says so.
 *
 * The core leaves no file open while an overlay runs, so no file control
 * block of ProDOS holds a stale position in this directory.
 */
#define UTIL_VOLUME
#define UTIL_WRITE
#define UTIL_STUBS
/* Only the v1 prefix through note is used; keep its ABI offsets intact. */
#define UTIL_API_END selected
#define r_sprintf a.sprintf     /* variadic: no stub, through the table */
#include "util.h"
#include <string.h>
/* The screen services through stubs too (service_stubs.h): a call through
 * the table costs cc65 a dozen bytes more at each site. A stub's last
 * argument is 16 bits; a service without one takes a dummy. */
#ifdef PLUGIN_HOST
#define S_gotoxy(x,y) a.gotoxy(x,y)
#define S_revers(on) a.revers(on)
#define S_clrscr() a.clrscr()
#define S_cgetc() a.cgetc()
#define S_cputs(s) a.cputs(s)
#define S_bar(s) a.keys_bar(0,s)
#else
#pragma optimize(push, off)
#pragma warn (unused-param, push, off)
static void __fastcall__ S_gotoxy(unsigned char x,unsigned int y) SERVICE(gotoxy)
static unsigned char __fastcall__ S_revers(unsigned int on) SERVICE(revers)
static void __fastcall__ r_clrscr(unsigned int unused) SERVICE(clrscr)
static char __fastcall__ r_cgetc(unsigned int unused) SERVICE(cgetc)
static void __fastcall__ S_cputs(const char* s) SERVICE(cputs)
static void __fastcall__ r_bar(unsigned char x,const char* s) SERVICE(keys_bar)
#pragma warn (unused-param, pop)
#pragma optimize(pop)
#define S_clrscr() r_clrscr(0)
#define S_cgetc() r_cgetc(0)
#define S_bar(s) r_bar(0,s)
#endif
void __fastcall__ plugin_entry(const struct A2fcApi*);
#define DIRSORT_DESCRIPTION "Reorder a ProDOS directory"
struct Header {unsigned int magic;unsigned char flags;void __fastcall__ (*entry)(const struct A2fcApi*);unsigned char r[3];char desc[sizeof DIRSORT_DESCRIPTION];};
#pragma rodata-name(push,"OVLHDR")
const struct Header __plugin_header={PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry,{0,0,0},DIRSORT_DESCRIPTION};
#pragma rodata-name(pop)

#ifndef MAXBLK
#define MAXBLK 4
#endif
#define MAXENT (MAXBLK*13-1)      /* the key block's header is never an entry */
#define LIST_ROWS 19
/* In a directory key block: the header starts at 4. */
#define H_ACCESS 0x22
#define H_FILES 0x25
#define H_PARENT 0x27
#define H_ENTRY 0x29
#define H_TOTAL 0x29
/* In an entry. */
#define E_TYPE 16
#define E_KEY 17
#define E_MDATE 33               /* then the time: minute, hour */
#define E_ACCESS 30
#define E_HEADER 37

static const char m_bad[]="Directory inconsistent (see FIXIT): nothing written.";
static const char m_changed[]="Directory changed or unreadable: nothing written.";
static const char m_none[]="Nothing written.";
static const char m_locked[]="Write-protected: nothing written.";

static unsigned char dir[MAXBLK][512];  /* the blocks as checked */
static unsigned int blk[MAXBLK],key,total,lastkey,lost;
static unsigned char nblk,nent,root,unit,pacc,cur,top,held,mode,by;
/* Entry i in disk order: in which block, in which slot (ep() is where it
 * is in dir[]). Position k of the new order is entry k's slot: order[k]
 * is the entry that goes there. */
static unsigned char eb[MAXENT],es[MAXENT],order[MAXENT];
static unsigned int csum[MAXENT];       /* position k: its child header's sum before any write */
static char path[PATH_LEN];
/* Drawing names and building sort keys never run together. */
static unsigned char kp[20],kq[20];
#define nm ((char*)kp)
static const char* leaf;                /* the last name of a subdirectory's path */

static unsigned char fail(const char* s){note(s);return 0;}
static unsigned char* ep(unsigned char k){return dir[eb[k]]+4+39*es[k];}
/* The library comparison avoids the C loop's stack arithmetic helpers,
 * leaving room for protection checks without changing the overlay limit. */
#define same(p,q,n) (!memcmp((p),(q),(n)))
static unsigned char up(unsigned char c){return c>='a' && c<='z'?c-32:c;}
/* READ_BLOCK of b into buf: 0 done, else the ProDOS error. */
static unsigned char rd(unsigned int b){return readblk(unit,b,buf);}
/* Is p a directory key block of storage `kind` with 39-byte entries,
 * 13 a block? */
static unsigned char hdr(const unsigned char* p,unsigned char kind) {
    return (p[4]>>4)==kind && p[0x23]==39 && p[0x24]==13;
}

/* The volume directory is the one ProDOS 8 searches at boot: the first
 * $FF file named *.SYSTEM, in this order. A forked entry before it (no
 * telling what ProDOS 8 does with one): no mark. 255: none. */
static unsigned char bootat(void) {
    unsigned char i,n,*e;
    if(root)for(i=0;i<nent;++i) {
        e=ep(order[i]);
        if((e[0]>>4)==5)break;
        n=e[0]&15;
        if((e[0]>>4)<4 && e[E_TYPE]==0xFF && n>7 && same(e+1+n-7,(const unsigned char*)".SYSTEM",7))return i;
    }
    return 255;
}

/* The chain whose key block is `key`, into dir[]. */
static unsigned char load(void) {
    unsigned int b=key,prev=0;
    nblk=0;
    do {
        if(nblk==MAXBLK)return fail("Directory too big: nothing written.");
        if(b<2 || b>=total)return fail(m_bad);
        if(readblk(unit,b,dir[nblk]))return fail(m_changed);
        if(rd16(dir[nblk])!=prev)return fail(m_bad);
        blk[nblk]=prev=b;b=rd16(dir[nblk++]+2);
    }while(b);
    return 1;
}

/* The key block of a subdirectory: the one its parent's listing gives,
 * through the core's own reader (it validates the names it returns). The
 * reader gives the file type, not the storage type: check() then proves
 * the entry from the other side, through the header's parent link. */
static unsigned char find(unsigned char l) {
    struct DirEntry* d=a.dir_entry;
    path[l]=0;leaf=path+l+1;
    if(!a.dir_open(path)){path[l]='/';return fail(m_changed);}
    path[l]='/';
    while(a.dir_next())if(d->type==0x0F && !RF(strcmp)(d->name,path+l+1)){key=d->key;break;}
    /* The frozen service-table slot is void, but the resident returns
     * listing/close errors in A. A found entry does not excuse either. */
    if(((unsigned char (*)(void))a.dir_close)())return fail(m_changed);
    return key!=2 || fail(m_bad);
}

/* A parent link: 0 where it comes from, 1 where it goes. */
static unsigned int pb[2];
static unsigned char ps[2];
/* Does the subdirectory header in buf name link i as its parent? */
static unsigned char parent_is(unsigned char i) {
    unsigned char* h=buf;
    return rd16(h+H_PARENT)==pb[i] && h[H_ENTRY]==ps[i];
}
/* Link i: the block and entry number of position k's slot. */
static void slotof(unsigned char i,unsigned char k){pb[i]=blk[eb[k]];ps[i]=es[k]+1;}

/* WRITE_BLOCK of w, then READ_BLOCK of the same block into buf. */
static unsigned char wrote(unsigned int b,const unsigned char* w) {
    return !writeblk(unit,b,w) && !rd(b);
}

/* Fletcher-16 of buf: what a read back of a child header is compared
 * with. Its original is nowhere else in this window, so that block alone
 * is checked by its link and this sum rather than byte for byte; a put
 * back that does not come back to the sum it had is a failed restore. */
static unsigned int sum(void) {
    unsigned char x=0,y=0;unsigned int i;
    for(i=0;i<512;++i){x+=buf[i];y+=x;}
    return x|(unsigned int)y<<8;
}

/* The header of the subdirectory that position k receives, if it moves.
 * mode 0: is its parent link still the entry's old slot? 1: from the old
 * slot to the new one. 2: back to the old slot, from the new one or from
 * the old one already (a write whose outcome is unknown). 1: done. */
static unsigned char link(unsigned char k) {
    unsigned char o=order[k],*e=ep(o);unsigned int x;
    if(o==k || (e[0]>>4)!=13)return 1;
    /* From the old slot to the new one; back the other way in mode 2. */
    slotof(mode==2,o);slotof(mode!=2,k);
    if(rd(lastkey=rd16(e+E_KEY)))return 0;
    /* Raw link updates bypass ProDOS. The child's own header must allow
     * writes as well as its entry; undo still restores our earlier write. */
    if(mode!=2 && !(e[E_ACCESS]&buf[H_ACCESS]&2)){lastkey=0;return fail("Locked subdirectory: nothing written.");}
    /* Back as it was already (its write never reached the disk): nothing
     * to write, so a disk that refuses writes is not a failed restore. */
    if(mode==2 && parent_is(1) && sum()==csum[k])return 1;
    if(parent_is(0)){if(!mode){csum[k]=sum();return 1;}}
    else if(mode!=2 || !parent_is(1))return 0;
    wr16(buf+H_PARENT,pb[1]);buf[H_ENTRY]=ps[1];
    x=mode==2?csum[k]:sum();
    /* A put back is judged by its read back alone: a device that writes
     * and then reports an error has put the block back all the same. */
    k=writeblk(unit,lastkey,buf);
    return (!k || mode==2) && !rd(lastkey) && parent_is(1) && sum()==x;
}

/* Prove the directory's identity and protections, including the entry in
 * its parent. Reused after confirmation: that parent block is outside
 * the snapshots of the directory being reordered. No writes or AUX use. */
static unsigned char parent_check(void) {
    unsigned char s,*e;
    if(!hdr(dir[0],root?15:14))return fail(m_bad);
    if(!root) {
        /* The entry the header names as its parent: a subdirectory whose
         * key is this directory, under the name the listing gave (not a
         * cross-linked one elsewhere), the access ProDOS checks. */
        s=dir[0][H_ENTRY]-1;
        if(s>12)return fail(m_bad);
        if(rd(rd16(dir[0]+H_PARENT)))return fail(m_changed);
        e=buf+4+39*s;
        s=e[0]&15;
        if((e[0]>>4)!=13 || rd16(e+E_KEY)!=key || RF(strlen)(leaf)!=s || !same(e+1,(const unsigned char*)leaf,s))
            return fail(m_bad);
        pacc &= e[E_ACCESS];
    }
    if(!(dir[0][H_ACCESS]&pacc&2))return fail(m_locked);
    return 1;
}

/* The whole directory accounted for, or refused. */
static unsigned char check(void) {
    unsigned char b,s,st,*e;
    if(!parent_check())return 0;
    nent=0;
    for(b=0;b<nblk;++b)for(s=!b,e=dir[b]+4+39*s;s<13;++s,e+=39) {
        st=e[0]>>4;
        if(!st)continue;
        if((st>3 && st!=5 && st!=13) || !(e[0]&15) || rd16(e+E_HEADER)!=key)return fail(m_bad);
        if(st==13) {
            /* The child's header must point back at this very slot. */
            if(rd(rd16(e+E_KEY)))return fail(m_changed);
            pb[0]=blk[b];ps[0]=s+1;
            if(!hdr(buf,14) || buf[0x2A]!=39 || !parent_is(0))
                return fail(m_bad);
        }
        eb[nent]=b;es[nent]=s;order[nent]=nent;++nent;
    }
    return nent==rd16(dir[0]+H_FILES) || fail(m_bad);
}

static void draw(void) {
    unsigned char r,i,n,boot=bootat(),*e;
    S_clrscr();
    S_cputs("DIRSORT ");S_cputs(path);
    for(r=0;r<LIST_ROWS && (i=top+r)<nent;++r) {
        e=ep(order[i]);n=e[0]&15;
        RF(memcpy)(nm,e+1,n);nm[n]=0;
        S_gotoxy(0,2+r);
        S_revers(i==cur);
        a.cprintf("%c%-15s $%02X%s",i==cur && held?'>':' ',nm,e[E_TYPE],i==boot?"  <- boots":"");
        S_revers(0);
    }
    S_gotoxy(0,23);
    S_bar(held?"SPC Drop,ESC Quit":"SPC Carry,N Name,T Type,D Date,R Disk,W Write,ESC Quit");
}

/* The sort key of entry e into k: by `by`, N name, T type then name, D
 * date and time of modification (oldest first) then name. Five bytes
 * first: the type, or the year as it sorts (0-39 are 2000-2039, 40-99 are
 * 1940-1999, as DATE writes them; no date at all comes first), month and
 * day, hour, minute. Then the name, zero-padded: a shorter name that is a
 * prefix of a longer one comes first. */
static void mk(unsigned char* k,const unsigned char* e) {
    unsigned char y=e[E_MDATE+1];
    RF(memset)(k,0,20);
    if(by=='T')k[0]=e[E_TYPE];
    if(by=='D' && (y|e[E_MDATE])) {
        k[1]=y&1;k[2]=e[E_MDATE];k[3]=e[E_MDATE+3];k[4]=e[E_MDATE+2];
        y>>=1;k[0]=y<40?y+100:y;
    }
    RF(memcpy)(k+5,e+1,e[0]&15);
}
/* Insertion sort, stable. */
static unsigned char after(unsigned char x,unsigned char y) {
    unsigned char i;
    mk(kp,ep(x));mk(kq,ep(y));
    for(i=0;i<20;++i)if(kp[i]!=kq[i])return kp[i]>kq[i];
    return 0;
}
static void sort(void) {
    unsigned char i,j,t;
    for(i=1;i<nent;++i)for(j=i;j && after(order[j-1],order[j]);--j){t=order[j];order[j]=order[j-1];order[j-1]=t;}
}

/* new=1: block b as it will be written, into buf. new=0: buf, just read
 * back, checked against what new=1 made: each slot is compared with the
 * entry it should hold, then given its original entry back. Either way
 * the answer is whether buf differs from dir[b], all 512 bytes: after a
 * read back, 0 is the right block. No second buffer. */
static unsigned char slots(unsigned char b,unsigned char new) {
    unsigned char k,*p,*q;
    if(new)RF(memcpy)(buf,dir[b],512);
    for(k=0;k<nent;++k)if(eb[k]==b) {
        p=buf+(ep(k)-dir[b]);q=ep(order[k]);
        if(new)RF(memcpy)(p,q,39);
        else{if(!same(p,q,39))return 1;RF(memcpy)(p,ep(k),39);}
    }
    return !same(buf,dir[b],512);
}

/* Does block w read as it was checked? (into buf) */
static unsigned char asis(unsigned char w) {
    return !rd(blk[w]) && same(buf,dir[w],512);
}

static void commit(void) {
    unsigned char i,w,c;
    /* Nothing has moved since the check: the blocks, then each child. */
    mode=0;lastkey=1;
    /* A subdirectory snapshot does not include the volume header. Recheck
     * its write bit after confirmation, before any raw block write. */
    if(rd(2) || !(buf[H_ACCESS]&2))goto changed;
    for(i=0;i<nblk;++i)if(!asis(i))goto changed;
    if(!parent_check())return;
    for(i=0;i<nent;++i)if(!link(i))goto changed;
    /* No child is written before every block is: a block that fails
     * leaves none to undo (c is BSS under -Cl, never zeroed). */
    mode=1;c=0;
    for(w=0;w<nblk;++w)if(slots(w,1) && !(wrote(blk[w],buf) && !slots(w,0))){++w;goto undo;}
    for(;c<nent;++c)if(!link(c)){++c;goto undo;}
    note("Reordered: every block read back.");
    return;
undo:
    /* Children first, then the blocks, each one read back. A block that
     * reads as it was is left alone: a write-protected or removed disk
     * refuses the first write and keeps every byte, which is no failed
     * restore, and a put back is judged by its read back, not by the
     * error a write returned. One that does not come back does not stop the others: the
     * closer to the original, the better. The first one that failed is
     * named. */
    mode=2;lost=0;
    while(c)if(!link(--c) && !lost)lost=lastkey;
    while(w)if(!asis(--w)){writeblk(unit,blk[w],dir[w]);if(!asis(w) && !lost)lost=blk[w];}
    if(lost)a.sprintf(a.note,"RESTORE FAILED (block %u): copy files off, run FIXIT.",lost);
    else note("Write failed: put back as it was.");
    return;
changed:
    if(lastkey)note(m_changed);
}

void __fastcall__ plugin_entry(const struct A2fcApi* api) {
    unsigned char k,n,i,t;
    init(api);
    /* The directory the active panel shows: a path, so never the volume
     * list, and on a ProDOS disk, not in an image. */
    if(pan->fs || !pan->path[0]){note("Open a ProDOS directory first.");return;}
    RF(strcpy)(path,pan->path);
    /* Two drives with this name: ProDOS may resolve the path to the other
     * one than the unit written by number. DIRSORT works by path only, so
     * it refuses rather than pointing at the volume list. */
    unit=unit_of(path,0);
    if(!unit){note("Volume not on line, or two with this name.");return;}
    /* The volume header (ON_LINE matched its name): its size. */
    if(rd(2)){note(m_changed);return;}
    if((buf[4]>>4)!=15){note(m_bad);return;}
    total=rd16(buf+H_TOTAL);key=2;pacc=buf[H_ACCESS];
    for(n=0,i=1;path[i];++i)if(path[i]=='/')n=i;
    root=!n;
    if((!root && !find(n)) || !load() || !check())return;
    cur=top=held=0;
    for(;;) {
        if(cur<top)top=cur;
        if(cur>=top+LIST_ROWS)top=cur-LIST_ROWS+1;
        draw();
        k=up(S_cgetc());
        if(k==KEY_ESC){note(m_none);return;}
        if(k==' ')held=!held;
        else if(k==KEY_UP || k==KEY_DOWN) {
            n=k==KEY_UP?cur-1:cur+1;
            if(n>=nent)continue;            /* above the first: 255 */
            if(held){t=order[cur];order[cur]=order[n];order[n]=t;}
            cur=n;
        }
        else if(held)continue;
        else if(k=='N' || k=='T' || k=='D'){by=k;sort();}
        else if(k=='R')for(i=0;i<nent;++i)order[i]=i;
        else if(k=='W')break;
    }
    for(i=0;i<nent && order[i]==i;++i);
    if(i==nent){note("Order unchanged: nothing written.");return;}
    S_gotoxy(0,21);S_cputs("A power cut while writing can damage this directory.");
    a.sprintf((char*)buf,"Write this order to %s?",path);
    if(!RF(confirm)((char*)buf)){note(m_none);return;}
    commit();
}
