/* TOTAL : un gestionnaire de fichiers ProDOS a deux panneaux, dans
 * l'esprit de Total Commander, pour l'Apple IIe 128 Ko.
 *
 * Programme SYS distinct du jeu, lance depuis Bitsy Bye comme DIAPO, avec
 * le meme lanceur (loader.c), le meme decodeur DHGR (hgr_loader.s) et les
 * memes bascules video (memory_swap.c). Il ne modifie jamais un fichier de
 * lui-meme : seules les commandes explicites (copie, deplacement, renommage,
 * suppression, creation de dossier, type, verrou) ecrivent sur le disque,
 * apres confirmation quand elles detruisent quelque chose. Il ecrit aussi
 * TOTAL/TOTAL.CFG en quittant : les deux dossiers, le tri, le panneau actif.
 *
 * Ouvrir (Entree) choisit d'apres le type : un dossier s'ouvre, une image
 * DHGR (.RLE, flux DHRR) s'affiche plein ecran, un TXT se lit page par page,
 * un SYS se lance apres confirmation, le reste se voit en hexadecimal.
 * Espace marque plusieurs fichiers : copie, deplacement et suppression
 * portent alors sur tous les fichiers marques.
 *
 * Memoire : code a $4000, tampons de travail en $1000-$1FFF (LOWBSS),
 * visionneuses et saisies dans la carte langage ($D400-$DFFF, segment LC,
 * copie par crt0 comme pour le jeu). Les deux tables d'entrees occupent la
 * page graphique MAIN $2000-$3FFF, libre tant qu'aucune image n'est
 * affichee : une image la recouvre (MAIN et AUX), et les deux panneaux sont
 * relus au retour. Deux fichiers ouverts au plus (copie) : tampons ProDOS
 * $0800 et $0C00, TOTAL n'utilise pas MAPBSS. Un dossier qui deborde la
 * table est lu par fenetres, dans l'ordre du disque.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <conio.h>
#include <unistd.h>
#include <fcntl.h>
#include <device.h>
#include <errno.h>
#include <apple2.h>
#include "memory_swap.h"
#include "music.h"

/* cc65 les lit a la creation d'un fichier (fopen "wb") : la copie garde le
 * type et l'auxtype de l'original, une image reste une image. */
extern unsigned char _filetype;
extern unsigned int _auxtype;

unsigned char __fastcall__ mli_gfi(void* params);   /* total_mli.s */
extern unsigned int chain_addr;                    /* chain.s */
void __fastcall__ chain_load(const char* path);
unsigned char __fastcall__ mli_sfi(void* params);
static unsigned char exists(const char* path);
static void too_long(void);
static void dir_fail(void);

#ifndef TOTAL_VERSION
#define TOTAL_VERSION "1.0"
#endif
#define MAX_ENTRIES 140         /* 2 x 140 x 29 octets = 8120, dans les 8 Ko de $2000 */
#define WINDOW (MAX_ENTRIES - 1)   /* entrees du disque par fenetre : ".." en plus */
#define ROWS 18                 /* lignes 2..19 de chaque panneau */
#define PATH_LEN 64
#define NAME_LEN 17             /* "/VOLUME" : 16 caracteres + zero */

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
    unsigned int mdate;         /* jour 5 bits, mois 4 bits, annee 7 bits ; volume : unite */
};

struct Panel {
    char path[PATH_LEN];        /* "" : la liste des volumes en ligne */
    unsigned char count, cursor, top, more;
    unsigned int first;         /* premiere entree du disque dans la fenetre */
    unsigned int free_blocks, total_blocks;
    struct Entry* e;
    unsigned char tags[(MAX_ENTRIES + 7) / 8];
};

enum { SORT_NAME, SORT_SIZE, SORT_TYPE, SORT_MODES };
enum { ASK, OVERWRITE_ALL, SKIP_ALL };

#define ENTRIES ((struct Entry*)0x2000)   /* la page HGR MAIN, voir l'en-tete */
#define EDIT_BUF ((char*)0x2000)          /* la meme page pour l'editeur et l'aide */
#define EDIT_MAX 0x1FF0
/* Toute la BSS de ce fichier vit en RAM basse ($1000-$1FFF, segment LOWBSS
 * de scoswamp.cfg) : main() la met a zero, crt0 ne le fait que pour BSS.
 * Bornes du segment exportees par le lieur (voir scoswamp.c). */
extern char _LOWBSS_RUN__[];
extern char _LOWBSS_SIZE__[];
#pragma bss-name (push, "LOWBSS")
static struct Panel panels[2];
static unsigned char active, sort_mode, over_policy;
static unsigned int progress_done, progress_total, progress_skipped;
/* Diagnostics lisibles par le banc de test POM2 (voir total.lbl). */
unsigned int total_draws, total_ops, total_errors;
unsigned char total_view;       /* 0 panneaux, 1 image, 2 texte, 3 hexa, 4 aide, 5 editeur */
unsigned char total_slot;       /* la Mockingboard, 0 sans ; 0xFF pas encore cherchee */
unsigned char total_playing;    /* 0 silence, 1 joue, 2 en pause */

static char full[PATH_LEN + NAME_LEN];
static char other_full[PATH_LEN + NAME_LEN];
static char cfg_path[PATH_LEN];
static char input[NAME_LEN];
static char question[64];
static unsigned char copy_buf[512];
static unsigned char gfi[18];
static unsigned char gfi_path[PATH_LEN + 1];
static unsigned char picked[MAX_ENTRIES];
static long text_starts[96];
/* Les parcours recursifs (copie et suppression d'un dossier) empilent
 * les entrees de chaque niveau : un niveau occupe pool[base..base+n[, le
 * niveau suivant commence a base+n. Un arbre dont un chemin cumule plus de
 * POOL_SIZE entrees est refuse avant toute ecriture. La reserve occupe la
 * table d'entrees du panneau inactif (4060 octets), inutile pendant
 * l'operation puisque les deux panneaux sont relus ensuite. */
#define POOL_SIZE 213
struct Mini { char name[16]; unsigned char type; unsigned int aux; };
static struct Mini* pool;

/* ---------------------------------------------------------------------- */
/* MLI : GET_FILE_INFO et SET_FILE_INFO                                    */
/* ---------------------------------------------------------------------- */

/* Remplit gfi[] pour `path` (nom ProDOS complet). Rend 0 sur erreur. */
static unsigned char file_info(const char* path)
{
    unsigned char len = strlen(path);
    gfi_path[0] = len;
    memcpy(gfi_path + 1, path, len);
    gfi[0] = 0x0A;
    gfi[1] = (unsigned char)((unsigned)gfi_path & 0xFF);
    gfi[2] = (unsigned char)((unsigned)gfi_path >> 8);
    return mli_gfi(gfi) == 0;
}

/* Reecrit acces, type et auxtype de gfi[] : SET_FILE_INFO partage la
 * disposition de GET_FILE_INFO sur ses sept premiers parametres. */
static unsigned char set_info(void)
{
    gfi[0] = 0x07;
    return mli_sfi(gfi) == 0;
}

/* Sur un repertoire de volume, aux_type = blocs du volume et blocks_used
 * = blocs occupes. */
static unsigned char volume_blocks(const char* volume, unsigned int* total, unsigned int* free)
{
    if (!file_info(volume)) return 0;
    *total = gfi[5] | ((unsigned int)gfi[6] << 8);
    *free = *total - (gfi[8] | ((unsigned int)gfi[9] << 8));
    return 1;
}

static void volume_space(struct Panel* pan)
{
    const char* slash;
    unsigned char len;
    char volume[NAME_LEN];
    pan->free_blocks = pan->total_blocks = 0;
    if (!pan->path[0]) return;
    slash = strchr(pan->path + 1, '/');
    len = slash ? (unsigned char)(slash - pan->path) : (unsigned char)strlen(pan->path);
    if (len >= NAME_LEN) return;
    memcpy(volume, pan->path, len);
    volume[len] = 0;
    volume_blocks(volume, &pan->total_blocks, &pan->free_blocks);
}

/* ---------------------------------------------------------------------- */
/* Lecture directe d'un repertoire                                         */
/* ---------------------------------------------------------------------- */

/* ProDOS laisse lire un repertoire comme un fichier : des blocs de 512
 * octets, quatre octets de chainage puis des entrees de 39 octets, la
 * premiere du premier bloc etant l'en-tete (longueur d'entree, entrees par
 * bloc). Lire ainsi evite opendir/readdir de cc65 et leur malloc : c'est
 * moins de code, et plus aucun tas a reserver. Le bloc courant vit dans
 * copy_buf, qui n'est jamais utilise en meme temps. */
struct DirEntry {
    char name[NAME_LEN];
    unsigned char type, access;
    unsigned int aux, blocks, mdate;
    unsigned long size;
};
static int dir_fd = -1;
static unsigned char dir_index, dir_per_block, dir_entry_len;
static struct DirEntry dir_entry;

static unsigned char dir_open(const char* path)
{
    dir_fd = open(path, O_RDONLY);
    if (dir_fd < 0) return 0;
    if (read(dir_fd, copy_buf, 512) != 512 || (copy_buf[4] >> 4) < 0x0E) { close(dir_fd); dir_fd = -1; return 0; }
    dir_entry_len = copy_buf[4 + 0x1F];
    dir_per_block = copy_buf[4 + 0x20];
    if (dir_entry_len != 0x27 || dir_per_block != 0x0D) { close(dir_fd); dir_fd = -1; return 0; }
    dir_index = 1;                   /* l'entree 0 est l'en-tete */
    return 1;
}

static void dir_close(void)
{
    if (dir_fd >= 0) close(dir_fd);
    dir_fd = -1;
}

/* L'entree suivante dans dir_entry, ou 0 a la fin. */
static unsigned char dir_next(void)
{
    const unsigned char* e;
    unsigned char len;
    for (;;) {
        if (dir_index >= dir_per_block) {
            if (read(dir_fd, copy_buf, 512) != 512) return 0;
            dir_index = 0;
        }
        e = copy_buf + 4 + dir_index * dir_entry_len;
        ++dir_index;
        if (!(e[0] & 0xF0)) continue;   /* entree effacee */
        len = e[0] & 0x0F;
        memcpy(dir_entry.name, e + 1, len);
        dir_entry.name[len] = 0;
        dir_entry.type = e[0x10];
        dir_entry.blocks = e[0x13] | ((unsigned int)e[0x14] << 8);
        dir_entry.size = (unsigned long)e[0x15] | ((unsigned long)e[0x16] << 8) | ((unsigned long)e[0x17] << 16);
        dir_entry.access = e[0x1E];
        dir_entry.aux = e[0x1F] | ((unsigned int)e[0x20] << 8);
        dir_entry.mdate = e[0x21] | ((unsigned int)e[0x22] << 8);
        return 1;
    }
}

