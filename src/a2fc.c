/* A2 FILE CMD -- un gestionnaire de fichiers ProDOS a deux panneaux, dans
 * l'esprit de Total Commander, tournant nativement sur Apple IIe 128 Ko.
 *
 * Programme SYS autonome, amorcable seul ou lance depuis un selecteur comme
 * Bitsy Bye, avec son propre lanceur (loader.c) et ses bascules video
 * (memory_swap.c). Il ne modifie jamais un fichier de
 * lui-meme : seules les commandes explicites (copie, deplacement, renommage,
 * suppression, creation de dossier, type, verrou) ecrivent sur le disque,
 * apres confirmation quand elles detruisent quelque chose. Il ecrit aussi
 * A2FILE/A2FILE.CFG en quittant : les deux dossiers, le tri, le panneau actif.
 *
 * Ouvrir (Entree) choisit d'apres le type : un dossier s'ouvre, une image
 * DHGR (.RLE, flux DHRR) s'affiche plein ecran, un TXT se lit page par page,
 * un SYS se lance apres confirmation, le reste se voit en hexadecimal.
 * Espace marque plusieurs fichiers : copie, deplacement et suppression
 * portent alors sur tous les fichiers marques.
 *
 * Memoire : code a $4000, tampons de travail en $1000-$1AFF (LOWBSS),
 * visionneuses et saisies dans la carte langage ($D400-$DFFF, segment LC,
 * copie par crt0 comme pour le jeu), et une fenetre de surcouche en
 * $1B00-$1FFF ou les surcouches (A2FILE/IMAGE.PLG, TEXT, HEX, DELETE,
 * HELP : liees avec le programme mais ecrites a part) sont lues a la
 * demande, voir overlay(). Les deux tables d'entrees occupent la
 * page graphique MAIN $2000-$3FFF, libre tant qu'aucune image n'est
 * affichee : une image la recouvre (MAIN et AUX), et les deux panneaux sont
 * relus au retour. Deux fichiers ouverts au plus (copie) : tampons ProDOS
 * $0800 et $0C00, A2FC n'utilise pas MAPBSS. Un dossier qui deborde la
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
#include "a2fc_plugin.h"

/* cc65 les lit a la creation d'un fichier (fopen "wb") : la copie garde le
 * type et l'auxtype de l'original, une image reste une image. */
extern unsigned char _filetype;
extern unsigned int _auxtype;

unsigned char __fastcall__ mli_gfi(void* params);   /* a2fc_mli.s */
unsigned char ram_format(void);
extern unsigned int chain_addr;                    /* chain.s */
void __fastcall__ chain_load(const char* path);
void __fastcall__ chain_command(const char* name);
unsigned char __fastcall__ mli_sfi(void* params);
unsigned char __fastcall__ mli_call(unsigned char cmd, void* params);
void __fastcall__ aux_copy(unsigned int main_addr, unsigned int aux_addr, unsigned char to_aux);
/* La souris (mouse.s) : une carte AppleMouse II, dans n'importe quel slot. */
unsigned char mouse_init(void);
unsigned char mouse_read(void);
void mouse_show(void);
void mouse_hide(void);
extern unsigned char mouse_x, mouse_y;
static unsigned char exists(const char* path);
int main(void);
static void too_long(void);
static unsigned char target_check(void);
static void progress_bar(const char* name, unsigned long copied, unsigned long size);
static void dir_fail(void);

#ifndef A2FC_VERSION
#define A2FC_VERSION "0.6.1"
#endif
#define WINDOW (MAX_ENTRIES - 1)   /* entrees du disque par fenetre : ".." en plus */

/* L'empreinte de ce qu'un panneau montre (a2fc_mli.s, en LOWEXE) : nombre,
 * fenetre, chemin ou son absence, et chaque octet de la table d'entrees.
 * Elle dit si une relecture a change l'ecran, pour bien moins cher que de
 * le redessiner. L'assembleur lit le panneau par les decalages notes en
 * face des champs de struct Panel : les deplacer, c'est le mettre a jour. */
unsigned int __fastcall__ panel_hash(const struct Panel* pan);

enum { SORT_NAME, SORT_SIZE, SORT_TYPE, SORT_MODES };
enum { ASK, OVERWRITE_ALL, SKIP_ALL };

#define ENTRIES ((struct Entry*)0x2000)   /* la page HGR MAIN, voir l'en-tete */
#define HELP_BUF ((char*)0x2000)          /* la meme page pour l'aide */
/* L'editeur est une grande surcouche : son code va de $1B00 a $27FF, le
 * texte occupe le reste de la page graphique. */
#define EDIT_BUF ((char*)0x2800)
#define EDIT_MAX 0x17F0
/* Toute la BSS de ce fichier vit en RAM basse ($1000-$1FFF, segment LOWBSS
 * d'a2fc.cfg) : main() la met a zero, crt0 ne le fait que pour BSS.
 * Bornes du segment exportees par le lieur. */
extern char _LOWBSS_RUN__[];
extern char _LOWBSS_SIZE__[];
#pragma bss-name (push, "LOWBSS")
static struct Panel panels[2];
static unsigned char active, sort_mode, over_policy;
static unsigned int progress_done, progress_total, progress_skipped;
/* Diagnostics lisibles par le banc de test POM2 (voir a2fc.lbl). */
unsigned int a2fc_draws, a2fc_ops, a2fc_errors;
unsigned char a2fc_view;       /* 0 panneaux, 1 image, 2 texte, 3 hexa, 4 aide, 5 editeur */
unsigned char a2fc_slot;       /* la Mockingboard, 0 sans ; 0xFF pas encore cherchee */
unsigned char a2fc_playing;    /* 0 silence, 1 joue, 2 en pause */
unsigned char a2fc_mouse;      /* le slot de la souris, 0 sans */
static unsigned char pointer;  /* la souris a bouge une fois : le pointeur s'affiche */

static char full[PATH_LEN + NAME_LEN];
static char other_full[PATH_LEN + NAME_LEN];
static char cfg_path[PATH_LEN];
static char input[NAME_LEN];
static char question[64];
static unsigned char copy_buf[512];
static unsigned char gfi[18];
static unsigned char gfi_path[PATH_LEN + 1];
static unsigned char picked[MAX_ENTRIES];
static char album[2][NAME_LEN];    /* visionneuse d'images : les voisines de gauche et de droite */
static unsigned int seen[2];       /* et l'empreinte des deux panneaux a l'entree */
static char overlay_loaded[12];     /* la surcouche en place dans la fenetre $1B00, "" sans */
static char reselect[NAME_LEN];    /* au retour d'une grande surcouche : le nom a reselectionner */
static struct Entry selected;      /* l'entree sous le curseur, copiee avant qu'une grande surcouche ne recouvre la table */
static char note[80];              /* ... et le message a ecrire en ligne 22 */
static long text_starts[80];   /* debuts de page connus */
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
    if (!pan->path[0] || pan->fs) return;
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
static int dir_fd = -1;
static unsigned char dir_index, dir_per_block, dir_entry_len;
static struct DirEntry dir_entry;

/* ---------------------------------------------------------------------- */
/* Une image disque lue comme un dossier (IMGFS)                          */
/* ---------------------------------------------------------------------- */

/* Une image disque ProDOS ouverte en lecture : ses blocs se lisent par
 * fseek dans le fichier (un .DSK est en ordre DOS 3.3, permute comme
 * po2dsk.py ; un .2MG porte son ordre et le decalage de ses donnees dans
 * son en-tete). Le repertoire se lit alors bloc par bloc en suivant le
 * chainage ProDOS, exactement comme un vrai dossier. */
static FILE* img_f;
static unsigned char img_dsk;        /* 1 : ordre DOS 3.3 */
static long img_base;                /* decalage des donnees (.2MG) */
static const unsigned char IMG_SECT[16] = { 0x0, 0xE, 0xD, 0xC, 0xB, 0xA, 0x9, 0x8, 0x7, 0x6, 0x5, 0x4, 0x3, 0x2, 0x1, 0xF };
static unsigned char dir_img;        /* dir_next lit depuis une image */

/* La source d'un secteur DOS 3.3 : 0 = image ouverte (img_f), sinon l'unite
 * ProDOS d'un vrai disque, lue par READ_BLOCK. */
static unsigned char dos_unit;
/* Un secteur DOS 3.3 logique (T, S) vers un demi-bloc ProDOS, sur le meme
 * disque : l'inverse de la table SECTORS de po2dsk.py. Valeur = bloc dans la
 * piste (T x 8 + valeur >> 1) et moitie (valeur & 1). */
static const unsigned char DOS_TS[16] = { 0, 14, 13, 12, 11, 10, 9, 8, 7, 6, 5, 4, 3, 2, 1, 15 };

/* Reconnait une image disque a son suffixe. Rend 1 (FS_IMG) si c'en est une,
 * FS_PRODOS (0) sinon. L'ordre des secteurs est deduit du suffixe par
 * img_open. */
static unsigned char image_order(const char* name)
{
    unsigned char n = strlen(name);
    return (n > 4 && (!strcmp(name + n - 4, ".DSK") || !strcmp(name + n - 4, ".2MG")))
        || (n > 3 && (!strcmp(name + n - 3, ".PO") || !strcmp(name + n - 3, ".DO"))) ? FS_IMG : FS_PRODOS;
}

/* Ouvre l'image `path` : l'ordre des secteurs vient du suffixe (.PO ProDOS,
 * .DSK/.DO DOS 3.3, .2MG de son en-tete). Rend 0 sur echec ; img_f ouvert. */
static unsigned char img_open(const char* path)
{
    unsigned char n = strlen(path);
    img_f = fopen(path, "rb");
    if (!img_f) return 0;
    img_dsk = (n > 4 && !strcmp(path + n - 4, ".DSK")) || (n > 3 && !strcmp(path + n - 3, ".DO"));
    img_base = 0;
    if (n > 4 && !strcmp(path + n - 4, ".2MG")) {
        if (fread(copy_buf, 1, 64, img_f) != 64 || memcmp(copy_buf, "2IMG", 4) || copy_buf[0x0C] > 1) { fclose(img_f); return 0; }
        img_dsk = copy_buf[0x0C] == 0;
        img_base = *(unsigned long*)(copy_buf + 0x18);
    }
    return 1;
}

/* Lit le secteur DOS 3.3 logique (track, sector), 256 octets, dans copy_buf.
 * Source : l'image ouverte (fseek dans l'ordre DOS) ou un vrai disque
 * (READ_BLOCK sur le demi-bloc ProDOS correspondant). Rend 1 si complet. */
static unsigned char dos_read_sector(unsigned char track, unsigned char sector)
{
    unsigned char code, parms[6];
    if (!dos_unit) {
        fseek(img_f, img_base + (((long)track * 16 + sector) << 8), SEEK_SET);
        return fread(copy_buf, 1, 256, img_f) == 256;
    }
    code = DOS_TS[sector];
    parms[0] = 3; parms[1] = dos_unit;
    parms[2] = (unsigned char)((unsigned)copy_buf & 0xFF);
    parms[3] = (unsigned char)((unsigned)copy_buf >> 8);
    parms[4] = (unsigned char)((unsigned)track * 8 + (code >> 1));
    parms[5] = (unsigned char)(((unsigned)track * 8 + (code >> 1)) >> 8);
    if (mli_call(0x80, parms)) return 0;
    if (code & 1) memmove(copy_buf, copy_buf + 256, 256);   /* la moitie haute du bloc */
    return 1;
}

/* Un vrai volume DOS 3.3 ? La VTOC (piste 17 secteur 0) : version DOS 1-3,
 * piste et secteur de catalogue plausibles, 35 pistes, 256 octets par
 * secteur, 122 paires par liste. Laisse la VTOC dans copy_buf. */
static unsigned char dos_vtoc_ok(void)
{
    return dos_read_sector(17, 0) && copy_buf[3] >= 1 && copy_buf[3] <= 3
        && copy_buf[1] && copy_buf[1] < 35 && copy_buf[2] < 16
        && copy_buf[0x34] == 35 && copy_buf[0x27] == 0x7A;
}

/* Lit le bloc ProDOS `block` de l'image dans `buf`. Rend 1 si complet. */
static unsigned char img_read_block(unsigned int block, unsigned char* buf)
{
    unsigned char half;
    if (!img_dsk) {
        fseek(img_f, img_base + ((long)block << 9), SEEK_SET);
        return fread(buf, 1, 512, img_f) == 512;
    }
    for (half = 0; half < 2; ++half) {
        fseek(img_f, img_base + ((((long)(block >> 3) << 4) + IMG_SECT[((block & 7) << 1) + half]) << 8), SEEK_SET);
        if (fread(buf + half * 256, 1, 256, img_f) != 256) return 0;
    }
    return 1;
}

/* Ouvre le repertoire de bloc-cle `key` dans l'image deja ouverte. Rend 0
 * si ce n'est pas un repertoire ProDOS. */
static unsigned char dir_open_image(unsigned int key)
{
    dir_img = 1;
    if (!img_read_block(key, copy_buf) || (copy_buf[4] >> 4) < 0x0E) return 0;
    dir_entry_len = copy_buf[4 + 0x1F];
    dir_per_block = copy_buf[4 + 0x20];
    if (dir_entry_len != 0x27 || dir_per_block != 0x0D) return 0;
    dir_index = 1;
    return 1;
}

static unsigned char dir_open(const char* path)
{
    dir_img = 0;
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
    if (dir_img) { if (img_f) fclose(img_f); img_f = 0; dir_img = 0; return; }
    if (dir_fd >= 0) close(dir_fd);
    dir_fd = -1;
}

/* Charge le bloc de repertoire suivant dans copy_buf. Pour une image, on
 * suit le pointeur de chainage avant (octets 2-3 du bloc courant) ; pour un
 * vrai dossier, ProDOS assemble les blocs, une simple lecture suffit. */
static unsigned char dir_block_next(void)
{
    if (dir_img) {
        unsigned int next = copy_buf[2] | ((unsigned int)copy_buf[3] << 8);
        return next && img_read_block(next, copy_buf);
    }
    return read(dir_fd, copy_buf, 512) == 512;
}

