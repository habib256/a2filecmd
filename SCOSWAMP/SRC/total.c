/* TOTAL : un gestionnaire de fichiers ProDOS a deux panneaux, dans
 * l'esprit de Total Commander, pour l'Apple IIe 128 Ko.
 *
 * Programme SYS distinct du jeu, lance depuis Bitsy Bye comme DIAPO, avec
 * le meme lanceur (loader.c), le meme decodeur DHGR (hgr_loader.s) et les
 * memes bascules video (memory_swap.c). Il ne modifie jamais un fichier de
 * lui-meme : seules les commandes explicites (copie, deplacement, renommage,
 * suppression, creation de dossier) ecrivent sur le disque, apres
 * confirmation quand elles detruisent quelque chose.
 *
 * Ouvrir (Entree) choisit d'apres le type : un dossier s'ouvre, une image
 * DHGR (.RLE, flux DHRR) s'affiche plein ecran, un TXT se lit page par page,
 * un SYS se lance apres confirmation, le reste se voit en hexadecimal.
 * Espace marque plusieurs fichiers : copie, deplacement et suppression
 * portent alors sur tous les fichiers marques.
 *
 * Memoire : code a $4000, images en $2000-$3FFF MAIN et AUX, tampon RLE en
 * $1000-$107F (LOWBSS). Deux fichiers ouverts au plus (copie) : tampons
 * ProDOS $0800 et $0C00, TOTAL n'utilise pas MAPBSS.
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

#define MAX_ENTRIES 96
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
    unsigned int aux;
    unsigned int blocks;
    unsigned long size;
    unsigned int mdate;         /* jour 5 bits, mois 4 bits, annee 7 bits */
};

struct Panel {
    char path[PATH_LEN];        /* "" : la liste des volumes en ligne */
    unsigned char count, cursor, top, truncated;
    unsigned int free_blocks, total_blocks;
    struct Entry* e;
    unsigned char tags[MAX_ENTRIES / 8];
};

enum { SORT_NAME, SORT_SIZE, SORT_TYPE, SORT_MODES };

static struct Entry entries[2][MAX_ENTRIES];
static struct Panel panels[2];
static unsigned char active, sort_mode;
/* Les tampons de travail vivent en RAM basse ($1000-$1FFF, segment LOWBSS
 * de scoswamp.cfg, a cote du tampon RLE) : aucun n'a besoin d'etre mis a
 * zero, chacun est rempli avant d'etre lu. La fenetre $4000-$BF00 garde
 * ainsi ses 32 Ko pour le code et les deux tables d'entrees. */
#pragma bss-name (push, "LOWBSS")
static char full[PATH_LEN + NAME_LEN];
static char other_full[PATH_LEN + NAME_LEN];
static char input[NAME_LEN];
static char question[48];
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
static unsigned int progress_done, progress_total;
/* Diagnostics lisibles par le banc de test POM2 (voir total.lbl). */
unsigned int total_draws, total_ops, total_errors;
unsigned char total_view;       /* 0 panneaux, 1 image, 2 texte, 3 hexa, 4 aide */

/* ---------------------------------------------------------------------- */
/* Volume : espace libre par MLI GET_FILE_INFO sur le repertoire racine    */
/* ---------------------------------------------------------------------- */

/* Sur un repertoire de volume, aux_type = blocs du volume et blocks_used
 * = blocs occupes. Bloc de parametres a la disposition du MLI ($C4). */
unsigned char __fastcall__ mli_gfi(void* params);   /* total_mli.s */

