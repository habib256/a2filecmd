; Set the ProDOS prefix for A2 File Cmd, from the launcher (src/loader.c).
;
; Everything starts from the prefix: A2FILE/A2FILE.CODE, the A2FILE/*.PLG
; overlays, the help, A2FILE.CFG are all read relative to it. Three cases:
;  - it is already set (cold boot: ProDOS sets "/VOL/"; Bitsy Bye: the
;    directory of the launched .SYSTEM; return from FORMAT.SYS: whatever it
;    left): we leave it alone. This is what allows A2FILE.SYSTEM and its
;    A2FILE directory to be installed anywhere on a hard disk, not only at
;    the root of a volume named /A2FILECMD.
;  - it is EMPTY: relaunch by "-A2FILE.SYSTEM" from BASIC.SYSTEM, which
;    clears it when launching a SYS but leaves at $0280 the full path of
;    the launched program ("/VOL/DIR/A2FILE.SYSTEM"): its directory is ours.
;  - otherwise (relative path at $0280, or nothing): ON_LINE on the last
;    device used ($BF30, the one A2FILE.CODE has just been read from) gives
;    the volume name, which we set as "/NAME".
;
; A direct MLI call rather than cc65's chdir()/getcwd(), whose linking
; (cwd module, heap) unbalanced the launcher's tight stack and made the
; load crash. The buffers are in low BSS ($35xx), outside the area that
; the read of A2FILE.CODE fills.

        .export         _set_boot_prefix

MLI          = $BF00
DEVNUM       = $BF30            ; last ProDOS device used
ON_LINE      = $C5
SET_PREFIX   = $C6
GET_PREFIX   = $C7
SYSPATH      = $0280            ; path of the launched .SYSTEM, length first

        .code

; void set_boot_prefix(void);
_set_boot_prefix:
        jsr     MLI
        .byte   GET_PREFIX
        .word   pfx_parm
        bcs     sbp_online
        lda     pfx_buf
        bne     sbp_fail        ; already set: keep it
        ldy     SYSPATH         ; empty: the launched program's directory
        beq     sbp_online
        lda     SYSPATH+1
        cmp     #'/'
        bne     sbp_online      ; relative path: without a prefix, unsolvable
sbp_last:
        lda     SYSPATH,y       ; the last slash, scanning from the end
        cmp     #'/'
        beq     sbp_dir
        dey
        bne     sbp_last
sbp_dir:
        cpy     #2
        bcc     sbp_online      ; "/NAME" alone: not a directory
        sty     pfx_buf         ; the directory, its trailing slash included
sbp_cpy:
        lda     SYSPATH,y
        sta     pfx_buf,y
        dey
        bne     sbp_cpy
        jmp     sbp_set

sbp_online:
        lda     DEVNUM
        beq     sbp_fail        ; unit 0 = "all drives": ON_LINE would
                                ; overflow ol_buf (16 bytes per volume).
                                ; Never the case after reading A2FILE.CODE,
                                ; but a guard if the routine is used elsewhere.
        sta     ol_unit
        jsr     MLI
        .byte   ON_LINE
        .word   ol_parm
        bcs     sbp_fail        ; MLI error: leave the prefix as it is

        lda     ol_buf          ; high nibble = slot/drive, low = name length
        and     #$0F
        beq     sbp_fail        ; length 0: ol_buf+1 carries an error code

        tax                     ; X = name length
        clc
        adc     #1              ; + the leading '/'
        sta     pfx_buf         ; length byte for SET_PREFIX
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
        .byte   0               ; unit_num, filled in at call time
        .word   ol_buf          ; data_buffer

pfx_parm:
        .byte   1               ; param_count
        .word   pfx_buf         ; pathname (length byte + string)

        .bss

ol_buf:
        .res    16              ; status byte + 15 of volume name
pfx_buf:
        .res    64