/* L'entree suivante dans dir_entry, ou 0 a la fin. */
static unsigned char dir_next(void)
{
    const unsigned char* e;
    unsigned char len;
    for (;;) {
        if (dir_index >= dir_per_block) {
            if (!dir_block_next()) return 0;
            dir_index = 0;
        }
        e = copy_buf + 4 + dir_index * dir_entry_len;
        ++dir_index;
        if (!(e[0] & 0xF0)) continue;   /* entree effacee */
        len = e[0] & 0x0F;
        memcpy(dir_entry.name, e + 1, len);
        dir_entry.name[len] = 0;
        dir_entry.type = e[0x10];
        dir_entry.key = e[0x11] | ((unsigned int)e[0x12] << 8);
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
    extern const char msg_toolong[]; message(msg_toolong);
}

static void dir_fail(void)
{
    extern const char msg_dirfail[]; message(msg_dirfail);
}

/* La barre de touches, facon Norton Commander : chaque touche dans un bloc
 * inverse de trois colonnes, son libelle en clair juste apres, un espace
 * entre les boutons. `spec` enchaine "TOUCHE Libelle" separes par des
 * virgules ; une touche d'une lettre est centree dans son bloc. La ligne 23
 * n'est jamais ecrite au-dela de la colonne 78 : conio passerait a la ligne
 * sur la 80e et ferait defiler l'ecran. */
extern const char MAIN_KEYS[];   /* defini en carte langage, plus bas (LC) */
extern const char VIEW_KEYS[];   /* en carte langage, defini plus bas */
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
    case 0x1A: return "AWP";
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

/* Les marques des deux panneaux, mises de cote dans picked[] pendant qu'une
 * image, l'aide ou l'editeur recouvre les tables d'entrees (save = 1), puis
 * rendues une fois les panneaux relus (save = 0). */
static void keep_tags(unsigned char save)
{
    if (save) {
        memcpy(picked, panels[0].tags, sizeof panels[0].tags);
        memcpy(picked + sizeof panels[0].tags, panels[1].tags, sizeof panels[1].tags);
    } else {
        memcpy(panels[0].tags, picked, sizeof panels[0].tags);
        memcpy(panels[1].tags, picked + sizeof panels[0].tags, sizeof panels[1].tags);
    }
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
    else if (!pan->path[0]) {
        /* 38 colonnes exactement, comme les autres lignes : avec 7 espaces
         * de queue cette ligne en faisait 42, et en inverse (selection) ses
         * 4 cellules de trop debordaient sur le separateur et le panneau
         * voisin a gauche, ou passaient a la ligne suivante, colonnes 0-1, a
         * droite -- les "carres blancs" en mode DOS 3.3. */
        if (!e->access) cprintf("%-15s S%u,D%u  DOS 3.3 disk   ", e->name, (e->mdate >> 4) & 7, (e->mdate >> 7) + 1);
        else cprintf("%-15s S%u,D%u %5u/%5u free", e->name, e->mdate & 7, (e->mdate >> 3) + 1, e->aux, e->blocks);
    }
    else if (is_dir(e)) cprintf("%-15s  <DIR>          %5u ", e->name, e->blocks);
    else cprintf("%-15s%c%c%s $%04X %8lu   ", e->name, tagged(pan, index) ? '*' : ' ',
                 is_locked(e) ? 'L' : ' ', type_name(e->type), e->aux, e->size);
    revers(0);
}

static void draw_panel(unsigned char p)
{
    struct Panel* pan = &panels[p];
    unsigned char x = p ? 40 : 0, i;
    extern const char a2fc_hdr_name[], a2fc_hdr_size[], a2fc_hdr_type[];
    static const char* const headers[SORT_MODES] = {
        a2fc_hdr_name, a2fc_hdr_size, a2fc_hdr_type };
    ++a2fc_draws;
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
    cputsxy(2, 20, " A2 FILE CMD " A2FC_VERSION " ");
    if (pan->total_blocks) {
        gotoxy(30, 20);
        cprintf(" %u of %u blocks free ", pan->free_blocks, pan->total_blocks);
    }
    if (a2fc_mouse) cputsxy(70, 20, " Mouse ");
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
    else if (pan->fs)           /* dans une image : mdate porte le bloc-cle, pas une date */
        cprintf("%s  type $%02X  aux $%04X  %u blocks  %lu bytes  (in image)",
                e->name, e->type, e->aux, e->blocks, e->size);
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
    /* Les disques DOS 3.3 n'ont pas de volume ProDOS : on sonde chaque unite
     * (DEVLST) pour une VTOC DOS 3.3 et on la propose comme un dossier. Un
     * disque ProDOS ou un lecteur vide echoue au controle et n'est pas
     * ajoute ; l'unite ProDOS est gardee dans mdate, access = 0 la marque. */
    {
        unsigned char nd = *(unsigned char*)0xBF31 + 1, i, unit;
        for (i = 0; i < nd && pan->count < MAX_ENTRIES; ++i) {
            unit = ((unsigned char*)0xBF32)[i] & 0xF0;
            dos_unit = unit;
            if (dos_vtoc_ok()) {
                e = add_entry(pan, "DOS 3.3", 0x0F);
                e->mdate = unit;
                e->access = 0;
                e->blocks = 560;
                e->aux = 0;
            }
        }
        dos_unit = 0;
    }
    DEVNUM = saved;
}

/* Remplit le panneau et oublie ses marques. La fenetre commence a l'entree
 * pan->first du disque ; ".." n'apparait que dans la premiere, et le tri ne
 * s'applique que si le dossier tient entier. Rend 0 si le dossier ne se lit
 * pas : le panneau retombe alors sur la liste des volumes, jamais sur un
 * ecran vide. */
/* read_image_panel, dos33_type et read_dos33_panel gardent leurs locales sur
 * la pile C (la RAM basse est pleine) ; aucun n'est recursif. */
#pragma static-locals (push, off)

/* Le type ProDOS le plus proche d'un type DOS 3.3 (octet de catalogue, bit 7
 * = verrouille) : T texte, I Integer, A Applesoft, B binaire, le reste BIN. */
static unsigned char dos33_type(unsigned char t)
{
    switch (t & 0x7F) {
    case 0x00: return 0x04;   /* T -> TXT */
    case 0x01: return 0xFA;   /* I -> INT */
    case 0x02: return 0xFC;   /* A -> BAS */
    case 0x04: return 0x06;   /* B -> BIN */
    }
    return 0x06;
}

/* Remplit le panneau depuis le catalogue DOS 3.3 de la source deja etablie
 * (dos_unit : une image ouverte ou un vrai disque). Le catalogue est plat :
 * pas de sous-dossiers, pas de "..". Chaque entree garde dans mdate la piste
 * et le secteur de sa premiere liste T/S, pour l'extraction. Le nom DOS est
 * ramene a un nom ProDOS valable (lettres, chiffres, points, 15 au plus).
 * Rend 0 si ce n'est pas un volume DOS 3.3. */
static unsigned char read_dos33_panel(struct Panel* pan)
{
    struct Entry* e;
    unsigned char ct, cs, i, k, len;
    const unsigned char* d;
    char name[NAME_LEN];
    char c;
    if (!dos_vtoc_ok()) return 0;
    ct = copy_buf[1]; cs = copy_buf[2];
    pan->count = 0;
    pan->more = 0;
    memset(pan->tags, 0, sizeof pan->tags);
    while (ct && ct < 35 && pan->count < MAX_ENTRIES) {
        if (!dos_read_sector(ct, cs)) break;
        ct = copy_buf[1]; cs = copy_buf[2];
        for (i = 0; i < 7 && pan->count < MAX_ENTRIES; ++i) {
            d = copy_buf + 0x0B + i * 0x23;
            if (!d[0]) { ct = 0; break; }        /* jamais utilise : fin du catalogue */
            if (d[0] == 0xFF) continue;          /* efface */
            len = 30;
            while (len && (d[2 + len] & 0x7F) == ' ') --len;
            for (k = 0; k < len && k < 15; ++k) {
                c = d[3 + k] & 0x7F;
                if (c >= 'a' && c <= 'z') c -= 32;
                if (!((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9'))) c = '.';
                name[k] = c;
            }
            name[k] = 0;
            if (name[0] < 'A' || name[0] > 'Z') name[0] = 'X';   /* ProDOS : une lettre d'abord */
            e = add_entry(pan, name, dos33_type(d[2]));
            e->blocks = d[0x21] | ((unsigned int)d[0x22] << 8);   /* secteurs, listes T/S comprises */
            e->size = (unsigned long)e->blocks << 8;
            e->access = (d[2] & 0x80) ? 0x01 : 0xC3;
            e->aux = 0;
            e->mdate = ((unsigned int)d[0] << 8) | d[1];          /* piste/secteur de la 1re liste T/S */
        }
    }
    return 1;
}


/* Remplit le panneau depuis une image ou un vrai disque ouvert comme un
 * dossier (pan->fs != 0). La source est une image fichier quand pan->img_len
 * > 0 (chemin dans pan->path[0..img_len], puis le chemin interne), sinon un
 * vrai disque DOS 3.3 dont l'unite ProDOS est dans pan->dir_key. Un volume
 * ProDOS se navigue par bloc-cle (dir_key), avec ".." et les sous-dossiers ;
 * un DOS 3.3 est un catalogue plat. Rend 0 si la source n'est pas lisible ;
 * le panneau retombe alors sur la liste des volumes. */





/* M : marque les fichiers absents de l'autre panneau ou de taille
 * differente, la base d'une synchronisation par C. */

static unsigned char read_image_panel(struct Panel* pan)
{
    struct Entry* e;
    unsigned int parent = 2;
    unsigned char i;
    dos_unit = 0;
    if (pan->img_len) {             /* une image fichier */
        unsigned char tail = pan->path[pan->img_len];
        pan->path[pan->img_len] = 0;
        i = img_open(pan->path);
        pan->path[pan->img_len] = tail;
        if (!i) goto fail;
    } else {                        /* un vrai disque DOS 3.3, par son unite ProDOS */
        dos_unit = (unsigned char)pan->dir_key;
        img_f = 0;
    }
    if (pan->fs == FS_DOS33) {       /* catalogue plat, lu par la surcouche */
        i = read_dos33_panel(pan);
        if (img_f) { fclose(img_f); img_f = 0; }
        if (!i) goto fail;
        return 1;
    }
    /* ProDOS ; si la lecture echoue et l'image est en ordre DOS, essayer
     * DOS 3.3 (une disquette DOS 3.3 lue par erreur comme ProDOS). */
    pan->count = 0;
    pan->more = 0;
    memset(pan->tags, 0, sizeof pan->tags);
    if (!dir_open_image(pan->dir_key)) {
        if (img_dsk && pan->dir_key == 2 && read_dos33_panel(pan)) {
            pan->fs = FS_DOS33;
            fclose(img_f); img_f = 0; dir_img = 0;
            return 1;
        }
        dir_close();
        goto fail;
    }
    if (pan->dir_key != 2)          /* pointeur parent d'un sous-dossier (0x23 dans l'en-tete) */
        parent = copy_buf[4 + 0x23] | ((unsigned int)copy_buf[4 + 0x24] << 8);
    if (pan->dir_key != 2) { e = add_entry(pan, "..", 0x0F); e->mdate = parent; }
    while (dir_next()) {
        if (pan->count >= MAX_ENTRIES) { pan->more = 1; break; }
        e = add_entry(pan, dir_entry.name, dir_entry.type);
        e->access = dir_entry.access;
        e->aux = dir_entry.aux;
        e->blocks = dir_entry.blocks;
        e->size = dir_entry.size;
        e->mdate = dir_entry.key;   /* le bloc-cle, pour naviguer et extraire */
    }
    dir_close();
    if (pan->count > 2) sort_entries(pan);
    return 1;
fail:
    pan->fs = FS_PRODOS;
    pan->path[0] = 0;
    read_volumes(pan);
    return 0;
}
#pragma static-locals (pop)

static unsigned char read_panel(unsigned char p)
{
    struct Panel* pan = &panels[p];
    struct Entry* e;
    unsigned int skip = pan->first;
    unsigned char ok = 1;
    if (pan->fs) {
        ok = read_image_panel(pan);
        goto placed;
    }
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
placed:
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

/* Pose le curseur du panneau actif sur `index` et ne reecrit que ce qui
 * bouge : les deux lignes quand la fenetre ne defile pas, le panneau
 * entier sinon, puis la ligne d'information. */
static void land(unsigned char index)
{
    struct Panel* pan = &panels[active];
    unsigned char previous = pan->cursor, old_top = pan->top;
    set_cursor(pan, index);
    if (pan->top != old_top) draw_panel(active);
    else { draw_entry(active, previous); draw_entry(active, pan->cursor); }
    draw_info();
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
    char* slash;
    if (pan->fs) {
        if (!pan->img_len) {   /* un vrai disque DOS 3.3 : retour a la liste des volumes */
            pan->fs = FS_PRODOS;
            pan->path[0] = 0;
            pan->dir_key = 2;
            open_path(pan);
            select_name(pan, "DOS 3.3");
            return;
        }
        if (pan->dir_key == 2) {
            /* racine de l'image : en sortir, revenir au dossier qui la
             * contient, curseur sur le fichier image. */
            pan->path[pan->img_len] = 0;
            slash = strrchr(pan->path, '/');
            strcpy(input, slash ? slash + 1 : pan->path);
            if (slash && slash != pan->path) *slash = 0;
            else pan->path[0] = 0;
            pan->fs = FS_PRODOS;
            open_path(pan);
            select_name(pan, input);
        } else {
            /* remonter d'un cran dans l'image : ".." porte le bloc du parent */
            slash = strrchr(pan->path + pan->img_len, '/');
            pan->dir_key = pan->count ? pan->e[0].mdate : 2;
            if (slash) *slash = 0;
            pan->cursor = pan->top = 0;
            read_panel(pan - panels);
        }
        return;
    }
    slash = strrchr(pan->path, '/');
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
    if (pan->fs) {
        /* un sous-dossier dans l'image : son bloc-cle est dans mdate */
        if (strlen(pan->path) + 1 + strlen(e->name) >= PATH_LEN) { too_long(); return; }
        pan->dir_key = e->mdate;
        strcat(pan->path, "/");
        strcat(pan->path, e->name);
        pan->cursor = pan->top = 0;
        read_panel(pan - panels);
        return;
    }
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

/* Le code d'erreur ProDOS ($BF00 le laisse dans _oserror, que cc65 tient a
 * jour meme apres un echec de fopen/fread) en clair : "errno 3, ProDOS $2B"
 * ne dit rien a l'utilisateur, "the disk is write-protected" si. Les codes
 * rares gardent leur hexa et l'errno cc65, pour le diagnostic. Table nommee
 * (pas un switch a return "...") pour que ses chaines suivent la carte
 * langage : la fenetre principale est pleine au bit pres. */
/* Chaines en tableaux NOMMES (const char[]), pas en litteraux "..." : cc65
 * regroupe les litteraux dans RODATA (fenetre principale, pleine), mais pose
 * un tableau nomme dans le segment rodata courant -- ici LC, la carte
 * langage, ou il reste de la place. */
static const char pdE27[] = "disk I/O error";
static const char pdE2B[] = "the disk is write-protected";
static const char pdE2F[] = "no disk in the drive";
static const char pdE40[] = "invalid file name";
static const char pdE44[] = "directory not found";
static const char pdE45[] = "volume not found";
static const char pdE46[] = "file not found";
static const char pdE47[] = "name already in use";
static const char pdE48[] = "the disk is full";
static const char pdE49[] = "the directory is full";
static const char pdE4E[] = "the file is locked";
static const char pdE52[] = "not a ProDOS disk";
const char msg_dirfail[] = "Directory unreadable or too many files.";
const char msg_toolong[] = "Path too long for ProDOS.";
const char msg_sysonly[] = "SYS, BIN or BAS only.";
const char msg_nomb[] = "No Mockingboard in slots 1-7.";
const char msg_notimg[] = "Not a ProDOS disk image (or DOS 3.3).";
const char msg_roimg[] = "Read-only disk image; C extracts to the other panel.";
const char msg_samedir[] = "Both panels show the same directory.";
const char msg_otherro[] = "The other panel is a read-only disk image.";
const char msg_nohelp[] = "A2FILE/A2FILE.HELP is missing: no help on this volume.";
const char msg_intoself[] = "Cannot copy a directory into itself.";
const char VIEW_KEYS[] = "SPC Next,B Prev,ESC Back";
/* Les 107 mots Applesoft ($80-$EA), separes par des zeros. Tableau NOMME
 * (const char[]), pas des litteraux "..." : cc65 regroupe les litteraux dans
 * RODATA (fenetre principale pleine), un tableau nomme suit le segment de la
 * surcouche. */
static const char BAS_TOK[] =
    "END\0FOR\0NEXT\0DATA\0INPUT\0DEL\0DIM\0READ\0GR\0TEXT\0PR#\0IN#\0CALL\0"
    "PLOT\0HLIN\0VLIN\0HGR2\0HGR\0HCOLOR=\0HPLOT\0DRAW\0XDRAW\0HTAB\0HOME\0"
    "ROT=\0SCALE=\0SHLOAD\0TRACE\0NOTRACE\0NORMAL\0INVERSE\0FLASH\0COLOR=\0"
    "POP\0VTAB\0HIMEM:\0LOMEM:\0ONERR\0RESUME\0RECALL\0STORE\0SPEED=\0LET\0"
    "GOTO\0RUN\0IF\0RESTORE\0&\0GOSUB\0RETURN\0REM\0STOP\0ON\0WAIT\0LOAD\0"
    "SAVE\0DEF\0POKE\0PRINT\0CONT\0LIST\0CLEAR\0GET\0NEW\0TAB(\0TO\0FN\0SPC(\0"
    "THEN\0AT\0NOT\0STEP\0+\0-\0*\0/\0^\0AND\0OR\0>\0=\0<\0SGN\0INT\0ABS\0USR\0"
    "FRE\0SCRN(\0PDL\0POS\0SQR\0RND\0LOG\0EXP\0COS\0SIN\0TAN\0ATN\0PEEK\0LEN\0"
    "STR$\0VAL\0ASC\0CHR$\0LEFT$\0RIGHT$\0MID$";

static const char* bas_token(unsigned char n)
{
    const char* s = BAS_TOK;
    while (n--) { while (*s) ++s; ++s; }
    return s;
}

/* Les trois en-tetes de colonne des panneaux, en carte langage plutot que
 * dans RODATA (fenetre principale pleine) : ~100 octets rendus au resident,
 * la marge qu'il fallait pour la surcouche UNSHRINK et ses calculs 32 bits.
 * draw_panel les designe par un tableau de pointeurs (six octets). */
const char a2fc_hdr_name[] = "Name*            Type  Aux     Size";
const char a2fc_hdr_size[] = "Name             Type  Aux     Size*";
const char a2fc_hdr_type[] = "Name             Type* Aux     Size";
const char MAIN_KEYS[] = "TAB Panel,RET Open,SPC Tag,C Copy,V Move,R Ren,D Del,K Mkdir,! More,? Help";
static const char re_fmt1[] = "%s failed: %s.";
static const char re_fmt2[] = "%s failed (ProDOS $%02X, errno %d).";
static const char* prodos_error(unsigned char e)
{
    switch (e) {
    case 0x27: return pdE27;
    case 0x2B: return pdE2B;
    case 0x2F: return pdE2F;
    case 0x40: return pdE40;
    case 0x44: return pdE44;
    case 0x45: return pdE45;
    case 0x46: return pdE46;
    case 0x47: return pdE47;
    case 0x48: return pdE48;
    case 0x49: return pdE49;
    case 0x4E: return pdE4E;
    case 0x52: return pdE52;
    default:   return 0;
    }
}

/* prodos_error appele deux fois plutot qu'une locale `why` : LOWBSS est plein
 * au bit pres et -Cl mettrait la locale dedans ; le second appel n'est que du
 * code, en carte langage ou il reste de la place. */
static void report_error(const char* what)
{
    ++a2fc_errors;
    clear_row(22);
    gotoxy(0, 22);
    if (prodos_error(_oserror))
        cprintf(re_fmt1, what, prodos_error(_oserror));
    else
        cprintf(re_fmt2, what, _oserror, errno);
}

/* ---------------------------------------------------------------------- */
/* Visionneuses -- dans la carte langage                                  */
/* ---------------------------------------------------------------------- */

/* Sans ouvrir le fichier : un FOT ($08), ou un BIN de la taille d'une page
 * HGR ou DHGR, ou un flux .RLE. L'ouverture tranche ensuite sur l'en-tete.
 * En RAM principale : la carte langage est pleine. */
#pragma code-name (push, "CODE")
#pragma rodata-name (push, "RODATA")
/* La taille d'une page HGR (8 192 ou 8 184 octets) ou DHGR (16 384), lue en
 * deux mots : cc65 compare un long par une routine, et chaque comparaison
 * se payait une trentaine d'octets. */
static unsigned char page_size(const unsigned long* size)
{
    const unsigned int* w = (const unsigned int*)size;
    return !w[1] && (w[0] == 8192 || w[0] == 8184 || w[0] == 16384);
}

static unsigned char looks_like_image(const struct Entry* e)
{
    unsigned char n = strlen(e->name);
    if (is_dir(e)) return 0;
    if (e->type == 0x08) return 1;
    if (e->type != 0x06) return 0;
    return page_size(&e->size) || (n > 4 && !strcmp(e->name + n - 4, ".RLE"));
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
#define TEXT_PAGES 80           /* text_starts[] : les debuts de page connus */

/* Une page de 22 lignes ; les retours ProDOS sont des CR. Les debuts de
 * page sont memorises au passage : la page precedente est un fseek. */
/* La surcouche TEXT : la visionneuse de texte, dans A2FILE/TEXT.PLG. */
#pragma code-name (push, "TEXT")
#pragma rodata-name (push, "TEXTRO")
static void view_text(const char* path)
{
    long* starts = text_starts;
    unsigned char page = 0, known = 1, row, col, done = 0;
    int c;
    char key;
    vf = fopen(path, "rb");
    if (!vf) { report_error("Open"); return; }
    a2fc_view = 2;
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
    a2fc_view = 0;
    draw_all();
}

void __fastcall__ text_entry(const struct A2fcApi* a)
{
    (void)a;
    if (full[0]) view_text(full);
}
#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* La surcouche BASLIST : lister un programme Applesoft, dans BASLIST.PLG. */
/* `T` sur un BAS ($FC) la charge au lieu de la visionneuse de texte : au   */
/* lieu de l'hexa des jetons, le listing detokenise. Elle relit le fichier  */
/* par view_getc (resident) et pagine comme la visionneuse de texte, en     */
/* retenant le debut de chaque page dans text_starts. Pas de tampon : elle  */
/* reste une petite surcouche.                                              */
/* ---------------------------------------------------------------------- */
#pragma code-name (push, "BASLIST")
#pragma rodata-name (push, "BASLISTRO")
#pragma static-locals (push, off)

extern const char* bas_token(unsigned char n);   /* en carte langage, plus haut */
#define bl_row input[0]      /* 2 octets du tampon resident input[] : LOWBSS est plein */
#define bl_col input[1]

/* Un caractere a l'ecran, coupe a 80 colonnes, 22 lignes ; au-dela on cesse
 * d'ecrire mais on continue de consommer le fichier. CR passe a la ligne. */
static void bl_putc(char c)
{
    if (bl_row >= TEXT_ROWS) return;
    if (c == 13) { ++bl_row; bl_col = 0; if (bl_row < TEXT_ROWS) gotoxy(0, bl_row); return; }
    if (bl_col == 80) { ++bl_row; bl_col = 0; if (bl_row >= TEXT_ROWS) return; gotoxy(0, bl_row); }
    cputc(c);
    ++bl_col;
}

static void bl_puts(const char* s) { while (*s) bl_putc(*s++); }

void __fastcall__ baslist_entry(const struct A2fcApi* a)
{
    unsigned char page = 0, known = 1, done;
    unsigned int num;
    int lo, hi, t;
    char key, buf[7];
    (void)a;
    vf = fopen(full, "rb");
    if (!vf) { report_error("Open"); return; }
    a2fc_view = 2;
    text_starts[0] = 0;
    for (;;) {
        view_seek(text_starts[page]);
        clrscr();
        bl_row = 0; bl_col = 0; done = 0;
        while (bl_row < TEXT_ROWS) {
            lo = view_getc(); hi = view_getc();      /* le pointeur de ligne suivante */
            if (lo < 0 || (lo == 0 && hi == 0)) { done = 1; break; }
            num = (unsigned int)view_getc();
            num |= (unsigned int)view_getc() << 8;    /* le numero de ligne */
            sprintf(buf, "%u ", num);
            bl_puts(buf);
            for (;;) {
                t = view_getc();
                if (t <= 0) break;                    /* $00 finit la ligne (ou EOF) */
                if (t >= 0x80 && t <= 0xEA) { bl_putc(' '); bl_puts(bas_token((unsigned char)(t - 0x80))); bl_putc(' '); }
                else bl_putc((char)(t & 0x7F));
            }
            bl_putc(13);
        }
        if (!done && page + 1 < TEXT_PAGES && known == page + 1) {
            text_starts[page + 1] = vbase + vpos;     /* le debut de la page suivante */
            known = page + 2;
        }
        bar_begin();
        cprintf("%-38.38s page %u%s", full, page + 1, done ? " (end)" : "");
        keys_bar(52, VIEW_KEYS);
        key = cgetc();
        if (key == KEY_ESC || key == 'q' || key == 'Q') break;
        if ((key == ' ' || key == KEY_RETURN || key == KEY_RIGHT || key == KEY_DOWN) && !done && page + 1 < known) ++page;
        if ((key == 'b' || key == 'B' || key == KEY_LEFT || key == KEY_UP) && page) --page;
    }
    fclose(vf);
    a2fc_view = 0;
    draw_all();
}
#pragma static-locals (pop)
#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* La surcouche AWP : un document AppleWorks (traitement de texte, type    */
/* $1A) lu page par page, dans A2FILE/AWP.PLG. Entree ou T sur un AWP, ou   */
/* le menu !. Le format : 300 octets d'en-tete (SFMinVers en +183 : a       */
/* partir de 30, deux octets de plus), puis des enregistrements de deux     */
/* octets d'en-tete : $D0 en second = un retour chariot seul, > $D0 = une   */
/* commande de mise en page (sautee), $FF $FF = la fin, sinon le premier    */
/* octet compte les octets d'une ligne de texte : position du curseur et    */
/* drapeaux ($FF = une regle, sautee), puis les caracteres, ou les codes    */
/* sous $20 sont des enrichissements (ignores) et des tabulations.         */
/* ---------------------------------------------------------------------- */
#pragma code-name (push, "AWP")
#pragma rodata-name (push, "AWPRO")
#pragma static-locals (push, off)

#define aw_row input[0]
#define aw_col input[1]

static const char aw_bad[] = "Not an AppleWorks word-processor file.";

static void aw_putc(char c)
{
    if (aw_row >= TEXT_ROWS) return;
    if (c == 13) { ++aw_row; aw_col = 0; if (aw_row < TEXT_ROWS) gotoxy(0, aw_row); return; }
    if (aw_col == 80) { ++aw_row; aw_col = 0; if (aw_row >= TEXT_ROWS) return; gotoxy(0, aw_row); }
    cputc(c);
    ++aw_col;
}

void __fastcall__ awp_entry(const struct A2fcApi* a)
{
    unsigned char page = 0, known = 1, done, len;
    int c, kind;
    char key;
    (void)a;
    if (!selected.name[0] || selected.type != 0x1A || !full[0]) { message(aw_bad); return; }
    vf = fopen(full, "rb");
    if (!vf) { report_error("Open"); return; }
    view_seek(183);
    c = view_getc();                              /* SFMinVers */
    a2fc_view = 2;
    text_starts[0] = c >= 30 ? 302 : 300;
    for (;;) {
        view_seek(text_starts[page]);
        clrscr();
        aw_row = 0; aw_col = 0; done = 0;
        while (aw_row < TEXT_ROWS) {
            c = view_getc(); kind = view_getc();
            if (c < 0 || kind < 0 || kind == 0xFF) { done = 1; break; }
            if (kind == 0xD0) { aw_putc(13); continue; }       /* un retour chariot seul */
            if (kind > 0xD0) continue;                          /* une commande de mise en page */
            len = (unsigned char)c;
            if (len < 2) { done = 1; break; }
            c = view_getc(); view_getc();                       /* position, puis compte et drapeau CR */
            len -= 2;
            if (c == 0xFF) { while (len--) view_getc(); continue; }   /* une regle */
            while (len--) {
                c = view_getc();
                if (c < 0) { done = 1; break; }
                if (c >= 0x20 && c < 0x7F) aw_putc((char)c);
                else if (c == 0x16 || c == 0x17) do aw_putc(' '); while (aw_col & 7);   /* tabulation */
                else if (c == 0x0B) aw_putc(' ');                                      /* espace insecable */
            }
            aw_putc(13);
        }
        if (!done && page + 1 < TEXT_PAGES && known == page + 1) {
            text_starts[page + 1] = vbase + vpos;
            known = page + 2;
        }
        bar_begin();
        cprintf("%-38.38s page %u%s", full, page + 1, done ? " (end)" : "");
        keys_bar(52, VIEW_KEYS);
        key = cgetc();
        if (key == KEY_ESC || key == 'q' || key == 'Q') break;
        if ((key == ' ' || key == KEY_RETURN || key == KEY_RIGHT || key == KEY_DOWN) && !done && page + 1 < known) ++page;
        if ((key == 'b' || key == 'B' || key == KEY_LEFT || key == KEY_UP) && page) --page;
    }
    fclose(vf);
    a2fc_view = 0;
    draw_all();
}
#pragma static-locals (pop)
#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* La surcouche COMPARE : le fichier selectionne et celui de meme nom dans  */
/* l'autre panneau, octet par octet, dans A2FILE/COMPARE.PLG. Lancee par le */
/* menu ! (M ne compare que les tailles). Deux moities du tampon de copie   */
/* resident, pas de reserve : petite surcouche.                             */
/* ---------------------------------------------------------------------- */
#pragma code-name (push, "COMPARE")
#pragma rodata-name (push, "COMPARERO")
#pragma static-locals (push, off)

static const char cmp_pick[]   = "Select a file to compare.";
static const char cmp_nooth[]  = "No file of that name in the other panel.";
static const char cmp_ident[]  = "Identical: %lu bytes.";
static const char cmp_diff[]   = "Differ at byte %lu.";
static const char cmp_short[]  = "Same for %lu bytes, then one is longer.";

void __fastcall__ compare_entry(const struct A2fcApi* a)
{
    struct Panel* oth = &panels[!active];
    FILE* fa;
    FILE* fb;
    unsigned int na, nb, i, m;
    unsigned long pos = 0;
    (void)a;
    if (!selected.name[0] || is_dir(&selected) || !full[0]) { message(cmp_pick); return; }
    if (!oth->path[0] || oth->fs) { message(cmp_nooth); return; }
    sprintf(other_full, "%s/%s", oth->path, selected.name);
    fa = fopen(full, "rb");
    if (!fa) { report_error("Open"); return; }
    fb = fopen(other_full, "rb");
    if (!fb) { fclose(fa); message(cmp_nooth); return; }
    for (;;) {
        na = fread(copy_buf, 1, 256, fa);
        nb = fread(copy_buf + 256, 1, 256, fb);
        m = na < nb ? na : nb;
        for (i = 0; i < m; ++i)
            if (copy_buf[i] != copy_buf[256 + i]) {
                fclose(fa); fclose(fb);
                sprintf(question, cmp_diff, pos + i);
                message(question);
                return;
            }
        pos += m;
        if (na != nb) { fclose(fa); fclose(fb); sprintf(question, cmp_short, pos); message(question); return; }
        if (na < 256) break;
    }
    fclose(fa); fclose(fb);
    sprintf(question, cmp_ident, pos);
    message(question);
}
#pragma static-locals (pop)
#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* La surcouche SEARCH : un texte cherche dans les fichiers du panneau, ceux */
/* qui le contiennent sont marques, dans A2FILE/SEARCH.PLG. Lancee par le    */
/* menu !. Recherche insensible a la casse ; le texte est un nom ProDOS      */
/* (prompt resident : lettres, chiffres, points), ce qui couvre les mots-    */
/* cles et les noms. Une fenetre glissante gere les bords de bloc.           */
/* ---------------------------------------------------------------------- */
#pragma code-name (push, "SEARCH")
#pragma rodata-name (push, "SEARCHRO")
#pragma static-locals (push, off)

static const char srch_label[] = "Search for";
static const char srch_none[]  = "No file in this panel.";
static const char srch_res[]   = "%u file(s) contain \"%s\", now tagged.";

/* fread (deja resident) plutot que fgetc (qui se lierait dans la fenetre
 * principale, pleine) : un bloc dans copy_buf, une fenetre glissante de plen
 * octets par-dessus, insensible a la casse. */
static unsigned char file_has(const char* path, const char* pat, unsigned char plen)
{
    FILE* f = fopen(path, "rb");
    unsigned char win[16], wlen = 0, i, c;
    unsigned int n, j;
    if (!f) return 0;
    for (;;) {
        n = fread(copy_buf, 1, 512, f);
        for (j = 0; j < n; ++j) {
            c = copy_buf[j] & 0x7F;
            if (c >= 'a' && c <= 'z') c -= 32;
            if (wlen < plen) win[wlen++] = c;
            else { for (i = 1; i < plen; ++i) win[i - 1] = win[i]; win[plen - 1] = c; }
            if (wlen == plen) {
                for (i = 0; i < plen && win[i] == (unsigned char)pat[i]; ++i) ;
                if (i == plen) { fclose(f); return 1; }
            }
        }
        if (n < 512) break;
    }
    fclose(f);
    return 0;
}

void __fastcall__ search_entry(const struct A2fcApi* a)
{
    struct Panel* pan = &panels[active];
    unsigned char plen, i, found = 0;
    (void)a;
    if (!pan->count) { message(srch_none); return; }
    if (!prompt(srch_label, 0, 0)) return;          /* input : le texte, en majuscules */
    plen = strlen(input);
    if (!plen || plen > 15) return;
    for (i = 0; i < pan->count; ++i) {
        if (is_dir(&pan->e[i]) || !build_full(full, pan, &pan->e[i])) continue;
        if (file_has(full, input, plen)) { set_tag(pan, i, 1); ++found; }
    }
    draw_panel(active);
    sprintf(question, srch_res, found, input);
    message(question);
}
#pragma static-locals (pop)
#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* La surcouche BINARY2 : extraire une archive Binary II (.BNY), dans        */
/* A2FILE/BINARY2.PLG. Lancee par le menu !. Chaque fichier : un en-tete de  */
/* 128 octets (magie 0A 47 4C), les donnees (EOF octets) completees au       */
/* multiple de 128. Pas de compression : on recopie. tools/mkbny.py ecrit et */
/* relit le meme format.                                                     */
/* ---------------------------------------------------------------------- */
#pragma code-name (push, "BINARY2")
#pragma rodata-name (push, "BINARY2RO")
#pragma static-locals (push, off)

static const char b2_pick[]  = "Select a Binary II archive.";
static const char b2_notdir[] = "Other panel must be a ProDOS folder.";
static const char b2_bad[]   = "Not a Binary II archive.";
static const char b2_path[]  = "%s/%s";
static const char b2_done[]  = "%u file(s) extracted.";

/* Un nom ProDOS a partir de celui de l'archive : lettres, chiffres et
 * points, une lettre en tete, 15 au plus. */
static void b2_name(const unsigned char* src, unsigned char len, char* out)
{
    unsigned char i, n = 0, start = 0;
    char c;
    for (i = 0; i < len; ++i) if (src[i] == '/' || src[i] == ':') start = i + 1;
    for (i = start; i < len && n < 15; ++i) {
        c = src[i];
        if (c >= 'a' && c <= 'z') c -= 32;
        if (!((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '.')) c = '.';
        if (!n && !(c >= 'A' && c <= 'Z')) { out[n++] = 'X'; if (n == 15) break; }
        out[n++] = c;
    }
    if (!n) out[n++] = 'X';
    out[n] = 0;
}

void __fastcall__ binary2_entry(const struct A2fcApi* a)
{
    struct Panel* oth = &panels[!active];
    FILE* in;
    FILE* out;
    unsigned long eof, pad;
    unsigned int n, k;
    unsigned char more = 1, done = 0;
    char name[17];
    (void)a;
    if (!selected.name[0] || is_dir(&selected) || !full[0]) { message(b2_pick); return; }
    if (!oth->path[0] || oth->fs) { message(b2_notdir); return; }
    in = fopen(full, "rb");
    if (!in) { report_error("Open"); return; }
    while (more) {
        if (fread(copy_buf, 1, 128, in) != 128) break;
        if (copy_buf[0] != 0x0A || copy_buf[1] != 0x47 || copy_buf[2] != 0x4C) {
            if (!done) { message(b2_bad); fclose(in); return; }
            break;
        }
        /* EOF sur 3 octets ($14-$16), le nom en $17/$18, "a suivre" en $7F.
         * Tout est lu de l'en-tete AVANT la boucle de copie, qui recouvre
         * copy_buf. Le bourrage au multiple de 128 se calcule ici. */
        eof = (unsigned long)copy_buf[0x14] | ((unsigned long)copy_buf[0x15] << 8)
              | ((unsigned long)copy_buf[0x16] << 16);   /* EOF sur 3 octets, $14-$16 */
        pad = (128 - (eof & 127)) & 127;
        more = copy_buf[0x7F] != 0;                       /* "a suivre" en $7F */
        b2_name(copy_buf + 0x18, copy_buf[0x17], name);   /* nom : longueur $17, texte $18 */
        _filetype = copy_buf[4];
        _auxtype = copy_buf[5] | (copy_buf[6] << 8);
        sprintf(other_full, b2_path, oth->path, name);
        out = fopen(other_full, "wb");
        if (!out) { report_error("Create"); fclose(in); return; }
        while (eof) {
            n = eof > 512 ? 512 : (unsigned int)eof;
            k = fread(copy_buf, 1, n, in);
            if (!k || fwrite(copy_buf, 1, k, out) != k) break;
            eof -= k;
        }
        fclose(out);
        if (eof) { remove(other_full); report_error("Extract"); fclose(in); return; }
        ++done;
        if (pad) fseek(in, (long)pad, SEEK_CUR);
    }
    fclose(in);
    sprintf(question, b2_done, done);
    message(question);
}
#pragma static-locals (pop)
#pragma rodata-name (pop)
#pragma code-name (pop)

#define HEX_ROWS 20
#define HEX_PAGE (HEX_ROWS * 16)

/* La surcouche HEX : la visionneuse hexadecimale, dans A2FILE/HEX.PLG. */
#pragma code-name (push, "HEX")
#pragma rodata-name (push, "HEXRO")
static void view_hex(const char* path, unsigned long size)
{
    unsigned int page = 0, pages = (unsigned int)((size + HEX_PAGE - 1) / HEX_PAGE), n, i, j;
    char key;
    vf = fopen(path, "rb");
    if (!vf) { report_error("Open"); return; }
    a2fc_view = 3;
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
    a2fc_view = 0;
    draw_all();
}

void __fastcall__ hex_entry(const struct A2fcApi* a)
{
    (void)a;
    if (full[0]) view_hex(full, panels[active].e[panels[active].cursor].size);
}
#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* Preferences : A2FILE/A2FILE.CFG -- dans la carte langage                 */
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
static unsigned char aux_dirty;    /* une image a ecrit en AUX : /RAM est a refaire */
static const char* ram_note;
static const char RAM_NOTE[] = "  /RAM was rebuilt empty.";

#define HGR_MAIN ((unsigned char*)0x2000)
#define OVERLAY ((unsigned char*)0x1B00)   /* la fenetre de surcouche, voir a2fc.cfg */

/* HGR simple, page 1, sans le mode double : 80COL et DHIRES coupes.
 * TXTCLR ($C050) en DERNIER : allumer le graphique avant d'avoir arme HIRES
 * montre la page texte relue en basse resolution -- un damier de couleurs le
 * temps de deux ecritures, juste assez pour une trame sur un moniteur lent. */
static void show_hgr(void)
{
    *(unsigned char*)0xC000 = 0; *(unsigned char*)0xC00C = 0; *(unsigned char*)0xC05F = 0;
    *(unsigned char*)0xC057 = 0; *(unsigned char*)0xC054 = 0; *(unsigned char*)0xC052 = 0;
    *(unsigned char*)0xC050 = 0;
}

/* Le chemin d'un fichier range a cote du programme : "/VOL/A2FILE/name",
 * dans other_full, d'apres celui de la configuration. Vide si le programme
 * ne sait pas d'ou il vient. */
static void a2file_file(const char* name)
{
    char* slash = strrchr(cfg_path, '/');
    other_full[0] = 0;
    if (!slash) return;
    memcpy(other_full, cfg_path, slash + 1 - cfg_path);
    strcpy(other_full + (slash + 1 - cfg_path), name);
}

/* Charge la surcouche `name` -- A2FILE/NAME.PLG, un fichier BIN lie avec le
 * programme -- dans la fenetre $1B00, si elle n'y est pas deja : feuilleter
 * un dossier d'images ne relit rien. Ses huit premiers octets sont l'en-tete
 * decrit dans a2fc_plugin.h : le mot de signature est l'adresse de main dans
 * le lien qui l'a produite (overlay.s), ou PLUGIN_MAGIC pour une surcouche
 * d'un tiers, que seul `any` accepte (le menu des surcouches) ; un fichier
 * d'une autre construction est refuse, comme un fichier absent, et la ligne
 * de message le dit. Une grande surcouche (OVERLAY_BIG) prend aussi la page
 * graphique : les marques sont mises de cote avant de l'ecraser, et c'est
 * overlay_run qui relit les panneaux au retour. Rend 0 si rien n'est charge. */
#define OVL ((struct Overlay*)OVERLAY_WINDOW)
static unsigned char load_overlay(const char* name, unsigned char any)
{
    FILE* f;
    unsigned char ok = 0;
    if (!strcmp(overlay_loaded, name)) return 1;
    overlay_loaded[0] = 0;
    a2file_file(name);
    strcat(other_full, ".PLG");
    f = fopen(other_full, "rb");
    if (f) {
        if (fread(OVERLAY_WINDOW, 1, 8, f) == 8
            && (OVL->signature == (unsigned int)main || (any && OVL->signature == PLUGIN_MAGIC))) {
            if (OVL->flags & OVERLAY_BIG) keep_tags(1);
            fread(OVERLAY_WINDOW + 8, 1, (OVL->flags & OVERLAY_BIG ? OVERLAY_LARGE : OVERLAY_SMALL) - 8, f);
            strcpy(overlay_loaded, name);
            ok = 1;
        }
        fclose(f);
    }
    if (!ok) {
        clear_row(22);
        gotoxy(0, 22);
        cprintf("A2FILE/%s.PLG is missing or stale on this volume.", name);
    }
    return ok;
}
#define overlay(name) load_overlay(name, 0)

/* Lance la surcouche `name` par son point d'entree, avec `arg` (la touche
 * qui l'appelle, 0 depuis le menu) dans la table de services. Une grande
 * surcouche rend la main sur une page graphique a elle : l'ecran revient au
 * texte, les deux panneaux sont relus, les marques rendues, le nom qu'elle a
 * laisse dans `reselect` retrouve, tout redessine, et son `note` ecrit en
 * ligne 22. */
static struct A2fcApi api;
static void select_name(struct Panel* pan, const char* name);
static void overlay_run(const char* name, unsigned char arg)
{
    struct Panel* pan = &panels[active];
    unsigned char big;
    /* L'entree sous le curseur et son chemin, mis a l'abri : une grande
     * surcouche recouvre la table d'entrees en se chargeant. */
    full[0] = 0;
    if (pan->count) { selected = pan->e[pan->cursor]; build_full(full, pan, &selected); }
    else selected.name[0] = 0;
    if (!load_overlay(name, 1)) return;
    /* Une grande surcouche a deja mis les marques de cote et recouvert la
     * table d'entrees en se chargeant (load_overlay) : meme sans point
     * d'entree, il faut passer par la relecture des panneaux, sinon l'ecran
     * garde la moitie haute de la surcouche a la place des entrees. Le point
     * d'entree manquant ne peut venir que d'une surcouche d'un tiers malformee
     * (PLUGIN_MAGIC sans entree). */
    big = OVL->flags & OVERLAY_BIG;
    api.arg = arg;
    reselect[0] = 0;
    note[0] = 0;
    if (OVL->entry) OVL->entry(&api);
    else strcpy(note, "This overlay has no entry point.");
    if (big) {
        overlay_loaded[0] = 0;   /* sa moitie haute est deja recouverte par les tables */
        switch_to_text();
        read_panel(0);
        read_panel(1);
        keep_tags(0);
        if (reselect[0]) select_name(&panels[active], reselect);
        draw_all();
        if (note[0]) message(note);
    } else if (!OVL->entry) message(note);
}

/* ---------------------------------------------------------------------- */
/* La surcouche IMAGE : le chargeur et le decodeur, dans A2FILE/IMAGE.PLG */
/* ---------------------------------------------------------------------- */

/* Tout ce qui suit jusqu'au pop est lie a part, dans la fenetre $1B00 :
 * de la RAM ordinaire, au meme prix que $4000, mais qui ne coute rien au
 * programme resident. Le noyau sait reconnaitre une image (looks_like_image)
 * et charger la surcouche ; il ne sait plus decoder. Les visionneuses de
 * texte et d'hexadecimal (TEXT, HEX), la suppression (DELETE) et l'aide
 * (HELP) sont d'autres surcouches, chacune marquee de la meme facon. */
#pragma code-name (push, "IMAGE")
#pragma rodata-name (push, "IMAGERO")

/* Aiguille les ecritures $2000-$3FFF vers AUX (80STORE + HIRES + PAGE2),
 * comme hgr_loader.s ; le MLI y ecrit alors aussi. */
static void aux_writes(unsigned char on)
{
    if (on) { *(unsigned char*)0xC002 = 0; *(unsigned char*)0xC004 = 0; *(unsigned char*)0xC057 = 0; *(unsigned char*)0xC001 = 0; *(unsigned char*)0xC055 = 0; }
    else { *(unsigned char*)0xC054 = 0; *(unsigned char*)0xC000 = 0; }
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

static unsigned char decode_rle(FILE* f, unsigned int bytes)
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

/* Identifie et charge l'image `full` (l'entree `e`) en page 1. Rend le
 * format, IMG_NONE si le fichier n'en est pas une. */
static unsigned char load_image(const struct Entry* e)
{
    FILE* f;
    unsigned int size = page_size(&e->size) ? (unsigned int)e->size : 0;
    unsigned char kind = IMG_NONE, ok = 0;
    /* Le firmware 80 colonnes laisse 80STORE arme et se sert de PAGE2 pour
     * atteindre la banque auxiliaire. Avec HIRES encore actif (une image
     * precedente), $2000-$3FFF suivrait ce routage et la lecture partirait
     * en AUX : ecran fige sur l'ancienne image, ou moitie d'image. On part
     * donc toujours d'un routage MAIN connu. */
    aux_writes(0);
    f = fopen(full, "rb");
    if (!f) return IMG_NONE;
    if (fread(copy_buf, 1, 8, f) == 8) {
        if (!memcmp(copy_buf, "DHRR\1\0\0\x40", 8)) kind = IMG_DHRR;
        else if (!memcmp(copy_buf, "HGRR\1\0\0\x20", 8)) kind = IMG_HGRR;
        else if (size == 16384) kind = IMG_DHGR;
        else if (size) kind = IMG_HGR;
    }
    if (kind == IMG_DHRR) { aux_dirty = 1; ok = decode_rle(f, 16384); }
    else if (kind == IMG_HGRR) ok = decode_rle(f, 8192);
    else if (kind == IMG_HGR) { rewind(f); ok = fread(HGR_MAIN, 1, 8192, f) >= 8184; }
    else if (kind == IMG_DHGR) {
        aux_dirty = 1;
        rewind(f);
        aux_writes(1);
        ok = fread(HGR_MAIN, 1, 8192, f) == 8192;
        aux_writes(0);
        ok = ok && fread(HGR_MAIN, 1, 8192, f) == 8192;
    }
    fclose(f);
    return ok ? kind : IMG_NONE;
}

static void view_image(void);
void __fastcall__ image_entry(const struct A2fcApi* a)
{
    (void)a;
    view_image();
}
#pragma rodata-name (pop)
#pragma code-name (pop)

static void loading(const char* name)
{
    clear_row(22);
    gotoxy(0, 22);
    cprintf("Loading %s...", name);
}

/* L'image du curseur, plein ecran, HGR ou DHGR selon ce que le fichier
 * contient. Gauche / Droite passent a l'image precedente / suivante du
 * meme dossier sans revenir aux panneaux : le dossier DHGR se feuillette
 * comme un album, et le curseur suit. Toute autre touche revient, et la
 * ligne de message dit le format reconnu.
 *
 * L'ecran texte n'est jamais efface : les panneaux restent en $400-$7FF
 * pendant tout le feuilletage, et seul ce qui change est reecrit -- les
 * deux lignes du curseur, la ligne d'information, la ligne de message. Au
 * retour, un panneau n'est redessine que si sa relecture montre autre
 * chose qu'a l'entree (/RAM refait a neuf, disquette changee). */
static void view_image(void)
{
    struct Panel* pan = &panels[active];
    unsigned char index = pan->cursor, next, p, dir;
    char key;
    if (!overlay("IMAGE")) return;
    aux_dirty = 0;
    /* L'image recouvre les tables d'entrees : les marques sont mises de
     * cote, les panneaux relus au retour, et le panneau actif avant chaque
     * image suivante pour y retrouver la voisine. */
    keep_tags(1);
    for (p = 0; p < 2; ++p) seen[p] = panel_hash(&panels[p]);
    a2fc_view = 1;
    loading(pan->e[index].name);
    for (;;) {
        full[0] = 0;
        if (!build_full(full, pan, &pan->e[index])) break;
        strcpy(input, pan->e[index].name);
        /* Les voisines qui ressemblent a une image, de chaque cote : leurs
         * noms survivent a l'image qui va recouvrir la table. Une fleche
         * sait ainsi, sans relire le dossier, si elle a quelque part ou
         * aller, et annonce la suivante avant meme de la chercher. */
        for (dir = 0; dir < 2; ++dir) {
            album[dir][0] = 0;
            next = index;
            for (;;) {
                if (!dir) { if (!next) break; --next; }
                else { if (next + 1 >= pan->count) break; ++next; }
                if (looks_like_image(&pan->e[next])) { strcpy(album[dir], pan->e[next].name); break; }
            }
        }
        /* RIEN ne doit ecrire dans $2000-$3FFF pendant que la page graphique
         * est a l'antenne : on y voyait sinon l'image precedente se faire
         * ronger par la table d'entrees, puis la nouvelle se peindre bande
         * par bande (et, en DHGR, le plan AUX avant le plan MAIN). L'ecran
         * est donc au texte -- les panneaux, intacts en $400-$7FF -- le
         * temps du decodage, et l'image ne s'allume qu'une fois complete. */
        img_kind = load_image(&pan->e[index]);
        if (img_kind == IMG_NONE) break;
        if (img_kind == IMG_HGR || img_kind == IMG_HGRR) show_hgr();
        else switch_to_hgr();
        /* Une fleche sans voisine de son cote ne fait rien : l'image reste. */
        do key = cgetc(); while ((key == KEY_LEFT || key == KEY_RIGHT) && !album[key == KEY_RIGHT][0]);
        if (key != KEY_LEFT && key != KEY_RIGHT) break;
        dir = key == KEY_RIGHT;
        /* Retour au texte avant que read_panel ne reecrive la table
         * d'entrees, donc la page graphique ; le nom de la voisine s'affiche
         * pendant qu'on la cherche, le curseur la rejoint des qu'elle est la. */
        switch_to_text();
        loading(album[dir]);
        read_panel(active);
        keep_tags(0);
        for (next = 0; next < pan->count && strcmp(pan->e[next].name, album[dir]); ++next) {}
        if (next >= pan->count) break;   /* le dossier a change sous nos pieds */
        land(next);
        index = next;
    }
    switch_to_text();
    a2fc_view = 0;
    /* Le prix du DHGR : sa moitie auxiliaire ($2000-$3FFF en banque AUX) est
     * de la memoire que le disque virtuel de ProDOS utilise -- 18 blocs,
     * mesures au banc, et c'est justement la que commencent les donnees d'un
     * fichier ecrit sur /RAM. Ils sont perdus, le volume est donc faux : la
     * prochaine ecriture rendrait n'importe quoi. On le refait a neuf par son
     * propre pilote, ce qui rend un volume vide et coherent, et on le dit --
     * des qu'un chargement DHGR a ECRIT en AUX, qu'il ait abouti ou non
     * (un fichier tronque a deja fait le degat), meme si la derniere image
     * etait une HGR. Une image HGR simple n'ecrit qu'en banque principale
     * et ne declenche rien. */
    ram_note = aux_dirty && ram_format() ? RAM_NOTE : (const char*)"";
    /* Les tables sont relues ; l'ecran, lui, n'a pas bouge, et un panneau
     * qui montre la meme chose qu'a l'entree n'est pas redessine. read_panel
     * ramene le curseur dans le panneau si celui-ci a retreci (dossier
     * change sous nos pieds, /RAM refait a neuf sous celui qui s'y trouvait). */
    for (p = 0; p < 2; ++p) read_panel(p);
    keep_tags(0);
    for (p = 0; p < 2; ++p) if (panel_hash(&panels[p]) != seen[p]) draw_panel(p);
    draw_status();
    draw_info();
    if (!full[0]) { too_long(); return; }
    clear_row(22);
    gotoxy(0, 22);
    if (img_kind == IMG_NONE) cprintf("%s: not an image.", input);
    else cprintf("%s: %s, %lu bytes on screen.%s", input, IMG_NAMES[img_kind], IMG_BYTES[img_kind], ram_note);
}

/* ---------------------------------------------------------------------- */
/* Editeur de texte -- la grande surcouche EDIT, dans A2FILE/EDIT.PLG      */
/* ---------------------------------------------------------------------- */
#pragma code-name (push, "EDIT")
#pragma rodata-name (push, "EDITRO")

/* Le texte vit dans la page HGR MAIN, au-dessus du code de la surcouche
 * ($2800-$3FEF : 6 Ko), fins de ligne CR, bit 7 ote au chargement.
 * Le curseur est un decalage dans le tampon ; l'ecran montre 22 lignes a
 * partir de `etop`, debut d'une ligne, sans repli des lignes longues. */
#define EDIT_ROWS 22
static unsigned int elen, ecur, etop, ewant, eblocks;   /* eblocks : ceux du fichier avant l'edition */
static unsigned char edirty, etype;
static unsigned int eaux;

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

/* fopen "wb" tronque le fichier avant d'ecrire (SET_EOF de cc65) : on
 * s'assure d'abord de la place, l'ancien contenu libere ses blocs. */
static unsigned char edit_save(void)
{
    FILE* f;
    if ((elen + 511) / 512 + 1 > panels[active].free_blocks + eblocks) { message("Volume full."); return 0; }
    _filetype = etype;
    _auxtype = eaux;
    f = fopen(full, "wb");
    if (!f) { report_error("Save"); return 0; }
    if (fwrite(EDIT_BUF, 1, elen, f) != elen) { fclose(f); report_error("Save"); return 0; }
    if (fclose(f)) { report_error("Save"); return 0; }
    edirty = 0;
    ++a2fc_ops;
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
        if (!f) { strcpy(note, "Open failed."); return 0xFF; }
        elen = fread(EDIT_BUF, 1, EDIT_MAX, f);   /* la taille est verifiee par l'appelant */
        fclose(f);
        for (i = 0; i < elen; ++i) { EDIT_BUF[i] &= 0x7F; if (EDIT_BUF[i] == '\n') EDIT_BUF[i] = '\r'; }
    }
    a2fc_view = 5;
    clrscr();
    cursor(1);
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
        case KEY_RETURN: if (edit_insert('\r')) row = 2; ewant = 0; break;   /* 2 : depuis la ligne coupee */
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
        /* row 0/1 : redessiner depuis la ligne courante ; 2 : depuis la
         * precedente, dont la fin vient de partir a la ligne. */
        if (row != 0xFF && !edit_place()) {
            unsigned int pos = etop; unsigned char r = 0;
            ls = line_start(row == 2 ? ecur - 1 : ecur);
            while (pos < ls) { pos = next_line(pos); ++r; }
            edit_draw(r);
            edit_place();
        } else edit_place();
    }
leave:
    cursor(0);
    a2fc_view = 0;
    return written;
}

/* E : edite le fichier sous le curseur, ou un fichier neuf si c'est un
 * dossier ; le noyau relit les panneaux et remet le curseur sur `reselect`. */
void __fastcall__ edit_entry(const struct A2fcApi* a)
{
    struct Panel* pan = &panels[active];
    const struct Entry* e = &selected;
    unsigned char fresh = 0;
    (void)a;
    if (!pan->count || !pan->path[0]) { strcpy(note, "Open a directory first."); return; }
    if (is_dir(e)) {
        if (!prompt("New text file", NULL, 0)) return;
        if (strlen(pan->path) + 1 + strlen(input) >= PATH_LEN) { strcpy(note, "Path too long for ProDOS."); return; }
        sprintf(full, "%s/%s", pan->path, input);
        if (exists(full)) { strcpy(note, "File exists: select it to edit."); return; }
        fresh = 1;
    } else if (!build_full(full, pan, e)) { strcpy(note, "Path too long for ProDOS."); return; }
    else if (e->size > (unsigned long)EDIT_MAX) { strcpy(note, "Too big for the editor (6 KB)."); return; }
    strcpy(reselect, fresh ? input : e->name);
    eblocks = fresh ? 0 : e->blocks;
    /* Les marques sont des index tries : un fichier nouveau les decale,
     * elles sont oubliees dans ce cas. */
    if (edit_file(fresh, fresh ? 0x04 : e->type, fresh ? 0 : e->aux) == 1 && fresh) memset(picked, 0, sizeof picked);
}
#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* Musique Mockingboard                                                   */
/* ---------------------------------------------------------------------- */

#pragma code-name (push, "LC")
#pragma rodata-name (push, "LC")
static unsigned char looks_like_music(const struct Entry* e)
{
    unsigned char n = strlen(e->name);
    return !is_dir(e) && e->type == 0x06 && n > 3 && !strcmp(e->name + n - 3, ".MB");
}
#pragma rodata-name (pop)
#pragma code-name (pop)

/* Entree sur un .MB : le flux MB1 est monte en AUX par le lecteur du jeu
 * (six voix, en interruption) et joue une fois pendant que l'on continue
 * de naviguer -- les lectures disque ne l'arretent pas, A2FC n'y touche
 * jamais ; P le met en pause, un autre .MB le remplace, Q et X le coupent.
 * La carte est cherchee a la premiere demande.
 *
 * Le flux vit en AUX $1000-$18FF, et cette memoire appartient au /RAM de
 * ProDOS : mesure dans l'emulateur, son pilote y range les blocs 9, 26,
 * 43... (un sur dix-sept), sa carte des blocs est en $0C00 et son
 * repertoire en $0E00. Il n'y a nulle part en AUX 2 304 octets hors de sa
 * portee. Une fois le flux monte, le volume est donc faux -- comme apres
 * une image DHGR -- et on le refait a neuf de la meme facon, en le disant.
 * Refait, il ne relit jamais les blocs libres : la musique joue sans
 * risque, tant qu'on n'ecrit pas sur /RAM pendant qu'elle joue (ce qui
 * abimerait le morceau, pas le volume). */
/* La surcouche MUSIC, dans A2FILE/MUSIC.PLG : le chargement du flux ; le
 * lecteur (music.s) reste resident, la surcouche peut partir des que le
 * morceau joue. */
#pragma code-name (push, "MUSIC")
#pragma rodata-name (push, "MUSICRO")
/* M : marque les fichiers absents de l'autre panneau ou de taille
 * differente ; S : le tri suivant. Surcouche, la RAM basse etant pleine. */
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

void __fastcall__ music_entry(const struct A2fcApi* a)
{
    const struct Entry* e = &panels[active].e[panels[active].cursor];
    FILE* f;
    unsigned int n, total = 0;
    unsigned char valid = 1, last = 0;
    (void)a;
    if (api.arg == 'S') { resort(); return; }
    if (api.arg == 'M') { mark_differences(); return; }
    if (a2fc_slot == 0xFF) a2fc_slot = music_detect();
    if (!a2fc_slot) { extern const char msg_nomb[]; message(msg_nomb); return; }
    if (e->size > MUSIC_ZONE) { message("MB file too large (2304 bytes max)."); return; }
    f = fopen(full, "rb");
    if (!f) { report_error("Open"); return; }
    music_stop();
    a2fc_playing = 0;
    do {
        n = fread(music_buf, 1, MUSIC_STAGE, f);
        if (!total && (n <= 8 || memcmp(music_buf, "MB1", 3))) { valid = 0; break; }
        if (n) { music_store(total, n); last = music_buf[n - 1]; }
        total += n;
    } while (n == MUSIC_STAGE);
    fclose(f);
    if ((last & 0xF0) != 0xE0) valid = 0;   /* sans END, le lecteur lirait l'AUX au-dela */
    if (!valid) { message("Not an MB1 stream."); return; }
    /* Le flux vit sur des blocs de /RAM (AUX $1000+) : on le refait a neuf,
     * comme au retour d'une image DHGR. ram_format se sert de la page $2000
     * comme tampon, donc des tables d'entrees ; on garde le nom du fichier
     * (e pointe dans la table) puis on relit et redessine les panneaux. */
    strcpy(input, e->name);
    if (ram_format()) {
        keep_tags(1);
        read_panel(0);
        read_panel(1);
        keep_tags(0);
        draw_all();
        ram_note = RAM_NOTE;
    } else ram_note = (const char*)"";
    music_select(0);
    music_set_loop(0);
    music_play();
    a2fc_playing = 1;
    clear_row(22);
    gotoxy(0, 22);
    cprintf("Playing %s, slot %u. P pauses.%s", input, a2fc_slot, ram_note);
}
#pragma rodata-name (pop)
#pragma code-name (pop)

static void toggle_music(void)
{
    if (!music_active) { a2fc_playing = 0; message("No music playing: open a .MB file."); }
    else if (a2fc_playing == 1) { music_pause(); a2fc_playing = 2; message("Music paused. P resumes."); }
    else { music_resume(); a2fc_playing = 1; message("Music resumed."); }
}

/* ---------------------------------------------------------------------- */
/* Aide                                                                   */
/* ---------------------------------------------------------------------- */

/* L'aide est lue dans A2FILE/A2FILE.HELP (a cote de A2FILE.CODE), une ligne
 * par element : "x,y,TOUCHE,libelle" pour un bouton, "x,y,#TITRE" pour un
 * titre de section, "x,y,~texte" pour du texte en clair ('=' et '-' sont
 * des touches). Le texte passe par
 * la page HGR, comme l'editeur : rien en memoire hors de l'aide. */
/* La surcouche HELP : la page d'aide, dans A2FILE/HELP.PLG. */
#pragma code-name (push, "HELP")
#pragma rodata-name (push, "HELPRO")
static void view_help(void)
{
    const char* s = HELP_BUF;
    FILE* f;
    unsigned int n;
    unsigned char x, y, klen, i, kind;
    a2file_file("A2FILE.HELP");
    f = fopen(other_full, "rb");
    if (!f) { { extern const char msg_nohelp[]; message(msg_nohelp); }; return; }
    n = fread(HELP_BUF, 1, 0x1FF0, f);
    fclose(f);
    HELP_BUF[n] = 0;
    keep_tags(1);
    a2fc_view = 4;
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
    a2fc_view = 0;
    read_panel(0);
    read_panel(1);
    keep_tags(0);
    draw_all();
}

void __fastcall__ help_entry(const struct A2fcApi* a)
{
    (void)a;
    view_help();
}
#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* Les images disque -- la grande surcouche DISKIMG                        */
/* ---------------------------------------------------------------------- */

/* W : ecrire une image (.PO, .DSK ou .DO, .2MG) sur une disquette, lire
 * une disquette dans une image neuve, copier une disquette sur une autre
 * -- ou sur elle-meme avec un seul lecteur, en changeant de disquette a
 * chaque passe. Les blocs passent par READ_BLOCK et WRITE_BLOCK, que le
 * pilote soit celui du Disk II, d'un SmartPort ou du /RAM : la disquette
 * cible doit deja etre formatee (F le fait), rien ici n'ecrit de piste.
 *
 * La reserve d'une passe : quatre blocs en banque principale ($3400-$3BFF,
 * au-dessus du code de la surcouche), et pour la copie a un seul lecteur
 * quatre-vingts blocs de plus en banque auxiliaire, $2000-$BFFF, la ou vit
 * /RAM -- qui est donc refait a neuf ensuite, comme apres une image DHGR.
 * Une disquette de 280 blocs se copie ainsi en quatre passes. Les
 * variables de la surcouche vivent en $3E00, hors de la RAM basse. */
#pragma code-name (push, "DISKIMG")
#pragma rodata-name (push, "DISKIMGRO")

/* Les textes, en tableaux nommes : cc65 2.18 range les litteraux de chaine
 * dans RODATA quel que soit le pragma rodata-name, et ceux d'une surcouche
 * peseraient sur la fenetre principale. */
static const char S_TITLE[] = "  A2 FILE CMD  -  DISK IMAGES";
static const char S_INTRO[] = "ProDOS order .PO, DOS 3.3 order .DSK or .DO, and .2MG. The target must be formatted.";
static const char S_W[] = "W  Write %s to a disk";
static const char S_R[] = "R  Read a disk into a new image file, in this directory";
static const char S_O[] = "O  Copy a disk to another disk (one drive: swap the disks at each pass)";
static const char S_KEYS[] = "W Write,R Read,O Copy,ESC Back";
static const char S_PICK_KEYS[] = "1-8 Choose the disk,ESC Back";
static const char S_DEV[] = "%c  %s  %-17s %5u blocks%s";
static const char S_WHERE[] = "slot %u drive %u";
static const char S_NOVOL[] = "(no ProDOS volume)";
static const char S_INUSE[] = "  IN USE";
static const char S_EMPTY[] = "";
static const char S_HOLDS[] = "That disk holds the running program: choose another.";
static const char S_LOST[] = " EVERYTHING on %s (%s) WILL BE LOST. ";
static const char S_ERASE[] = "Type ERASE then RETURN to go on";
static const char S_WORD[] = "ERASE";
static const char S_TO[] = "Write the image to which disk?";
static const char S_FROM[] = "Read which disk into an image?";
static const char S_CFROM[] = "Copy FROM which disk?";
static const char S_CTO[] = "Copy TO which disk? (the same one: one drive, swapping the disks)";
static const char S_NOTIMG[] = "The selection is not a disk image (.PO, .DSK, .2MG).";
static const char S_SMALL[] = "That disk is smaller than the image.";
static const char S_NODIR[] = "Open a ProDOS directory first: the image goes there.";
static const char S_NOSIZE[] = "Unknown size: neither a ProDOS volume nor a Disk II.";
static const char S_NOROOM[] = "Not enough room on this volume for the image.";
static const char S_NAME[] = "Image name, without suffix";
static const char S_LONG[] = "Name too long for its suffix.";
static const char S_ORDER[] = "P ProDOS order (.PO) or D DOS 3.3 order (.DSK)?";
static const char S_DOT[] = "%s.%s";
static const char S_SLASH[] = "%s/%s";
static const char S_DSK[] = "DSK";
static const char S_PO[] = "PO";
static const char S_EXISTS[] = "A file of that name exists.";
static const char S_CREATE[] = "Cannot create the image file.";
static const char S_DONE[] = "%u blocks %s %s.";
static const char S_WRITTEN[] = "written to";
static const char S_READ[] = "read from";
static const char S_COPIED[] = "copied to";
static const char S_INSERT[] = "Insert the %s disk, then press a key (ESC cancels).";
static const char S_SOURCE[] = "SOURCE";
static const char S_TARGET[] = "TARGET";
static const char S_READING[] = "Reading";
static const char S_WRITING[] = "Writing";
static const char S_FAILED[] = "Failed: %s.";
static const char S_E_CANCEL[] = "cancelled";
static const char S_E_IO[] = "I/O error, no disk or an unformatted one";
static const char S_E_NODEV[] = "no device there";
static const char S_E_WP[] = "the disk is write protected";
static const char S_E_SWITCH[] = "the disk was switched";
static const char S_E_CODE[] = "ProDOS error $%02X";
static const char S_RAM[] = "  /RAM was rebuilt empty.";

#define DI_BLOCK ((unsigned char*)0x3C00)   /* le bloc des appels MLI */
#define DI_MAIN ((unsigned char*)0x3400)    /* quatre blocs de reserve */
#define DI_MAIN_BLOCKS 4
#define DI_AUX 0x2000                       /* quatre-vingts de plus en AUX */
#define DI_AUX_BLOCKS 80
#define DI ((struct DiskImg*)0x3E00)

enum { SIDE_DEVICE, SIDE_PO, SIDE_DSK };
struct Side { unsigned char kind, unit; FILE* f; unsigned long base; };
struct Dev { unsigned char unit, inuse; unsigned int blocks; char name[NAME_LEN]; };
struct DiskImg {
    struct Side src, dst;
    struct Dev dev[8];
    unsigned char ndev, aux_used;
    unsigned int total;
    unsigned char parms[6];
};

/* Le bloc ProDOS b d'une piste occupe deux secteurs physiques (moitie basse
 * puis haute) : ceux-ci, par paire, comme po2dsk.py. */
static const unsigned char DSK_SECTORS[16] = { 0x0, 0xE, 0xD, 0xC, 0xB, 0xA, 0x9, 0x8, 0x7, 0x6, 0x5, 0x4, 0x3, 0x2, 0x1, 0xF };

/* "slot s drive d" de l'unite, dans input. */
static const char* di_where(unsigned char unit)
{
    sprintf(input, S_WHERE, (unit >> 4) & 7, (unit >> 7) + 1);
    return input;
}

/* Lit (write = 0) ou ecrit le bloc `block` du cote `s`, via DI_BLOCK. Rend
 * 0 ou l'erreur ProDOS ; un fichier court vaut une erreur d'E/S. */
static unsigned char di_xfer(struct Side* s, unsigned int block, unsigned char write)
{
    unsigned char half, n = 1;
    unsigned int len = 512;
    unsigned char* p = DI->parms;
    unsigned long off;
    if (s->kind == SIDE_DEVICE) {
        p[0] = 3; p[1] = s->unit;
        p[2] = 0x00; p[3] = 0x3C;
        p[4] = (unsigned char)block; p[5] = (unsigned char)(block >> 8);
        return mli_call(write ? 0x81 : 0x80, p);
    }
    if (s->kind == SIDE_DSK) { n = 2; len = 256; }
    for (half = 0; half < n; ++half) {
        if (s->kind == SIDE_DSK) off = (((unsigned long)(block >> 3) << 4) + DSK_SECTORS[((block & 7) << 1) + half]) << 8;
        else off = (unsigned long)block << 9;
        fseek(s->f, s->base + off, SEEK_SET);
        if ((write ? fwrite(DI_BLOCK + half * 256, 1, len, s->f) : fread(DI_BLOCK + half * 256, 1, len, s->f)) != len) return 0x27;
    }
    return 0;
}

/* Le bloc i de la reserve : DI_BLOCK y va (put) ou en revient. */
static void di_stage(unsigned char i, unsigned char put)
{
    if (i < DI_MAIN_BLOCKS) {
        if (put) memcpy(DI_MAIN + i * 512, DI_BLOCK, 512);
        else memcpy(DI_BLOCK, DI_MAIN + i * 512, 512);
    } else {
        DI->aux_used = 1;
        aux_copy((unsigned)DI_BLOCK, DI_AUX + ((unsigned)(i - DI_MAIN_BLOCKS) << 9), put);
    }
}

static unsigned char di_ask(const char* which)
{
    clear_row(22);
    gotoxy(0, 22);
    cprintf(S_INSERT, which);
    return cgetc() != KEY_ESC;
}

/* Une image .DSK ecrit ses secteurs a des positions eparses dans le fichier
 * (l'ordre DOS 3.3, voir DSK_SECTORS) : le premier saute au-dela de la fin
 * d'un fichier tout neuf, et ProDOS refuse SET_MARK au-dela de l'EOF. On
 * donne donc au fichier sa taille pleine, en zeros et dans l'ordre, avant
 * les ecritures eparses -- elles tombent alors toutes sous l'EOF. Un .PO
 * ecrit bloc apres bloc et n'en aurait pas besoin, mais le pre-remplir ne
 * coute qu'une passe et garde le code simple. */
static unsigned char di_presize(struct Side* s, unsigned int blocks)
{
    unsigned int b;
    memset(copy_buf, 0, 512);
    fseek(s->f, s->base, SEEK_SET);
    for (b = 0; b < blocks; ++b)
        if (fwrite(copy_buf, 1, 512, s->f) != 512) return 0x27;
    return 0;
}

/* Copie DI->total blocs de src vers dst, par passes de la reserve ; avec
 * `swap` (un seul lecteur), demande la disquette a chaque passe. Rend 0,
 * l'erreur ProDOS, ou $FF si l'utilisateur a renonce. */
static unsigned char di_copy(unsigned char swap)
{
    unsigned int done = 0, total = DI->total, left;
    unsigned char n, i, r, per = swap ? DI_MAIN_BLOCKS + DI_AUX_BLOCKS : DI_MAIN_BLOCKS;
    if (DI->dst.kind != SIDE_DEVICE && (r = di_presize(&DI->dst, total))) return r;
    progress_total = 1;
    progress_done = 0;
    while ((left = total - done) != 0) {
        n = left < per ? (unsigned char)left : per;
        if (swap && !di_ask(S_SOURCE)) return 0xFF;
        for (i = 0; i < n; ++i) {
            if ((r = di_xfer(&DI->src, done + i, 0))) return r;
            di_stage(i, 1);
            progress_bar(S_READING, done + i + 1, total);
        }
        if (swap && !di_ask(S_TARGET)) return 0xFF;
        for (i = 0; i < n; ++i) {
            di_stage(i, 0);
            if ((r = di_xfer(&DI->dst, done + i, 1))) return r;
            progress_bar(S_WRITING, done + i + 1, total);
        }
        done += n;
    }
    return 0;
}

/* Les unites de bloc que ProDOS connait (DEVLST), leur volume s'il y en a
 * un (ON_LINE), leur taille (celle du volume, ou 280 pour un Disk II : son
 * pilote est en carte langage, sous $FF00 ou vit celui du /RAM), et si le
 * programme tourne dessus. */
static void di_scan(void)
{
    unsigned char i, n = *(unsigned char*)0xBF31 + 1, len;
    unsigned char* online = copy_buf;
    unsigned char* p = DI->parms;
    unsigned int drv, dummy;
    struct Dev* d;
    DI->ndev = 0;
    for (i = 0; i < n && DI->ndev < 8; ++i) {
        d = &DI->dev[DI->ndev];
        d->unit = ((unsigned char*)0xBF32)[i] & 0xF0;
        drv = ((unsigned int*)0xBF10)[d->unit >> 4];
        d->blocks = drv >= 0xD000 && drv < 0xFF00 ? 280 : 0;
        d->name[0] = 0;
        d->inuse = 0;
        p[0] = 2; p[1] = d->unit;
        p[2] = (unsigned char)((unsigned)online & 0xFF); p[3] = (unsigned char)((unsigned)online >> 8);
        if (!mli_call(0xC5, p) && (len = online[0] & 0x0F) != 0) {
            d->name[0] = '/';
            memcpy(d->name + 1, online + 1, len);
            d->name[len + 1] = 0;
            /* la taille du volume vaut pour celle du disque, sauf sur un
             * Disk II : une disquette fait 280 blocs, quel que soit le
             * volume qu'on y a ecrit */
            if (!d->blocks) volume_blocks(d->name, &d->blocks, &dummy);
            d->inuse = !strncmp(cfg_path, d->name, len + 1) && cfg_path[len + 1] == '/';
        }
        ++DI->ndev;
    }
}

static void di_title(const char* sub)
{
    clrscr();
    revers(1);
    gotoxy(0, 0);
    cprintf("%-79.79s", S_TITLE);
    revers(0);
    cputsxy(0, 2, sub);
}

/* La liste des unites ; rend celle que l'utilisateur choisit par son
 * numero, NULL sur Echap. Pour ecrire (writing), la disquette du programme
 * est refusee. */
static struct Dev* di_pick(const char* what, unsigned char writing)
{
    struct Dev* d = DI->dev;
    unsigned char i;
    char key;
    di_title(what);
    for (i = 0; i < DI->ndev; ++i, ++d) {
        gotoxy(2, 4 + i);
        cprintf(S_DEV, '1' + i, di_where(d->unit), d->name[0] ? (const char*)d->name : S_NOVOL, d->blocks, d->inuse ? S_INUSE : S_EMPTY);
    }
    bar_begin();
    keys_bar(0, S_PICK_KEYS);
    for (;;) {
        key = cgetc();
        if (key == KEY_ESC) return NULL;
        if (key < '1' || key >= '1' + DI->ndev) continue;
        d = &DI->dev[key - '1'];
        if (writing && d->inuse) { message(S_HOLDS); continue; }
        return d;
    }
}

/* L'avertissement, puis le mot ERASE en toutes lettres : rien n'est ecrit
 * avant. */
static unsigned char di_erase(const struct Dev* d)
{
    gotoxy(0, 20);
    revers(1);
    cprintf(S_LOST, di_where(d->unit), d->name[0] ? (const char*)d->name : S_NOVOL);
    revers(0);
    return prompt(S_ERASE, NULL, 0) && !strcmp(input, S_WORD);
}

/* Ouvre l'image `full` (l'entree e) : l'ordre des secteurs d'apres son nom
 * (.DSK ou .DO : DOS 3.3 ; .2MG : son en-tete le dit ; sinon ProDOS), le
 * nombre de blocs d'apres sa taille. Rend 0 si ce n'est pas une image. */
static unsigned char di_open_image(struct Side* s, const struct Entry* e)
{
    unsigned char n = strlen(e->name);
    const char* end = e->name + n;
    unsigned long size = e->size;
    s->kind = SIDE_PO;
    s->base = 0;
    if ((n > 4 && !strcmp(end - 4, ".DSK")) || (n > 3 && !strcmp(end - 3, ".DO"))) s->kind = SIDE_DSK;
    s->f = fopen(full, "rb");
    if (!s->f) return 0;
    if (n > 4 && !strcmp(end - 4, ".2MG")) {
        if (fread(DI_BLOCK, 1, 64, s->f) != 64 || memcmp(DI_BLOCK, "2IMG", 4) || DI_BLOCK[0x0C] > 1) return 0;
        s->kind = DI_BLOCK[0x0C] ? SIDE_PO : SIDE_DSK;
        s->base = *(unsigned long*)(DI_BLOCK + 0x18);
        size = *(unsigned long*)(DI_BLOCK + 0x1C);
    }
    DI->total = (unsigned int)(size >> 9);
    return DI->total != 0 && (size & 511) == 0;
}

static const char* di_error(unsigned char code)
{
    switch (code) {
    case 0xFF: return S_E_CANCEL;
    case 0x27: return S_E_IO;
    case 0x28: return S_E_NODEV;
    case 0x2B: return S_E_WP;
    case 0x2E: return S_E_SWITCH;
    }
    sprintf(input, S_E_CODE, code);
    return input;
}

void __fastcall__ diskimg_entry(const struct A2fcApi* a)
{
    struct Panel* pan = &panels[active];
    const struct Entry* e = &selected;
    struct Dev* from;
    struct Dev* to;
    struct Side* src = &DI->src;
    struct Side* dst = &DI->dst;
    const char* verb;
    unsigned char r = 0, image = pan->count && pan->path[0] && !is_dir(e);
    char key;
    (void)a;
    music_stop();                      /* la banque auxiliaire va servir de reserve */
    a2fc_playing = 0;
    /* Les tampons de blocs vivent dans la page graphique ($2800-$3FFF) : une
     * image vue avant a pu laisser HIRES arme, et 80STORE y router $2000-$3FFF
     * vers la banque AUX -- READ_BLOCK y lirait a cote. On coupe HIRES (le
     * texte, lui, garde 80STORE pour ses colonnes paires) et on remet la
     * lecture/ecriture sur la banque principale. aux_copy fait son propre
     * routage pour la reserve auxiliaire. */
    *(unsigned char*)0xC056 = 0;       /* LORES : $2000-$3FFF hors du routage 80STORE */
    *(unsigned char*)0xC002 = 0;       /* RAMRD banque principale */
    *(unsigned char*)0xC004 = 0;       /* RAMWRT banque principale */
    DI->aux_used = 0;
    src->f = dst->f = NULL;
    di_title(S_INTRO);
    if (image) { gotoxy(2, 4); cprintf(S_W, e->name); }
    cputsxy(2, 5, S_R);
    cputsxy(2, 6, S_O);
    bar_begin();
    keys_bar(0, S_KEYS);
    do key = cgetc() & 0xDF; while (key != 'W' && key != 'R' && key != 'O' && key != 0x1B);
    if (key == 0x1B) return;
    di_scan();
    if (key == 'W') {
        verb = S_WRITTEN;
        if (!image || !full[0] || !di_open_image(src, e)) { strcpy(note, S_NOTIMG); goto out; }
        if (!(to = di_pick(S_TO, 1))) goto out;
        if (to->blocks && to->blocks < DI->total) { strcpy(note, S_SMALL); goto out; }
        if (!di_erase(to)) goto out;
        dst->kind = SIDE_DEVICE;
        dst->unit = to->unit;
        r = di_copy(0);
    } else if (key == 'R') {
        verb = S_READ;
        if (!pan->path[0] || pan->fs) { strcpy(note, S_NODIR); goto out; }
        if (!(to = di_pick(S_FROM, 0))) goto out;
        DI->total = to->blocks;
        if (!DI->total) { strcpy(note, S_NOSIZE); goto out; }
        if (DI->total + (DI->total >> 8) + 2 > pan->free_blocks) { strcpy(note, S_NOROOM); goto out; }
        if (!prompt(S_NAME, NULL, 0)) goto out;
        if (strlen(input) > 11 || strlen(pan->path) + 17 >= PATH_LEN) { strcpy(note, S_LONG); goto out; }
        message(S_ORDER);
        do key = cgetc() & 0xDF; while (key != 'P' && key != 'D' && key != 0x1B);
        if (key == 0x1B) goto out;
        sprintf(reselect, S_DOT, input, key == 'D' ? S_DSK : S_PO);
        sprintf(full, S_SLASH, pan->path, reselect);
        if (exists(full)) { strcpy(note, S_EXISTS); goto out; }
        _filetype = 0x06;
        _auxtype = 0;
        dst->kind = key == 'D' ? SIDE_DSK : SIDE_PO;
        dst->base = 0;
        dst->f = fopen(full, "wb");
        if (!dst->f) { strcpy(note, S_CREATE); goto out; }
        src->kind = SIDE_DEVICE;
        src->unit = to->unit;
        r = di_copy(0);
        if (r) { fclose(dst->f); dst->f = NULL; remove(full); }
    } else {
        verb = S_COPIED;
        if (!(from = di_pick(S_CFROM, 0))) goto out;
        DI->total = from->blocks;
        if (!DI->total) { strcpy(note, S_NOSIZE); goto out; }
        if (!(to = di_pick(S_CTO, 1))) goto out;
        if (to->blocks && to->blocks < DI->total) { strcpy(note, S_SMALL); goto out; }
        if (!di_erase(to)) goto out;
        src->kind = dst->kind = SIDE_DEVICE;
        src->unit = from->unit;
        dst->unit = to->unit;
        r = di_copy(from == to);
    }
    if (!r) sprintf(note, S_DONE, DI->total, verb, di_where(to->unit));
out:
    if (src->f) fclose(src->f);
    if (dst->f && fclose(dst->f) && !r) r = 0x27;
    if (r) { sprintf(note, S_FAILED, di_error(r)); reselect[0] = 0; }
    if (DI->aux_used && ram_format()) strcat(note, S_RAM);
}
#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* Le menu des surcouches -- la grande surcouche MENU                     */
/* ---------------------------------------------------------------------- */

/* ! : la liste des surcouches A2FILE/ .PLG, chacune avec la ligne de description de
 * son en-tete, lancee sur la selection courante. Une commande de plus ne
 * demande plus ni touche ni recompilation : une surcouche d'un tiers, dont
 * la signature est PLUGIN_MAGIC, y parait comme les autres. Entree depose
 * le nom choisi dans `input`, Echap le laisse vide ; le noyau lance ensuite
 * la surcouche par overlay_run. La liste vit dans la page graphique, hors
 * du code de cette surcouche. */
#pragma code-name (push, "MENU")
#pragma rodata-name (push, "MENURO")
struct MenuItem { char name[12]; char desc[52]; };
#define MENU_ITEMS ((struct MenuItem*)0x3000)
#define MENU_MAX 20
void __fastcall__ menu_entry(const struct A2fcApi* a)
{
    struct MenuItem* m = MENU_ITEMS;
    const struct Overlay* hdr = (const struct Overlay*)copy_buf;
    unsigned char n = 0, i, cur = 0, len;
    FILE* f;
    char key;
    (void)a;
    input[0] = 0;
    a2file_file("");
    if (!other_full[0]) { strcpy(note, "The program directory is unknown."); return; }
    other_full[strlen(other_full) - 1] = 0;   /* "/VOL/A2FILE/" -> "/VOL/A2FILE" */
    if (!dir_open(other_full)) { strcpy(note, "A2FILE/ is unreadable."); return; }
    while (n < MENU_MAX && dir_next()) {
        len = strlen(dir_entry.name);
        if (dir_entry.type != 0x06 || len < 5 || strcmp(dir_entry.name + len - 4, ".PLG") || !strcmp(dir_entry.name, "MENU.PLG")) continue;
        memcpy(m[n].name, dir_entry.name, len - 4);
        m[n].name[len - 4] = 0;
        ++n;
    }
    dir_close();
    for (i = 0; i < n; ++i) {          /* l'en-tete de chacune : sa description */
        a2file_file(m[i].name);
        strcat(other_full, ".PLG");
        strcpy(m[i].desc, "(unreadable)");
        f = fopen(other_full, "rb");
        if (!f) continue;
        len = fread(copy_buf, 1, 64, f);
        fclose(f);
        copy_buf[8 + 51] = 0;
        if (len < 9 || (hdr->signature != (unsigned int)main && hdr->signature != PLUGIN_MAGIC)) strcpy(m[i].desc, "(from another build of A2 File Cmd)");
        else if (!hdr->entry) strcpy(m[i].desc, "(no entry point)");
        else strcpy(m[i].desc, hdr->desc);
    }
    clrscr();
    revers(1);
    gotoxy(0, 0);
    cprintf("%-79.79s", "  A2FILE/*.PLG  -  the overlays, run on the selected entry");
    revers(0);
    if (!n) cputsxy(2, 2, "No overlay here.");
    for (;;) {
        for (i = 0; i < n; ++i) {
            if (i == cur) revers(1);
            gotoxy(2, 2 + i);
            cprintf("%-12s %-52s", m[i].name, m[i].desc);
            revers(0);
        }
        bar_begin();
        keys_bar(0, "U/D Choose,RET Run,ESC Back to the panels");
        key = cgetc();
        if (key == KEY_ESC) return;
        if (key == KEY_RETURN && n) { strcpy(input, m[cur].name); return; }
        if (key == KEY_UP && cur) --cur;
        else if (key == KEY_DOWN && cur + 1 < n) ++cur;
        else {
            if (key >= 'a' && key <= 'z') key -= 32;
            for (i = 1; i <= n; ++i) if (m[(cur + i) % n].name[0] == key) { cur = (cur + i) % n; break; }
        }
    }
}
#pragma rodata-name (pop)
#pragma code-name (pop)

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
    ++a2fc_ops;
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
/* La surcouche DELETE, premiere moitie : delete_tree, que le deplacement d'un
 * dossier charge aussi, une fois la copie faite. */
#pragma code-name (push, "DELETE")
#pragma rodata-name (push, "DELETERO")
static unsigned char delete_tree(unsigned char base)
{
    unsigned char n, i, len = strlen(full), ok = 1;
    if (!list_dir(full, base, &n)) { dir_fail(); return 0; }
    for (i = 0; i < n && ok; ++i) {
        if (!push_name(full, pool[base + i].name)) { too_long(); ok = 0; break; }
        if (pool[base + i].type == 0x0F) ok = delete_tree(base + n);
        else if (remove(full)) { report_error("Delete"); ok = 0; }
        else ++a2fc_ops;
        full[len] = 0;
    }
    if (ok && rmdir(full)) { report_error("Delete"); ok = 0; }
    if (ok) ++a2fc_ops;
    return ok;
}
#pragma rodata-name (pop)
#pragma code-name (pop)

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
        { extern const char msg_intoself[]; message(msg_intoself); };
        return 0;
    }
    if (!exists(other_full)) {
        if (mkdir(other_full)) { report_error("Mkdir"); return 0; }
        ++a2fc_ops;
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
    if (dst->fs) { { extern const char msg_otherro[]; message(msg_otherro); }; return 0; }
    if (!dst->path[0]) { message("Open a directory in the other panel."); return 0; }
    if (!strcmp(dst->path, panels[active].path)) { { extern const char msg_samedir[]; message(msg_samedir); }; return 0; }
    return 1;
}

/* ---------------------------------------------------------------------- */
/* La surcouche IMGFS : extraire des fichiers d'une image (C)              */
/* ---------------------------------------------------------------------- */
#pragma code-name (push, "IMGFS")
#pragma rodata-name (push, "IMGFSRO")
#pragma static-locals (push, off)

/* Ecrit le fichier ProDOS de bloc-cle `key`, taille `size`, dans `out`, lu
 * dans l'image ouverte (img_f). Le type de stockage vient de la taille :
 * germe (<= 512 : la cle est le bloc de donnees) ou plant (la cle est un
 * bloc d'index de 256 pointeurs, poids faibles [0..255] puis forts
 * [256..511]) ; un bloc-pointeur nul est un trou (zeros). Les fichiers
 * arborescents (> 128 Ko) sont rares sur une disquette et refuses. `idx`
 * est un tampon de 512 octets hors des tables de panneaux. Rend 0 sur
 * erreur, 2 si le fichier est trop grand. */
static unsigned char img_read_file(unsigned int key, unsigned long size, FILE* out, unsigned char* idx)
{
    unsigned int need = (unsigned int)((size + 511) >> 9), i, n, blk;
    unsigned long left = size;
    if (size > 128UL * 1024) return 2;
    if (size > 512 && !img_read_block(key, idx)) return 0;
    for (i = 0; i < need; ++i) {
        blk = size <= 512 ? key : (idx[i] | ((unsigned int)idx[256 + i] << 8));
        n = left > 512 ? 512 : (unsigned int)left;
        if (blk) { if (!img_read_block(blk, copy_buf)) return 0; }
        else memset(copy_buf, 0, 512);
        if (fwrite(copy_buf, 1, n, out) != n) return 0;
        left -= n;
    }
    return 1;
}

/* C sur une image ouverte comme un dossier : extrait les fichiers marques,
 * sinon le fichier sous le curseur, vers le dossier ProDOS de l'autre
 * panneau (les sous-dossiers sont a entrer et extraire un a un). Le tampon
 * d'index emprunte la table du panneau destination, inutile pendant
 * l'operation ; les panneaux sont relus au retour. */
static void extract_targets(void)
{
    struct Panel* pan = &panels[active];
    struct Panel* dst = &panels[!active];
    unsigned char* idx = (unsigned char*)dst->e;
    unsigned char n, i, done = 0, big = 0, r;
    FILE* out;
    if (dst->fs || !dst->path[0]) { message("Open a ProDOS folder in the other panel."); return; }
    n = pick_targets();
    if (!n) return;
    progress_total = n;
    progress_done = 0;
    i = pan->path[pan->img_len];         /* rouvrir l'image sans perdre le chemin interne */
    pan->path[pan->img_len] = 0;
    r = img_open(pan->path);
    pan->path[pan->img_len] = i;
    if (!r) { message("Cannot reopen the image."); return; }
    for (i = 0; i < n; ++i) {
        const struct Entry* e = &pan->e[picked[i]];
        if (is_up(e) || is_dir(e)) { ++progress_done; continue; }
        if (strlen(dst->path) + 1 + strlen(e->name) >= PATH_LEN) { too_long(); break; }
        sprintf(other_full, "%s/%s", dst->path, e->name);
        _filetype = e->type;
        _auxtype = e->aux;
        out = fopen(other_full, "wb");
        if (!out) { report_error("Create"); break; }
        progress_bar(e->name, 0, e->size);
        r = img_read_file(e->mdate, e->size, out, idx);
        fclose(out);
        if (r != 1) { remove(other_full); if (r == 0) { report_error("Extract"); break; } ++big; }
        else { ++a2fc_ops; ++done; }
        ++progress_done;
        progress_bar(e->name, e->size, e->size);
    }
    fclose(img_f);
    refresh_both();                       /* la table de destination a servi de tampon */
    clear_row(22);
    gotoxy(0, 22);
    cprintf("%u file%s extracted", done, done == 1 ? "" : "s");
    if (big) cprintf(", %u too big (>128K)", big);
    cputc('.');
}

void __fastcall__ imgfs_entry(const struct A2fcApi* a)
{
    (void)a;
    extract_targets();
}
#pragma static-locals (pop)
#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* La surcouche DOS33 : catalogue DOS 3.3, extraction, et M                */
/* ---------------------------------------------------------------------- */
#pragma code-name (push, "DOS33")
#pragma rodata-name (push, "DOS33RO")
#pragma static-locals (push, off)

/* C sur une image ou un disque DOS 3.3 : extrait les fichiers marques (sinon
 * celui sous le curseur) vers le dossier ProDOS de l'autre panneau. On suit
 * la liste T/S de chaque fichier ; les octets de tete propres a DOS sont otes
 * (deux pour un Applesoft/Integer, quatre pour un binaire) pour que le
 * fichier soit utilisable, le reste des secteurs est ecrit tel quel (le
 * remplissage final d'un dernier secteur est sans consequence). Le tampon T/S
 * emprunte la table du panneau destination, inutile pendant l'operation. */
static void dos_extract(void)
{
    struct Panel* pan = &panels[active];
    struct Panel* dst = &panels[!active];
    unsigned char* tsbuf = (unsigned char*)dst->e;
    unsigned char n, i, done = 0, r;
    FILE* out;
    if (dst->fs || !dst->path[0]) { message("Open a ProDOS folder in the other panel."); return; }
    n = pick_targets();
    if (!n) return;
    dos_unit = 0;
    if (pan->img_len) {
        i = pan->path[pan->img_len];
        pan->path[pan->img_len] = 0;
        r = img_open(pan->path);
        pan->path[pan->img_len] = i;
        if (!r) { message("Cannot reopen the image."); return; }
    } else dos_unit = (unsigned char)pan->dir_key;
    for (i = 0; i < n; ++i) {
        const struct Entry* e = &pan->e[picked[i]];
        unsigned char tslt = (unsigned char)(e->mdate >> 8), tsls = (unsigned char)e->mdate;
        unsigned char t, j, skip = 0, first = 1;
        if (is_up(e)) continue;
        if (strlen(dst->path) + 1 + strlen(e->name) >= PATH_LEN) { too_long(); break; }
        sprintf(other_full, "%s/%s", dst->path, e->name);
        _filetype = e->type;
        _auxtype = e->type == 0xFC ? 0x0801 : 0;
        out = fopen(other_full, "wb");
        if (!out) { report_error("Create"); break; }
        r = 1;
        while (tslt && tslt < 35 && r) {
            unsigned char nt = copy_buf[1], ns = copy_buf[2];
            if (!dos_read_sector(tslt, tsls)) { r = 0; break; }
            nt = copy_buf[1]; ns = copy_buf[2];
            memcpy(tsbuf, copy_buf + 0x0C, 244);
            tslt = nt; tsls = ns;
            for (j = 0; j < 122; ++j) {
                t = tsbuf[j * 2];
                if (!t) { tslt = 0; break; }
                if (!dos_read_sector(t, tsbuf[j * 2 + 1])) { r = 0; break; }
                if (first) { first = 0; skip = (e->type == 0xFC || e->type == 0xFA) ? 2 : e->type == 0x06 ? 4 : 0; }
                if (fwrite(copy_buf + skip, 1, 256 - skip, out) != 256 - skip) { r = 0; break; }
                skip = 0;
            }
        }
        fclose(out);
        if (!r) { remove(other_full); report_error("Extract"); break; }
        ++a2fc_ops;
        ++done;
    }
    if (img_f) { fclose(img_f); img_f = 0; }
    refresh_both();
    clear_row(22);
    gotoxy(0, 22);
    cprintf("%u file%s extracted.", done, done == 1 ? "" : "s");
}

void __fastcall__ dos33_entry(const struct A2fcApi* a)
{
    (void)a;
    dos_extract();
}
#pragma static-locals (pop)
#pragma rodata-name (pop)
#pragma code-name (pop)

/* ---------------------------------------------------------------------- */
/* La surcouche UNSHRINK : une archive ShrinkIt (.SHK, NuFX) extraite vers   */
/* le dossier de l'autre panneau -- dans A2FILE/UNSHRINK.PLG, grande         */
/* surcouche. Le coeur LZW/RLE est en assembleur (src/unshrink.s), en tete    */
/* de la surcouche ($1B00-$1FFF) et recopie en AUX a la meme adresse pour    */
/* tourner sous RAMRD/RAMWRT AUX, ou vivent les tables du dictionnaire ; ce  */
/* pilote C, lui, reste en MAIN ($2000-$2FFF). Lancee par le menu ! sur     */
/* l'archive selectionnee.                                                   */
/* ---------------------------------------------------------------------- */
#pragma code-name (push, "UNSHRINK")
#pragma rodata-name (push, "UNSHRINKRO")
#pragma static-locals (push, off)

/* Toute chaine de cette surcouche est un tableau NOMME (const char[]), pas
 * un litteral "..." : cc65 regroupe les litteraux dans RODATA -- la fenetre
 * principale, pleine au bit pres, et dont chaque octet de plus rapproche la
 * fin d'A2FILE.CODE de $BF00, ou le lanceur tient sa pile C (31 octets de
 * litteral ont suffi a figer l'amorcage). Un tableau nomme suit le segment
 * UNSHRINKRO, dans le fichier de la surcouche. De meme, l'etat volumineux
 * vit dans une structure a adresse fixe, $3000, hors de LOWBSS (plein) et
 * de la pile C (192 octets) ; les locales vraies vont sur la pile C
 * (static-locals off). */

/* Le coeur en assembleur, src/unshrink.s. Ses adresses AUX, repetees ici. */
void __fastcall__ us_init(unsigned int fmt_esc);
unsigned int __fastcall__ us_chunk(unsigned int in_addr);
#define US_INBUF  0x6000            /* la fenetre d'entree, 8 Ko, en AUX */
#define US_OUTBUF 0x8000            /* le bloc decode, 4096 octets, en AUX */
#define US_WINDOW 8192
#define US_NEED   4100              /* un bloc comprime entier, en-tete compris */

struct UsState {
    FILE* in;
    FILE* out;
    unsigned int records, threads, attrib, filetype, auxtype, storage;
    unsigned int win_len, win_pos, n_done, name_len;
    unsigned long teof, ceof, rem_in, rem_out, total, done;
    unsigned char fmt, klass, kind, sep, disk;
    char name[17];
    unsigned char th[8 * 16];       /* jusqu'a huit en-tetes de fil */
    unsigned char hdr[256];         /* les attributs d'un enregistrement */
};
#define US ((struct UsState*)0x3000)
#define U16(p, o) ((unsigned int)(p)[o] | ((unsigned int)(p)[(o) + 1] << 8))
/* 32 bits sans aucune routine d'appui (decalage long, multiplication) : le
 * moindre helper de cc65 que le resident n'a pas deja se lie dans SA fenetre,
 * pleine au bit pres -- memcmp et la multiplication 32 bits ont coute 91
 * octets de trop au premier essai. D'ou l'union par octets, le compare a la
 * main, et blocs*512 en decalages. */
static unsigned long us_u32(const unsigned char* p)
{
    union { unsigned long l; unsigned char b[4]; } u;
    u.b[0] = p[0]; u.b[1] = p[1]; u.b[2] = p[2]; u.b[3] = p[3];
    return u.l;
}
static unsigned char us_eq(const unsigned char* a, const unsigned char* b, unsigned char n)
{
    while (n--) if (*a++ != *b++) return 0;
    return 1;
}
#define U32(p, o) us_u32((p) + (o))

static const char us_notfile[]  = "Select a ShrinkIt archive (.SHK).";
static const char us_notarch[]  = "Not a ShrinkIt (NuFX) archive.";
static const char us_notdir[]   = "The other panel must show a ProDOS directory.";
static const char us_noram[]    = "Extract to a disk, not /RAM (it shares aux memory).";
static const char us_corrupt[]  = "Corrupt archive.";
static const char us_unsupp[]   = "Unsupported compression (only LZW/1, LZW/2, stored).";
static const char us_done[]     = "%u file(s) extracted.";
static const char us_doneram[]  = "%u file(s) extracted. /RAM was rebuilt empty.";
static const char us_path[]     = "%s/%s";
static const char us_po[]       = ".PO";
static const char us_create[]   = "Create";
static const char us_extract[]  = "Extract";
static const char us_rb[]       = "rb";
static const char us_wb[]       = "wb";
static const unsigned char us_magic_master[] = { 0x4E, 0xF5, 0x46, 0xE9, 0x6C, 0xE5 };
static const unsigned char us_magic_record[] = { 0x4E, 0xF5, 0x46, 0xD8 };

/* Garde la fenetre d'entree AUX pleine d'au moins un bloc entier : ramene
 * le reste en tete (par la principale, 512 par 512), puis lit la suite du
 * fil. Rend 0 sur une lecture manquee. */
static unsigned char us_fill(void)
{
    unsigned int left = US->win_len - US->win_pos, off, n;
    if (left >= US_NEED || !US->rem_in) return 1;
    for (off = 0; off < left; off += 512) {
        aux_copy((unsigned int)copy_buf, US_INBUF + US->win_pos + off, 0);
        aux_copy((unsigned int)copy_buf, US_INBUF + off, 1);
    }
    US->win_len = left;
    US->win_pos = 0;
    while (US->win_len <= US_WINDOW - 512 && US->rem_in) {
        n = US->rem_in > 512 ? 512 : (unsigned int)US->rem_in;
        if (fread(copy_buf, 1, n, US->in) != n) return 0;
        if (n < 512) memset(copy_buf + n, 0, 512 - n);
        aux_copy((unsigned int)copy_buf, US_INBUF + US->win_len, 1);
        US->win_len += 512;
        US->rem_in -= n;
    }
    return 1;
}

/* Les n premiers octets du bloc decode (OUTBUF, AUX) dans le fichier. */
static unsigned char us_write(unsigned int n)
{
    unsigned int off, k;
    for (off = 0; off < n; off += 512) {
        k = n - off > 512 ? 512 : n - off;
        aux_copy((unsigned int)copy_buf, US_OUTBUF + off, 0);
        if (fwrite(copy_buf, 1, k, US->out) != k) return 0;
    }
    return 1;
}

/* Un nom ProDOS a partir du nom archive : le dernier composant, majuscules,
 * lettres, chiffres et points, une lettre en tete, 15 caracteres. */
static void us_prodos_name(const char* src, unsigned int len)
{
    unsigned int i, start = 0, n = 0;
    char c;
    for (i = 0; i < len; ++i) if (src[i] == (char)US->sep) start = i + 1;
    for (i = start; i < len && n < 15; ++i) {
        c = src[i];
        if (c >= 'a' && c <= 'z') c -= 32;
        if (!((c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9') || c == '.')) c = '.';
        if (!n && !(c >= 'A' && c <= 'Z')) { US->name[n++] = 'X'; if (n == 15) break; }
        US->name[n++] = c;
    }
    if (!n) US->name[n++] = 'X';
    US->name[n] = 0;
    US->name_len = n;
}

/* Un fil de donnees (fourche de donnees ou image disque) vers le dossier de
 * l'autre panneau. Rend 0 sur un echec deja signale. */
static unsigned char us_extract_thread(void)
{
    unsigned int n, used, hdr;
    unsigned char r = 1;
    if (US->disk) {                        /* une image disque : NOM.PO, bloc par 512 */
        if (US->name_len > 12) US->name_len = 12;
        strcpy(US->name + US->name_len, us_po);
        /* blocs * 512, par une union de deux entiers 16 bits (pas de decalage
         * long, dont les routines d'appui se lieraient dans le resident, plein) :
         * mot faible = blocs << 9, mot fort = blocs >> 7. */
        { union { unsigned long l; unsigned int w[2]; } ro;
          ro.w[0] = US->auxtype << 9; ro.w[1] = US->auxtype >> 7; US->rem_out = ro.l; }
        _filetype = 0x06;
        _auxtype = 0;
    } else {
        US->rem_out = US->teof;
        _filetype = (unsigned char)US->filetype;
        _auxtype = US->auxtype;
    }
    US->total = US->rem_out;
    US->done = 0;
    sprintf(other_full, us_path, panels[!active].path, US->name);
    US->out = fopen(other_full, us_wb);
    if (!US->out) { report_error(us_create); return 0; }
    US->rem_in = US->ceof;
    if (US->fmt == 0) {                    /* stocke tel quel */
        while (US->rem_out && r) {
            n = US->rem_out > 512 ? 512 : (unsigned int)US->rem_out;
            if (fread(copy_buf, 1, n, US->in) != n || fwrite(copy_buf, 1, n, US->out) != n) r = 0;
            else { US->rem_out -= n; US->rem_in -= n; US->done += n; progress_bar(US->name, US->done, US->total); }
        }
    } else {                               /* LZW/1 ou LZW/2 : l'en-tete du flux, puis bloc par bloc */
        hdr = US->fmt == 2 ? 4 : 2;        /* LZW/1 : crc(2) vol esc ; LZW/2 : vol esc */
        if (fread(copy_buf, 1, hdr, US->in) != hdr) r = 0;
        else {
            US->rem_in -= hdr;
            us_init(((unsigned int)copy_buf[hdr - 1] << 8) | US->fmt);
            US->win_len = US->win_pos = 0;
            while (US->rem_out && r) {
                if (!us_fill()) { r = 0; break; }
                used = us_chunk(US_INBUF + US->win_pos);
                US->win_pos += used;
                n = US->rem_out > 4096 ? 4096 : (unsigned int)US->rem_out;
                if (!us_write(n)) { r = 0; break; }
                US->rem_out -= n;
                US->done += n;
                progress_bar(US->name, US->done, US->total);
            }
        }
    }
    fclose(US->out);
    if (!r) { remove(other_full); report_error(us_extract); return 0; }
    /* ce qui reste du fil (l'octet de bourrage de ShrinkIt, un fil tronque) */
    if (US->rem_in) fseek(US->in, (long)US->rem_in, SEEK_CUR);
    ++US->n_done;
    return 1;
}

void __fastcall__ unshrink_entry(const struct A2fcApi* a)
{
    struct Panel* pan = &panels[active];
    unsigned int i, t, len;
    unsigned char* th;
    (void)a;
    if (!pan->count || !pan->path[0] || is_dir(&selected) || !full[0]) { strcpy(note, us_notfile); return; }
    if (!panels[!active].path[0] || panels[!active].fs) { strcpy(note, us_notdir); return; }
    /* La banque auxiliaire porte le dictionnaire LZW ET le disque /RAM :
     * extraire vers /RAM le detruirait (et ram_format le refait vide
     * ensuite). On refuse ; toute autre volume convient. */
    if (!strcmp(panels[!active].path, "/RAM")) { strcpy(note, us_noram); return; }
    music_stop();                          /* la banque auxiliaire va servir de dictionnaire */
    a2fc_playing = 0;
    /* Le coeur, en tete de la surcouche ($1B00-$1FFF), recopie en AUX a la
     * meme adresse : c'est cette copie qui s'executera sous RAMRD AUX. */
    aux_copy(0x1B00, 0x1B00, 1);
    aux_copy(0x1D00, 0x1D00, 1);
    aux_copy(0x1F00, 0x1F00, 1);
    US->n_done = 0;
    US->in = fopen(full, us_rb);
    if (!US->in) { report_error(us_extract); return; }
    if (fread(US->hdr, 1, 48, US->in) != 48) goto corrupt;
    if (US->hdr[0] == 0x0A && US->hdr[1] == 0x47 && US->hdr[2] == 0x4C) {   /* Binary II : 128 octets a sauter */
        if (fread(US->hdr + 48, 1, 80, US->in) != 80 || fread(US->hdr, 1, 48, US->in) != 48) goto corrupt;
    }
    if (!us_eq(US->hdr, us_magic_master, 6)) { strcpy(note, us_notarch); fclose(US->in); return; }
    US->records = U16(US->hdr, 8);
    for (i = 0; i < US->records; ++i) {
        /* l'enregistrement : magic, crc, attrib_count, puis le reste des attributs */
        if (fread(US->hdr, 1, 8, US->in) != 8 || !us_eq(US->hdr, us_magic_record, 4)) goto corrupt;
        US->attrib = U16(US->hdr, 6);
        if (US->attrib < 8 || US->attrib > 256) goto corrupt;
        if (fread(US->hdr + 8, 1, US->attrib - 8, US->in) != US->attrib - 8) goto corrupt;
        US->threads = U16(US->hdr, 0x0A);
        US->sep = US->hdr[0x10];
        US->filetype = U16(US->hdr, 0x16);
        US->auxtype = U16(US->hdr, 0x1A);
        US->storage = U16(US->hdr, 0x1E);
        len = U16(US->hdr, US->attrib - 2);            /* nom dans l'en-tete (ancien ShrinkIt) */
        US->name[0] = 0;
        US->name_len = 0;
        if (len) {
            if (len > 255 || fread(US->hdr, 1, len, US->in) != len) goto corrupt;
            us_prodos_name((char*)US->hdr, len);
        }
        if (US->threads > 8) goto corrupt;
        if (fread(US->th, 1, US->threads * 16, US->in) != US->threads * 16) goto corrupt;
        for (t = 0; t < US->threads; ++t) {
            th = US->th + t * 16;
            US->klass = th[0];
            US->fmt = th[2];
            US->kind = th[4];
            US->teof = U32(th, 8);
            US->ceof = U32(th, 12);
            if (US->klass == 3 && US->kind == 0) {              /* le nom du fichier */
                len = US->ceof > 512 ? 512 : (unsigned int)US->ceof;
                if (fread(copy_buf, 1, len, US->in) != len) goto corrupt;
                if (US->ceof > len) fseek(US->in, (long)(US->ceof - len), SEEK_CUR);
                us_prodos_name((char*)copy_buf, US->teof > len ? len : (unsigned int)US->teof);
            } else if (US->klass == 2 && (US->kind == 0 || US->kind == 1)) {   /* donnees ou image disque */
                if (US->fmt != 0 && US->fmt != 2 && US->fmt != 3) {
                    strcpy(note, us_unsupp);
                    fseek(US->in, (long)US->ceof, SEEK_CUR);
                    continue;
                }
                US->disk = US->kind == 1;
                if (!US->name_len) us_prodos_name(us_create, 6);   /* sans nom : "CREATE" */
                if (!us_extract_thread()) { fclose(US->in); goto out; }
            } else {
                fseek(US->in, (long)US->ceof, SEEK_CUR);       /* fourche de ressources, commentaire */
            }
        }
    }
    fclose(US->in);
    sprintf(note, ram_format() ? us_doneram : us_done, US->n_done);
    goto out;
corrupt:
    fclose(US->in);
    strcpy(note, us_corrupt);
out:
    strcpy(reselect, selected.name);
}

#pragma static-locals (pop)
#pragma rodata-name (pop)
#pragma code-name (pop)

static void copy_or_move(unsigned char move)
{
    struct Panel* pan = &panels[active];
    unsigned char n, i, done = 0;
    unsigned int sub;
    if (pan->fs == FS_DOS33) { overlay_run("DOS33", 'C'); return; }   /* extraction DOS 3.3 */
    if (pan->fs) { overlay_run("IMGFS", 0); return; }   /* extraction d'une image ProDOS */
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
            if (is_dir(e) ? !(overlay("DELETE") && delete_tree(0)) : remove(full) != 0) { if (!is_dir(e)) report_error("Delete source"); break; }
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

/* La surcouche DELETE, seconde moitie : la commande D. */
#pragma code-name (push, "DELETE")
#pragma rodata-name (push, "DELETERO")
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
        else ++a2fc_ops;
        ++done;
    }
    refresh_both();
    if (done == n) {
        clear_row(22);
        gotoxy(0, 22);
        cprintf("%u item%s deleted.", done, done > 1 ? "s" : "");
    }
}

void __fastcall__ delete_entry(const struct A2fcApi* a)
{
    (void)a;
    delete_targets();
}
#pragma rodata-name (pop)
#pragma code-name (pop)

/* La surcouche ATTR, dans A2FILE/ATTR.PLG : R, K, A et L. */
#pragma code-name (push, "ATTR")
#pragma rodata-name (push, "ATTRRO")
static void rename_selected(const struct Entry* e)
{
    if (is_up(e) || !panels[active].path[0]) { message("Select something to rename."); return; }
    if (!prompt("New name", e->name, 0)) return;
    if (!build_full(full, &panels[active], e)) { too_long(); return; }
    if (strlen(panels[active].path) + 1 + strlen(input) >= PATH_LEN) { too_long(); return; }
    sprintf(other_full, "%s/%s", panels[active].path, input);
    if (rename(full, other_full)) { report_error("Rename"); return; }
    ++a2fc_ops;
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
    ++a2fc_ops;
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
    ++a2fc_ops;
    strcpy(input, e->name);
    read_panel(active);
    select_name(&panels[active], input);
    show_active();
}

void __fastcall__ attr_entry(const struct A2fcApi* a)
{
    struct Panel* pan = &panels[active];
    const struct Entry* e = &pan->e[pan->cursor];
    (void)a;
    if (api.arg == 'K') make_directory();
    else if (!pan->count) return;
    else if (api.arg == 'R') rename_selected(e);
    else change_attributes(e, api.arg == 'L');
}
#pragma rodata-name (pop)
#pragma code-name (pop)

/* La surcouche RUN, dans A2FILE/RUN.PLG : X, F, et Entree sur un SYS ou un
 * BAS. */
#pragma code-name (push, "RUN")
#pragma rodata-name (push, "RUNRO")
/* Charge le fichier `full` a `addr` et y saute, sans retour, par le talon
 * de chain.s : quelle que soit sa taille, il ecrase A2FC sans dommage.
 * La musique est coupee, les preferences ecrites. */
static void launch_file(unsigned int addr)
{
    if (!exists(full)) {
        /* _oserror porte le vrai code de GET_FILE_INFO (a2fc_mli.s le pose) :
         * $46 "file not found" -- typiquement BASIC.SYSTEM absent du volume
         * d'un BAS (un /RAM, un disque sans systeme) -- ou $2E/$2F si le
         * disque a change ou manque. report_error le rend en clair. */
        chain_command("");   /* sinon un SYS lance ensuite recevrait le "-NOM" en $2006 */
        report_error("Run");
        return;
    }
    music_stop();
    save_config();
    clrscr();
    chain_addr = addr;
    chain_load(full);
}

/* X : un SYS est lu en $2000, la ou ProDOS l'aurait mis, un BIN a son
 * auxtype. Un BAS ne se lance pas seul : c'est BASIC.SYSTEM qu'on charge, le
 * nom du programme depose en $2006 par chain_command -- il en fait la
 * commande "-NOM" au demarrage, exactement comme Bitsy Bye. BASIC.SYSTEM est
 * cherche a la racine du volume du programme, sa place d'usage, sinon sur
 * le volume amorce (basic_path). */
static const char run_pick[]  = "Select a program.";
static const char run_range[] = "BIN must load in $0800-$BAFF.";
static const char run_ask[]   = "Run %s? No return to A2FC.";
static const char run_basic[] = "/BASIC.SYSTEM";

/* BASIC.SYSTEM dans `full` : a la racine du volume du programme, sa place
 * d'usage ; sinon a celle du volume amorce -- un BAS sur /RAM, sur un disque
 * de donnees ou sur le disque dur part quand meme, avec le BASIC.SYSTEM de
 * la disquette d'A2FC. */
static void basic_path(void)
{
    char* s;
    strcpy(full, panels[active].path);
    s = strchr(full + 1, '/'); if (s) *s = 0;          /* "/VOL/DIR" -> "/VOL" */
    strcat(full, run_basic);
    if (exists(full)) return;
    strcpy(full, cfg_path);
    s = strchr(full + 1, '/'); if (s) *s = 0;          /* "/VOL/A2FILE/A2FILE.CFG" -> "/VOL" */
    strcat(full, run_basic);
}

static void run_selected(const struct Entry* e)
{
    unsigned int addr = e->type == 0xFF ? 0x2000 : e->aux;
    unsigned char bas = e->type == 0xFC, whole = 0;
    if (is_dir(e) || !panels[active].path[0]) { message(run_pick); return; }
    if (bas) {
        /* BASIC.SYSTEM (basic_path) recoit le programme par son chemin
         * complet "-/VOL/DIR/NOM" quand il tient dans le talon de chain.s
         * (46 caracteres) : il se resout quel que soit le prefixe -- et
         * BASIC.SYSTEM pose le sien sur son propre volume, d'ou
         * "-A2FILE.SYSTEM" (le retour que l'aide annonce) revient quand il
         * vient de la disquette d'A2FC. Trop long, on retombe sur l'ancien
         * comportement (prefixe = dossier du programme, "-NOM", sans retour
         * possible). BASIC.SYSTEM absent : launch_file dira "Run failed". */
        whole = build_full(other_full, &panels[active], e) && strlen(other_full) <= 46;
        basic_path();
        addr = 0x2000;
    } else {
        if (e->type != 0xFF && e->type != 0x06) { extern const char msg_sysonly[]; message(msg_sysonly); return; }
        if (addr < 0x0800 || (unsigned long)addr + e->size > 0xBB00) { message(run_range); return; }
        if (!build_full(full, &panels[active], e)) { too_long(); return; }
    }
    sprintf(question, run_ask, e->name);
    if (!confirm(question)) return;
    if (bas && whole) {                    /* prefixe = racine, "-/VOL/DIR/NOM" */
        chain_command(other_full);
        strcpy(full, panels[active].path);
        { char* s = strchr(full + 1, '/'); if (s) *s = 0; }
        chdir(full);
        basic_path();
    } else {
        if (bas) chain_command(e->name);
        chdir(panels[active].path);
    }
    launch_file(addr);
}

/* F : le formateur, A2FILE/FORMAT.SYS a cote de A2FILE.CODE (Bitsy Bye le
 * propose aussi), lance depuis la racine du volume ; il relance A2FC en
 * sortant. */
static const char fmt_ask[] = "Open the disk formatter?";
static const char fmt_sys[] = "A2FILE/FORMAT.SYS";

static void format_disk(void)
{
    if (!confirm(fmt_ask)) return;
    strcpy(full, cfg_path);
    { char* s = strchr(full + 1, '/'); if (s) *s = 0; }   /* "/VOL/A2FILE/A2FILE.CFG" -> "/VOL" */
    chdir(full);
    strcpy(full, fmt_sys);
    launch_file(0x2000);
}

void __fastcall__ run_entry(const struct A2fcApi* a)
{
    struct Panel* pan = &panels[active];
    (void)a;
    if (api.arg == 'F') format_disk();
    else if (pan->count) run_selected(&pan->e[pan->cursor]);
}
#pragma rodata-name (pop)
#pragma code-name (pop)

/* Entree sur un fichier .PO/.DSK/.DO/.2MG d'un vrai dossier : l'ouvrir en
 * lecture comme un dossier (read_image_panel). Le chemin de l'image devient
 * pan->path, pan->fs son ordre, et le repertoire de volume (bloc 2) s'affiche.
 * Rend 1 si l'entree etait une image (traitee), 0 sinon. */
static unsigned char open_image(struct Panel* pan, const struct Entry* e)
{
    unsigned char ord = pan->fs ? FS_PRODOS : image_order(e->name);
    char* slash;
    if (!ord || e->size < 512 || ((e->size & 511) && (e->size & 511) != 64)) return 0;   /* 64 : l'en-tete 2IMG */
    if (!build_full(full, pan, e)) { too_long(); return 1; }
    strcpy(input, e->name);
    strcpy(pan->path, full);
    pan->img_len = strlen(full);
    pan->fs = ord;
    pan->dir_key = 2;
    pan->cursor = pan->top = pan->first = 0;
    if (!read_panel(active)) {      /* pas un volume ProDOS : revenir au dossier */
        strcpy(pan->path, full);
        slash = strrchr(pan->path, '/');
        if (slash) *slash = 0; else pan->path[0] = 0;
        pan->fs = FS_PRODOS;
        open_path(pan);
        select_name(pan, input);
        { extern const char msg_notimg[]; message(msg_notimg); };
    }
    show_active();
    return 1;
}

static void open_selected(void)
{
    struct Panel* pan = &panels[active];
    const struct Entry* e;
    if (!pan->count) return;
    e = &pan->e[pan->cursor];
    if (!pan->path[0] && is_dir(e) && !e->access) {   /* un vrai disque DOS 3.3 de la liste */
        pan->fs = FS_DOS33;
        pan->img_len = 0;
        pan->dir_key = e->mdate;                       /* l'unite ProDOS */
        strcpy(pan->path, "/DOS 3.3");
        pan->cursor = pan->top = pan->first = 0;
        read_panel(active);
        show_active();
        return;
    }
    if (is_dir(e)) { enter_dir(pan, e); show_active(); return; }
    if (open_image(pan, e)) return;
    if (!build_full(full, pan, e)) { too_long(); return; }
    if (looks_like_image(e)) view_image();
    else if (looks_like_music(e)) overlay_run("MUSIC", 0);
    else if (e->type == 0x04) { if (overlay("TEXT")) view_text(full); }
    else if (e->type == 0x1A) overlay_run("AWP", 0);
    else if (e->type == 0xFF || e->type == 0xFC) overlay_run("RUN", 'X');
    else if (overlay("HEX")) view_hex(full, e->size);
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
    land(pan->cursor + 1 < pan->count ? pan->cursor + 1 : pan->cursor);
}

/* Ctrl-T marque tous les fichiers du panneau (mode 1), Ctrl-N les demarque
 * tous (0), * inverse les marques (2) ; les dossiers ne se marquent pas. */
static void retag(unsigned char mode)
{
    struct Panel* pan = &panels[active];
    unsigned char i;
    if (!pan->path[0]) return;
    for (i = 0; i < pan->count; ++i)
        set_tag(pan, i, !is_dir(&pan->e[i]) && (mode == 2 ? !tagged(pan, i) : mode));
    show_active();
}

/* M : marque les fichiers absents de l'autre panneau ou de taille
 * differente, la base d'une synchronisation par C. */
/* ' puis une touche : l'entree suivante dont le nom commence par elle. */
static void find_letter(void)
{
    struct Panel* pan = &panels[active];
    unsigned char i, j;
    char key;
    message("Jump to name starting with: ");
    key = cgetc();
    clear_row(22);
    if (key >= 'a' && key <= 'z') key -= 32;
    if (!pan->count) return;
    for (i = 1; i <= pan->count; ++i) {
        j = (pan->cursor + i) % pan->count;
        if (pan->e[j].name[pan->path[0] ? 0 : 1] == key) { land(j); return; }
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
    land((unsigned char)target);
}

static void swap_panels(void)
{
    active = !active;
    draw_panel(0);
    draw_panel(1);
    draw_status();
    draw_info();
}

/* La touche du bouton de la barre des commandes sous la colonne x, d'apres
 * MAIN_KEYS et la mise en page de keys_bar : trois colonnes de touche, le
 * libelle, un espace. Une touche d'une lettre est elle-meme ; TAB, RET et
 * SPC sont les touches qu'ils nomment. 0 entre deux boutons. */
static char key_of(const char* s)
{
    return s[1] == ' ' ? *s : *s == 'T' ? KEY_TAB : *s == 'R' ? KEY_RETURN : ' ';
}

static char bar_key(unsigned char x)
{
    const char* s = MAIN_KEYS;
    unsigned char x0 = 0, w;
    char key;
    while (*s) {
        key = key_of(s);
        s = strchr(s, ' ') + 1;
        for (w = 3; *s && *s != ','; ++s) ++w;
        if (x < x0 + w) return key;
        x0 += w + 1;
        if (*s) ++s;
    }
    return 0;
}

/* 1..9 et 0 : les dix boutons de la barre, dans l'ordre -- les touches de
 * fonction de Norton Commander et d'A2Command. */
static char bar_nth(unsigned char n)
{
    const char* s = MAIN_KEYS;
    while (n--) { s = strchr(s, ','); if (!s) return 0; ++s; }
    return key_of(s);
}

/* Un clic. Sur la barre des commandes, la touche du bouton. Sur une entree,
 * la selection -- le panneau devient actif s'il ne l'etait pas -- ou
 * l'ouverture si elle etait deja selectionnee : deux clics ouvrent. Sur
 * l'en-tete d'un panneau, le tri (la ligne des colonnes) ou le dossier
 * parent (le chemin). Rend la touche equivalente, 0 quand tout est fait. */
static char click(void)
{
    unsigned char x = mouse_x, y = mouse_y, i, swapped;
    struct Panel* pan;
    if (y == 23) return bar_key(x);
    if (y >= 20) return 0;
    swapped = (x >= 40) != active;
    if (swapped) swap_panels();
    pan = &panels[active];
    if (y < 2) return swapped ? 0 : y ? 's' : KEY_ESC;
    i = pan->top + y - 2;
    if (i >= pan->count) return 0;
    if (i == pan->cursor) return swapped ? 0 : KEY_RETURN;
    land(i);
    return 0;
}

/* Attend une touche, ou un clic quand une souris est la. Le pointeur suit
 * la souris des qu'elle a bouge une fois, et s'efface avant que la main ne
 * revienne, pour qu'aucun redessin ne le recouvre. Un clic rend la touche
 * qu'il vaut, 0 s'il a tout fait lui-meme. */
static char wait_key(void)
{
    unsigned char st;
    char key;
    if (!a2fc_mouse) return cgetc();
    if (pointer) mouse_show();
    for (;;) {
        if (kbhit()) { key = cgetc(); break; }
        st = mouse_read();
        if (st & 0x20) { pointer = 1; mouse_show(); }
        if ((st & 0xC0) == 0x80) { mouse_hide(); key = click(); break; }
    }
    mouse_hide();
    return key;
}

/* La table de services : ce qu'une surcouche d'un tiers recoit a son point
 * d'entree (a2fc_plugin.h). Les surcouches du programme n'en ont pas
 * besoin, elles sont liees avec lui. */
static struct A2fcApi api = {
    A2FC_API_VERSION, 0,
    panels, &active, full, other_full, input, copy_buf, &dir_entry,
    message, confirm, prompt, progress_bar, keys_bar, bar_begin, draw_all, read_panel, report_error, wait_key,
    build_full, dir_open, dir_next, dir_close, mli_call,
    fopen, fread, fwrite, fclose, fseek, remove, cprintf, sprintf, cputs, cputc, gotoxy, revers, cclearxy, clrscr, cgetc,
    memcpy, memset, strcpy, strcmp, strlen, &_filetype, &_auxtype, reselect, note, &selected };

int main(void)
{
    char key;
    struct Panel* pan;
    videomode(VIDEOMODE_80COL);
    memset(_LOWBSS_RUN__, 0, (size_t)_LOWBSS_SIZE__);
    a2fc_slot = 0xFF;
    panels[0].e = ENTRIES;
    panels[1].e = ENTRIES + MAX_ENTRIES;
    /* Le panneau gauche s'ouvre sur le volume amorce, le droit sur son
     * dossier DEMO ; sans prefixe, ou sans DEMO, read_panel retombe sur la
     * liste des volumes, ce qui est aussi un bon point de depart. */
    if (!getcwd(panels[0].path, PATH_LEN)) panels[0].path[0] = 0;
    strcpy(panels[1].path, panels[0].path);
    if (panels[1].path[0] && strlen(panels[1].path) + 5 < PATH_LEN)
        strcat(panels[1].path, "/DEMO");
    strcpy(cfg_path, panels[0].path);
    if (strlen(cfg_path) + 20 < PATH_LEN) strcat(cfg_path, "/A2FILE/A2FILE.CFG");
    load_config();
    a2fc_mouse = mouse_init();
    read_panel(0);
    read_panel(1);
    draw_all();
    for (;;) {
        pan = &panels[active];
        key = wait_key();
        if (key >= '0' && key <= '9') key = bar_nth(key == '0' ? 9 : key - '1');
        if (key != KEY_ESC && key != 'q' && key != 'Q') clear_row(22);
        /* Une image ouverte comme un dossier est en lecture seule : seules la
         * navigation, le marquage, C/V (extraire) et le formateur agissent ;
         * les commandes qui ecriraient ou qui ont besoin d'un vrai chemin
         * sont refusees en clair. */
        if (pan->fs && strchr("RKALDXEWTHIM", key & 0xDF)) {
            { extern const char msg_roimg[]; message(msg_roimg); };
            continue;
        }
        switch (key) {
        case KEY_UP: move_cursor(-1); break;
        case KEY_DOWN: move_cursor(1); break;
        /* Les fleches horizontales font la page, pas l'ouverture : sur un
         * dossier de cent fichiers, monter et descendre est ce qu'on fait
         * le plus souvent, et le clavier de l'Apple IIe n'a pas de PgUp.
         * RET ouvre, ESC remonte -- les deux seules autres facons de le
         * faire restent inchangees. */
        case '<': case '-': case KEY_LEFT: move_cursor(-ROWS); break;
        case '>': case '+': case KEY_RIGHT: move_cursor(ROWS); break;
        case '[': set_cursor(pan, 0); show_active(); break;
        case ']': if (pan->count) set_cursor(pan, pan->count - 1); show_active(); break;
        case ' ': toggle_tag(); break;
        case '*': retag(2); break;
        case 20: retag(1); break;                             /* Ctrl-T : tout marquer */
        case 14: retag(0); break;                             /* Ctrl-N : rien */
        case 18: refresh_both(); break;                       /* Ctrl-R : relire les panneaux */
        case '\'': find_letter(); break;
        case KEY_TAB: swap_panels(); break;
        case KEY_RETURN: open_selected(); break;
        case KEY_ESC:
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
        case 'r': case 'R': case 'k': case 'K': case 'a': case 'A': case 'l': case 'L':
            overlay_run("ATTR", key & 0xDF);
            break;
        case 'm': case 'M': overlay_run("MUSIC", 'M'); break;
        case 'd': case 'D': if (overlay("DELETE")) delete_targets(); break;
        case 's': case 'S': overlay_run("MUSIC", 'S'); break;
        case 't': case 'T':
            if (pan->count && !is_dir(&pan->e[pan->cursor]) && build_full(full, pan, &pan->e[pan->cursor])) {
                key = pan->e[pan->cursor].type;
                if ((unsigned char)key == 0xFC) { if (overlay("BASLIST")) baslist_entry(0); }
                else if ((unsigned char)key == 0x1A) overlay_run("AWP", 0);
                else if (overlay("TEXT")) view_text(full);
            }
            break;
        case 'h': case 'H':
            if (pan->count && !is_dir(&pan->e[pan->cursor]) && build_full(full, pan, &pan->e[pan->cursor]))
                if (overlay("HEX")) view_hex(full, pan->e[pan->cursor].size);
            break;
        case 'x': case 'X': case 'f': case 'F': overlay_run("RUN", key & 0xDF); break;
        case 'e': case 'E': overlay_run("EDIT", 'E'); break;
        case 'w': case 'W': overlay_run("DISKIMG", 'W'); break;
        case 'p': case 'P': toggle_music(); break;
        case '!': overlay_run("MENU", 0); if (input[0]) overlay_run(input, 0); break;
        case 'i': case 'I': if (pan->count && !is_dir(&pan->e[pan->cursor]) && pan->path[0]) view_image(); break;
        case '?': if (overlay("HELP")) view_help(); break;
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
