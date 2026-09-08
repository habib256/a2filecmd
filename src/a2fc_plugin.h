/* a2fc_plugin.h -- ce qu'une surcouche voit d'A2 File Cmd.
 *
 * Une surcouche est un fichier A2FILE/NOM.PLG, un BIN lu dans la fenetre
 * $1B00-$1FFF (une « grande » surcouche prend aussi la page graphique
 * $2000-$3FFF, et le noyau relit les deux panneaux a son retour). Ses huit
 * premiers octets sont l'en-tete ci-dessous (struct Overlay), puis une
 * description d'une ligne, puis le code.
 *
 * Deux sortes de surcouches :
 *
 *  - celles du programme, liees avec lui (a2fc.c, segments IMAGE, TEXT,
 *    HEX, DELETE, HELP, EDIT, MUSIC, RUN, ATTR, MENU, DISKIMG...) : elles
 *    appellent ses fonctions a leurs adresses de ce lien-la, et leur
 *    signature est l'adresse de main dans ce lien ; A2FILE.CODE et ses .PLG
 *    vont par ensemble ;
 *
 *  - celles d'un tiers, compilees a part avec ce fichier et sdk/plugin.cfg :
 *    leur signature est PLUGIN_MAGIC, et elles ne touchent au programme que
 *    par la table de services (struct A2fcApi) que le noyau passe a leur
 *    point d'entree. Cette table est l'ABI stable : ses champs ne changent
 *    pas de place, il ne s'en ajoute qu'a la fin, et api->version le dit.
 *
 * Le point d'entree :  void __fastcall__ entry(const struct A2fcApi* api);
 * Il est appele depuis le menu des surcouches (touche !) sur la selection
 * courante ; api->panels[*api->active] est le panneau actif, l'entree sous
 * le curseur est pan->e[pan->cursor], et api->full en est le chemin ProDOS
 * complet. Les marques sont deja mises de cote pour une grande surcouche.
 *
 * Toutes les fonctions sont en convention fastcall de cc65, sauf cprintf
 * et sprintf (variadiques, cdecl) ; ne pas compiler avec --all-cdecl. */
#ifndef A2FC_PLUGIN_H
#define A2FC_PLUGIN_H

#include <stdio.h>

#define A2FC_API_VERSION 1
#define PLUGIN_MAGIC 0xA2FC        /* la signature d'une surcouche d'un tiers */
#define OVERLAY_BIG 0x01           /* prend aussi $2000-$3FFF */
#define OVERLAY_WINDOW ((unsigned char*)0x1B00)
#define OVERLAY_SMALL 0x0500       /* $1B00-$1FFF */
#define OVERLAY_LARGE 0x2500       /* $1B00-$3FFF */

#define MAX_ENTRIES 140            /* 2 x 140 x 29 octets = 8120, dans les 8 Ko de $2000 */
#define PATH_LEN 64
#define NAME_LEN 17                /* "/VOLUME" : 16 caracteres + zero */
#define ROWS 18                    /* lignes 2..19 de chaque panneau */

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
    unsigned char access;       /* bit 7 : destructible ; un fichier verrouille l'a a zero */
    unsigned int aux;           /* volume : blocs libres */
    unsigned int blocks;        /* volume : blocs en tout */
    unsigned long size;
    unsigned int mdate;         /* jour 5 bits, mois 4 bits, annee 7 bits ; volume : unite ;
                                 * dans une image ou un DOS 3.3 : le bloc de cle */
};

struct Panel {                  /* decalages lus par panel_hash (a2fc_mli.s) : */
    char path[PATH_LEN];        /* 0 ; "" : la liste des volumes en ligne */
    unsigned char count, cursor, top, more;   /* 64, 65, 66, 67 */
    unsigned int first;         /* 68 ; premiere entree du disque dans la fenetre */
    unsigned int free_blocks, total_blocks;
    struct Entry* e;            /* 74 ; des entrees de 29 octets */
    unsigned char tags[(MAX_ENTRIES + 7) / 8];
    unsigned char fs;           /* 0 ProDOS ; sinon le systeme de fichiers etranger (FS_*) */
    unsigned char img_len;      /* fs != 0 : longueur du chemin de l'image dans path, 0 = un lecteur */
    unsigned int dir_key;       /* fs != 0 : le bloc de cle (ProDOS) ou piste/secteur (DOS 3.3) du dossier montre */
};

