; unshrink.s -- le coeur de A2FILE/UNSHRINK.PLG : les deux LZW de ShrinkIt
; (LZW/1 du ShrinkIt ProDOS 8, LZW/2 de GS/ShrinkIt) et leur RLE, un bloc de
; 4096 octets par appel. D'apres nufxlib (Lzw.c : Nu_ExpandLZW1/2,
; Nu_ExpandRLE, Nu_LZWGetCode), verifie contre tools/mkshk.py, lui-meme
; verifie octet a octet contre nulib2.
;
; La surcouche est chargee en $1B00 ; ce coeur en est la tete, et le pilote C
; (a2fc.c, unshrink_entry) le recopie en AUX a la meme adresse avant tout
; appel (aux_copy). _us_chunk passe RAMRD et RAMWRT en AUX : des lors le
; 6502 EXECUTE la copie AUX, et lit et ecrit l'AUX, ou vivent le
; dictionnaire, la pile de decodage, la fenetre d'entree et le bloc de
; sortie. La page zero et la pile 6502 ($0000-$01FF) ne changent pas de
; banque : les parametres y passent (ptr1..ptr4, tmp1..tmp4 de cc65, que
; l'appele a le droit d'ecraser). L'etat LZW (entry, old, final, fresh, le
; tampon de bits) vit dans les variables de ce fichier -- dans la copie AUX,
; la seule que le coeur touche -- et survit d'un bloc a l'autre, comme LZW/2
; l'exige. Pas d'interruption pendant (sei) : la Mockingboard doit etre
; arretee avant (music_stop), et le lecteur de souris n'en a pas.
;
;   void __fastcall__ us_init(unsigned int fmt_esc);
;       A = format (2 LZW/1, 3 LZW/2), X = l'octet d'echappement RLE, lu par
;       le pilote dans l'en-tete du flux. A appeler APRES la recopie en AUX :
;       n'ecrit qu'en AUX (RAMWRT), l'execution reste en MAIN.
;   unsigned int __fastcall__ us_chunk(unsigned int in_addr);
;       Decode UN bloc dont l'en-tete est a in_addr, dans la fenetre d'entree
;       AUX que le pilote garde pleine d'au moins un bloc entier (au plus
;       4096 + 4 octets), et pose ses 4096 octets en OUTBUF (AUX). Rend le
;       nombre d'octets d'entree consommes, en-tete compris. Le pilote
;       recopie OUTBUF vers MAIN par aux_copy et l'ecrit dans le fichier, en
;       tronquant le dernier bloc a thread_eof.
;
; Carte de l'AUX (le pilote C repete ces adresses) :
;   PREFIX $2000-$3FFF  prefix[code], 2 octets, a PREFIX + code*2
;   SUFFIX $4000-$4FFF  suffix[code], 1 octet
;   STACK  $5000-$5FFF  la pile de decodage (au pire 4096)
;   INBUF  $6000-$7FFF  la fenetre d'entree, 8 Ko
;   OUTBUF $8000-$8FFF  le bloc decode, 4096 octets
;   TMPBUF $9000-$9FFF  la sortie LZW quand le RLE suit
;
; Le bloc : rlelen(2) [lzw(1) en LZW/1 | bit 15 de rlelen = LZW, et 2 octets
; de longueur a sauter, en LZW/2] puis les donnees. rlelen = 4096 : pas de
; RLE. Entree -> [LZW -> rlelen octets] -> [RLE -> 4096] ; ni l'un ni
; l'autre : 4096 octets bruts. LZW/1 repart d'une table vide a chaque bloc ;
; LZW/2 garde la sienne, la vide sur le code $100, et repart a neuf sur un
; bloc sans LZW. Codes de 9 a 12 bits, poids faible d'abord, la largeur du
; PROCHAIN code selon entry : 9 jusqu'a $1FE, 10 jusqu'a $3FE, 11 jusqu'a
; $7FE, 12 au-dela. Chaque bloc commence sur un octet : les bits qui restent
; sont jetes, et l'entree consommee est exactement les octets lus.

        .export         _us_init, _us_chunk
        .importzp       ptr1, ptr2, ptr3, ptr4, tmp1, tmp2, tmp3, tmp4
        .segment        "UNSHRINK"

PREFIX  = $2000
SUFFIX  = $4000
STACK   = $5000
OUTBUF  = $8000
TMPBUF  = $9000
CHUNK   = 4096
CLEAR   = $100
FIRST   = $101

