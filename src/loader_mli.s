; Poser le prefixe ProDOS sur le volume amorce, pour le lanceur
; (src/loader.c). Relance depuis le "]" de BASIC.SYSTEM ("-A2FILE.SYSTEM"),
; ProDOS a un prefixe VIDE quand le lanceur reprend la main (BASIC.SYSTEM le
; vide en lancant un programme SYS). A2 File Cmd s'ouvre alors sur la liste
; des volumes au lieu des deux panneaux, et ne retrouve pas ses preferences.
; On refait le prefixe nous-memes : ON_LINE sur le dernier peripherique
; utilise ($BF30, celui d'ou A2FILE.CODE vient d'etre lu, donc le volume
; amorce) donne le nom du volume, qu'on pose par SET_PREFIX en "/NOM".
;
; Appel MLI direct plutot que chdir()/getcwd() de cc65, dont l'edition de
; liens (module cwd, tas) desequilibrait la pile serree du lanceur et
; faisait planter le chargement. Les tampons sont en BSS basse ($35xx),
; hors de la zone que la lecture d'A2FILE.CODE remplit.

        .export         _set_boot_prefix

MLI          = $BF00
DEVNUM       = $BF30            ; dernier peripherique ProDOS utilise
ON_LINE      = $C5
SET_PREFIX   = $C6

        .code

; void set_boot_prefix(void);
_set_boot_prefix:
        lda     DEVNUM
        beq     sbp_fail        ; unit 0 = « tous les lecteurs » : ON_LINE
                                ; deborderait ol_buf (16 octets par volume).
                                ; Jamais le cas apres la lecture d'A2FILE.CODE,
                                ; mais une garde si la routine sert ailleurs.
        sta     ol_unit
        jsr     MLI
        .byte   ON_LINE
        .word   ol_parm
        bcs     sbp_fail        ; erreur MLI : on laisse le prefixe tel quel

        lda     ol_buf          ; nibble haut = slot/drive, bas = longueur du nom
        and     #$0F
        beq     sbp_fail        ; longueur 0 : ol_buf+1 porte un code d'erreur

        pha                     ; garder la longueur du nom
        clc
        adc     #1              ; + le '/' de tete
        sta     pfx_buf         ; octet de longueur pour SET_PREFIX
        lda     #'/'
        sta     pfx_buf+1
        pla
        tax                     ; X = longueur du nom
        ldy     #0
sbp_cp: lda     ol_buf+1,y
        sta     pfx_buf+2,y
        iny
        dex
        bne     sbp_cp

        jsr     MLI
        .byte   SET_PREFIX
        .word   pfx_parm
sbp_fail:
        rts

        .data

ol_parm:
        .byte   2               ; param_count
ol_unit:
        .byte   0               ; unit_num, rempli a l'appel
        .word   ol_buf          ; data_buffer

pfx_parm:
        .byte   1               ; param_count
        .word   pfx_buf         ; pathname (octet de longueur + chaine)

        .bss

ol_buf:
        .res    16              ; octet d'etat + 15 du nom de volume
pfx_buf:
        .res    64