/* ---------------------------------------------------------------------- */
/* Affichage                                                              */
/* ---------------------------------------------------------------------- */

static void clear_row(unsigned char row)
{
    cclearxy(0, row, 80);
}

static void message(const char* text)
{
    clear_row(22);
    cputsxy(0, 22, text);
}

static void too_long(void)
{
    message("Path too long for ProDOS.");
}

static void dir_fail(void)
{
    message("Directory unreadable or too many files.");
}

/* La barre de touches, facon Norton Commander : chaque touche dans un bloc
 * inverse de trois colonnes, son libelle en clair juste apres, un espace
 * entre les boutons. `spec` enchaine "TOUCHE Libelle" separes par des
 * virgules ; une touche d'une lettre est centree dans son bloc. La ligne 23
 * n'est jamais ecrite au-dela de la colonne 78 : conio passerait a la ligne
 * sur la 80e et ferait defiler l'ecran. */
static const char MAIN_KEYS[] = "TAB Panel,RET Open,SPC Tag,C Copy,V Move,R Ren,D Del,K Mkdir,S Sort,? Help";
static const char VIEW_KEYS[] = "SPC Next,B Prev,ESC Back";
static const char HELP_KEYS[] = "ANY Return to the panels";

static void keys_bar(unsigned char x, const char* spec)
{
    const char* s = spec;
    unsigned char klen, i;
    gotoxy(x, 23);
    while (*s) {
        for (klen = 0; s[klen] && s[klen] != ' '; ++klen) {}
        revers(1);
        if (klen == 1) { cputc(' '); cputc(*s); cputc(' '); }
        else for (i = 0; i < 3; ++i) cputc(i < klen ? s[i] : ' ');
        revers(0);
        s += klen;
        if (*s == ' ') ++s;
        while (*s && *s != ',') cputc(*s++);
        if (*s == ',') { cputc(' '); ++s; }
    }
}

/* Efface la ligne 23 (79 colonnes, voir keys_bar) avant de la reecrire. */
static void bar_begin(void)
{
    cclearxy(0, 23, 79);
    gotoxy(0, 23);
}

static void help_bar(void)
{
    bar_begin();
    keys_bar(0, MAIN_KEYS);
}

static const char* type_name(unsigned char type)
{
    static char hex[4];
    switch (type) {
    case 0x04: return "TXT";
    case 0x06: return "BIN";
    case 0x0F: return "DIR";
    case 0xB3: return "S16";
    case 0xFA: return "INT";
    case 0xFC: return "BAS";
    case 0xFD: return "VAR";
    case 0xFF: return "SYS";
    }
    sprintf(hex, "$%02X", type);
    return hex;
}

static unsigned char is_up(const struct Entry* e)
{
    return e->name[0] == '.' && e->name[1] == '.' && !e->name[2];
}

static unsigned char is_dir(const struct Entry* e)
{
    return e->type == 0x0F;
}

static unsigned char is_locked(const struct Entry* e)
{
    return !(e->access & 0x80);
}

static unsigned char tagged(const struct Panel* pan, unsigned char index)
{
    return (pan->tags[index >> 3] >> (index & 7)) & 1;
}

static void set_tag(struct Panel* pan, unsigned char index, unsigned char on)
{
    if (on) pan->tags[index >> 3] |= 1 << (index & 7);
    else pan->tags[index >> 3] &= ~(1 << (index & 7));
}

static unsigned char tag_count(const struct Panel* pan)
{
    unsigned char i, n = 0;
    for (i = 0; i < pan->count; ++i) n += tagged(pan, i);
    return n;
}

/* Une ligne d'entree, 38 caracteres exactement (une ligne plus courte
 * laisserait a l'ecran la fin de la ligne precedente), en inverse quand le
 * curseur y est ; une etoile apres le nom marque un fichier selectionne par
 * Espace, un L un fichier verrouille. */
static void draw_entry(unsigned char p, unsigned char index)
{
    struct Panel* pan = &panels[p];
    unsigned char x = p ? 40 : 0;
    unsigned char row = 2 + (index - pan->top);
    const struct Entry* e = &pan->e[index];
    if (index >= pan->count) { cclearxy(x, row, 38); return; }
    if (p == active && index == pan->cursor) revers(1);
    gotoxy(x, row);
    if (is_up(e)) cprintf("%-15s  <UP>                 ", e->name);
    else if (!pan->path[0]) cprintf("%-15s S%u,D%u %5u/%5u free", e->name, e->mdate & 7, (e->mdate >> 3) + 1, e->aux, e->blocks);
    else if (is_dir(e)) cprintf("%-15s  <DIR>          %5u ", e->name, e->blocks);
    else cprintf("%-15s%c%c%s $%04X %8lu   ", e->name, tagged(pan, index) ? '*' : ' ',
                 is_locked(e) ? 'L' : ' ', type_name(e->type), e->aux, e->size);
    revers(0);
}

static void draw_panel(unsigned char p)
{
    struct Panel* pan = &panels[p];
    unsigned char x = p ? 40 : 0, i;
    static const char* const headers[SORT_MODES] = {
        "Name*            Type  Aux     Size",
        "Name             Type  Aux     Size*",
        "Name             Type* Aux     Size" };
    ++total_draws;
    cclearxy(x, 0, 38);
    if (p == active) revers(1);
    gotoxy(x, 0);
    i = strlen(pan->path);
    cprintf("%-38.38s", !pan->path[0] ? "[Volumes]" : i > 38 ? pan->path + i - 38 : pan->path);
    revers(0);
    gotoxy(x, 1);
    if (!pan->path[0]) cprintf("%-38s", "Volume          Slot   Free/Total");
    else if (pan->first || pan->more) cprintf("%-4u+ disk order    Type  Aux     Size", pan->first);
    else cprintf("%-38s", headers[sort_mode]);
    for (i = 0; i < ROWS; ++i) draw_entry(p, pan->top + i);
}

/* La ligne de separation porte le nom du programme et l'espace libre du
 * volume du panneau actif. */
static void draw_status(void)
{
    struct Panel* pan = &panels[active];
    chlinexy(0, 20, 80);
    cputsxy(2, 20, " TOTAL " TOTAL_VERSION " ");
    if (pan->total_blocks) {
        gotoxy(30, 20);
        cprintf(" %u of %u blocks free ", pan->free_blocks, pan->total_blocks);
    }
}

static void draw_frame(void)
{
    unsigned char row;
    clrscr();
    for (row = 0; row < 20; ++row) cputcxy(39, row, '|');
    draw_status();
    help_bar();
}

static void draw_info(void)
{
    struct Panel* pan = &panels[active];
    const struct Entry* e;
    unsigned char n;
    clear_row(21);
    if (!pan->count) return;
    e = &pan->e[pan->cursor];
    gotoxy(0, 21);
    if (is_up(e)) cputs("Parent directory");
    else if (!pan->path[0]) cprintf("Volume %s  slot %u drive %u  %u blocks, %u free", e->name, e->mdate & 7, (e->mdate >> 3) + 1, e->blocks, e->aux);
    else if (is_dir(e)) cprintf("%s  directory  %u blocks", e->name, e->blocks);
    else {                      /* 83 colonnes au pire (nom de 15, 16 Mo, verrou) : coupee a 79 */
        sprintf((char*)copy_buf, "%s  type $%02X  aux $%04X  %u blocks  %lu bytes  %02u/%02u/%02u%s",
                e->name, e->type, e->aux, e->blocks, e->size,
                e->mdate & 31, (e->mdate >> 5) & 15, (e->mdate >> 9) % 100,
                is_locked(e) ? "  locked" : "");
        copy_buf[79] = 0;
        cputs((char*)copy_buf);
    }
    n = tag_count(pan);
    if (n) { gotoxy(70, 21); cprintf("%u tagged", n); }
}

static void draw_all(void)
{
    draw_frame();
    draw_panel(0);
    draw_panel(1);
    draw_info();
}

static void show_active(void)
{
    draw_panel(active);
    draw_status();
    draw_info();
}

/* ---------------------------------------------------------------------- */
/* Lecture des repertoires                                                */
/* ---------------------------------------------------------------------- */

static int compare(const void* a, const void* b)
{
    const struct Entry* x = a;
    const struct Entry* y = b;
    if (is_dir(x) != is_dir(y)) return is_dir(x) ? -1 : 1;
    if (!is_dir(x)) {
        if (sort_mode == SORT_SIZE && x->size != y->size) return x->size < y->size ? 1 : -1;
        if (sort_mode == SORT_TYPE && x->type != y->type) return x->type < y->type ? -1 : 1;
    }
    return strcmp(x->name, y->name);
}

/* Tri par insertion, ".." reste en tete : moins de code que qsort, et les
 * dossiers du disque arrivent presque tries. */
static void sort_entries(struct Panel* pan)
{
    unsigned char i, j;
    struct Entry tmp;
    for (i = 2; i < pan->count; ++i) {
        tmp = pan->e[i];
        for (j = i; j > 1 && compare(&pan->e[j - 1], &tmp) > 0; --j) pan->e[j] = pan->e[j - 1];
        pan->e[j] = tmp;
    }
}

static struct Entry* add_entry(struct Panel* pan, const char* name, unsigned char type)
{
    struct Entry* e = &pan->e[pan->count++];
    strncpy(e->name, name, NAME_LEN - 1);
    e->name[NAME_LEN - 1] = 0;
    e->type = type;
    e->access = 0xC3;
    e->aux = e->blocks = e->mdate = 0;
    e->size = 0;
    return e;
}

/* DEVNUM ($BF30) : le dernier peripherique touche par ProDOS. L'enumeration
 * des volumes le laisse sur le dernier lecteur interroge (/RAM sur un IIe),
 * et Bitsy Bye s'ouvrirait la au retour : on le remet tel qu'il etait. */
