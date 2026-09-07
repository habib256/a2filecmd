; total_mli.s -- un appel MLI GET_FILE_INFO pour TOTAL.
;
; unsigned char __fastcall__ mli_gfi(void* params);
;   params : le bloc de 18 octets de GET_FILE_INFO ($C4), prepare en C
;            (param_count $0A, pointeur vers un nom ProDOS prefixe de sa
;            longueur) ; rend le code d'erreur ProDOS, 0 si tout va bien.
;
; cc65 n'admet ni .byte ni .word dans l'asm en ligne, et l'adresse du bloc
; suit l'appel : la routine vit donc en DATA, ou elle peut se modifier.
        .export _mli_gfi
        .segment "DATA"
_mli_gfi:
        sta     block
        stx     block+1
        jsr     $BF00
        .byte   $C4
block:  .word   $0000
        ldx     #0
        rts
