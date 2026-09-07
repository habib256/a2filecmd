/*
 * MEMORY SWAP - Bascules video (texte 80 col / HGR plein / HGR mixte)
 */

#ifndef MEMORY_SWAP_H
#define MEMORY_SWAP_H

#include <stdint.h>

/* Bascules video. Elles ne touchent QUE des soft-switches : l'ecran texte
 * reste en place en $400-$7FF pendant tout le passage en graphique, il n'y a
 * donc rien a sauvegarder ni a restaurer. Voir memory_swap.c. */
void switch_to_hgr(void);         /* HGR page 1, plein ecran */
void switch_to_text(void);        /* Texte 80 colonnes */
void switch_to_mixed(void);       /* HGR + 4 lignes de texte 80 colonnes */

/* Fonction utilitaire */
uint8_t get_current_mode(void);   /* 0=texte, 1=HGR, 2=mixte */

#endif /* MEMORY_SWAP_H */