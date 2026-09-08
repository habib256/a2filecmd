; vsdrive.s -- VDrive : deux volumes ProDOS servis par la ligne serie.
;
;   unsigned char vsdrive_install(void);     rend (slot serie << 4) | slot des
;                                            volumes, ou 0 sans carte serie
;   void vsdrive_uninstall(void);            destructeur cc65 : Q, X, F, exit
;
; Le protocole est celui du VSDrive d'ADTPro, que servent aussi veserver.py
; (ProDOS-Utils) et surl-server (a2tools, Raspberry) : pour chaque bloc, une
; enveloppe de cinq octets -- $C5, la commande (lecture 3 ou 5, ecriture 2 ou
; 4 selon le lecteur), le bloc (faible, fort), le XOR des quatre -- puis les
; 512 octets et leur XOR. En lecture l'hote renvoie d'abord l'enveloppe en
; echo, suivie de quatre octets d'heure et de date ProDOS, puis son XOR ; on
; en profite pour regler l'horloge ($BF90). Un XOR faux signale l'erreur.
;
; A la Ammonoid (Colin Leroy-Mira, a2tools/src/lib/vsdrive.s, dont ce
; pilote s'inspire) : le pilote vit DANS le programme, pas dans ProDOS. A
; l'installation on cherche une carte serie (la signature Pascal 1.1 de son
; ROM : $Cn05=$38 $Cn07=$18 $Cn0B=$01 $Cn0C=$31, puis un 6551 qui repond), on
; la regle a 115 200 bauds 8N1, et on prend le premier slot 1..7 dont ni le
; lecteur 1 ni le 2 ne figurent dans DEVLST : son entree DEVADR recoit notre
; pilote, ses deux unites entrent dans DEVLST, et la liste des volumes les
; montre comme n'importe quel disque. Le destructeur defait tout : ProDOS ne
; doit plus pointer chez nous une fois le programme parti.
;
; La place : la fenetre principale est pleine, le pilote et sa couche serie
; sont donc en carte langage (segment LC, banc 2, $D400-$DFFF). ProDOS, lui,
; appelle ses pilotes depuis SON banc 1 : un talon de 17 octets en page 3
; ($0300, libre sous ProDOS ; chain.s n'y pose son propre talon qu'apres le
; destructeur) bascule le banc 2 en lecture, appelle le pilote, et rend le
; banc 1 en lecture/ecriture avant de revenir au MLI. La carte langage est
; en lecture seule (crt0 : bit $C080) : les variables sont en page 3 aussi.
;
; Les temps : a 115 200 bauds un octet toutes les 87 cycles environ ; la
; boucle de reception en fait ~60, interruptions coupees (SEI) le temps d'un
; bloc, sinon la musique Mockingboard ferait perdre des octets. Chaque
; attente d'octet a un delai (~0,3 s) : un hote absent rend une erreur d'E/S
; ($27) au lieu de figer la machine -- la liste des volumes le dit.

        .export         _vsdrive_install, _vsdrive_uninstall
        .destructor     _vsdrive_uninstall, 9
        .importzp       ptr1

; ProDOS
DEVADR          = $BF10         ; 16 mots : slot 0..7, lecteur 1 puis 2
DEVCNT          = $BF31         ; unites moins une
DEVLST          = $BF32
DATE            = $BF90
TIME            = $BF92
P_CMD           = $42           ; 0 STATUS, 1 READ, 2 WRITE, 3 FORMAT
P_UNIT          = $43           ; slot x 16, + $80 pour le lecteur 2
P_BUF           = $44
P_BLK           = $46
E_IO            = $27
E_NODEV         = $28

