/* a2fc_plugin.h -- what an overlay sees of A2 File Cmd.
 *
 * An overlay is a file A2FILE/NAME.PLG, a BIN read into the window
 * $1B00-$1FFF (a "big" overlay also takes the graphics page $2000-$3FFF,
 * and the core re-reads both panels when it returns). Its first eight
 * bytes are the header below (struct Overlay), then a one-line
 * description, then the code.
 *
 * Two kinds of overlays:
 *
 *  - the program's own, linked with it (a2fc.c, segments IMAGE, TEXT,
 *    HEX, DELETE, HELP, EDIT, MUSIC, RUN, ATTR, MENU, DISKIMG...): they
 *    call its functions at their addresses in that particular link, and
 *    their signature is the address of main in that link; A2FILE.CODE and
 *    its .PLG files go together as a set;
 *
 *  - a third party's, compiled separately with this file and sdk/plugin.cfg:
 *    their signature is PLUGIN_MAGIC, and they touch the program only
 *    through the service table (struct A2fcApi) that the core passes to
 *    their entry point. This table is the stable ABI: its fields do not
 *    move, new ones are only appended at the end, and api->version says so.
 *
 * The entry point:  void __fastcall__ entry(const struct A2fcApi* api);
 * It is called from the overlay menu (the ! key) on the current selection;
 * api->panels[*api->active] is the active panel, the entry under the
 * cursor is pan->e[pan->cursor], and api->full is its complete ProDOS
 * path. The tags are already set aside for a big overlay.
 *
 * All functions use the cc65 fastcall convention, except cprintf and
 * sprintf (variadic, cdecl); do not compile with --all-cdecl. */
#ifndef A2FC_PLUGIN_H
#define A2FC_PLUGIN_H

#include <stdio.h>

#define A2FC_API_VERSION 2
#define PLUGIN_MAGIC 0xA2FC        /* the signature of a third-party overlay */
#define OVERLAY_BIG 0x01           /* also takes $2000-$3FFF */
#define OVERLAY_WINDOW ((unsigned char*)0x1B00)
#define OVERLAY_SMALL 0x0500       /* $1B00-$1FFF */
#define OVERLAY_LARGE 0x2500       /* $1B00-$3FFF */

#define MAX_ENTRIES 140            /* 2 x 140 x 29 bytes = 8120, within the 8 KB at $2000 */
#define PATH_LEN 64
#define NAME_LEN 17                /* "/VOLUME": 16 characters + zero */
#define ROWS 18                    /* rows 2..19 of each panel */

#define KEY_UP 11
#define KEY_DOWN 10
#define KEY_LEFT 8
#define KEY_RIGHT 21
#define KEY_RETURN 13
#define KEY_ESC 27
#define KEY_TAB 9
#define KEY_DELETE 127

struct Entry {
    char name[NAME_LEN];
    unsigned char type;
    unsigned char access;       /* bit 7: destroy-enable; a locked file has it clear */
    unsigned int aux;           /* volume: free blocks */
    unsigned int blocks;        /* volume: total blocks */
    unsigned long size;
    unsigned int mdate;         /* day 5 bits, month 4 bits, year 7 bits; volume: the unit
                                 * number SHIFTED RIGHT BY FOUR (READ_BLOCK wants mdate << 4);
                                 * in an image or a DOS 3.3: the key block */
};

struct Panel {                  /* offsets read by panel_hash (a2fc_mli.s): */
    char path[PATH_LEN];        /* 0; "": the list of online volumes */
    unsigned char count, cursor, top, more;   /* 64, 65, 66, 67 */
    unsigned int first;         /* 68; first disk entry in the window */
    unsigned int free_blocks, total_blocks;
    struct Entry* e;            /* 74; entries of 29 bytes */
    unsigned char tags[(MAX_ENTRIES + 7) / 8];
    unsigned char fs;           /* 0 ProDOS; otherwise the foreign file system (FS_*) */
    unsigned char img_len;      /* fs != 0: length of the image path within path, 0 = a drive */
    unsigned int dir_key;       /* fs != 0: the key block (ProDOS) or track/sector (DOS 3.3) of the directory shown */
};

struct DirEntry {               /* what dir_next returns */
    char name[NAME_LEN];
    unsigned char type, access;
    unsigned int aux, blocks, mdate;
    unsigned long size;
    unsigned int key;           /* the key block (ProDOS key pointer): navigation and image extraction */
};

