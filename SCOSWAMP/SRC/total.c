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
#include <dirent.h>
#include <device.h>
#include <errno.h>
#include <apple2.h>
#include "hgr_rle.h"
#include "memory_swap.h"

/* cc65 les lit a la creation d'un fichier (fopen "wb") : la copie garde le
 * type et l'auxtype de l'original, une image reste une image. */
extern unsigned char _filetype;
extern unsigned int _auxtype;

unsigned char __fastcall__ mli_gfi(void* params);   /* total_mli.s */
unsigned char __fastcall__ mli_sfi(void* params);

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
    unsigned char tags[MAX_ENTRIES / 8];
};

enum { SORT_NAME, SORT_SIZE, SORT_TYPE, SORT_MODES };
enum { ASK, OVERWRITE_ALL, SKIP_ALL };

#define ENTRIES ((struct Entry*)0x2000)   /* la page HGR MAIN, voir l'en-tete */
static struct Panel panels[2];
static unsigned char active, sort_mode, over_policy;
static unsigned int progress_done, progress_total, progress_skipped;
/* Diagnostics lisibles par le banc de test POM2 (voir total.lbl). */
unsigned int total_draws, total_ops, total_errors;
unsigned char total_view;       /* 0 panneaux, 1 image, 2 texte, 3 hexa, 4 aide */

/* Les tampons de travail vivent en RAM basse ($1000-$1FFF, segment LOWBSS
 * de scoswamp.cfg, a cote du tampon RLE) : aucun n'a besoin d'etre mis a
 * zero, chacun est rempli avant d'etre lu -- crt0 y a d'ailleurs lu l'image
 * de la carte langage avant main. */
#pragma bss-name (push, "LOWBSS")
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
/* Les parcours recursifs (copie et suppression d'un dossier) empilent ici
 * les entrees de chaque niveau : un niveau occupe pool[base..base+n[, le
 * niveau suivant commence a base+n. Un arbre dont un chemin cumule plus de
 * POOL_SIZE entrees est refuse avant toute ecriture. */
#define POOL_SIZE 120
struct Mini { char name[16]; unsigned char type; unsigned int aux; };
static struct Mini pool[POOL_SIZE];
#pragma bss-name (pop)

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

/* Une barre en inverse sur toute la largeur. conio ecrit 79 colonnes : la
 * 80e passerait a la ligne et ferait defiler l'ecran, elle est posee
 * directement dans la page texte (ligne 23, colonne impaire : MAIN,
 * $7D0 + 39). */
static void bar(const char* text)
{
    revers(1);
    gotoxy(0, 23);
    cprintf("%-79.79s", text);
    revers(0);
    *(unsigned char*)0x07F7 = 0x20;
}

static void help_bar(void)
{
    bar("TAB panel RET open SPC tag ' find C copy V move R ren D del K mkdir S sort ? help");
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
    else if (!pan->path[0]) cprintf("%-15s S%u,D%u %5u/%5u free ", e->name, e->mdate & 7, (e->mdate >> 3) + 1, e->aux, e->blocks);
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
    cprintf("%-38.38s", pan->path[0] ? pan->path : "[Volumes]");
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
    cputsxy(2, 20, " TOTAL ");
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
    else cprintf("%s  type $%02X  aux $%04X  %u blocks  %lu bytes  %02u/%02u/%02u%s",
                 e->name, e->type, e->aux, e->blocks, e->size,
                 e->mdate & 31, (e->mdate >> 5) & 15, (e->mdate >> 9) % 100,
                 is_locked(e) ? "  locked" : "");
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
    DIR* dir;
    struct dirent* d;
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
        dir = opendir(pan->path);
        if (!dir) {
            ok = 0;
            pan->path[0] = 0;
            pan->first = 0;
            read_volumes(pan);
        } else {
            if (!pan->first) add_entry(pan, "..", 0x0F);
            while ((d = readdir(dir)) != NULL) {
                if (skip) { --skip; continue; }
                if (pan->count >= MAX_ENTRIES) { pan->more = 1; break; }
                e = add_entry(pan, d->d_name, d->d_type);
                e->access = d->d_access;
                e->aux = d->d_auxtype;
                e->blocks = d->d_blocks;
                e->size = d->d_size;
                e->mdate = *(unsigned int*)&d->d_mdate;
            }
            closedir(dir);
            if (!pan->first && !pan->more && pan->count > 2)
                qsort(pan->e + 1, pan->count - 1, sizeof(struct Entry), compare);
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
    strcpy(last, slash + 1);
    if (slash == pan->path) pan->path[0] = 0;   /* "/VOL" -> volumes */
    else *slash = 0;
    open_path(pan);
    select_name(pan, last);
}

static void enter_dir(struct Panel* pan, const struct Entry* e)
{
    if (is_up(e)) { go_up(pan); return; }
    if (!build_full(full, pan, e)) { message("Path too long for ProDOS."); return; }
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

static unsigned char looks_like_image(const struct Entry* e)
{
    unsigned char n = strlen(e->name);
    return e->type == 0x06 && n > 4 && !strcmp(e->name + n - 4, ".RLE");
}

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
            if (col == 80) { ++row; col = 0; if (row >= TEXT_ROWS) { --row; break; } gotoxy(0, row); }
            cputc((char)c);
            ++col;
        }
        if (!done && page + 1 < TEXT_PAGES && known == page + 1) {
            starts[page + 1] = vbase + vpos;
            known = page + 2;
        }
        sprintf(question, "%-40.40s page %u%s  SPACE next  B prev  ESC back", path, page + 1, done ? " (end)" : "");
        bar(question);
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
        sprintf(question, "%-30.30s %lu bytes  page %u/%u  SPACE next  B prev  ESC", path, size, page + 1, pages);
        bar(question);
        key = cgetc();
        if (key == KEY_ESC || key == 'q' || key == 'Q') break;
        if ((key == ' ' || key == KEY_RETURN || key == KEY_RIGHT || key == KEY_DOWN) && page + 1 < pages) ++page;
        if ((key == 'b' || key == 'B' || key == KEY_LEFT || key == KEY_UP) && page) --page;
    }
    fclose(vf);
    total_view = 0;
    draw_all();
}