#define DEVNUM (*(volatile unsigned char*)0xBF30)

static void read_volumes(struct Panel* pan)
{
    unsigned char dev = getfirstdevice();
    unsigned char saved = DEVNUM;
    char name[NAME_LEN];
    struct Entry* e;
    while (dev != INVALID_DEVICE && pan->count < MAX_ENTRIES) {
        if (getdevicedir(dev, name, sizeof name)) {
            e = add_entry(pan, name, 0x0F);
            e->mdate = dev;
            volume_blocks(name, &e->blocks, &e->aux);
        }
        dev = getnextdevice(dev);
    }
    DEVNUM = saved;
}

/* Remplit le panneau et oublie ses marques. La fenetre commence a l'entree
 * pan->first du disque ; ".." n'apparait que dans la premiere, et le tri ne
 * s'applique que si le dossier tient entier. Rend 0 si le dossier ne se lit
 * pas : le panneau retombe alors sur la liste des volumes, jamais sur un
 * ecran vide. */
static unsigned char read_panel(unsigned char p)
{
    struct Panel* pan = &panels[p];
    struct Entry* e;
    unsigned int skip = pan->first;
    unsigned char ok = 1;
    pan->count = 0;
    pan->more = 0;
    memset(pan->tags, 0, sizeof pan->tags);
    if (!pan->path[0]) {
        pan->first = 0;
        read_volumes(pan);
    } else {
        if (!dir_open(pan->path)) {
            ok = 0;
            pan->path[0] = 0;
            pan->first = 0;
            read_volumes(pan);
        } else {
            if (!pan->first) add_entry(pan, "..", 0x0F);
            while (dir_next()) {
                if (skip) { --skip; continue; }
                if (pan->count >= (pan->first ? WINDOW : MAX_ENTRIES)) { pan->more = 1; break; }
                e = add_entry(pan, dir_entry.name, dir_entry.type);
                e->access = dir_entry.access;
                e->aux = dir_entry.aux;
                e->blocks = dir_entry.blocks;
                e->size = dir_entry.size;
                e->mdate = dir_entry.mdate;
            }
            dir_close();
            if (pan->first && !pan->count) { pan->first = 0; return read_panel(p); }
            if (!pan->first && !pan->more && pan->count > 2) sort_entries(pan);
        }
    }
    volume_space(pan);
    if (pan->cursor >= pan->count) pan->cursor = pan->count ? pan->count - 1 : 0;
    if (pan->top > pan->cursor) pan->top = pan->cursor;
    if (pan->cursor >= pan->top + ROWS) pan->top = pan->cursor - ROWS + 1;
    return ok;
}

static void set_cursor(struct Panel* pan, unsigned char index)
{
    pan->cursor = index;
    if (pan->cursor < pan->top) pan->top = pan->cursor;
    if (pan->cursor >= pan->top + ROWS) pan->top = pan->cursor - ROWS + 1;
}

static void select_name(struct Panel* pan, const char* name)
{
    unsigned char i;
    pan->cursor = 0;
    pan->top = 0;
    for (i = 0; i < pan->count; ++i)
        if (!strcmp(pan->e[i].name, name)) { set_cursor(pan, i); break; }
}

/* Chemin complet de l'entree : "/VOL/DIR/NAME", ou "/VOL" depuis la liste
 * des volumes. Rend 0 si le resultat depasserait les 64 caracteres ProDOS. */
static unsigned char build_full(char* out, const struct Panel* pan, const struct Entry* e)
{
    if (!pan->path[0]) { strcpy(out, e->name); return 1; }
    if (strlen(pan->path) + 1 + strlen(e->name) >= PATH_LEN) return 0;
    sprintf(out, "%s/%s", pan->path, e->name);
    return 1;
}

static void open_path(struct Panel* pan)
{
    pan->cursor = pan->top = 0;
    pan->first = 0;
    if (!read_panel(pan - panels)) message("Cannot read this directory.");
}

static void go_up(struct Panel* pan)
{
    char last[NAME_LEN];
    char* slash = strrchr(pan->path, '/');
    if (!slash) return;
    strcpy(last, slash == pan->path ? slash : slash + 1);   /* la liste des volumes nomme "/VOL" */
    if (slash == pan->path) pan->path[0] = 0;   /* "/VOL" -> volumes */
    else *slash = 0;
    open_path(pan);
    select_name(pan, last);
}

static void enter_dir(struct Panel* pan, const struct Entry* e)
{
    if (is_up(e)) { go_up(pan); return; }
    if (!build_full(full, pan, e)) { too_long(); return; }
    strcpy(pan->path, full);
    open_path(pan);
}

/* ---------------------------------------------------------------------- */
/* Saisie -- dans la carte langage                                        */
/* ---------------------------------------------------------------------- */
#pragma code-name (push, "LC")
#pragma rodata-name (push, "LC")

static unsigned char confirm(const char* text)
{
    char key;
    clear_row(22);
    gotoxy(0, 22);
    cprintf("%s (Y/N) ", text);
    for (;;) {
        key = cgetc();
        if (key == 'y' || key == 'Y') { clear_row(22); return 1; }
        if (key == 'n' || key == 'N' || key == KEY_ESC) { clear_row(22); return 0; }
    }
}

/* Une saisie dans `input` : un nom ProDOS (lettre, puis lettres, chiffres
 * ou points, 15 au plus) ou, avec hex != 0, ce nombre de chiffres
 * hexadecimaux. Rend 0 si l'utilisateur annule (Echap) ou ne saisit rien. */
static unsigned char prompt(const char* label, const char* initial, unsigned char hex)
{
    unsigned char len = 0, max = hex ? hex : 15;
    char key;
    if (initial) { strcpy(input, initial); len = strlen(input); }
    else input[0] = 0;
    for (;;) {
        clear_row(22);
        gotoxy(0, 22);
        cprintf("%s: %s%s_", label, hex ? "$" : "", input);
        key = cgetc();
        if (key == KEY_ESC) { clear_row(22); return 0; }
        if (key == KEY_RETURN) { clear_row(22); return hex ? len == max : len != 0; }
        if (key == KEY_LEFT || key == KEY_DELETE) { if (len) input[--len] = 0; continue; }
        if (key >= 'a' && key <= 'z') key -= 32;
        if (len >= max) continue;
        if (hex ? ((key >= '0' && key <= '9') || (key >= 'A' && key <= 'F'))
                : ((key >= 'A' && key <= 'Z') || (len && ((key >= '0' && key <= '9') || key == '.')))) {
            input[len++] = key;
            input[len] = 0;
        }
    }
}

static unsigned int hex_value(void)
{
    unsigned int v = 0;
    const char* s = input;
    for (; *s; ++s) v = (v << 4) | (*s <= '9' ? *s - '0' : *s - 'A' + 10);
    return v;
}

static void report_error(const char* what)
{
    ++total_errors;
    clear_row(22);
    gotoxy(0, 22);
    cprintf("%s failed (errno %d, ProDOS $%02X).", what, errno, _oserror);
}

/* ---------------------------------------------------------------------- */
/* Visionneuses -- dans la carte langage                                  */
/* ---------------------------------------------------------------------- */

/* Sans ouvrir le fichier : un FOT ($08), ou un BIN de la taille d'une page
 * HGR ou DHGR, ou un flux .RLE. L'ouverture tranche ensuite sur l'en-tete.
 * En RAM principale : la carte langage est pleine. */
#pragma code-name (push, "CODE")
#pragma rodata-name (push, "RODATA")
static unsigned char looks_like_image(const struct Entry* e)
{
    unsigned char n = strlen(e->name);
    if (is_dir(e)) return 0;
    if (e->type == 0x08) return 1;
    if (e->type != 0x06) return 0;
    return e->size == 8192 || e->size == 8184 || e->size == 16384
        || (n > 4 && !strcmp(e->name + n - 4, ".RLE"));
}
#pragma rodata-name (pop)
#pragma code-name (pop)

/* Lecture tamponnee : fgetc de cc65 passe par ProDOS a chaque octet. */
static FILE* vf;
static unsigned int vlen, vpos;
static long vbase;

static int view_getc(void)
{
    if (vpos >= vlen) {
        vbase += vlen;
        vpos = 0;
        vlen = fread(copy_buf, 1, sizeof copy_buf, vf);
        if (!vlen) return -1;
    }
    return copy_buf[vpos++];
}

static void view_seek(long offset)
{
    fseek(vf, offset, SEEK_SET);
    vbase = offset;
    vlen = vpos = 0;
}

#define TEXT_ROWS 22
#define TEXT_PAGES 96           /* text_starts[] : les debuts de page connus */

/* Une page de 22 lignes ; les retours ProDOS sont des CR. Les debuts de
 * page sont memorises au passage : la page precedente est un fseek. */
static void view_text(const char* path)
{
    long* starts = text_starts;
    unsigned char page = 0, known = 1, row, col, done = 0;
    int c;
    char key;
    vf = fopen(path, "rb");
    if (!vf) { report_error("Open"); return; }
    total_view = 2;
    starts[0] = 0;
    for (;;) {
        view_seek(starts[page]);
        clrscr();
        row = 0; col = 0; done = 0;
        while (row < TEXT_ROWS) {
            c = view_getc();
            if (c < 0) { done = 1; break; }
            c &= 0x7F;
            if (c == 13 || c == 10) { ++row; col = 0; if (row < TEXT_ROWS) gotoxy(0, row); continue; }
            if (c < 32) c = '.';
            if (col == 80) { ++row; col = 0; if (row >= TEXT_ROWS) { --row; --vpos; break; } gotoxy(0, row); }   /* le caractere ouvrira la page suivante */
            cputc((char)c);
            ++col;
        }
        if (!done && page + 1 < TEXT_PAGES && known == page + 1) {
            starts[page + 1] = vbase + vpos;
            known = page + 2;
        }
        bar_begin();
        cprintf("%-38.38s page %u%s", path, page + 1, done ? " (end)" : "");
        keys_bar(52, VIEW_KEYS);
        key = cgetc();
        if (key == KEY_ESC || key == 'q' || key == 'Q') break;
        if ((key == ' ' || key == KEY_RETURN || key == KEY_RIGHT || key == KEY_DOWN) && !done && page + 1 < known) ++page;
        if ((key == 'b' || key == 'B' || key == KEY_LEFT || key == KEY_UP) && page) --page;
    }
    fclose(vf);
    total_view = 0;
    draw_all();
}