/* The file systems of a panel (struct Panel.fs): 0 = real ProDOS;
 * a disk image opened as a directory, in ProDOS or in DOS 3.3.
 * The sector order (.PO ProDOS, .DSK/.DO DOS 3.3, .2MG per its header)
 * is deduced from the suffix at open time, independently of the file system. */
enum { FS_PRODOS, FS_IMG, FS_DOS33 };

struct Overlay {                /* the overlay header, at $1B00 */
    unsigned int signature;     /* main of the link, or PLUGIN_MAGIC */
    unsigned char flags;        /* OVERLAY_BIG */
    void __fastcall__ (*entry)(const struct A2fcApi*);   /* 0: no entry point */
    unsigned char reserved[3];
    char desc[1];               /* one line, zero terminated, 65 characters at most
                                 * (the menu shows it in the 80-column row); code follows */
};

struct A2fcApi {
    unsigned char version;      /* A2FC_API_VERSION */
    unsigned char arg;          /* the key that called the overlay, or 0 from the menu */
    /* the program's data */
    struct Panel* panels;       /* the two panels */
    unsigned char* active;      /* 0 or 1 */
    char* full;                 /* the path of the entry under the cursor (64 + 17) */
    char* other_full;           /* the same in the other panel, or free */
    char* input;                /* what prompt() read (17 bytes) */
    unsigned char* copy_buf;    /* 512 bytes of scratch space */
    struct DirEntry* dir_entry; /* what dir_next read */
    /* the screen: line 22 is the message line, line 23 the key bar */
    void (*message)(const char*);
    unsigned char (*confirm)(const char*);                     /* (Y/N), 1 = yes */
    unsigned char (*prompt)(const char*, const char*, unsigned char);   /* a ProDOS name into input, or hex digits; 0 = cancelled */
    void (*progress_bar)(const char*, unsigned long, unsigned long);
    void (*keys_bar)(unsigned char, const char*);              /* "KEY Label,..." at column x */
    void (*bar_begin)(void);                                   /* clears the bar */
    void (*draw_all)(void);                                    /* the whole panel screen */
    unsigned char (*read_panel)(unsigned char);                /* re-reads a panel */
    void (*report_error)(const char*);                         /* "X failed (errno, ProDOS $xx)" */
    char (*wait_key)(void);                                    /* a key, or a click */
    /* the files */
    unsigned char (*build_full)(char*, const struct Panel*, const struct Entry*);
    unsigned char (*dir_open)(const char*);                    /* a directory read entry by entry */
    unsigned char (*dir_next)(void);
    void (*dir_close)(void);
    unsigned char (*mli)(unsigned char, void*);                /* one MLI call, returns the ProDOS error */
    /* the C library */
    FILE* (*fopen)(const char*, const char*);
    size_t (*fread)(void*, size_t, size_t, FILE*);
    size_t (*fwrite)(const void*, size_t, size_t, FILE*);
    int (*fclose)(FILE*);
    int (*fseek)(FILE*, long, int);
    int (*remove)(const char*);
    int (*cprintf)(const char*, ...);
    int (*sprintf)(char*, const char*, ...);
    void (*cputs)(const char*);
    void (*cputc)(char);
    void (*gotoxy)(unsigned char, unsigned char);
    unsigned char (*revers)(unsigned char);
    void (*cclearxy)(unsigned char, unsigned char, unsigned char);
    void (*clrscr)(void);
    char (*cgetc)(void);
    void* (*memcpy)(void*, const void*, size_t);
    void* (*memset)(void*, int, size_t);
    char* (*strcpy)(char*, const char*);
    int (*strcmp)(const char*, const char*);
    size_t (*strlen)(const char*);
    unsigned char* filetype;    /* cc65's _filetype and _auxtype, read by fopen "wb" */
    unsigned int* auxtype;
    /* on return from a big overlay, once the panels have been re-read and
     * redrawn: the name to reselect in the active panel, and the message
     * to write on line 22 (79 characters at most); empty otherwise */
    char* reselect;
    char* note;
    /* the entry under the cursor at call time, copied out of the table
     * (which a big overlay covers); name[0] = 0 if the panel is empty.
     * api->full is its complete path, "" if it does not fit. */
    struct Entry* selected;
    /* since version 2: the path of the program's settings file,
     * "/VOL/A2FILE/A2FILE.CFG" -- its directory is where the overlays live,
     * and where an overlay keeps its own files (GOTO.CFG...). */
    const char* cfg_path;
};

#endif /* A2FC_PLUGIN_H */