RDMAIN  = $C002
RDAUX   = $C003
WRMAIN  = $C004
WRAUX   = $C005

; ---- l'etat : dans la copie AUX, la seule que le coeur lise et ecrive ----
fmt:    .byte   0
esc:    .byte   0
entry:  .word   0               ; la prochaine entree libre de la table
old:    .word   0               ; le code precedent
final:  .byte   0               ; le premier octet de la chaine precedente
fresh:  .byte   0               ; 1 : table vide, le prochain code est un octet
bb:     .res    3               ; le tampon de bits, poids faible d'abord
bc:     .byte   0               ; bits presents dans bb
tsh2:   .byte   0               ; octet 2 du temporaire de decalage
rlelen: .word   0
lzwon:  .byte   0
instart: .word  0
outcnt: .word   0
code:   .word   0
width:  .byte   0
hmask:  .byte   $01, $03, $07, $0F   ; poids fort d'un code de 9, 10, 11, 12 bits

; ---- us_init : format et echappement, table vide, tampon de bits vide ----
_us_init:
        sei
        sta     tmp1
        stx     tmp2
        sta     WRAUX           ; les ecritures vont en AUX, l'execution reste en MAIN
        lda     tmp1
        sta     fmt
        lda     tmp2
        sta     esc
        jsr     reset_table
        lda     #0
        sta     bc
        sta     WRMAIN
        cli
        rts

reset_table:
        lda     #<FIRST
        sta     entry
        lda     #>FIRST
        sta     entry+1
        lda     #1
        sta     fresh
        rts

; ---- us_chunk : un bloc, de l'en-tete en (A/X) vers OUTBUF ----
_us_chunk:
        sta     ptr1
        stx     ptr1+1
        sei
        sta     WRAUX
        sta     RDAUX           ; a partir d'ici, c'est la copie AUX qui s'execute
        lda     ptr1
        sta     instart
        lda     ptr1+1
        sta     instart+1
        lda     #0
        sta     bc
        sta     lzwon
        jsr     getb            ; rlelen
        sta     rlelen
        jsr     getb
        sta     rlelen+1
        lda     fmt
        cmp     #3
        beq     @h2
        jsr     getb            ; LZW/1 : le drapeau LZW, et une table neuve
        sta     lzwon
        jsr     reset_table
        jmp     @hdone
@h2:    lda     rlelen+1        ; LZW/2 : bit 15 = LZW, rlelen sur 13 bits
        and     #$80
        sta     lzwon
        lda     rlelen+1
        and     #$1F
        sta     rlelen+1
        lda     lzwon
        beq     @h2none
        jsr     getb            ; la longueur comprimee : inutile, le flux se termine seul
        jsr     getb
        jmp     @hdone
@h2none: jsr    reset_table     ; un bloc sans LZW repart a neuf
@hdone: lda     rlelen          ; RLE utilise si rlelen != 4096
        bne     @rle
        lda     rlelen+1
        cmp     #>CHUNK
        bne     @rle
        lda     lzwon           ; --- pas de RLE ---
        beq     @raw
        lda     #<OUTBUF        ; LZW seul : droit dans OUTBUF
        ldx     #>OUTBUF
        jsr     lzw
        jsr     byte_align
        jmp     @done
@raw:   jsr     copy_raw        ; ni l'un ni l'autre : 4096 octets tels quels
        jmp     @done
@rle:   lda     lzwon           ; --- RLE ---
        beq     @rleonly
        lda     #<TMPBUF        ; LZW vers TMPBUF, puis RLE de TMPBUF vers OUTBUF
        ldx     #>TMPBUF
        jsr     lzw
        jsr     byte_align
        lda     #<TMPBUF
        ldx     #>TMPBUF
        jsr     rle
        jmp     @done
@rleonly:
        lda     ptr1            ; RLE depuis l'entree meme
        ldx     ptr1+1
        jsr     rle
        lda     ptr3            ; ce que le RLE a lu est l'entree consommee
        sta     ptr1
        lda     ptr3+1
        sta     ptr1+1
@done:  sec                     ; consomme = ptr1 - instart, calcule AVANT de
        lda     ptr1            ; revenir en MAIN : instart n'existe qu'en AUX
        sbc     instart
        sta     ptr4
        lda     ptr1+1
        sbc     instart+1
        sta     ptr4+1
        sta     RDMAIN
        sta     WRMAIN
        cli
        lda     ptr4
        ldx     ptr4+1
        rts