#define HEX_ROWS 20
#define HEX_PAGE (HEX_ROWS * 16)

static void view_hex(const char* path, unsigned long size)
{
    unsigned int page = 0, pages = (unsigned int)((size + HEX_PAGE - 1) / HEX_PAGE), n, i, j;
    char key;
    vf = fopen(path, "rb");
    if (!vf) { report_error("Open"); return; }
    total_view = 3;
    if (!pages) pages = 1;
    for (;;) {
        fseek(vf, (long)page * HEX_PAGE, SEEK_SET);
        n = fread(copy_buf, 1, HEX_PAGE, vf);
        clrscr();
        for (i = 0; i < n; i += 16) {
            gotoxy(0, i / 16);
            cprintf("%05lX ", (unsigned long)page * HEX_PAGE + i);
            for (j = 0; j < 16; ++j) {
                if (i + j < n) cprintf("%02X ", copy_buf[i + j]);
                else cputs("   ");
            }
            cputc(' ');
            for (j = 0; j < 16 && i + j < n; ++j) {
                unsigned char c = copy_buf[i + j] & 0x7F;
                cputc(c < 32 || c == 127 ? '.' : (char)c);
            }
        }
        bar_begin();
        cprintf("%-22.22s %lu bytes page %u/%u", path, size, page + 1, pages);
        keys_bar(52, VIEW_KEYS);
        key = cgetc();
        if (key == KEY_ESC || key == 'q' || key == 'Q') break;
        if ((key == ' ' || key == KEY_RETURN || key == KEY_RIGHT || key == KEY_DOWN) && page + 1 < pages) ++page;
        if ((key == 'b' || key == 'B' || key == KEY_LEFT || key == KEY_UP) && page) --page;
    }
    fclose(vf);
    total_view = 0;
    draw_all();
}

/* ---------------------------------------------------------------------- */
/* Preferences : TOTAL/TOTAL.CFG -- dans la carte langage                 */
/* ---------------------------------------------------------------------- */

/* Trois lignes CR : panneau gauche, panneau droit, "S<tri>A<actif>". */
static void save_config(void)
{
    FILE* f;
    unsigned char n;
    _filetype = 0x04;
    _auxtype = 0;
    f = fopen(cfg_path, "wb");
    if (!f) return;
    n = sprintf((char*)copy_buf, "%s\r%s\rS%uA%u\r", panels[0].path, panels[1].path, sort_mode, active);
    fwrite(copy_buf, 1, n, f);
    fclose(f);
}

static void load_config(void)
{
    FILE* f = fopen(cfg_path, "rb");
    unsigned char n, p = 0, i, len = 0;
    char line[PATH_LEN];
    if (!f) return;
    n = fread(copy_buf, 1, 200, f);
    fclose(f);
    for (i = 0; i < n && p < 3; ++i) {
        if (copy_buf[i] != '\r') { if (len < PATH_LEN - 1) line[len++] = copy_buf[i]; continue; }
        line[len] = 0;
        if (p < 2 && line[0] == '/') strcpy(panels[p].path, line);
        if (p == 2 && len >= 4 && line[0] == 'S' && line[2] == 'A' && (unsigned char)(line[1] - '0') < SORT_MODES) {
            sort_mode = line[1] - '0';
            active = (line[3] - '0') & 1;
        }
        ++p;
        len = 0;
    }
}

#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* Image                                                                  */
/* ---------------------------------------------------------------------- */

/* Les formats d'image reconnus, d'apres les huit premiers octets et la
 * taille : une page HGR brute (8 192 ou 8 184 octets), une page DHGR brute
 * (16 384 : AUX puis MAIN, l'ordre des fichiers A2FC et du jeu), un flux
 * HGRR v1 (RLE, 8 192 decompresses) ou DHRR v1 (RLE, 16 384). */
enum { IMG_NONE, IMG_HGR, IMG_DHGR, IMG_HGRR, IMG_DHRR };
static const char* const IMG_NAMES[] = { "not an image", "HGR raw", "DHGR raw", "HGR RLE", "DHGR RLE" };
static const unsigned long IMG_BYTES[] = { 0, 8192, 16384, 8192, 16384 };
static unsigned char img_kind;

#define HGR_MAIN ((unsigned char*)0x2000)

/* Aiguille les ecritures $2000-$3FFF vers AUX (80STORE + HIRES + PAGE2),
 * comme hgr_loader.s ; le MLI y ecrit alors aussi. */
static void aux_writes(unsigned char on)
{
    if (on) { *(unsigned char*)0xC002 = 0; *(unsigned char*)0xC004 = 0; *(unsigned char*)0xC057 = 0; *(unsigned char*)0xC001 = 0; *(unsigned char*)0xC055 = 0; }
    else { *(unsigned char*)0xC054 = 0; *(unsigned char*)0xC000 = 0; }
}

/* HGR simple, page 1, sans le mode double : 80COL et DHIRES coupes. */
static void show_hgr(void)
{
    *(unsigned char*)0xC000 = 0; *(unsigned char*)0xC00C = 0; *(unsigned char*)0xC05F = 0;
    *(unsigned char*)0xC050 = 0; *(unsigned char*)0xC057 = 0; *(unsigned char*)0xC054 = 0; *(unsigned char*)0xC052 = 0;
}

/* Un flux RLE v1 (HGRR ou DHRR) decompresse en $2000 : `bytes` octets, la
 * premiere moitie d'un DHRR vers AUX. Le fichier est ouvert sur l'en-tete.
 * Une repetition peut chevaucher la frontiere des deux plans : l'ecriture
 * se fait octet par octet, et le plan bascule au passage de $4000. */
static unsigned int dn;
static unsigned char dplane, dplanes;

/* Avance de `n` octets ecrits ; bascule le plan a $4000. */
static void advance(unsigned int n)
{
    dn += n;
    if (dn == 8192) { dn = 0; ++dplane; if (dplane == 1 && dplanes == 2) aux_writes(0); }
}

static unsigned char decode_rle(FILE* f, unsigned long bytes)
{
    unsigned int count, chunk;
    int t, v;
    dn = 0; dplane = 0; dplanes = bytes > 8192 ? 2 : 1;
    vf = f;
    view_seek(8);
    if (dplanes == 2) aux_writes(1);
    while (dplane < dplanes) {
        t = view_getc();
        if (t < 0) break;
        if (t & 0x80) {
            count = (t & 0x7F) + 3;
            v = view_getc();
            if (v < 0) break;
            while (count && dplane < dplanes) {
                chunk = count < 8192 - dn ? count : 8192 - dn;
                memset(HGR_MAIN + dn, v, chunk);
                count -= chunk;
                advance(chunk);
            }
        } else {
            count = t + 1;
            while (count && dplane < dplanes) {
                /* tampon vide : view_getc le recharge et prend un octet, rendu ici */
                if (vpos >= vlen) { if (view_getc() < 0) { count = 0xFFFF; break; } --vpos; }
                chunk = vlen - vpos;
                if (chunk > count) chunk = count;
                if (chunk > 8192 - dn) chunk = 8192 - dn;
                memcpy(HGR_MAIN + dn, copy_buf + vpos, chunk);
                vpos += chunk;
                count -= chunk;
                advance(chunk);
            }
            if (count == 0xFFFF) break;
        }
    }
    aux_writes(0);
    return dplane == dplanes;
}

/* Identifie et charge l'image `full` en page 1. Rend le format, IMG_NONE
 * si le fichier n'en est pas une. */
static unsigned char load_image(unsigned long size)
{
    FILE* f = fopen(full, "rb");
    unsigned char kind = IMG_NONE, ok = 0;
    if (!f) return IMG_NONE;
    if (fread(copy_buf, 1, 8, f) == 8) {
        if (!memcmp(copy_buf, "DHRR\1\0\0\x40", 8)) kind = IMG_DHRR;
        else if (!memcmp(copy_buf, "HGRR\1\0\0\x20", 8)) kind = IMG_HGRR;
        else if (size == 8192 || size == 8184) kind = IMG_HGR;
        else if (size == 16384) kind = IMG_DHGR;
    }
    if (kind == IMG_DHRR) ok = decode_rle(f, 16384);
    else if (kind == IMG_HGRR) ok = decode_rle(f, 8192);
    else if (kind == IMG_HGR) { rewind(f); ok = fread(HGR_MAIN, 1, 8192, f) >= 8184; }
    else if (kind == IMG_DHGR) {
        rewind(f);
        aux_writes(1);
        ok = fread(HGR_MAIN, 1, 8192, f) == 8192;
        aux_writes(0);
        ok = ok && fread(HGR_MAIN, 1, 8192, f) == 8192;
    }
    fclose(f);
    return ok ? kind : IMG_NONE;
}

/* L'image du curseur, plein ecran, HGR ou DHGR selon ce que le fichier
 * contient. Gauche / Droite passent a l'image precedente / suivante du
 * meme dossier sans revenir aux panneaux : le dossier DHGR se feuillette
 * comme un album. Toute autre touche revient, et la ligne de message dit
 * le format reconnu. */
static void view_image(void)
{
    struct Panel* pan = &panels[active];
    unsigned char index = pan->cursor, next;
    char key;
    /* L'image recouvre les tables d'entrees : les marques sont mises de
     * cote, les panneaux relus au retour (et avant chaque image suivante). */
    memcpy(picked, panels[0].tags, sizeof panels[0].tags);
    memcpy(picked + sizeof panels[0].tags, panels[1].tags, sizeof panels[1].tags);
    for (;;) {
        if (!build_full(full, pan, &pan->e[index])) { too_long(); break; }
        strcpy(input, pan->e[index].name);
        total_view = 1;
        img_kind = load_image(pan->e[index].size);
        if (img_kind == IMG_NONE) break;
        if (img_kind == IMG_HGR || img_kind == IMG_HGRR) show_hgr(); else switch_to_hgr();
        key = cgetc();
        if (key != KEY_LEFT && key != KEY_RIGHT) break;
        read_panel(active);
        next = index;
        for (;;) {
            if (key == KEY_LEFT) { if (!next) break; --next; }
            else { if (next + 1 >= pan->count) break; ++next; }
            if (looks_like_image(&pan->e[next])) { index = next; break; }
        }
    }
    switch_to_text();
    total_view = 0;
    read_panel(0);
    read_panel(1);
    memcpy(panels[0].tags, picked, sizeof panels[0].tags);
    memcpy(panels[1].tags, picked + sizeof panels[0].tags, sizeof panels[1].tags);
    set_cursor(pan, index);
    draw_all();
    clear_row(22);
    gotoxy(0, 22);
    if (img_kind == IMG_NONE) cprintf("%s: not an image.", input);
    else cprintf("%s: %s, %lu bytes on screen.", input, IMG_NAMES[img_kind], IMG_BYTES[img_kind]);
}

