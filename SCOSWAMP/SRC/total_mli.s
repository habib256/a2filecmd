; total_mli.s -- deux appels MLI pour TOTAL.
;
; unsigned char __fastcall__ mli_gfi(void* params);   GET_FILE_INFO ($C4)
; unsigned char __fastcall__ mli_sfi(void* params);   SET_FILE_INFO ($C3)
;   params : le bloc de parametres prepare en C (param_count en tete, puis
;            un pointeur vers un nom ProDOS prefixe de sa longueur) ; rend
;            le code d'erreur ProDOS, 0 si tout va bien.
;
; cc65 n'admet ni .byte ni .word dans l'asm en ligne, et l'adresse du bloc
; suit l'appel : la routine vit donc en DATA, ou elle peut se modifier.
        .export _mli_gfi, _mli_sfi
        .segment "DATA"
_mli_sfi:
        ldy     #$C3
        bne     call            ; toujours pris
_mli_gfi:
        ldy     #$C4
call:   sty     command
        sta     block
        stx     block+1
        jsr     $BF00
command:
        .byte   $C4
block:  .word   $0000
        ldx     #0
        rts
