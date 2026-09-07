; a2rc_mli.s -- deux appels MLI pour A2RC.
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

; unsigned char ram_format(void);
;
; Cherche l'unite dont le pilote est le /RAM de ProDOS -- il se reconnait a
; son adresse $FF00 dans DEVADR ($BF10), comme dans format.c -- et lui
; demande FORMAT ($03). Le pilote vit au-dessus de $D000 : la carte langage
; passe en banque 1, lecture et ecriture, autour de l'appel, comme
; format_mli.s le fait pour le formateur -- mais le retour se fait sur la
; banque 2 de A2RC, pas sur la ROM. Rend 1 si un /RAM a ete refait a neuf,
; 0 sinon (aucun /RAM en ligne, ou refus du pilote).
;
; Le tampon annonce est $2000, la page graphique : cet appel n'a lieu qu'au
; retour d'une image, ou elle est deja perdue et ou les panneaux vont etre
; relus. FORMAT ne s'en sert pas, mais le pilote lit les six octets.
        .export _ram_format
_ram_format:
        ldy $BF31               ; DEVCNT : le nombre d'unites, moins une
scan:   lda $BF32,y             ; DEVLST
        and #$F0
        sta unit
        lsr a
        lsr a
        lsr a                   ; (unite >> 4) x 2 : l'index dans DEVADR
        tax
        lda $BF10,x
        bne next
        lda $BF11,x
        cmp #$FF                ; $FF00 : le pilote /RAM
        beq found
next:   dey
        bpl scan
        lda #0                  ; aucun /RAM en ligne
        tax
        rts
found:  lda $BF10,x
        sta vec
        lda $BF11,x
        sta vec+1
        lda #3
        sta $42                 ; commande FORMAT
        lda unit
        sta $43
        lda #$00
        sta $44
        sta $46
        sta $47                 ; bloc 0
        lda #$20
        sta $45                 ; tampon $2000
        php                     ; le pilote tourne carte langage commutee :
        sei                     ; pas d'interruption pendant ce temps-la
        lda $C08B               ; banque 1, lecture et ecriture
        lda $C08B
        jsr indirect
        lda #0                  ; la retenue dit l'erreur ; en faire le
        bcs :+                  ; resultat AVANT de rendre l'etat au plp
        lda #1
        ; On rend l'etat que crt0 laisse -- banque 2 en lecture, protegee en
        ; ecriture -- et non la ROM ($C082, ce que fait le formateur, qui
        ; n'a rien dans la carte langage). A2RC, lui, execute ses
        ; visionneuses, ses saisies et sa configuration depuis $D400. En
        ; pratique le premier appel MLI qui suit remet deja la banque 2
        ; (mesure : confirm() repond meme si l'on rend la ROM), mais cela
        ; tient a l'ordre des appels, pas au contrat de cette routine.
:       bit $C080
        plp
        ldx #0
        rts
indirect:
        jmp (vec)
vec:    .word 0
unit:   .byte 0
