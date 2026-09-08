; a2fc_mli.s -- deux appels MLI pour A2FC.
;
; unsigned char __fastcall__ mli_gfi(void* params);   GET_FILE_INFO ($C4)
; unsigned char __fastcall__ mli_sfi(void* params);   SET_FILE_INFO ($C3)
;   params : le bloc de parametres prepare en C (param_count en tete, puis
;            un pointeur vers un nom ProDOS prefixe de sa longueur) ; rend
;            le code d'erreur ProDOS, 0 si tout va bien.
;
; cc65 n'admet ni .byte ni .word dans l'asm en ligne, et l'adresse du bloc
; suit l'appel : la routine vit donc en DATA, ou elle peut se modifier.
; unsigned char __fastcall__ mli_call(unsigned char cmd, void* params);
;   Un appel MLI quelconque, pour les surcouches (READ_BLOCK, WRITE_BLOCK,
;   ON_LINE...) : la commande est le premier argument, le bloc le second.
        .export _mli_gfi, _mli_sfi, _mli_call
        .import popa
        .import __oserror       ; _oserror de cc65 : report_error le lit
        .segment "DATA"
_mli_call:
        sta     block
        stx     block+1
        jsr     popa
        sta     command
        bne     go              ; toujours pris : aucune commande n'est 0
_mli_sfi:
        ldy     #$C3
        bne     call            ; toujours pris
_mli_gfi:
        ldy     #$C4
call:   sty     command
        sta     block
        stx     block+1
go:     jsr     $BF00
command:
        .byte   $C4
block:  .word   $0000
        ; Le code ProDOS rendu par le MLI (0 si tout va bien) va aussi dans
        ; _oserror : seule la stdio de cc65 le tenait a jour, et report_error
        ; affichait sinon la raison de l'echec PRECEDENT -- en clair, donc
        ; avec assurance, depuis que prodos_error traduit les codes.
        sta     __oserror
        ldx     #0
        rts

; unsigned char ram_format(void);
;
; Cherche l'unite dont le pilote est le /RAM de ProDOS -- il se reconnait a
; son adresse $FF00 dans DEVADR ($BF10), comme dans format.c -- et lui
; demande FORMAT ($03). Le pilote vit au-dessus de $D000 : la carte langage
; passe en banque 1, lecture et ecriture, autour de l'appel, comme
; format_mli.s le fait pour le formateur -- mais le retour se fait sur la
; banque 2 de A2FC, pas sur la ROM. Rend 1 si un /RAM a ete refait a neuf,
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
        ; n'a rien dans la carte langage). A2FC, lui, execute ses
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

; unsigned int __fastcall__ panel_hash(const struct Panel* pan);
;
; L'empreinte d'un panneau : chaque octet de sa table d'entrees (count
; entrees de 29 octets, a l'adresse e), plie dans un mot par rotation et
; addition, plus le nombre d'entrees, la fenetre (first, more) et le premier
; caractere du chemin. Les decalages des champs sont ceux que a2fc.c verifie
; en face des champs de struct Panel. En C, cc65 en faisait 325 octets ; ici
; une centaine. Une table pleine (4 060 octets) se plie en un dixieme de
; seconde, bien moins qu'un panneau ne se redessine.
        .export _panel_hash
        .importzp ptr1, ptr2, tmp1, tmp2, tmp3
        .segment "CODE"
_panel_hash:
        sta ptr1
        stx ptr1+1
        ldy #74                 ; e
        lda (ptr1),y
        sta ptr2
        iny
        lda (ptr1),y
        sta ptr2+1
        ldy #69                 ; first, octet haut
        lda (ptr1),y
        sta tmp3                ; h haut
        dey
        lda (ptr1),y            ; first, octet bas
        ldy #64                 ; count
        clc
        adc (ptr1),y
        bcc :+
        inc tmp3
:       lda (ptr1),y
        sta tmp1                ; entrees restantes
        ldy #67                 ; more
        clc
        adc (ptr1),y
        bcc :+
        inc tmp3
:       ldy #0                  ; path[0]
        clc
        adc (ptr1),y
        bcc :+
        inc tmp3
:       sta tmp2                ; h bas
entry:  lda tmp1
        beq done
        dec tmp1
        ldy #0
byte:   lda tmp3
        cmp #$80                ; C = bit 15
        rol tmp2
        rol tmp3                ; h tourne d'un bit
        lda (ptr2),y
        clc
        adc tmp2
        sta tmp2
        bcc :+
        inc tmp3
:       iny
        cpy #29
        bne byte
        clc
        lda ptr2
        adc #29
        sta ptr2
        bcc entry
        inc ptr2+1
        bne entry               ; toujours pris
done:   lda tmp2
        ldx tmp3
        rts

; void __fastcall__ aux_copy(unsigned int main_addr, unsigned int aux_addr,
;                            unsigned char to_aux);
;
; 512 octets entre la banque principale et la banque auxiliaire, par
; AUXMOVE ($C311) du firmware du //e : A1/A2 la source, A4 la destination,
; C = 1 de la principale vers l'auxiliaire. Interruptions coupees le temps
; de la copie : AUXMOVE commute RAMRD et RAMWRT, et le lecteur Mockingboard
; ne s'attend pas a etre reveille dans l'autre banque.
        .export _aux_copy
        .import popax
        .segment "CODE"
_aux_copy:
        sta dir
        jsr popax
        sta aux
        stx aux+1
        jsr popax               ; l'adresse principale
        ldy dir
        beq from_aux
        sta $3C                 ; source : principale
        stx $3D
        ldy aux
        sty $42                 ; destination : auxiliaire
        ldy aux+1
        sty $43
        bne move                ; toujours pris : AUX >= $2000
from_aux:
        sta $42                 ; destination : principale
        stx $43
        lda aux
        ldx aux+1
        sta $3C                 ; source : auxiliaire
        stx $3D
move:   clc
        adc #$FF                ; A2 = A1 + 511
        sta $3E
        txa
        adc #$01
        sta $3F
        php
        sei
        lda dir
        cmp #1                  ; C = 1 : principale vers auxiliaire
        jsr $C311
        plp
        rts
dir:    .byte 0
aux:    .word 0
