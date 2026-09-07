; overlay.s -- la signature en tete de chaque surcouche (IMAGE, TEXT, HEX,
; DELETE, HELP).
;
; Une surcouche est liee avec le programme : elle appelle ses fonctions a
; leurs adresses de ce lien-la, et une surcouche d'une autre construction
; partirait dans le decor. Ses deux premiers octets sont donc l'adresse de
; main dans le programme qui l'a liee, et le noyau la compare a la sienne
; avant d'y entrer (overlay(), dans a2fc.c). Ce fichier est le premier objet
; du lien apres crt0 pour que le mot soit bien en tete du segment.
        .import _main
        .segment "IMAGE"
        .word   _main
        .segment "HELP"
        .word   _main
        .segment "TEXT"
        .word   _main
        .segment "HEX"
        .word   _main
        .segment "DELETE"
        .word   _main