/* ---------------------------------------------------------------------- */
/* Editeur de texte                                                       */
/* ---------------------------------------------------------------------- */

/* Le texte vit dans la page HGR MAIN, comme les tables d'entrees (relues
 * a la sortie) : 8 Ko au plus, fins de ligne CR, bit 7 ote au chargement.
 * Le curseur est un decalage dans le tampon ; l'ecran montre 22 lignes a
 * partir de `etop`, debut d'une ligne, sans repli des lignes longues. */
#define EDIT_ROWS 22
static unsigned int elen, ecur, etop, ewant;
static unsigned char edirty, etype;
static unsigned int eaux;

#pragma code-name (push, "LC")
static unsigned int line_start(unsigned int pos)
{
    while (pos && EDIT_BUF[pos - 1] != '\r') --pos;
    return pos;
}

static unsigned int line_end(unsigned int pos)
{
    while (pos < elen && EDIT_BUF[pos] != '\r') ++pos;
    return pos;
}

static unsigned int next_line(unsigned int pos)
{
    pos = line_end(pos);
    return pos < elen ? pos + 1 : pos;
}
#pragma code-name (pop)

/* Redessine les lignes a partir de `from` (numero d'ecran). */
static void edit_draw(unsigned char from)
{
    unsigned int pos = etop;
    unsigned char row, col;
    for (row = 0; row < from; ++row) pos = next_line(pos);
    for (row = from; row < EDIT_ROWS; ++row) {
        gotoxy(0, row);
        col = 0;
        while (pos < elen && EDIT_BUF[pos] != '\r') {
            if (col < 79) cputc(EDIT_BUF[pos] < 32 ? '.' : EDIT_BUF[pos]);
            ++pos;
            ++col;
        }
        if (col < 79) cclear(79 - col);
        if (pos < elen) ++pos;
    }
}

static void edit_status(void)
{
    unsigned int line = 0, pos = 0, ls = line_start(ecur);
    while (pos < ls) { pos = next_line(pos); ++line; }
    bar_begin();
    revers(1);
    cprintf(" %-30.30s  Line %u  Col %u  %u/%u bytes %s", full, line + 1, ecur - ls + 1, elen, EDIT_MAX, edirty ? "*" : " ");
    revers(0);
    keys_bar(69, "ESC Menu");
}

/* Place le curseur a l'ecran ; fait defiler si la ligne n'est pas visible. */
static unsigned char edit_place(void)
{
    unsigned int ls = line_start(ecur), pos;
    unsigned char row, scrolled = 0;
    while (ls < etop) { etop = line_start(etop - 1); scrolled = 1; }
    for (;;) {
        pos = etop;
        for (row = 0; row < EDIT_ROWS && pos < ls; ++row) pos = next_line(pos);
        if (pos == ls && row < EDIT_ROWS) break;
        etop = next_line(etop);
        scrolled = 1;
    }
    if (scrolled) edit_draw(0);
    edit_status();
    gotoxy(ecur - ls < 79 ? (unsigned char)(ecur - ls) : 79, row);
    return scrolled;
}

static void edit_vertical(int lines)
{
    unsigned int ls = line_start(ecur), target = ls;
    while (lines > 0 && next_line(target) < elen + 1 && line_end(target) < elen) { target = next_line(target); --lines; }
    while (lines < 0 && target) { target = line_start(target - 1); ++lines; }
    ecur = target + ewant;
    if (ecur > line_end(target)) ecur = line_end(target);
}

#pragma code-name (push, "LC")
static unsigned char edit_insert(char c)
{
    if (elen >= EDIT_MAX) { return 0; }
    memmove(EDIT_BUF + ecur + 1, EDIT_BUF + ecur, elen - ecur);
    EDIT_BUF[ecur++] = c;
    ++elen;
    edirty = 1;
    return 1;
}

static void edit_delete(void)
{
    if (ecur >= elen) return;
    memmove(EDIT_BUF + ecur, EDIT_BUF + ecur + 1, elen - ecur - 1);
    --elen;
    edirty = 1;
}
#pragma code-name (pop)

static unsigned char edit_save(void)
{
    FILE* f;
    _filetype = etype;
    _auxtype = eaux;
    f = fopen(full, "wb");
    if (!f) { report_error("Save"); return 0; }
    if (fwrite(EDIT_BUF, 1, elen, f) != elen) { fclose(f); report_error("Save"); return 0; }
    if (fclose(f)) { report_error("Save"); return 0; }
    edirty = 0;
    ++total_ops;
    return 1;
}

/* E : edite le fichier `full` (type et auxtype conserves a l'ecriture), ou
 * un fichier neuf si `fresh`. Rend 1 si quelque chose a ete ecrit. */
static unsigned char edit_file(unsigned char fresh, unsigned char type, unsigned int aux)
{
    FILE* f;
    unsigned int i, ls;
    unsigned char row, written = 0;
    char key;
    elen = ecur = etop = ewant = 0;
    edirty = 0;
    etype = type;
    eaux = aux;
    if (!fresh) {
        f = fopen(full, "rb");
        if (!f) { report_error("Open"); return 0; }
        elen = fread(EDIT_BUF, 1, EDIT_MAX + 1, f);
        fclose(f);
        if (elen > EDIT_MAX) { message("Too big for the editor (8 KB)."); return 0; }
        for (i = 0; i < elen; ++i) { EDIT_BUF[i] &= 0x7F; if (EDIT_BUF[i] == '\n') EDIT_BUF[i] = '\r'; }
    }
    total_view = 5;
    clrscr();
    edit_draw(0);
    edit_place();
    for (;;) {
        key = cgetc();
        ls = line_start(ecur);
        row = 0xFF;                     /* 0xFF : rien a redessiner */
        switch (key) {
        case KEY_LEFT: if (ecur) --ecur; ewant = ecur - line_start(ecur); break;
        case KEY_RIGHT: if (ecur < elen) ++ecur; ewant = ecur - line_start(ecur); break;
        case KEY_UP: edit_vertical(-1); break;
        case KEY_DOWN: edit_vertical(1); break;
        case 16: edit_vertical(-(EDIT_ROWS - 2)); break;      /* Ctrl-P */
        case 14: edit_vertical(EDIT_ROWS - 2); break;         /* Ctrl-N */
        case 1: ecur = ls; ewant = 0; break;                  /* Ctrl-A */
        case 5: ecur = line_end(ecur); ewant = ecur - ls; break;   /* Ctrl-E */
        case 20: ecur = 0; ewant = 0; break;                  /* Ctrl-T */
        case 2: ecur = elen; ewant = ecur - line_start(ecur); break;   /* Ctrl-B */
        case KEY_DELETE:
            if (ecur) { --ecur; row = EDIT_BUF[ecur] == '\r' ? 0 : 1; edit_delete(); }
            ewant = ecur - line_start(ecur);
            break;
        case 4:                                               /* Ctrl-D */
            if (ecur < elen) { row = EDIT_BUF[ecur] == '\r' ? 0 : 1; edit_delete(); }
            break;
        case KEY_RETURN: if (edit_insert('\r')) row = 0; ewant = 0; break;
        case KEY_TAB: for (i = 0; i < 4; ++i) edit_insert(' '); row = 1; ewant = ecur - ls; break;
        case KEY_ESC:
            bar_begin();
            keys_bar(0, "S Save,X Save and exit,Q Quit without saving,ESC Continue editing");
            key = cgetc();
            if (key == 's' || key == 'S') written |= edit_save();
            else if (key == 'x' || key == 'X') { if (edit_save()) { written = 1; goto leave; } }
            else if (key == 'q' || key == 'Q') { if (!edirty) goto leave; bar_begin(); keys_bar(0, "Y Discard the changes,N Keep editing"); key = cgetc(); if (key == 'y' || key == 'Y') goto leave; }
            break;
        default:
            if (key >= 32 && key < 127) { if (edit_insert(key)) row = 1; else message("Buffer full."); ewant = ecur - ls; }
            break;
        }
        /* row 1 : la ligne seule ; row 0 : elle et les suivantes. */
        if (row != 0xFF && !edit_place()) {
            unsigned int pos = etop; unsigned char r = 0;
            ls = line_start(ecur);
            while (pos < ls) { pos = next_line(pos); ++r; }
            edit_draw(row ? r : r);
            if (row == 1) { /* seule la ligne courante a change */ }
            edit_place();
        } else edit_place();
    }
leave:
    total_view = 0;
    return written;
}

static void edit_selected(void)
{
    struct Panel* pan = &panels[active];
    const struct Entry* e;
    unsigned char fresh = 0;
    if (!pan->count || !pan->path[0]) { message("Open a directory first."); return; }
    e = &pan->e[pan->cursor];
    if (is_dir(e)) {
        if (!prompt("New text file", NULL, 0)) return;
        if (strlen(pan->path) + 1 + strlen(input) >= PATH_LEN) { too_long(); return; }
        sprintf(full, "%s/%s", pan->path, input);
        if (exists(full)) { message("File exists: select it to edit."); return; }
        fresh = 1;
    } else if (!build_full(full, pan, e)) { too_long(); return; }
    strcpy(question, fresh ? input : e->name);
    memcpy(picked, panels[0].tags, sizeof panels[0].tags);
    memcpy(picked + sizeof panels[0].tags, panels[1].tags, sizeof panels[1].tags);
    edit_file(fresh, fresh ? 0x04 : e->type, fresh ? 0 : e->aux);
    switch_to_text();
    read_panel(0);
    read_panel(1);
    memcpy(panels[0].tags, picked, sizeof panels[0].tags);
    memcpy(panels[1].tags, picked + sizeof panels[0].tags, sizeof panels[1].tags);
    select_name(pan, question);
    draw_all();
}

