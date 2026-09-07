; format_mli.s -- trois appels de bas niveau pour FORMAT.SYSTEM.
;
;   unsigned char __fastcall__ mli_call(unsigned char cmd, void* parms);
;       Un appel MLI quelconque ; rend le code d'erreur ProDOS, 0 si bon.
;   unsigned char __fastcall__ driver_call(unsigned char unit, unsigned char cmd, unsigned char lc);
;       Appelle le pilote de bloc ProDOS de l'unite (table DEVADR, $BF10)
;       avec la commande cmd (0 STATUS, 3 FORMAT), tampon $6800, bloc 0 ;
;       lc != 0 commute la carte langage banque 1 en lecture/ecriture
;       autour de l'appel, comme le veut le pilote /RAM (Hyper-FORMAT).
;       Rend le code d'erreur ; STATUS laisse le nombre de blocs dans
;       driver_blocks.

        .export _mli_call, _driver_call, _driver_blocks
        .import popa

        .segment "BSS"
_driver_blocks: .res 2

        .segment "DATA"
_mli_call:
        sta mparms
        stx mparms+1
        jsr popa
        sta mcmd
        jsr $BF00
mcmd:   .byte 0
mparms: .word 0
        ldx #0
        rts

_driver_call:
        sta lcflag
        jsr popa
        sta $42                 ; commande
        jsr popa
        sta $43                 ; unite DSSS0000
        lsr a
        lsr a
        lsr a
        lsr a
        asl a                   ; index x 2 dans DEVADR
        tax
        lda $BF10,x
        sta vector
        lda $BF11,x
        sta vector+1
        lda #$00
        sta $44
        lda #$68
        sta $45                 ; tampon $6800
        lda #$00
        sta $46
        sta $47                 ; bloc 0
        lda lcflag
        beq :+
        lda $C08B               ; carte langage banque 1, lecture et ecriture
        lda $C08B
:       jsr dispatch
        php
        stx _driver_blocks
        sty _driver_blocks+1
        pha
        lda lcflag
        beq :+
        bit $C082               ; ROM de retour, comme avant l'appel
:       pla
        plp
        bcs :+
        lda #0
:       ldx #0
        rts
dispatch:
        jmp (vector)
vector: .word 0
lcflag: .byte 0