; Le 6551 : $C088 + slot x 16 (donnees, etat, commande, controle). La base
; $BFF9 = $C088 - $8F fait tomber la fausse lecture de l'indexation en page
; $BF, jamais dans les entrees-sorties (le tour de cc65 et d'a2tools).
ACIA_OFS        = $8F
ACIA_DATA       = $C088 - ACIA_OFS
ACIA_STATUS     = $C089 - ACIA_OFS
ACIA_CMD        = $C08A - ACIA_OFS
ACIA_CTRL       = $C08B - ACIA_OFS

; Le protocole
VD_ENV          = $C5
VD_WRITE        = $02
VD_READ         = $03

; Page 3 : le talon en $0300, les variables derriere lui.
THUNK           = $0300
vs_slot         = $03B0         ; le slot des volumes
vs_dev1         = $03B1         ; son unite lecteur 1 (slot x 16)
vs_dev2         = $03B2         ; lecteur 2 (+ $80)
vs_orig         = $03B3         ; l'ancien DEVADR de ce slot (2 octets)
vs_on           = $03B5         ; 1 : installe
vs_acia         = $03B6         ; l'index X du 6551 (slot x 16 + $8F)
vs_chk          = $03B7
vs_cmd          = $03B8
vs_to           = $03B9         ; le compte a rebours du delai (2 octets)
vs_dt           = $03BB         ; heure et date recues (4 octets)
vs_pg           = $03BF         ; les pages du bloc qui restent
vs_int          = $03C0         ; le numero ProDOS de notre gestionnaire d'interruption, 0 sans
vs_ip           = $03C1         ; ses parametres MLI (3 octets) : compte, numero, adresse

; ----------------------------------------------------------------------
; Le destructeur : en fenetre principale, car _exit (crt0) remet la ROM
; avant d'appeler donelib -- la carte langage n'est plus lisible alors.
; ----------------------------------------------------------------------
        .segment "CODE"

_vsdrive_uninstall:
        lda     vs_on
        beq     un_done
        lda     #0
        sta     vs_on
        jsr     del_irq
        lda     vs_slot                 ; l'ancien pilote reprend DEVADR
        asl
        tax
        lda     vs_orig
        sta     DEVADR,x
        sta     DEVADR+16,x
        lda     vs_orig+1
        sta     DEVADR+1,x
        sta     DEVADR+17,x
        ldx     #0                      ; nos deux unites quittent DEVLST,
        ldy     #0                      ; ou qu'elles soient (/RAM refait
un_scan:                                ; peut en avoir ajoute apres nous)
        lda     DEVLST,y
        cmp     vs_dev1
        beq     un_skip
        cmp     vs_dev2
        beq     un_skip
        sta     DEVLST,x
        inx
un_skip:
        iny
        cpy     DEVCNT
        bcc     un_scan
        beq     un_scan
        dex
        stx     DEVCNT
        ldx     vs_acia                 ; DTR retombe : le port se ferme
        lda     #$0A
        sta     ACIA_CMD,x
un_done:
        rts

; ----------------------------------------------------------------------
; Le reste en carte langage.
; ----------------------------------------------------------------------
        .segment "LC"

; La signature Pascal 1.1 d'une carte serie ou parallele de type 1.
id_ofs: .byte   $05, $07, $0B, $0C
id_val: .byte   $38, $18, $01, $31

; Le talon, recopie en $0300. Sa source est en memoire principale (segment
; CODE), pas en carte langage : l'image LC est pleine a 7 octets pres, et
; une source qu'on ne fait que recopier n'a rien a y faire.
;
; Le pilote vit dans le banc 2 de la carte langage ($D400-$DFFF, l'image LC
; de cc65) et ProDOS dans le banc 1 -- avec son tampon general GBUF en
; $DC00 : c'est la que ON_LINE, la lecture d'un repertoire et l'ecriture
; d'un bloc de repertoire posent P_BUF. Un `sta (P_BUF),y` execute depuis
; le banc 2 ne peut pas y arriver (les deux bancs se partagent les memes
; adresses, et le banc 2 etait meme en lecture seule) : le tampon gardait
; le dernier bloc lu par le pilote du Disk II, et le volume distant
; paraissait sous le nom de la disquette. Les deux acces au tampon passent
; donc par ici, en page 3, hors carte langage : banc 1 en lecture/ecriture
; le temps d'un octet, puis retour au banc 2 pour retrouver le pilote.
; (Banc de POM2, bench/vdrive.py, 2026-09-08.)
        .segment "CODE"