static void volume_space(struct Panel* pan)
{
    const char* slash;
    unsigned char len;
    pan->free_blocks = pan->total_blocks = 0;
    if (!pan->path[0]) return;
    slash = strchr(pan->path + 1, '/');
    len = slash ? (unsigned char)(slash - pan->path) : (unsigned char)strlen(pan->path);
    gfi_path[0] = len;
    memcpy(gfi_path + 1, pan->path, len);
    gfi[0] = 0x0A;
    gfi[1] = (unsigned char)((unsigned)gfi_path & 0xFF);
    gfi[2] = (unsigned char)((unsigned)gfi_path >> 8);
    if (mli_gfi(gfi)) return;
    pan->total_blocks = gfi[5] | ((unsigned int)gfi[6] << 8);
    pan->free_blocks = pan->total_blocks - (gfi[8] | ((unsigned int)gfi[9] << 8));
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

/* La barre du bas, en inverse sur toute la largeur. conio ecrit 79
 * colonnes : la 80e passerait a la ligne et ferait defiler l'ecran, elle
 * est posee directement dans la page texte (ligne 23, colonne impaire :
 * MAIN, $7D0 + 39). */
static void help_bar(void)
{
    revers(1);
    gotoxy(0, 23);
    cprintf("%-79.79s", "TAB panel RET open SPC tag C copy V move R ren D del K mkdir S sort ? help Q");
    revers(0);
    *(unsigned char*)0x07F7 = 0x20;
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

/* Une ligne d'entree, 38 caracteres, en inverse quand le curseur y est ;
 * une etoile apres le nom marque un fichier selectionne par Espace. */
static void draw_entry(unsigned char p, unsigned char index)
{
    struct Panel* pan = &panels[p];
    unsigned char x = p ? 40 : 0;
    unsigned char row = 2 + (index - pan->top);
    const struct Entry* e = &pan->e[index];
    char mark;
    if (index >= pan->count) { cclearxy(x, row, 38); return; }
    mark = tagged(pan, index) ? '*' : ' ';
    if (p == active && index == pan->cursor) revers(1);
    gotoxy(x, row);
    /* Trois formats de 38 caracteres exactement : une ligne plus courte
     * laisserait a l'ecran la fin de la ligne precedente. */
    if (is_up(e)) cprintf("%-15s  <UP>                 ", e->name);
    else if (is_dir(e)) cprintf("%-15s  <DIR>          %5u ", e->name, e->blocks);
    else cprintf("%-15s%c %s $%04X %8lu   ", e->name, mark, type_name(e->type), e->aux, e->size);
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
    cprintf("%-37s%c", headers[sort_mode], pan->truncated ? '+' : ' ');
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
    else if (!pan->path[0]) cprintf("Volume %s", e->name);
    else if (is_dir(e)) cprintf("%s  directory  %u blocks", e->name, e->blocks);
    else cprintf("%s  type $%02X  aux $%04X  %u blocks  %lu bytes  %02u/%02u/%02u",
                 e->name, e->type, e->aux, e->blocks, e->size,
                 e->mdate & 31, (e->mdate >> 5) & 15, (e->mdate >> 9) % 100);
    n = tag_count(pan);
    if (n) { gotoxy(64, 21); cprintf("%u tagged", n); }
}

static void draw_all(void)
{
    draw_frame();
    draw_panel(0);
    draw_panel(1);
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

static void add_entry(struct Panel* pan, const char* name, unsigned char type,
                      unsigned int aux, unsigned int blocks, unsigned long size,
                      unsigned int mdate)
{
    struct Entry* e;
    if (pan->count >= MAX_ENTRIES) { pan->truncated = 1; return; }
    e = &pan->e[pan->count++];
    strncpy(e->name, name, NAME_LEN - 1);
    e->name[NAME_LEN - 1] = 0;
    e->type = type;
    e->aux = aux;
    e->blocks = blocks;
    e->size = size;
    e->mdate = mdate;
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
    while (dev != INVALID_DEVICE) {
        if (getdevicedir(dev, name, sizeof name)) add_entry(pan, name, 0x0F, 0, 0, 0, 0);
        dev = getnextdevice(dev);
    }
    DEVNUM = saved;
}

/* Remplit le panneau et oublie ses marques. Rend 0 si le dossier ne se lit
 * pas : le panneau retombe alors sur la liste des volumes, jamais sur un
 * ecran vide. */
static unsigned char read_panel(unsigned char p)
{
    struct Panel* pan = &panels[p];
    DIR* dir;
    struct dirent* d;
    unsigned char ok = 1;
    pan->count = 0;
    pan->truncated = 0;
    memset(pan->tags, 0, sizeof pan->tags);
    if (!pan->path[0]) {
        read_volumes(pan);
    } else {
        dir = opendir(pan->path);
        if (!dir) {
            ok = 0;
            pan->path[0] = 0;
            read_volumes(pan);
        } else {
            add_entry(pan, "..", 0x0F, 0, 0, 0, 0);
            while ((d = readdir(dir)) != NULL)
                add_entry(pan, d->d_name, d->d_type, d->d_auxtype, d->d_blocks, d->d_size,
                          *(unsigned int*)&d->d_mdate);
            closedir(dir);
            if (pan->count > 2) qsort(pan->e + 1, pan->count - 1, sizeof(struct Entry), compare);
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

static void go_up(struct Panel* pan)
{
    char last[NAME_LEN];
    char* slash = strrchr(pan->path, '/');
    if (!slash) return;
    strcpy(last, slash + 1);
    if (slash == pan->path) pan->path[0] = 0;   /* "/VOL" -> volumes */
    else *slash = 0;
    read_panel(pan - panels);
    select_name(pan, last);
}

static void enter_dir(struct Panel* pan, const struct Entry* e)
{
    if (is_up(e)) { go_up(pan); return; }
    if (!build_full(full, pan, e)) { message("Path too long for ProDOS."); return; }
    strcpy(pan->path, full);
    pan->cursor = 0;
    pan->top = 0;
    if (!read_panel(pan - panels)) message("Cannot read this directory.");
}

static void show_active(void)
{
    draw_panel(active);
    draw_status();
    draw_info();
}

/* ---------------------------------------------------------------------- */
/* Saisie                                                                 */
/* ---------------------------------------------------------------------- */

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

/* Un nom ProDOS : lettre, puis lettres, chiffres ou points, 15 au plus.
 * Rend 0 si l'utilisateur annule (Echap) ou ne saisit rien. */
static unsigned char prompt_name(const char* label, const char* initial)
{
    unsigned char len = 0;
    char key;
    if (initial) { strcpy(input, initial); len = strlen(input); }
    else input[0] = 0;
    for (;;) {
        clear_row(22);
        gotoxy(0, 22);
        cprintf("%s: %s_", label, input);
        key = cgetc();
        if (key == KEY_ESC) { clear_row(22); return 0; }
        if (key == KEY_RETURN) { clear_row(22); return len != 0; }
        if (key == KEY_LEFT || key == KEY_DELETE) { if (len) input[--len] = 0; continue; }
        if (key >= 'a' && key <= 'z') key -= 32;
        if (len >= 15) continue;
        if ((key >= 'A' && key <= 'Z') || (len && ((key >= '0' && key <= '9') || key == '.'))) {
            input[len++] = key;
            input[len] = 0;
        }
    }
}

static void report_error(const char* what)
{
    ++total_errors;
    clear_row(22);
    gotoxy(0, 22);
    cprintf("%s failed (errno %d, ProDOS $%02X).", what, errno, _oserror);
}

/* ---------------------------------------------------------------------- */
/* Visionneuses                                                           */
/* ---------------------------------------------------------------------- */

static unsigned char looks_like_image(const struct Entry* e)
{
    unsigned char n = strlen(e->name);
    return e->type == 0x06 && n > 4 && !strcmp(e->name + n - 4, ".RLE");
}

/* L'image du curseur, plein ecran. Gauche / Droite passent a l'image
 * precedente / suivante du meme dossier sans revenir aux panneaux : le
 * dossier DHGR se feuillette comme un album. Toute autre touche revient. */
static void view_image(void)
{
    struct Panel* pan = &panels[active];
    unsigned char index = pan->cursor, next;
    char key;
    for (;;) {
        if (!build_full(full, pan, &pan->e[index])) { message("Path too long for ProDOS."); break; }
        total_view = 1;
        if (!hgr_rle_load(full)) {
            total_view = 0;
            switch_to_text();
            draw_all();
            message("Not a DHGR image (DHRR stream expected).");
            return;
        }
        switch_to_hgr();
        key = cgetc();
        if (key != KEY_LEFT && key != KEY_RIGHT) break;
        next = index;
        for (;;) {
            if (key == KEY_LEFT) { if (!next) break; --next; }
            else { if (next + 1 >= pan->count) break; ++next; }
            if (looks_like_image(&pan->e[next])) { index = next; break; }
        }
    }
    set_cursor(pan, index);
    switch_to_text();
    total_view = 0;
    draw_all();
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

static void viewer_bar(const char* text)
{
    revers(1);
    gotoxy(0, 23);
    cprintf("%-79.79s", text);
    revers(0);
    *(unsigned char*)0x07F7 = 0x20;
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
        sprintf(question, "page %u%s", page + 1, done ? " (end)" : "");
        gotoxy(0, 23);
        revers(1);
        cprintf("%-40.40s %-12s SPACE next  B prev  ESC back ", path, question);
        revers(0);
        *(unsigned char*)0x07F7 = 0x20;
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
        sprintf(question, "%lu bytes  page %u/%u", size, page + 1, pages);
        gotoxy(0, 23);
        revers(1);
        cprintf("%-30.30s %-24s SPACE next  B prev  ESC ", path, question);
        revers(0);
        *(unsigned char*)0x07F7 = 0x20;
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
    cputsxy(2, 2,  "Up / Down        move        < > or - +   page        [ ]  first / last");
    cputsxy(2, 3,  "TAB              other panel =            same directory in the other panel");
    cputsxy(2, 4,  "RETURN / Right   open : directory, .RLE image, TXT text, SYS program, else hex");
    cputsxy(2, 5,  "ESC / Left       parent directory        /   list of volumes");
    cputsxy(2, 6,  "SPACE            tag / untag the file and move down (* after the name)");
    cputsxy(2, 8,  "C  copy to the other panel      V  move (copy, then delete the original)");
    cputsxy(2, 9,  "R  rename                       D  delete (a directory with its contents)");
    cputsxy(2, 10, "K  make a directory             S  sort by name, size or type");
    cputsxy(2, 11, "T  view as text                 H  view as hexadecimal");
    cputsxy(2, 12, "X  run a SYS or BIN program     Q  quit to ProDOS (Bitsy Bye)");
    cputsxy(2, 14, "C, V and D act on every tagged file of the panel, else on the cursor.");
    cputsxy(2, 15, "Directories are copied whole; copies keep type and auxtype, never overwrite.");
    cputsxy(2, 16, "In an image: Left / Right show the previous / next image of the folder.");
    cputsxy(2, 17, "In a text or hex view: SPACE next page, B previous page, ESC back.");
    viewer_bar("Press any key to return to the panels");
    cgetc();
    total_view = 0;
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

static void progress_bar(const char* name, unsigned long copied, unsigned long size)
{
    unsigned char filled = size ? (unsigned char)(copied * 20 / size) : 20, i;
    gotoxy(0, 22);
    cprintf("%u/%u %-15s [", progress_done + 1, progress_total, name);
    for (i = 0; i < 20; ++i) cputc(i < filled ? '#' : '.');
    cprintf("] %6lu/%-6lu", copied, size);
}

/* Copie le fichier `full` vers `other_full`, meme type et auxtype, avec la
 * barre de progression. Refuse d'ecraser : un fichier existant se supprime
 * d'abord, explicitement. Rend 1 si la copie est complete. */
static unsigned char copy_file(const char* name, unsigned char type, unsigned int aux)
{
    FILE* in;
    FILE* out;
    unsigned int n;
    unsigned long size, copied = 0;
    unsigned char ok = 1;
    out = fopen(other_full, "rb");
    if (out) { fclose(out); clear_row(22); gotoxy(0, 22); cprintf("%s exists in the target: delete it first.", name); return 0; }
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

/* Copie le contenu du dossier `full` dans le dossier `other_full`, qui
 * existe deja, sous-dossiers compris. */
static unsigned char copy_tree(unsigned char base)
{
    unsigned char n, i, sl = strlen(full), dl = strlen(other_full), ok = 1;
    if (!list_dir(full, base, &n)) { message("Directory unreadable or too many files at once."); return 0; }
    for (i = 0; i < n && ok; ++i) {
        const struct Mini* m = &pool[base + i];
        if (!push_name(full, m->name) || !push_name(other_full, m->name)) { message("Path too long for ProDOS."); ok = 0; }
        else if (m->type == 0x0F) {
            if (mkdir(other_full)) { report_error("Mkdir"); ok = 0; }
            else ok = copy_tree(base + n);
        } else ok = copy_file(m->name, m->type, m->aux);
        full[sl] = 0;
        other_full[dl] = 0;
    }
    return ok;
}

/* Copie l'entree dans le dossier de l'autre panneau : un fichier, ou un
 * dossier entier. Rend 1 si tout est copie. */
static unsigned char copy_one(const struct Entry* e)
{
    struct Panel* dst = &panels[!active];
    FILE* probe;
    if (!build_full(full, &panels[active], e) || !build_full(other_full, dst, e)) { message("Path too long for ProDOS."); return 0; }
    if (!is_dir(e)) return copy_file(e->name, e->type, e->aux);
    if (!strncmp(dst->path, full, strlen(full)) && (dst->path[strlen(full)] == '/' || !dst->path[strlen(full)])) {
        message("Cannot copy a directory into itself.");
        return 0;
    }
    probe = fopen(other_full, "rb");
    if (probe) { fclose(probe); clear_row(22); gotoxy(0, 22); cprintf("%s exists in the target: delete it first.", e->name); return 0; }
    if (mkdir(other_full)) { report_error("Mkdir"); return 0; }
    ++total_ops;
    return copy_tree(0);
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
        cprintf("%u file%s %s.", progress_done, progress_done > 1 ? "s" : "", move ? "moved" : "copied");
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
    if (!prompt_name("New name", e->name)) return;
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
    if (!prompt_name("New directory", NULL)) return;
    if (strlen(pan->path) + 1 + strlen(input) >= PATH_LEN) { message("Path too long for ProDOS."); return; }
    sprintf(full, "%s/%s", pan->path, input);
    if (mkdir(full)) { report_error("Mkdir"); return; }
    ++total_ops;
    refresh_both();
    select_name(pan, input);
    show_active();
}

static void run_selected(const struct Entry* e)
{
    if (is_dir(e) || !panels[active].path[0]) { message("Select a SYS or BIN program."); return; }
    if (e->type != 0xFF && e->type != 0x06) { message("Only SYS and BIN files can be run."); return; }
    if (!build_full(full, &panels[active], e)) { message("Path too long for ProDOS."); return; }
    sprintf(question, "Run %s? TOTAL will not resume.", e->name);
    if (!confirm(question)) return;
    clrscr();
    exec(full, NULL);
    /* Ici seulement si le lancement a echoue. */
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

/* ---------------------------------------------------------------------- */
/* Boucle principale                                                      */
/* ---------------------------------------------------------------------- */

static void move_cursor(int delta)
{
    struct Panel* pan = &panels[active];
    unsigned char previous = pan->cursor, old_top = pan->top;
    int target;
    if (!pan->count) return;
    target = (int)pan->cursor + delta;
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
    panels[0].e = entries[0];
    panels[1].e = entries[1];
    if (!getcwd(panels[0].path, PATH_LEN)) strcpy(panels[0].path, "/SCOSWAMP");
    strcpy(panels[1].path, panels[0].path);
    if (strlen(panels[1].path) + 5 < PATH_LEN) strcat(panels[1].path, "/DHGR");
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
        case '[': move_cursor(-MAX_ENTRIES); break;
        case ']': move_cursor(MAX_ENTRIES); break;
        case ' ': toggle_tag(); break;
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
            pan->cursor = pan->top = 0;
            read_panel(active);
            show_active();
            break;
        case '=':
            strcpy(panels[!active].path, pan->path);
            panels[!active].cursor = panels[!active].top = 0;
            read_panel(!active);
            draw_panel(!active);
            break;
        case 'c': case 'C': copy_or_move(0); break;
        case 'v': case 'V': copy_or_move(1); break;
        case 'r': case 'R': if (pan->count) rename_selected(&pan->e[pan->cursor]); break;
        case 'd': case 'D': delete_targets(); break;
        case 'k': case 'K': make_directory(); break;
        case 's': case 'S': resort(); break;
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