; ---- les octets ----
getb:   ldy     #0              ; A = l'octet d'entree suivant
        lda     (ptr1),y
        inc     ptr1
        bne     :+
        inc     ptr1+1
:       rts

getsrc: ldy     #0              ; A = l'octet suivant de la source du RLE
        lda     (ptr3),y
        inc     ptr3
        bne     :+
        inc     ptr3+1
:       rts

out:    ldy     #0              ; l'octet A en sortie ; outcnt++
        sta     (ptr2),y
        inc     ptr2
        bne     :+
        inc     ptr2+1
:       inc     outcnt
        bne     :+
        inc     outcnt+1
:       rts

push:   ldy     #0
        sta     (ptr3),y
        inc     ptr3
        bne     :+
        inc     ptr3+1
:       rts

pop:    lda     ptr3
        bne     :+
        dec     ptr3+1
:       dec     ptr3
        ldy     #0
        lda     (ptr3),y
        rts

; ---- 4096 octets bruts, de l'entree vers OUTBUF ----
copy_raw:
        lda     #<OUTBUF
        sta     ptr2
        lda     #>OUTBUF
        sta     ptr2+1
        lda     #0
        sta     outcnt
        sta     outcnt+1
@l:     lda     outcnt+1
        cmp     #>CHUNK
        beq     @e
        jsr     getb
        jsr     out
        jmp     @l
@e:     rts

; ---- RLE : de la source (A/X) vers OUTBUF, 4096 octets ----
; esc val cnt : val repete cnt+1 fois ; tout autre octet, tel quel.
rle:    sta     ptr3
        stx     ptr3+1
        lda     #<OUTBUF
        sta     ptr2
        lda     #>OUTBUF
        sta     ptr2+1
        lda     #0
        sta     outcnt
        sta     outcnt+1
@loop:  lda     outcnt+1
        cmp     #>CHUNK
        beq     @end
        jsr     getsrc
        cmp     esc
        beq     @run
        jsr     out
        jmp     @loop
@run:   jsr     getsrc
        sta     tmp3            ; la valeur
        jsr     getsrc
        sta     tmp4            ; le compte moins un
@rep:   lda     tmp3
        jsr     out
        dec     tmp4
        bpl     @rep
        jmp     @loop
@end:   rts

; ---- LZW : rlelen octets vers (A/X) ----
lzw:    sta     ptr2
        stx     ptr2+1
        lda     #0
        sta     outcnt
        sta     outcnt+1
@loop:  lda     outcnt+1        ; fini quand outcnt >= rlelen
        cmp     rlelen+1
        bcc     @more
        bne     @fin
        lda     outcnt
        cmp     rlelen
        bcc     @more
@fin:   jmp     @end            ; @end est trop loin pour un branchement
@more:  jsr     getcode
        lda     fmt
        cmp     #3
        bne     @nclr
        lda     code            ; LZW/2 : $100 vide la table
        bne     @nclr
        lda     code+1
        cmp     #>CLEAR
        bne     @nclr
        jsr     reset_table
        jmp     @loop
@nclr:  lda     fresh
        beq     @norm
        lda     code            ; le premier code d'une table neuve : un octet
        jsr     out
        lda     code
        sta     old
        sta     final
        lda     code+1
        sta     old+1
        lda     #0
        sta     fresh
        jmp     @loop
@norm:  lda     code            ; p = code, pile vide
        sta     tmp1
        lda     code+1
        sta     tmp2
        lda     #<STACK
        sta     ptr3
        lda     #>STACK
        sta     ptr3+1
        lda     tmp2            ; p >= entry : KwKwK -> empiler final, p = old
        cmp     entry+1
        bcc     @walk
        bne     @kwk
        lda     tmp1
        cmp     entry
        bcc     @walk
@kwk:   lda     final
        jsr     push
        lda     old
        sta     tmp1
        lda     old+1
        sta     tmp2
@walk:  lda     tmp2            ; tant que p > $FF : empiler suffix[p], p = prefix[p]
        beq     @leaf
        clc
        lda     tmp1
        adc     #<SUFFIX
        sta     ptr4
        lda     tmp2
        adc     #>SUFFIX
        sta     ptr4+1
        ldy     #0
        lda     (ptr4),y
        jsr     push
        lda     tmp1            ; prefix[p] a PREFIX + p*2
        asl     a
        sta     ptr4
        lda     tmp2
        rol     a
        clc
        adc     #>PREFIX
        sta     ptr4+1
        ldy     #0
        lda     (ptr4),y
        sta     tmp1
        iny
        lda     (ptr4),y
        sta     tmp2
        jmp     @walk
