; Poser le prefixe ProDOS pour A2 File Cmd, depuis le lanceur (src/loader.c).
;
; Tout part du prefixe : A2FILE/A2FILE.CODE, les surcouches A2FILE/*.PLG,
; l'aide, A2FILE.CFG s'y lisent en relatif. Trois cas :
;  - il est deja pose (amorcage a froid : ProDOS met "/VOL/" ; Bitsy Bye :
;    le dossier du .SYSTEM lance ; retour de FORMAT.SYS : ce qu'il a laisse) :
;    on n'y touche pas. C'est ce qui permet d'installer A2FILE.SYSTEM et son
;    dossier A2FILE n'importe ou sur un disque dur, pas seulement a la racine
;    d'un volume nomme /A2FILECMD.
;  - il est VIDE : relance par "-A2FILE.SYSTEM" depuis BASIC.SYSTEM, qui le
;    vide en lancant un SYS mais laisse en $0280 le chemin complet du
;    programme lance ("/VOL/DIR/A2FILE.SYSTEM") : son dossier est le notre.
;  - sinon (chemin relatif en $0280, ou rien) : ON_LINE sur le dernier
;    peripherique utilise ($BF30, celui d'ou A2FILE.CODE vient d'etre lu)
;    donne le nom du volume, qu'on pose en "/NOM".
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
GET_PREFIX   = $C7
SYSPATH      = $0280            ; le chemin du .SYSTEM lance, longueur en tete

        .code

; void set_boot_prefix(void);
_set_boot_prefix:
        jsr     MLI
        .byte   GET_PREFIX
        .word   pfx_parm
        bcs     sbp_online
        lda     pfx_buf
        bne     sbp_fail        ; deja pose : on le garde
        ldy     SYSPATH         ; vide : le dossier du programme lance
        beq     sbp_online
        lda     SYSPATH+1
        cmp     #'/'
        bne     sbp_online      ; chemin relatif : sans prefixe, insoluble
sbp_last:
        lda     SYSPATH,y       ; la derniere barre, en partant de la fin
        cmp     #'/'
        beq     sbp_dir
        dey
        bne     sbp_last
sbp_dir:
        cpy     #2
        bcc     sbp_online      ; "/NOM" seul : pas un dossier
        sty     pfx_buf         ; le dossier, sa barre finale comprise
sbp_cpy:
        lda     SYSPATH,y
        sta     pfx_buf,y
        dey
        bne     sbp_cpy
        jmp     sbp_set

sbp_online:
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

        tax                     ; X = longueur du nom
        clc
        adc     #1              ; + le '/' de tete
        sta     pfx_buf         ; octet de longueur pour SET_PREFIX
        lda     #'/'
        sta     pfx_buf+1
        ldy     #0
sbp_cp: lda     ol_buf+1,y
        sta     pfx_buf+2,y
        iny
        dex
        bne     sbp_cp

sbp_set:
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