/* ---------------------------------------------------------------------- */
/* Musique Mockingboard                                                   */
/* ---------------------------------------------------------------------- */

static unsigned char looks_like_music(const struct Entry* e)
{
    unsigned char n = strlen(e->name);
    return !is_dir(e) && e->type == 0x06 && n > 3 && !strcmp(e->name + n - 3, ".MB");
}

/* Entree sur un .MB : le flux MB1 est monte en AUX par le lecteur du jeu
 * (six voix, en interruption) et joue une fois pendant que l'on continue
 * de naviguer -- les lectures disque ne l'arretent pas, TOTAL n'y touche
 * jamais ; P le met en pause, un autre .MB le remplace, Q et X le coupent.
 * La carte est cherchee a la premiere demande. */
static void play_music(const struct Entry* e)
{
    FILE* f;
    unsigned int n, total = 0;
    unsigned char valid = 1;
    if (total_slot == 0xFF) total_slot = music_detect();
    if (!total_slot) { message("No Mockingboard found in slots 1-7."); return; }
    if (e->size > MUSIC_ZONE) { message("MB file too large (2304 bytes at most)."); return; }
    f = fopen(full, "rb");
    if (!f) { report_error("Open"); return; }
    music_stop();
    total_playing = 0;
    do {
        n = fread(music_buf, 1, MUSIC_STAGE, f);
        if (!total && (n <= 8 || memcmp(music_buf, "MB1", 3))) { valid = 0; break; }
        if (n) music_store(total, n);
        total += n;
    } while (n == MUSIC_STAGE);
    fclose(f);
    if (!valid) { message("Not an MB1 Mockingboard stream."); return; }
    music_select(0);
    music_set_loop(0);
    music_play();
    total_playing = 1;
    clear_row(22);
    gotoxy(0, 22);
    cprintf("Playing %s once on the Mockingboard in slot %u. P pauses.", e->name, total_slot);
}

static void toggle_music(void)
{
    if (!music_active) { total_playing = 0; message("No music playing: open a .MB file."); }
    else if (total_playing == 1) { music_pause(); total_playing = 2; message("Music paused. P resumes."); }
    else { music_resume(); total_playing = 1; message("Music resumed."); }
}

/* ---------------------------------------------------------------------- */
/* Aide                                                                   */
/* ---------------------------------------------------------------------- */

/* L'aide est lue dans TOTAL/TOTAL.HELP (a cote de TOTAL.CODE), une ligne
 * par element : "x,y,TOUCHE,libelle" pour un bouton, "x,y,#TITRE" pour un
 * titre de section, "x,y,~texte" pour du texte en clair ('=' et '-' sont
 * des touches). Le texte passe par
 * la page HGR, comme l'editeur : rien en memoire hors de l'aide. */
static void view_help(void)
{
    const char* s = EDIT_BUF;
    FILE* f;
    unsigned int n;
    unsigned char x, y, klen, i, kind;
    strcpy(other_full, cfg_path);
    strcpy(other_full + strlen(other_full) - 3, "HELP");
    f = fopen(other_full, "rb");
    if (!f) { message("TOTAL/TOTAL.HELP is missing: no help on this volume."); return; }
    n = fread(EDIT_BUF, 1, EDIT_MAX, f);
    fclose(f);
    EDIT_BUF[n] = 0;
    memcpy(picked, panels[0].tags, sizeof panels[0].tags);
    memcpy(picked + sizeof panels[0].tags, panels[1].tags, sizeof panels[1].tags);
    total_view = 4;
    clrscr();
    while (*s) {
        x = 0; while (*s >= '0' && *s <= '9') x = x * 10 + (*s++ - '0');
        if (*s++ != ',') break;
        y = 0; while (*s >= '0' && *s <= '9') y = y * 10 + (*s++ - '0');
        if (*s++ != ',' || x >= 80 || y >= 23) break;
        gotoxy(x, y);
        kind = *s;
        if (kind == '#' || kind == '~') {         /* # titre de section, ~ texte en clair */
            if (kind == '#') { revers(1); cputc(' '); }
            ++s;
            while (*s && *s != '\n' && *s != '\r') cputc(*s++);
            if (kind == '#') { cputc(' '); revers(0); }
        } else {
            for (klen = 0; s[klen] && s[klen] != ',' && s[klen] != '\r' && s[klen] != '\n'; ++klen) {}
            if (s[klen] != ',') break;
            revers(1);
            if (klen == 1) { cputc(' '); cputc(*s); cputc(' '); }
            else for (i = 0; i < 3; ++i) cputc(i < klen ? s[i] : ' ');
            revers(0);
            cputc(' ');
            s += klen + 1;
            while (*s && *s != '\n' && *s != '\r') cputc(*s++);
        }
        while (*s == '\n' || *s == '\r') ++s;
    }
    bar_begin();
    keys_bar(0, HELP_KEYS);
    cgetc();
    total_view = 0;
    read_panel(0);
    read_panel(1);
    memcpy(panels[0].tags, picked, sizeof panels[0].tags);
    memcpy(panels[1].tags, picked + sizeof panels[0].tags, sizeof panels[1].tags);
    draw_all();
}

/* ---------------------------------------------------------------------- */
/* Operations sur les fichiers                                            */
/* ---------------------------------------------------------------------- */

static void refresh_both(void)
{
    read_panel(0);
    read_panel(1);
    draw_panel(0);
    draw_panel(1);
    draw_status();
    draw_info();
}

/* Lit un dossier dans pool[base..] : noms, types, auxtypes. Rend 0 si le
 * dossier ne se lit pas ou si la reserve deborde. */
static unsigned char list_dir(const char* path, unsigned char base, unsigned char* count)
{
    unsigned char n = 0;
    if (!dir_open(path)) return 0;
    while (dir_next()) {
        if (base + n >= POOL_SIZE) { dir_close(); return 0; }
        strcpy(pool[base + n].name, dir_entry.name);
        pool[base + n].type = dir_entry.type;
        pool[base + n].aux = dir_entry.aux;
        ++n;
    }
    dir_close();
    *count = n;
    return 1;
}

/* Ajoute "/name" a un chemin ; rend 0 au-dela des 64 caracteres ProDOS. */
static unsigned char push_name(char* path, const char* name)
{
    unsigned char len = strlen(path);
    if (len + 1 + strlen(name) >= PATH_LEN) return 0;
    path[len] = '/';
    strcpy(path + len + 1, name);
    return 1;
}

/* GET_FILE_INFO : plus leger qu'un fopen, et gfi[4] garde le type. */
static unsigned char exists(const char* path)
{
    return file_info(path);
}

static void progress_bar(const char* name, unsigned long copied, unsigned long size)
{
    unsigned char filled = size ? (unsigned char)(copied * 20 / size) : 20, i;
    gotoxy(0, 22);
    cprintf("%u/%u %-15s [", progress_done + 1, progress_total, name);
    for (i = 0; i < 20; ++i) cputc(i < filled ? '#' : '.');
    cprintf("] %6lu/%-6lu", copied, size);
}

/* Le fichier `other_full` existe deja : la regle de la copie en cours, ou
 * la question. Rend 1 pour ecraser, 0 pour passer. */
static unsigned char may_overwrite(const char* name)
{
    char key;
    if (over_policy == OVERWRITE_ALL) return 1;
    if (over_policy == SKIP_ALL) return 0;
    clear_row(22);
    gotoxy(0, 22);
    cprintf("%s exists: Overwrite, Skip, All, None? ", name);
    for (;;) {
        key = cgetc();
        if (key == 'o' || key == 'O') return 1;
        if (key == 's' || key == 'S') return 0;
        if (key == 'a' || key == 'A') { over_policy = OVERWRITE_ALL; return 1; }
        if (key == 'n' || key == 'N' || key == KEY_ESC) { over_policy = SKIP_ALL; return 0; }
    }
}

/* Copie le fichier `full` vers `other_full`, meme type et auxtype, avec la
 * barre de progression. Rend 1 si la copie est complete, 2 si elle a ete
 * passee, 0 sur erreur. */
static unsigned char copy_file(const char* name, unsigned char type, unsigned int aux)
{
    FILE* in;
    FILE* out;
    unsigned int n;
    unsigned long size, copied = 0;
    unsigned char ok = 1;
    in = fopen(full, "rb");
    if (!in) { report_error("Open"); return 0; }
    if (exists(other_full)) {
        if (gfi[4] == 0x0F) { fclose(in); message("Skipped: a directory."); ++progress_skipped; ++progress_done; return 2; }
        if (!may_overwrite(name)) { fclose(in); ++progress_skipped; ++progress_done; return 2; }
        if (remove(other_full)) { fclose(in); report_error("Overwrite"); return 0; }
    }
    fseek(in, 0, SEEK_END);
    size = ftell(in);
    rewind(in);
    _filetype = type;
    _auxtype = aux;
    out = fopen(other_full, "wb");
    if (!out) { fclose(in); report_error("Create"); return 0; }
    clear_row(22);
    progress_bar(name, 0, size);
    while ((n = fread(copy_buf, 1, sizeof copy_buf, in)) > 0) {
        if (fwrite(copy_buf, 1, n, out) != n) { ok = 0; break; }
        copied += n;
        progress_bar(name, copied, size);
    }
    if (ferror(in)) ok = 0;
    fclose(in);
    if (fclose(out)) ok = 0;
    if (!ok) { remove(other_full); report_error("Copy"); return 0; }
    ++total_ops;
    ++progress_done;
    return 1;
}

/* Les trois parcours qui suivent sont recursifs : leurs variables locales
 * doivent vivre sur la pile, pas en statique comme le veut -Cl pour le
 * reste du programme, sinon le niveau interne ecrase la longueur de chemin
 * du niveau externe et le dossier parent n'est jamais retrouve. */
#pragma static-locals (push, off)

/* Le nombre de fichiers sous `full` (dossiers exclus), pour le compteur de
 * progression. 0xFFFF si l'arbre ne se parcourt pas. */