@leaf:  lda     tmp1            ; final = p, sortie de p, puis la pile
        sta     final
        jsr     out
@pop:   lda     ptr3
        cmp     #<STACK
        bne     @popone
        lda     ptr3+1
        cmp     #>STACK
        beq     @add
@popone: jsr    pop
        jsr     out
        jmp     @pop
@add:   lda     entry+1         ; suffix[entry] = final, prefix[entry] = old, entry++
        cmp     #$10            ; (jamais atteint : le compresseur vide a $FFD)
        bcs     @setold
        clc
        lda     entry
        adc     #<SUFFIX
        sta     ptr4
        lda     entry+1
        adc     #>SUFFIX
        sta     ptr4+1
        lda     final
        ldy     #0
        sta     (ptr4),y
        lda     entry
        asl     a
        sta     ptr4
        lda     entry+1
        rol     a
        clc
        adc     #>PREFIX
        sta     ptr4+1
        lda     old
        ldy     #0
        sta     (ptr4),y
        lda     old+1
        iny
        sta     (ptr4),y
        inc     entry
        bne     @setold
        inc     entry+1
@setold: lda    code
        sta     old
        lda     code+1
        sta     old+1
        jmp     @loop
@end:   rts

; ptr1 -= bc>>3 : getcode lit des octets ENTIERS dans son tampon de bits mais
; n'en consomme que `width` : a la fin du morceau, ptr1 a lu jusqu'a deux octets
; de trop (le reliquat de bb). Le flux d'un morceau etant cale sur l'octet, on
; recule ptr1 des octets entiers encore en tampon, sinon le morceau suivant se
; lit de travers et le dictionnaire part en vrille.
byte_align:
        lda     bc
        lsr     a
        lsr     a
        lsr     a               ; A = bc >> 3, octets lus en trop
        beq     @z
        sta     tmp1
        lda     ptr1
        sec
        sbc     tmp1
        sta     ptr1
        lda     ptr1+1
        sbc     #0
        sta     ptr1+1
@z:     rts

; ---- un code : largeur selon entry, bits poids faible d'abord ----
getcode:
        ldx     #9              ; 9 jusqu'a $1FE, 10 jusqu'a $3FE, 11 jusqu'a $7FE, 12 au-dela
        lda     entry+1
        cmp     #$01
        bcc     @w
        bne     @ge200
        lda     entry
        cmp     #$FF
        bcc     @w
        inx
        bne     @w
@ge200: inx
        lda     entry+1
        cmp     #$03
        bcc     @w
        bne     @ge400
        lda     entry
        cmp     #$FF
        bcc     @w
        inx
        bne     @w
@ge400: inx
        lda     entry+1
        cmp     #$07
        bcc     @w
        bne     @ge800
        lda     entry
        cmp     #$FF
        bcc     @w
        inx
        bne     @w
@ge800: inx
@w:     stx     width
@fill:  lda     bc              ; remplir : bb |= octet << bc, bc += 8, tant que bc < width
        cmp     width
        bcs     @have
        jsr     getb
        sta     tmp3
        lda     #0
        sta     tmp4
        sta     tsh2
        ldx     bc
        beq     @orin
@sh:    asl     tmp3
        rol     tmp4
        rol     tsh2
        dex
        bne     @sh
@orin:  lda     bb
        ora     tmp3
        sta     bb
        lda     bb+1
        ora     tmp4
        sta     bb+1
        lda     bb+2
        ora     tsh2
        sta     bb+2
        lda     bc
        clc
        adc     #8
        sta     bc
        jmp     @fill
@have:  lda     bb              ; code = bb & masque(width)
        sta     code
        lda     bb+1
        ldx     width
        and     hmask-9,x
        sta     code+1
        ldx     width           ; bb >>= width, bc -= width
@shr:   lsr     bb+2
        ror     bb+1
        ror     bb
        dex
        bne     @shr
        lda     bc
        sec
        sbc     width
        sta     bc
        rts

us_end:
        .assert us_end <= $2000, error, "UNSHRINK core must end under $2000 (AUX mirror)"
        .assert (PREFIX & $FF) = 0 .and (SUFFIX & $FF) = 0, error, "PREFIX and SUFFIX must be page-aligned"