static void view_help(void)
{
    total_view = 4;
    clrscr();
    cputsxy(30, 0, "T O T A L  -  keys");
    cputsxy(1, 2,  "Up / Down      move          < > or - +  page          [ ]  first / last");
    cputsxy(1, 3,  "TAB            other panel   =           same directory in the other panel");
    cputsxy(1, 4,  "RETURN / Right open : directory, .RLE image, TXT text, SYS program, else hex");
    cputsxy(1, 5,  "ESC / Left     parent directory          /  list of volumes");
    cputsxy(1, 6,  "SPACE          tag / untag the file (* after the name)     *  invert tags");
    cputsxy(1, 7,  "' then a key   jump to the next name starting with that letter or digit");
    cputsxy(1, 9,  "C  copy to the other panel      V  move (copy, then delete the original)");
    cputsxy(1, 10, "R  rename                       D  delete (a directory with its contents)");
    cputsxy(1, 11, "K  make a directory             S  sort by name, size or type");
    cputsxy(1, 12, "T  view as text                 H  view as hexadecimal");
    cputsxy(1, 13, "X  run a SYS or BIN program     Q  quit to ProDOS (Bitsy Bye)");
    cputsxy(1, 14, "A  change type and auxtype      L  lock / unlock (L after the name)");
    cputsxy(1, 15, "M  mark the files missing from the other panel or of a different size");
    cputsxy(1, 17, "C, V and D act on every tagged file of the panel, else on the cursor.");
    cputsxy(1, 18, "Directories are copied whole; copies keep type and auxtype. When a file");
    cputsxy(1, 19, "exists, TOTAL asks: Overwrite, Skip, All, None. Large directories are shown");
    cputsxy(1, 20, "by windows in disk order. In an image: Left / Right show the previous / next.");
    cputsxy(1, 21, "Both directories, the sort and the panel are saved in TOTAL/TOTAL.CFG.");
    bar("Press any key to return to the panels");
    cgetc();
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
        if (p == 2 && line[0] == 'S' && line[2] == 'A') {
            sort_mode = (line[1] - '0') % SORT_MODES;
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

/* L'image du curseur, plein ecran. Gauche / Droite passent a l'image
 * precedente / suivante du meme dossier sans revenir aux panneaux : le
 * dossier DHGR se feuillette comme un album. Toute autre touche revient. */
static void view_image(void)
{
    struct Panel* pan = &panels[active];
    unsigned char index = pan->cursor, next, bad = 0;
    char key;
    /* L'image recouvre les tables d'entrees : les marques sont mises de
     * cote, les panneaux relus au retour (et avant chaque image suivante). */
    memcpy(picked, panels[0].tags, sizeof panels[0].tags);
    memcpy(picked + sizeof panels[0].tags, panels[1].tags, sizeof panels[1].tags);
    for (;;) {
        if (!build_full(full, pan, &pan->e[index])) { message("Path too long for ProDOS."); break; }
        total_view = 1;
        if (!hgr_rle_load(full)) { bad = 1; break; }
        switch_to_hgr();
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
    if (bad) message("Not a DHGR image (DHRR stream expected).");
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
    DIR* dir = opendir(path);
    struct dirent* d;
    unsigned char n = 0;
    if (!dir) return 0;
    while ((d = readdir(dir)) != NULL) {
        if (base + n >= POOL_SIZE) { closedir(dir); return 0; }
        strncpy(pool[base + n].name, d->d_name, 15);
        pool[base + n].name[15] = 0;
        pool[base + n].type = d->d_type;
        pool[base + n].aux = d->d_auxtype;
        ++n;
    }
    closedir(dir);
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

static unsigned char exists(const char* path)
{
    FILE* f = fopen(path, "rb");
    if (!f) return 0;
    fclose(f);
    return 1;
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
    if (exists(other_full)) {
        if (!may_overwrite(name)) { ++progress_skipped; ++progress_done; return 2; }
        if (remove(other_full)) { report_error("Overwrite"); return 0; }
    }
    in = fopen(full, "rb");
    if (!in) { report_error("Open"); return 0; }
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
    if (!list_dir(full, base, &n)) { message("Directory unreadable or too many files at once."); return 0; }
    for (i = 0; i < n && ok; ++i) {
        const struct Mini* m = &pool[base + i];
        if (!push_name(full, m->name) || !push_name(other_full, m->name)) { message("Path too long for ProDOS."); ok = 0; }
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
    if (!list_dir(full, base, &n)) { message("Directory unreadable or too many files at once."); return 0; }
    for (i = 0; i < n && ok; ++i) {
        if (!push_name(full, pool[base + i].name)) { message("Path too long for ProDOS."); ok = 0; break; }
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
    if (!build_full(full, &panels[active], e) || !build_full(other_full, dst, e)) { message("Path too long for ProDOS."); return 0; }
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
    if (!dst->path[0]) { message("Open a directory in the other panel first."); return 0; }
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
        if (!build_full(full, pan, e)) { message("Path too long for ProDOS."); return; }
        sub = count_tree(0);
        if (sub == 0xFFFF) { message("Directory unreadable or too many files at once."); return; }
        progress_total += sub;
    }
    for (i = 0; i < n; ++i) {
        const struct Entry* e = &pan->e[picked[i]];
        if (is_up(e)) { ++done; continue; }
        if (!copy_one(e)) break;
        if (move) {
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
    e = &pan->e[picked[0]];
    if (n == 1 && is_up(e)) { message("Nothing to delete here."); return; }
    if (n == 1) sprintf(question, "Delete %s%s?", e->name, is_dir(e) ? " and everything inside" : "");
    else sprintf(question, "Delete %u tagged files?", n);
    if (!confirm(question)) return;
    for (i = 0; i < n; ++i) {
        e = &pan->e[picked[i]];
        if (is_up(e)) continue;
        if (!build_full(full, pan, e)) { message("Path too long for ProDOS."); break; }
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
    if (is_up(e) || !panels[active].path[0]) { message("Select a file or directory to rename."); return; }
    if (!prompt("New name", e->name, 0)) return;
    if (!build_full(full, &panels[active], e)) { message("Path too long for ProDOS."); return; }
    if (strlen(panels[active].path) + 1 + strlen(input) >= PATH_LEN) { message("Path too long for ProDOS."); return; }
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
    if (strlen(pan->path) + 1 + strlen(input) >= PATH_LEN) { message("Path too long for ProDOS."); return; }
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
    if (!build_full(full, &panels[active], e)) { message("Path too long for ProDOS."); return; }
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

static void run_selected(const struct Entry* e)
{
    if (is_dir(e) || !panels[active].path[0]) { message("Select a SYS or BIN program."); return; }
    if (e->type != 0xFF && e->type != 0x06) { message("Only SYS and BIN files can be run."); return; }
    if (!build_full(full, &panels[active], e)) { message("Path too long for ProDOS."); return; }
    sprintf(question, "Run %s? TOTAL will not resume.", e->name);
    if (!confirm(question)) return;
    save_config();
    clrscr();
    /* Le programme lance attend la ROM, pas la carte langage de TOTAL. */
    __asm__("bit $C082");
    exec(full, NULL);
    /* Ici seulement si le lancement a echoue. */
    __asm__("bit $C080");
    draw_all();
    report_error("Run");
}

static void open_selected(void)
{
    struct Panel* pan = &panels[active];
    const struct Entry* e;
    if (!pan->count) return;
    e = &pan->e[pan->cursor];
    if (is_dir(e)) { enter_dir(pan, e); show_active(); return; }
    if (!build_full(full, pan, e)) { message("Path too long for ProDOS."); return; }
    if (looks_like_image(e)) view_image();
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
        case '?': view_help(); break;
        case 'q': case 'Q':
            if (confirm("Quit to ProDOS?")) {
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