thunk_src:
        bit     $C080                   ; le banc 2 en lecture : nous
        jsr     vs_driver
        php                             ; A et le report : le verdict
        pha
        bit     $C08B                   ; le banc 1 en lecture/ecriture :
        bit     $C08B                   ; ProDOS, tel qu'il s'attend a se
        pla                             ; retrouver
        plp
        rts
st_src:                                 ; A -> (P_BUF),y dans le banc de ProDOS
        bit     $C08B
        bit     $C08B
        sta     (P_BUF),y
        bit     $C080
        rts
ld_src:                                 ; A <- (P_BUF),y dans le banc de ProDOS
        bit     $C08B
        bit     $C08B
        lda     (P_BUF),y
        bit     $C080
        rts
; Le gestionnaire d'interruption ProDOS. Un 6551 leve IRQ quand DCD ou DSR
; change, quoi qu'en disent ses registres : sur une vraie SSC dont le cable
; porte ces lignes, debrancher l'hote tuerait ProDOS ("RESTART SYSTEM -
; $01", personne n'a reclame l'interruption). Lire le registre d'etat
; l'acquitte ; bit 7 dit si c'etait nous. L'adresse est posee a
; l'installation (page 3 : modifiable).
irq_src:
        lda     $C089                   ; -> $C089 + slot x 16
        and     #$80
        beq     irq_no
        clc                             ; reclamee
        rts
irq_no: sec
        rts
thunk_len = * - thunk_src
irq_adr = THUNK + (irq_src - thunk_src) + 1
IRQH    = THUNK + (irq_src - thunk_src)

; L'inscription et le retrait du gestionnaire (MLI $40 / $41), en fenetre
; principale : le retrait sert au destructeur, hors carte langage.
ins_irq:
        lda     vs_acia                 ; l'adresse du registre d'etat
        sec
        sbc     #ACIA_OFS
        clc
        adc     #$89
        sta     irq_adr
        lda     #$C0
        sta     irq_adr+1
        lda     #2
        sta     vs_ip
        lda     #<IRQH
        sta     vs_ip+2
        lda     #>IRQH
        sta     vs_ip+3
        jsr     $BF00
        .byte   $40                     ; ALLOC_INTERRUPT
        .word   vs_ip
        bcc     :+
        lda     #0                      ; plus de place chez ProDOS : sans gestionnaire
        sta     vs_ip+1
:       lda     vs_ip+1
        sta     vs_int
        rts
del_irq:
        lda     vs_int
        beq     :+
        sta     vs_ip+1
        lda     #1
        sta     vs_ip
        jsr     $BF00
        .byte   $41                     ; DEALLOC_INTERRUPT
        .word   vs_ip
        lda     #0
        sta     vs_int
:       rts
st_buf  = THUNK + (st_src - thunk_src)
ld_buf  = THUNK + (ld_src - thunk_src)
        .segment "LC"

; unsigned char vsdrive_install(void)
_vsdrive_install:
        lda     #0                      ; la page 3 n'est pas initialisee :
        sta     vs_on                   ; sans carte, le destructeur ne doit
        sta     ptr1                    ; rien defaire
        lda     #$C1                    ; la carte serie : slots 1..7
        sta     ptr1+1
ins_card:
        ldx     #0
ins_id: ldy     id_ofs,x
        lda     (ptr1),y
        cmp     id_val,x
        bne     ins_next
        inx
        cpx     #4
        bcc     ins_id
        lda     ptr1+1                  ; signature vue : slot x 16 + $8F
        asl
        asl
        asl
        asl
        clc
        adc     #ACIA_OFS
        tax
        ; Un 6551 y repond-il ? Deux valeurs ecrites dans son registre de
        ; commande doivent s'y relire (a2tools) ; sinon on remet tout.
        lda     ACIA_STATUS,x
        pha
        lda     ACIA_CMD,x
        pha
        ldy     #%00000010
ins_try:
        tya
        sta     ACIA_CMD,x
        cmp     ACIA_CMD,x
        bne     ins_not
        iny
        cpy     #%00000100
        bne     ins_try
        sta     ACIA_STATUS,x           ; reset logiciel
        lda     ACIA_CMD,x
        lsr
        bcc     ins_acia                ; DTR retombe : c'est bien un 6551
