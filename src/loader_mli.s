; Set the ProDOS prefix for A2 File Cmd, from the launcher (src/loader.c).
;
; Everything starts from the prefix: A2FILE/A2FILE.CODE, the A2FILE/*.PLG
; overlays, the help, A2FILE.CFG are all read relative to it. First prefer
; a bounded absolute $0280 path ending in A2FILE.SYSTEM: BASIC may retain
; the old program's prefix when launching a SYS by its full path. Otherwise:
;  - it is already set (cold boot: ProDOS sets "/VOL/"; Bitsy Bye: the
;    directory of the launched .SYSTEM; relaunch from a selector: whatever it
;    left): we leave it alone. This is what allows A2FILE.SYSTEM and its
;    A2FILE directory to be installed anywhere on a hard disk, not only at
;    the root of a volume named /A2FILECMD.
;  - if empty (relative/unrelated path at $0280, or nothing): ON_LINE on the last
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
        bcs     sbp_fail        ; a failed query is not an empty prefix
        ; BASIC may retain the program's prefix even for an absolute SYS
        ; launch. Only trust $0280 if it names THIS launcher, not stale data.
        ldy     SYSPATH
        cpy     #64
        bcs     sbp_keep
        cpy     #14
        bcc     sbp_keep
        lda     SYSPATH+1
        cmp     #'/'
        bne     sbp_keep
        ldx     #12
sbp_name:
        lda     SYSPATH,y
        ora     #$20
        cmp     own_name,x
        bne     sbp_keep
        dey
        dex
        bpl     sbp_name
        lda     SYSPATH,y
        cmp     #'/'
        bne     sbp_keep
        jmp     sbp_dir
sbp_keep:
        lda     pfx_buf
        bne     sbp_fail
        jmp     sbp_online
sbp_dir:
        cpy     #2
        bcc     sbp_keep        ; "/NAME" alone: not a directory
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

        .rodata
own_name: .byte "a2file.system"

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