static unsigned int count_tree(unsigned char base)
{
    unsigned char n, i, len = strlen(full);
    unsigned int files = 0, sub;
    if (!list_dir(full, base, &n)) return 0xFFFF;
    for (i = 0; i < n; ++i) {
        if (pool[base + i].type != 0x0F) { ++files; continue; }
        if (!push_name(full, pool[base + i].name)) return 0xFFFF;
        sub = count_tree(base + n);
        full[len] = 0;
        if (sub == 0xFFFF) return sub;
        files += sub;
    }
    return files;
}

/* Copie le contenu du dossier `full` dans le dossier `other_full`, qui
 * existe deja, sous-dossiers compris ; un sous-dossier deja present est
 * complete, pas recree. */
static unsigned char copy_tree(unsigned char base)
{
    unsigned char n, i, sl = strlen(full), dl = strlen(other_full), ok = 1;
    if (!list_dir(full, base, &n)) { dir_fail(); return 0; }
    for (i = 0; i < n && ok; ++i) {
        const struct Mini* m = &pool[base + i];
        if (!push_name(full, m->name) || !push_name(other_full, m->name)) { too_long(); ok = 0; }
        else if (m->type == 0x0F) {
            if (!exists(other_full) && mkdir(other_full)) { report_error("Mkdir"); ok = 0; }
            else ok = copy_tree(base + n);
        } else ok = copy_file(m->name, m->type, m->aux) != 0;
        full[sl] = 0;
        other_full[dl] = 0;
    }
    return ok;
}

/* Supprime tout ce que contient le dossier `full`, puis le dossier. */
static unsigned char delete_tree(unsigned char base)
{
    unsigned char n, i, len = strlen(full), ok = 1;
    if (!list_dir(full, base, &n)) { dir_fail(); return 0; }
    for (i = 0; i < n && ok; ++i) {
        if (!push_name(full, pool[base + i].name)) { too_long(); ok = 0; break; }
        if (pool[base + i].type == 0x0F) ok = delete_tree(base + n);
        else if (remove(full)) { report_error("Delete"); ok = 0; }
        else ++total_ops;
        full[len] = 0;
    }
    if (ok && rmdir(full)) { report_error("Delete"); ok = 0; }
    if (ok) ++total_ops;
    return ok;
}

#pragma static-locals (pop)

/* Copie l'entree dans le dossier de l'autre panneau : un fichier, ou un
 * dossier entier. Rend 1 si tout est copie. */
static unsigned char copy_one(const struct Entry* e)
{
    struct Panel* dst = &panels[!active];
    unsigned char len;
    if (!build_full(full, &panels[active], e) || !build_full(other_full, dst, e)) { too_long(); return 0; }
    if (!is_dir(e)) return copy_file(e->name, e->type, e->aux) != 0;
    len = strlen(full);
    if (!strncmp(dst->path, full, len) && (dst->path[len] == '/' || !dst->path[len])) {
        message("Cannot copy a directory into itself.");
        return 0;
    }
    if (!exists(other_full)) {
        if (mkdir(other_full)) { report_error("Mkdir"); return 0; }
        ++total_ops;
    }
    return copy_tree(0);
}

/* Les fichiers vises par C, V et D : les marques du panneau, sinon le
 * curseur. Rend leur nombre et les depose dans `picked`. */
static unsigned char pick_targets(void)
{
    struct Panel* pan = &panels[active];
    unsigned char i, n = 0;
    if (!pan->count || !pan->path[0]) return 0;
    for (i = 0; i < pan->count; ++i) if (tagged(pan, i)) picked[n++] = i;
    if (!n) picked[n++] = pan->cursor;
    return n;
}

static unsigned char target_check(void)
{
    struct Panel* dst = &panels[!active];
    if (!panels[active].path[0]) { message("Open a directory first."); return 0; }
    if (!dst->path[0]) { message("Open a directory in the other panel."); return 0; }
    if (!strcmp(dst->path, panels[active].path)) { message("Both panels show the same directory."); return 0; }
    return 1;
}

static void copy_or_move(unsigned char move)
{
    struct Panel* pan = &panels[active];
    unsigned char n, i, done = 0;
    unsigned int sub;
    if (!target_check()) return;
    n = pick_targets();
    if (!n) return;
    pool = (struct Mini*)panels[!active].e;
    /* Le compteur "fichier x sur y" demande de connaitre y : un premier
     * parcours compte les fichiers, dossiers compris. */
    progress_total = 0;
    progress_done = 0;
    progress_skipped = 0;
    over_policy = ASK;
    for (i = 0; i < n; ++i) {
        const struct Entry* e = &pan->e[picked[i]];
        if (is_up(e)) continue;
        if (!is_dir(e)) { ++progress_total; continue; }
        if (!build_full(full, pan, e)) { too_long(); refresh_both(); return; }   /* la reserve a recouvert l'autre panneau */
        sub = count_tree(0);
        if (sub == 0xFFFF) { dir_fail(); refresh_both(); return; }
        progress_total += sub;
    }
    for (i = 0; i < n; ++i) {
        const struct Entry* e = &pan->e[picked[i]];
        unsigned int skipped_before = progress_skipped;
        if (is_up(e)) { ++done; continue; }
        if (!copy_one(e)) break;
        /* Deplacer, c'est copier puis effacer : un fichier passe (Skip)
         * n'a pas ete copie, il reste ; un dossier dont un fichier a ete
         * passe reste aussi, entier, plutot que d'en perdre une partie. */
        if (move && progress_skipped == skipped_before) {
            build_full(full, pan, e);
            if (is_dir(e) ? !delete_tree(0) : remove(full) != 0) { if (!is_dir(e)) report_error("Delete source"); break; }
        }
        ++done;
    }
    refresh_both();
    if (done == n) {
        clear_row(22);
        gotoxy(0, 22);
        cprintf("%u file%s %s", progress_done - progress_skipped, progress_done - progress_skipped == 1 ? "" : "s", move ? "moved" : "copied");
        if (progress_skipped) cprintf(", %u skipped", progress_skipped);
        cputc('.');
    }
}

static void delete_targets(void)
{
    struct Panel* pan = &panels[active];
    unsigned char n, i, done = 0;
    const struct Entry* e;
    n = pick_targets();
    if (!n) { message("Nothing to delete here."); return; }
    pool = (struct Mini*)panels[!active].e;
    e = &pan->e[picked[0]];
    if (n == 1 && is_up(e)) { message("Nothing to delete here."); return; }
    if (n == 1) sprintf(question, "Delete %s%s?", e->name, is_dir(e) ? " and everything inside" : "");
    else sprintf(question, "Delete %u tagged files?", n);
    if (!confirm(question)) return;
    for (i = 0; i < n; ++i) {
        e = &pan->e[picked[i]];
        if (is_up(e)) continue;
        if (!build_full(full, pan, e)) { too_long(); break; }
        if (is_dir(e)) { if (!delete_tree(0)) break; }
        else if (remove(full)) { report_error("Delete"); break; }
        else ++total_ops;
        ++done;
    }
    refresh_both();
    if (done == n) {
        clear_row(22);
        gotoxy(0, 22);
        cprintf("%u item%s deleted.", done, done > 1 ? "s" : "");
    }
}

static void rename_selected(const struct Entry* e)
{
    if (is_up(e) || !panels[active].path[0]) { message("Select something to rename."); return; }
    if (!prompt("New name", e->name, 0)) return;
    if (!build_full(full, &panels[active], e)) { too_long(); return; }
    if (strlen(panels[active].path) + 1 + strlen(input) >= PATH_LEN) { too_long(); return; }
    sprintf(other_full, "%s/%s", panels[active].path, input);
    if (rename(full, other_full)) { report_error("Rename"); return; }
    ++total_ops;
    read_panel(active);
    select_name(&panels[active], input);
    show_active();
}

static void make_directory(void)
{
    struct Panel* pan = &panels[active];
    if (!pan->path[0]) { message("Open a volume first."); return; }
    if (!prompt("New directory", NULL, 0)) return;
    if (strlen(pan->path) + 1 + strlen(input) >= PATH_LEN) { too_long(); return; }
    sprintf(full, "%s/%s", pan->path, input);
    if (mkdir(full)) { report_error("Mkdir"); return; }
    ++total_ops;
    refresh_both();
    select_name(pan, input);
    show_active();
}

/* A : type et auxtype ; L : verrou. Les deux passent par GET_FILE_INFO puis
 * SET_FILE_INFO sur le meme bloc, et relisent le panneau. */
static void change_attributes(const struct Entry* e, unsigned char lock)
{
    unsigned char type;
    unsigned int aux;
    if (is_up(e) || !panels[active].path[0]) { message("Select a file or directory."); return; }
    if (!build_full(full, &panels[active], e)) { too_long(); return; }
    if (!lock) {
        if (is_dir(e)) { message("A directory keeps its type."); return; }
        sprintf(input, "%02X", e->type);
        if (!prompt("File type", input, 2)) return;
        type = (unsigned char)hex_value();
        sprintf(input, "%04X", e->aux);
        if (!prompt("Aux type", input, 4)) return;
        aux = hex_value();
    }
    if (!file_info(full)) { report_error("Get info"); return; }
    if (lock) gfi[3] = is_locked(e) ? 0xC3 : 0x01;   /* tout, ou lecture seule */
    else { gfi[4] = type; gfi[5] = (unsigned char)(aux & 0xFF); gfi[6] = (unsigned char)(aux >> 8); }
    if (!set_info()) { report_error("Set info"); return; }
    ++total_ops;
    strcpy(input, e->name);
    read_panel(active);
    select_name(&panels[active], input);
    show_active();
}

/* Charge le fichier `full` a `addr` et y saute, sans retour, par le talon
 * de chain.s : quelle que soit sa taille, il ecrase TOTAL sans dommage.
 * La musique est coupee, les preferences ecrites. */
static void launch_file(unsigned int addr)
{
    if (!exists(full)) { report_error("Run"); return; }
    music_stop();
    save_config();
    clrscr();
    chain_addr = addr;
    chain_load(full);
}

/* X : un SYS est lu en $2000, la ou ProDOS l'aurait mis, un BIN a son
 * auxtype. */
