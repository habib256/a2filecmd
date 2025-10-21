/*
 * MEMORY SWAP - Header pour optimisation Apple II
 * Évite le rechargement du texte lors des switches HGR ↔ TXT
 */

#ifndef MEMORY_SWAP_H
#define MEMORY_SWAP_H

#include <stdint.h>

/* Structure pour un choix (doit correspondre à Choice dans scoswamp.c) */
typedef struct {
    int scene_id;
    char title[80];
} SwapChoice;

/* Fonctions principales */
void save_text_screen(void);      /* Sauvegarde zone texte ($400-$7FF) */
void restore_text_screen(void);   /* Restaure zone texte depuis backup */
void switch_to_hgr(void);         /* HGR + sauvegarde auto */
void switch_to_text(void);        /* Texte + restauration auto */
void switch_to_mixed(void);       /* Mode mixte + sauvegarde auto */

/* Fonctions de sauvegarde des choix */
void save_choices(SwapChoice* choices, int num_choices);   /* Sauvegarde les choix */
void restore_choices(SwapChoice* choices, int* num_choices); /* Restaure les choix */
uint8_t has_saved_choices(void);  /* Vérifie si des choix sont sauvegardés */

/* Fonctions utilitaires */
uint8_t get_current_mode(void);   /* 0=texte, 1=HGR, 2=mixte */
void force_save_text(void);       /* Force la sauvegarde */
void clear_text_backup(void);     /* Efface la sauvegarde */
void clear_all_backup(void);      /* Efface tout (texte + choix) */

#endif /* MEMORY_SWAP_H */