ins_not:
        pla
        sta     ACIA_CMD,x
        pla
        sta     ACIA_STATUS,x
ins_next:
        inc     ptr1+1
        lda     ptr1+1
        cmp     #$C8
        bcc     ins_card
ins_none:
        lda     #0
        tax
        rts

ins_acia:
        pla                             ; les deux registres sauves, sans suite
        pla
        stx     vs_acia
        lda     #%00010000              ; 115 200 bauds (horloge externe x16),
        sta     ACIA_CTRL,x             ; 8 bits, 1 stop
        lda     #%00001011              ; DTR, pas d'interruption, RTS bas
        sta     ACIA_CMD,x
        ; Le slot des volumes : le premier dont aucune unite n'est prise.
        lda     #0
        sta     vs_slot
ins_slot:
        inc     vs_slot
        lda     vs_slot
        cmp     #8
        bcs     ins_none                ; sept slots pris : pas de place
        asl
        asl
        asl
        asl
        sta     vs_dev1
        ora     #$80
        sta     vs_dev2
        ldy     DEVCNT
ins_dev:
        lda     DEVLST,y
        cmp     vs_dev1
        beq     ins_slot
        cmp     vs_dev2
        beq     ins_slot
        dey
        bpl     ins_dev
        ; Le slot est libre : DEVADR, DEVLST, le talon.
        lda     vs_slot
        asl
        tax
        lda     DEVADR,x
        sta     vs_orig
        lda     DEVADR+1,x
        sta     vs_orig+1
        lda     #<THUNK
        sta     DEVADR,x
        sta     DEVADR+16,x
        lda     #>THUNK
        sta     DEVADR+1,x
        sta     DEVADR+17,x
        ldy     DEVCNT
        iny
        lda     vs_dev1
        sta     DEVLST,y
        iny
        lda     vs_dev2
        sta     DEVLST,y
        sty     DEVCNT
        ldy     #thunk_len-1
ins_cpy:
        lda     thunk_src,y
        sta     THUNK,y
        dey
        bpl     ins_cpy
        jsr     ins_irq
        lda     #1
        sta     vs_on
        lda     vs_acia                 ; (slot serie << 4) | slot des volumes
        sec
        sbc     #ACIA_OFS
        ora     vs_slot
        ldx     #0
        rts

; ----------------------------------------------------------------------
; Le pilote, tel que ProDOS l'appelle (par le talon) : $42-$47 poses,
; A = erreur et report leve en cas d'echec.
; ----------------------------------------------------------------------
vs_driver:
        cld
        lda     #0                      ; A = 0 (lecteur 1) ou 2 (lecteur 2)
        ldx     P_UNIT
        cpx     vs_dev1
        beq     drv_cmd
        lda     #2
        cpx     vs_dev2
        beq     drv_cmd
        lda     #E_NODEV
        sec
        rts
drv_cmd:
        ldx     P_CMD
        beq     drv_status
        cpx     #1
        beq     drv_read
        cpx     #2
        bne     drv_other
        jmp     drv_write
drv_other:
        lda     #0                      ; FORMAT et le reste : rien a faire
        clc
        rts
drv_status:
        lda     #0                      ; taille inconnue : $FFFF blocs
        ldx     #$FF
        ldy     #$FF
        clc
        rts

drv_read:
        clc
        adc     #VD_READ                ; 3 ou 5
        jsr     envelope                ; php, sei, X = 6551, l'enveloppe partie
        jsr     expect_env              ; son echo
        bcs     drv_fail
        ldy     #0                      ; l'heure et la date, dans le XOR
rd_dt:  jsr     getc
        bcs     drv_fail
        sta     vs_dt,y
        eor     vs_chk
        sta     vs_chk
        iny
        cpy     #4
        bcc     rd_dt
        jsr     getc                    ; le XOR de l'en-tete
        bcs     drv_fail
        cmp     vs_chk
        bne     drv_fail
        lda     #0
        sta     vs_chk
        lda     #2                      ; les 512 octets : deux pages
        sta     vs_pg
        ldy     #0
