/*
 * MEMORY SWAP - Optimisation Apple II
 * Évite le rechargement du texte lors des switches HGR ↔ TXT
 * 
 * Principe : Sauvegarder la zone texte ($400-$7FF) avant HGR
 * et la restaurer au retour en mode texte
 */

#include <stdint.h>
#include <peekpoke.h>
#include <string.h>

/* Zones mémoire Apple II */
#define TEXT_SCREEN_START  0x400   /* Début zone texte */
#define TEXT_SCREEN_SIZE   1024    /* 40×24 = 1024 octets */

/* Soft switches Apple II */
#define TXTCLR  (*(volatile uint8_t*)0xC050)  /* Mode graphique */
#define TXTSET  (*(volatile uint8_t*)0xC051)  /* Mode texte */
#define MIXCLR  (*(volatile uint8_t*)0xC052)  /* Mode mixte OFF */
#define MIXSET  (*(volatile uint8_t*)0xC053)  /* Mode mixte ON */
#define LOWSCR  (*(volatile uint8_t*)0xC054)  /* Page 1 visible */
#define HISCR   (*(volatile uint8_t*)0xC055)  /* Page 2 visible */
#define LORES   (*(volatile uint8_t*)0xC056)  /* Low-res */
#define HIRES   (*(volatile uint8_t*)0xC057)  /* Hi-res */

/* Structure pour un choix (doit correspondre à Choice dans scoswamp.c) */
typedef struct {
    int scene_id;
    char title[80];
} SwapChoice;

/* Constantes */
#define MAX_CHOICES 10

/* Variables globales pour l'état */
static uint8_t text_backup[TEXT_SCREEN_SIZE];  /* Sauvegarde zone texte */
static uint8_t text_saved = 0;                 /* Flag : texte sauvegardé ? */
static uint8_t current_mode = 0;               /* 0=texte, 1=HGR, 2=mixte */

/* Sauvegarde des choix */
static SwapChoice choices_backup[MAX_CHOICES]; /* Sauvegarde des choix */
static int num_choices_backup = 0;             /* Nombre de choix sauvegardés */
static uint8_t choices_saved = 0;              /* Flag : choix sauvegardés ? */

/*
 * Sauvegarde la zone texte vers la zone de backup
 */
void save_text_screen(void) {
    uint16_t i;
    
    /* Copier $400-$7FF vers backup */
    for (i = 0; i < TEXT_SCREEN_SIZE; i++) {
        text_backup[i] = PEEK(TEXT_SCREEN_START + i);
    }
    
    text_saved = 1;
}

/*
 * Restaure la zone texte depuis la sauvegarde
 */
void restore_text_screen(void) {
    uint16_t i;
    
    if (!text_saved) return;  /* Rien à restaurer */
    
    /* Copier backup vers $400-$7FF */
    for (i = 0; i < TEXT_SCREEN_SIZE; i++) {
        POKE(TEXT_SCREEN_START + i, text_backup[i]);
    }
}

/*
 * Bascule vers mode HGR en sauvegardant le texte
 */
void switch_to_hgr(void) {
    /* Toujours sauvegarder et activer HGR, même si on pense y être déjà */
    /* Car l'état peut avoir été modifié par d'autres fonctions */
    
    /* Sauvegarder le texte actuel */
    save_text_screen();
    
    /* Activer HGR */
    TXTCLR = 0;   /* Mode graphique */
    HIRES = 0;    /* Hi-res */
    LOWSCR = 0;   /* Page 1 */
    MIXCLR = 0;   /* Pas de mode mixte */
    
    current_mode = 1;
}

/*
 * Bascule vers mode texte en restaurant le contenu
 */
void switch_to_text(void) {
    /* Toujours activer le mode texte, même si on pense y être déjà */
    /* Car l'état peut avoir été modifié par d'autres fonctions */
    
    /* Activer mode texte */
    TXTSET = 0;
    
    /* Restaurer le contenu texte sauvegardé */
    restore_text_screen();
    
    current_mode = 0;
}

/*
 * Bascule vers mode mixte (HGR + 4 lignes texte)
 */
void switch_to_mixed(void) {
    /* Toujours activer le mode mixte, même si on pense y être déjà */
    /* Car l'état peut avoir été modifié par d'autres fonctions */
    
    /* Sauvegarder le texte actuel */
    save_text_screen();
    
    /* Activer mode mixte */
    TXTCLR = 0;   /* Mode graphique */
    HIRES = 0;    /* Hi-res */
    LOWSCR = 0;   /* Page 1 */
    MIXSET = 0;   /* Mode mixte ON */
    
    current_mode = 2;
}

/*
 * Fonction utilitaire : état actuel
 */
uint8_t get_current_mode(void) {
    return current_mode;
}

/*
 * Fonction utilitaire : forcer la sauvegarde
 */
void force_save_text(void) {
    save_text_screen();
}

/*
 * Fonction utilitaire : effacer la sauvegarde texte
 */
void clear_text_backup(void) {
    text_saved = 0;
    memset(text_backup, 0, TEXT_SCREEN_SIZE);
}

/*
 * Sauvegarde les choix
 */
void save_choices(SwapChoice* choices, int num_choices) {
    int i;
    
    if (num_choices < 0 || num_choices > MAX_CHOICES) {
        return;  /* Nombre invalide */
    }
    
    /* Copier les choix */
    for (i = 0; i < num_choices; i++) {
        choices_backup[i].scene_id = choices[i].scene_id;
        strncpy(choices_backup[i].title, choices[i].title, 79);
        choices_backup[i].title[79] = '\0';
    }
    
    num_choices_backup = num_choices;
    choices_saved = 1;
}

/*
 * Restaure les choix
 */
void restore_choices(SwapChoice* choices, int* num_choices) {
    int i;
    
    if (!choices_saved) {
        *num_choices = 0;
        return;  /* Rien à restaurer */
    }
    
    /* Copier les choix sauvegardés */
    for (i = 0; i < num_choices_backup; i++) {
        choices[i].scene_id = choices_backup[i].scene_id;
        strncpy(choices[i].title, choices_backup[i].title, 79);
        choices[i].title[79] = '\0';
    }
    
    *num_choices = num_choices_backup;
}

/*
 * Vérifie si des choix sont sauvegardés
 */
uint8_t has_saved_choices(void) {
    return choices_saved;
}

/*
 * Efface tout (texte + choix)
 */
void clear_all_backup(void) {
    clear_text_backup();
    choices_saved = 0;
    num_choices_backup = 0;
    memset(choices_backup, 0, sizeof(choices_backup));
}