; chain.s -- lancer un programme ProDOS quelle que soit sa taille.
;
;   extern unsigned int chain_addr;         adresse de chargement ($2000 pour un SYS)
;   void __fastcall__ chain_load(const char* path);
;
; Le programme appelant est ecrase par ce qu'il charge : le travail se fait
; depuis un talon recopie en page $0300 (libre sous ProDOS, hors de tout
; programme), qui ouvre le fichier, le lit tout entier a chain_addr, le
; ferme, remet la ROM en lecture et y saute. Un echec renvoie a ProDOS
; (QUIT, Bitsy Bye). Partage par A2FC (touches X et F) et par FORMAT.SYSTEM
; (retour a A2FC).
;
;   void __fastcall__ chain_command(const char* name);
;
; Une commande facultative pour le programme charge, a appeler AVANT
; chain_load. C'est la porte que BASIC.SYSTEM ouvre a ses lanceurs, Bitsy
; Bye compris : a son demarrage il regarde en $2006 un nom precede de sa
; longueur, et s'il existe l'execute comme la commande "-NOM" -- ce qui
; lance un programme Applesoft. Le talon depose donc le nom en
; chain_addr+6 juste avant de sauter. Sans appel, le premier octet reste
; nul et rien n'est ecrit.

        .export _chain_load, _chain_addr, _chain_command
        .import donelib
        .importzp ptr1

        .segment "BSS"
_chain_addr: .res 2

        .segment "RODATA"
stub_src:
        .org $0300
stub:   jsr $BF00               ; OPEN
        .byte $C8
        .word open_p
        bcs fail
        lda ref_num
        sta rd_ref
        sta cl_ref
        jsr $BF00               ; READ
        .byte $CA
        .word read_p
        bcs fail
        jsr $BF00               ; CLOSE
        .byte $CC
        .word close_p
        ldy cmd                 ; une commande a passer ?
        beq run
        clc                     ; oui : en chain_addr+6, longueur comprise
        lda rd_addr
        adc #6
        sta put+1
        lda rd_addr+1
        adc #0
        sta put+2
:       lda cmd,y
put:    sta $FFFF,y
        dey
        bpl :-
run:    bit $C082
        jmp (rd_addr)
fail:   jsr $BF00               ; QUIT : Bitsy Bye
        .byte $65
        .word quit_p
open_p: .byte 3
        .word path
        .word $BB00             ; tampon ProDOS de 1 Ko, hors de portee d'un
                                ; programme charge entre $0800 et $BAFF
ref_num:
        .byte 0
read_p: .byte 4
rd_ref: .byte 0
rd_addr:
        .word $2000             ; chain_addr
rd_len: .word $2000             ; $BF00 - chain_addr
        .word 0
close_p:
        .byte 1
cl_ref: .byte 0
quit_p: .byte 4, 0
        .word 0
        .byte 0
        .word 0
path:   .res 64
cmd:    .res 16                 ; longueur puis nom, zero = pas de commande
stub_end:
        .reloc
stub_len = stub_end - stub
; Le talon vit en $0300-$03CF : au-dela commencent les vecteurs (BRK, RESET,
; entree DOS) que ProDOS et le moniteur s'attendent a trouver intacts.
        .assert stub_len <= $D0, error, "le talon de chain.s deborde la page 3"
cmd_src = stub_src + (cmd - stub)

        .segment "CODE"
_chain_load:
        sta ptr1
        stx ptr1+1
        ; Les destructeurs cc65 d'abord : doneirq rend a ProDOS l'entree
        ; d'interruption prise au demarrage (music_irq). Sans cela chaque
        ; lancement en gardait une, avec un vecteur vers de la memoire
        ; recouverte : au troisieme aller-retour F/ESC, plantage dans le
        ; moniteur. ProDOS n'en a que quatre.
        jsr donelib
        ldy #0                  ; copier le talon en $0300
:       lda stub_src,y
        sta $0300,y
        iny
        cpy #stub_len
        bne :-
        lda _chain_addr         ; l'adresse, et la longueur jusqu'a $BF00
        sta rd_addr
        sec
        lda #$00
        sbc _chain_addr
        sta rd_len
        lda _chain_addr+1
        sta rd_addr+1
        lda #$BF
        sbc _chain_addr+1
        sta rd_len+1
        ldy #0                  ; le chemin, prefixe de sa longueur
:       lda (ptr1),y
        beq :+
        sta path+1,y
        iny
        cpy #63
        bne :-
:       sty path
        jmp stub

; Depose le nom dans le talon SOURCE (RODATA, donc en RAM et modifiable) :
; le prochain chain_load l'emporte avec le reste du talon.
_chain_command:
        sta ptr1
        stx ptr1+1
        ldy #0
:       lda (ptr1),y
        beq :+
        sta cmd_src+1,y
        iny
        cpy #15
        bne :-
:       sty cmd_src
        rts