static void run_selected(const struct Entry* e)
{
    unsigned int addr = e->type == 0xFF ? 0x2000 : e->aux;
    if (is_dir(e) || !panels[active].path[0]) { message("Select a SYS or BIN program."); return; }
    if (e->type != 0xFF && e->type != 0x06) { message("Only SYS and BIN run."); return; }
    if (addr < 0x0800 || (unsigned long)addr + e->size > 0xBB00) { message("A BIN must load between $0800 and $BAFF."); return; }
    if (!build_full(full, &panels[active], e)) { too_long(); return; }
    sprintf(question, "Run %s? TOTAL will not resume.", e->name);
    if (!confirm(question)) return;
    chdir(panels[active].path);
    launch_file(addr);
}

/* F : le formateur, TOTAL/FORMAT.SYS a cote de TOTAL.CODE (Bitsy Bye le
 * propose aussi), lance depuis la racine du volume ; il relance TOTAL en
 * sortant. */
static void format_disk(void)
{
    if (!confirm("Open the disk formatter?")) return;
    strcpy(full, cfg_path);
    { char* s = strchr(full + 1, '/'); if (s) *s = 0; }   /* "/VOL/TOTAL/TOTAL.CFG" -> "/VOL" */
    chdir(full);
    strcpy(full, "TOTAL/FORMAT.SYS");
    launch_file(0x2000);
}

static void open_selected(void)
{
    struct Panel* pan = &panels[active];
    const struct Entry* e;
    if (!pan->count) return;
    e = &pan->e[pan->cursor];
    if (is_dir(e)) { enter_dir(pan, e); show_active(); return; }
    if (!build_full(full, pan, e)) { too_long(); return; }
    if (looks_like_image(e)) view_image();
    else if (looks_like_music(e)) play_music(e);
    else if (e->type == 0x04) view_text(full);
    else if (e->type == 0xFF) run_selected(e);
    else view_hex(full, e->size);
}

/* ---------------------------------------------------------------------- */
/* Marques, tri, recherche                                                */
/* ---------------------------------------------------------------------- */

static void toggle_tag(void)
{
    struct Panel* pan = &panels[active];
    const struct Entry* e;
    if (!pan->count || !pan->path[0]) return;
    e = &pan->e[pan->cursor];
    if (!is_dir(e)) set_tag(pan, pan->cursor, !tagged(pan, pan->cursor));
    if (pan->cursor + 1 < pan->count) {
        ++pan->cursor;
        if (pan->cursor >= pan->top + ROWS) { pan->top = pan->cursor - ROWS + 1; draw_panel(active); }
        else { draw_entry(active, pan->cursor - 1); draw_entry(active, pan->cursor); }
    } else draw_entry(active, pan->cursor);
    draw_info();
}

static void invert_tags(void)
{
    struct Panel* pan = &panels[active];
    unsigned char i;
    if (!pan->path[0]) return;
    for (i = 0; i < pan->count; ++i)
        if (!is_dir(&pan->e[i])) set_tag(pan, i, !tagged(pan, i));
    show_active();
}

/* M : marque les fichiers absents de l'autre panneau ou de taille
 * differente, la base d'une synchronisation par C. */
static void mark_differences(void)
{
    struct Panel* pan = &panels[active];
    struct Panel* other = &panels[!active];
    unsigned char i, j, n = 0;
    if (!target_check()) return;
    for (i = 0; i < pan->count; ++i) {
        const struct Entry* e = &pan->e[i];
        unsigned char differs = 1;
        if (is_dir(e)) continue;
        for (j = 0; j < other->count; ++j)
            if (!strcmp(other->e[j].name, e->name)) { differs = other->e[j].size != e->size; break; }
        set_tag(pan, i, differs);
        n += differs;
    }
    show_active();
    clear_row(22);
    gotoxy(0, 22);
    cprintf("%u file%s missing from the other panel or of a different size.", n, n == 1 ? "" : "s");
}

static void resort(void)
{
    unsigned char p;
    char keep[NAME_LEN];
    sort_mode = (sort_mode + 1) % SORT_MODES;
    for (p = 0; p < 2; ++p) {
        strcpy(keep, panels[p].count ? panels[p].e[panels[p].cursor].name : "");
        read_panel(p);
        select_name(&panels[p], keep);
        draw_panel(p);
    }
    draw_info();
}

/* ' puis une touche : l'entree suivante dont le nom commence par elle. */
static void find_letter(void)
{
    struct Panel* pan = &panels[active];
    unsigned char i, j, previous = pan->cursor, old_top = pan->top;
    char key;
    message("Jump to name starting with: ");
    key = cgetc();
    clear_row(22);
    if (key >= 'a' && key <= 'z') key -= 32;
    if (!pan->count) return;
    for (i = 1; i <= pan->count; ++i) {
        j = (pan->cursor + i) % pan->count;
        if (pan->e[j].name[pan->path[0] ? 0 : 1] == key) {
            set_cursor(pan, j);
            if (pan->top != old_top) draw_panel(active);
            else { draw_entry(active, previous); draw_entry(active, pan->cursor); }
            draw_info();
            return;
        }
    }
    message("No such name in this panel.");
}

/* ---------------------------------------------------------------------- */
/* Boucle principale                                                      */
/* ---------------------------------------------------------------------- */

/* Deplace le curseur ; au-dela des bords d'un dossier lu par fenetres,
 * charge la fenetre suivante ou precedente. */
static void move_cursor(int delta)
{
    struct Panel* pan = &panels[active];
    unsigned char previous = pan->cursor, old_top = pan->top;
    int target;
    if (!pan->count) return;
    target = (int)pan->cursor + delta;
    if (target >= pan->count && pan->more) {
        pan->first += WINDOW;
        pan->cursor = pan->top = 0;
        read_panel(active);
        show_active();
        return;
    }
    if (target < 0 && pan->first) {
        pan->first -= WINDOW;
        pan->cursor = pan->top = 0;
        read_panel(active);
        set_cursor(pan, pan->count - 1);
        show_active();
        return;
    }
    if (target < 0) target = 0;
    if (target >= pan->count) target = pan->count - 1;
    set_cursor(pan, (unsigned char)target);
    if (pan->top != old_top) draw_panel(active);
    else { draw_entry(active, previous); draw_entry(active, pan->cursor); }
    draw_info();
}

int main(void)
{
    char key;
    struct Panel* pan;
    videomode(VIDEOMODE_80COL);
    memset(_LOWBSS_RUN__, 0, (size_t)_LOWBSS_SIZE__);
    total_slot = 0xFF;
    panels[0].e = ENTRIES;
    panels[1].e = ENTRIES + MAX_ENTRIES;
    if (!getcwd(panels[0].path, PATH_LEN)) strcpy(panels[0].path, "/SCOSWAMP");
    strcpy(panels[1].path, panels[0].path);
    if (strlen(panels[1].path) + 5 < PATH_LEN) strcat(panels[1].path, "/DHGR");
    strcpy(cfg_path, panels[0].path);
    if (strlen(cfg_path) + 16 < PATH_LEN) strcat(cfg_path, "/TOTAL/TOTAL.CFG");
    load_config();
    read_panel(0);
    read_panel(1);
    draw_all();
    for (;;) {
        pan = &panels[active];
        key = cgetc();
        if (key != KEY_ESC && key != 'q' && key != 'Q') clear_row(22);
        switch (key) {
        case KEY_UP: move_cursor(-1); break;
        case KEY_DOWN: move_cursor(1); break;
        case '<': case '-': move_cursor(-ROWS); break;
        case '>': case '+': move_cursor(ROWS); break;
        case '[': set_cursor(pan, 0); show_active(); break;
        case ']': if (pan->count) set_cursor(pan, pan->count - 1); show_active(); break;
        case ' ': toggle_tag(); break;
        case '*': invert_tags(); break;
        case '\'': find_letter(); break;
        case KEY_TAB:
            active = !active;
            draw_panel(0);
            draw_panel(1);
            draw_status();
            draw_info();
            break;
        case KEY_RETURN: case KEY_RIGHT: open_selected(); break;
        case KEY_LEFT: case KEY_ESC:
            if (pan->path[0]) { go_up(pan); show_active(); }
            break;
        case '/':
            pan->path[0] = 0;
            open_path(pan);
            show_active();
            break;
        case '=':
            strcpy(panels[!active].path, pan->path);
            open_path(&panels[!active]);
            draw_panel(!active);
            break;
        case 'c': case 'C': copy_or_move(0); break;
        case 'v': case 'V': copy_or_move(1); break;
        case 'r': case 'R': if (pan->count) rename_selected(&pan->e[pan->cursor]); break;
        case 'd': case 'D': delete_targets(); break;
        case 'k': case 'K': make_directory(); break;
        case 's': case 'S': resort(); break;
        case 'm': case 'M': mark_differences(); break;
        case 'a': case 'A': if (pan->count) change_attributes(&pan->e[pan->cursor], 0); break;
        case 'l': case 'L': if (pan->count) change_attributes(&pan->e[pan->cursor], 1); break;
        case 't': case 'T':
            if (pan->count && !is_dir(&pan->e[pan->cursor]) && build_full(full, pan, &pan->e[pan->cursor]))
                view_text(full);
            break;
        case 'h': case 'H':
            if (pan->count && !is_dir(&pan->e[pan->cursor]) && build_full(full, pan, &pan->e[pan->cursor]))
                view_hex(full, pan->e[pan->cursor].size);
            break;
        case 'x': case 'X': if (pan->count) run_selected(&pan->e[pan->cursor]); break;
        case 'e': case 'E': edit_selected(); break;
        case 'p': case 'P': toggle_music(); break;
        case 'f': case 'F': format_disk(); break;
        case 'i': case 'I': if (pan->count && !is_dir(&pan->e[pan->cursor]) && pan->path[0]) view_image(); break;
        case '?': view_help(); break;
        case 'q': case 'Q':
            if (confirm("Quit to ProDOS?")) {
                music_stop();
                save_config();
                /* Le prefixe ProDOS suit le panneau actif : Bitsy Bye
                 * reprend dans le dossier ou l'on etait. */
                if (pan->path[0]) chdir(pan->path);
                switch_to_text();
                clrscr();
                return 0;   /* crt0 : QUIT ProDOS, Bitsy Bye reprend. */
            }
            break;
        }
    }
}