struct DirEntry {               /* ce que dir_next rend */
    char name[NAME_LEN];
    unsigned char type, access;
    unsigned int aux, blocks, mdate;
    unsigned long size;
    unsigned int key;           /* le bloc de cle (pointeur-cle ProDOS) : navigation et extraction d'image */
};

/* Les systemes de fichiers d'un panneau (struct Panel.fs) : 0 = ProDOS reel ;
 * une image disque ouverte comme un dossier, en ProDOS ou en DOS 3.3.
 * L'ordre des secteurs (.PO ProDOS, .DSK/.DO DOS 3.3, .2MG selon l'en-tete)
 * est deduit du suffixe a l'ouverture, independamment du systeme de fichiers. */
enum { FS_PRODOS, FS_IMG, FS_DOS33 };

struct Overlay {                /* l'en-tete d'une surcouche, en $1B00 */
    unsigned int signature;     /* main du lien, ou PLUGIN_MAGIC */
    unsigned char flags;        /* OVERLAY_BIG */
    void __fastcall__ (*entry)(const struct A2fcApi*);   /* 0 : pas de point d'entree */
    unsigned char reserved[3];
    char desc[1];               /* une ligne, zero terminee ; le code suit */
};

struct A2fcApi {
    unsigned char version;      /* A2FC_API_VERSION */
    unsigned char arg;          /* la touche qui a appele la surcouche, ou 0 depuis le menu */
    /* les donnees du programme */
    struct Panel* panels;       /* les deux panneaux */
    unsigned char* active;      /* 0 ou 1 */
    char* full;                 /* le chemin de l'entree sous le curseur (64 + 17) */
    char* other_full;           /* le meme dans l'autre panneau, ou libre */
    char* input;                /* ce que prompt() a lu (17 octets) */
    unsigned char* copy_buf;    /* 512 octets de travail */
    struct DirEntry* dir_entry; /* ce que dir_next a lu */
    /* l'ecran : la ligne 22 est celle des messages, la 23 la barre de touches */
    void (*message)(const char*);
    unsigned char (*confirm)(const char*);                     /* (Y/N), 1 = oui */
    unsigned char (*prompt)(const char*, const char*, unsigned char);   /* un nom ProDOS dans input, ou hex chiffres ; 0 = annule */
    void (*progress_bar)(const char*, unsigned long, unsigned long);
    void (*keys_bar)(unsigned char, const char*);              /* "TOUCHE Libelle,..." en colonne x */
    void (*bar_begin)(void);                                   /* efface la barre */
    void (*draw_all)(void);                                    /* tout l'ecran des panneaux */
    unsigned char (*read_panel)(unsigned char);                /* relit un panneau */
    void (*report_error)(const char*);                         /* "X failed (errno, ProDOS $xx)" */
    char (*wait_key)(void);                                    /* une touche, ou un clic */
    /* les fichiers */
    unsigned char (*build_full)(char*, const struct Panel*, const struct Entry*);
    unsigned char (*dir_open)(const char*);                    /* un dossier lu entree par entree */
    unsigned char (*dir_next)(void);
    void (*dir_close)(void);
    unsigned char (*mli)(unsigned char, void*);                /* un appel MLI, rend l'erreur ProDOS */
    /* la bibliotheque C */
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
    unsigned char* filetype;    /* _filetype et _auxtype de cc65, lus par fopen "wb" */
    unsigned int* auxtype;
    /* au retour d'une grande surcouche, une fois les panneaux relus et
     * redessines : le nom a reselectionner dans le panneau actif, et le
     * message a ecrire en ligne 22 (79 caracteres au plus) ; vides sinon */
    char* reselect;
    char* note;
    /* l'entree sous le curseur au moment de l'appel, copiee hors de la table
     * (qu'une grande surcouche recouvre) ; name[0] = 0 si le panneau est
     * vide. api->full est son chemin complet, "" s'il ne tient pas. */
    struct Entry* selected;
};

#endif /* A2FC_PLUGIN_H */