rd_blk: jsr     getc
        bcs     drv_fail
        jsr     st_buf                  ; dans le banc de ProDOS (voir le talon)
        eor     vs_chk
        sta     vs_chk
        iny
        bne     rd_blk
        inc     P_BUF+1
        dec     vs_pg
        bne     rd_blk
        jsr     getc                    ; le XOR du bloc
        bcs     drv_fail
        cmp     vs_chk
        bne     drv_fail
        dec     P_BUF+1                 ; le tampon comme on l'a recu
        dec     P_BUF+1
        lda     vs_dt                   ; l'horloge ProDOS a l'heure de l'hote
        sta     TIME
        lda     vs_dt+1
        sta     TIME+1
        lda     vs_dt+2
        sta     DATE
        lda     vs_dt+3
        sta     DATE+1
drv_ok:
        plp                             ; les interruptions comme avant
        lda     #0
        clc
        rts
drv_fail:
        plp
        lda     #E_IO
        sec
        rts

drv_write:
        clc
        adc     #VD_WRITE               ; 2 ou 4
        jsr     envelope
        lda     #0
        sta     vs_chk
        lda     #2
        sta     vs_pg
        ldy     #0
wr_blk: jsr     ld_buf                  ; depuis le banc de ProDOS (voir le talon)
        jsr     putc_chk
        iny
        bne     wr_blk
        inc     P_BUF+1
        dec     vs_pg
        bne     wr_blk
        dec     P_BUF+1
        dec     P_BUF+1
        lda     vs_chk                  ; le XOR du bloc
        jsr     putc
        jsr     expect_env              ; l'echo de l'enveloppe
        bcs     wr_fail
        jsr     getc                    ; le XOR du bloc, tel que l'hote l'a vu
        bcs     wr_fail
        cmp     vs_chk
        beq     wr_ok
wr_fail:
        jmp     drv_fail
wr_ok:  jmp     drv_ok

; L'echo de l'enveloppe : $C5, la commande, le bloc. Report leve si un octet
; manque ou differe.
expect_env:
        jsr     getc
        bcs     ex_bad
        cmp     #VD_ENV
        bne     ex_bad
        jsr     getc
        bcs     ex_bad
        cmp     vs_cmd
        bne     ex_bad
        jsr     getc
        bcs     ex_bad
        cmp     P_BLK
        bne     ex_bad
        jsr     getc
        bcs     ex_bad
        cmp     P_BLK+1
        bne     ex_bad
        clc
        rts
ex_bad: sec
        rts

; L'enveloppe : A = la commande. Coupe les interruptions (php sur la pile
; de l'appelant, repris par drv_ok/drv_fail), charge X, envoie les cinq
; octets et laisse vs_chk a leur XOR.
envelope:
        sta     vs_cmd
        pla                             ; l'adresse de retour, sous le php
        tay
        pla
        php
        sei
        pha
        tya
        pha
        ldx     vs_acia
        lda     #0
        sta     vs_chk
        lda     #VD_ENV
        jsr     putc_chk
        lda     vs_cmd
        jsr     putc_chk
        lda     P_BLK
        jsr     putc_chk
        lda     P_BLK+1
        jsr     putc_chk
        lda     vs_chk
        jmp     putc

; Un octet envoye, et dans le XOR.
putc_chk:
        jsr     putc
        eor     vs_chk
        sta     vs_chk
        rts

; Un octet envoye (A garde). X = le 6551.
putc:
        pha
:       lda     ACIA_STATUS,x
        and     #$10                    ; TDRE
        beq     :-
        pla
        sta     ACIA_DATA,x
        rts

; Un octet recu dans A, report bas ; report leve apres ~0,3 s sans rien.
; X = le 6551, Y intact.
getc:
        lda     #0
        sta     vs_to
        lda     #$C0
        sta     vs_to+1
:       lda     ACIA_STATUS,x
        and     #$08                    ; RDRF
        bne     :+
        inc     vs_to
        bne     :-
        inc     vs_to+1
        bne     :-
        sec
        rts
:       lda     ACIA_DATA,x
        clc
        rts
