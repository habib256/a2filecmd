; fanta.s -- FANTA.SYSTEM, the Fantavision movie player of A2 File Cmd.
;
; A ProDOS interpreter (JMP, $EE $EE, buffer length, path at $2006): A2 File
; Cmd loads it at $2000 with the movie's full path, the prefix set to its own
; directory. The program moves itself to $A400 (both hi-res pages are
; needed), reads the movie to $8000, has the engine (engine.s) check it and
; plays it. Escape, the end of a counted movie followed by a key, or a
; refused movie return to A2 File Cmd: A2FILE.SYSTEM is loaded again from
; the prefix, the way src/chain.s does it; QUIT to ProDOS only if that fails.
;
; Keys while playing: Escape returns, Space pauses and resumes, Tab switches
; between the accelerated speed (the default: as fast as the engine draws,
; plus a delay per frame set by the digits 1-9, 0 for none) and the
; original speed (each frame held until the original player's time for it
; has passed: fv_timing).
;
; Data safety: the only MLI calls are OPEN, GET_EOF, READ and CLOSE (and
; QUIT); nothing is ever written to a disk. Main memory only: no auxiliary
; memory, so /RAM is untouched. The pages the program uses are marked in
; the ProDOS system bitmap while it runs and the bitmap is given back as it
; was before A2FILE.SYSTEM is loaded. Memory map: fanta.cfg.
;
; Plain 6502: the same file serves both editions.

        .import fv_check, fv_begin, fv_first, fv_next, fv_timing
        .import fv_movie, fv_len, fv_shown, fv_wait, fv_count
        .import __CODE_LOAD__, __CODE_RUN__, __CODE_SIZE__, __RODATA_SIZE__
        .import __BSS_RUN__, __BSS_SIZE__
        .import __TABLES_LOAD__, __TABLES_RUN__, __TABLES_SIZE__
        .macpack longbranch

MLI     = $BF00
BITMAP  = $BF58                 ; 24 bytes, one bit a page, $80 = lowest
KBD     = $C000
STORE80OFF = $C000              ; (write)
CLR80VID = $C00C
KBDSTRB = $C010
TXTCLR  = $C050
TXTSET  = $C051
MIXCLR  = $C052
LOWSCR  = $C054
HISCR   = $C055
HIRES   = $C057
SETAN3  = $C05F
ROMIN   = $C082
MOVIE   = $8000
IOBUF   = $0800
MAXLEN  = 9216
PATHMAX = 64

        .zeropage
src:    .res 2
dst:    .res 2
cnt:    .res 2
wl:     .res 2                  ; wait, in units of 257 cycles
msgp:   .res 2

        .bss
mpath:  .res PATHMAX + 1        ; the movie's path, length first
savebm: .res 24                 ; the system bitmap as it was
mode:   .res 1                  ; 0 accelerated, 1 original speed
delay:  .res 1                  ; 0-9: per-frame delay, accelerated

; -- at $2000: the interpreter header, then the move -----------------------
        .segment "LOADER"
        jmp     start
        .byte   $EE, $EE
        .byte   PATHMAX + 1     ; the path buffer's length
path0:  .byte   0               ; the launcher stores the path here
        .res    PATHMAX
start:  cld
        ldx     #$FF
        txs
        lda     #<__BSS_RUN__   ; variables to zero
        sta     dst
        lda     #>__BSS_RUN__
        sta     dst+1
        lda     #<__BSS_SIZE__
        sta     cnt
        lda     #>__BSS_SIZE__
        sta     cnt+1
        ldy     #0
@zero:  lda     cnt
        ora     cnt+1
        beq     @path
        tya
        sta     (dst),y
        inc     dst
        bne     :+
        inc     dst+1
:       lda     cnt
        bne     :+
        dec     cnt+1
:       dec     cnt
        jmp     @zero
@path:  ldx     path0           ; the path, if one fits
        cpx     #PATHMAX + 1
        bcs     @move
:       lda     path0,x
        sta     mpath,x
        dex
        bpl     :-
@move:  lda     #<__CODE_LOAD__ ; the program, to $A400
        sta     src
        lda     #>__CODE_LOAD__
        sta     src+1
        lda     #<__CODE_RUN__
        sta     dst
        lda     #>__CODE_RUN__
        sta     dst+1
        lda     #<(__CODE_SIZE__ + __RODATA_SIZE__)
        sta     cnt
        lda     #>(__CODE_SIZE__ + __RODATA_SIZE__)
        sta     cnt+1
        jsr     copy
        lda     #<__TABLES_LOAD__ ; the engine's tables, to low memory
        sta     src
        lda     #>__TABLES_LOAD__
        sta     src+1
        lda     #<__TABLES_RUN__
        sta     dst
        lda     #>__TABLES_RUN__
        sta     dst+1
        lda     #<__TABLES_SIZE__
        sta     cnt
        lda     #>__TABLES_SIZE__
        sta     cnt+1
        jsr     copy
        jmp     main

; cnt bytes from src to dst, upwards.
copy:   ldy     #0
@copy:  lda     cnt
        ora     cnt+1
        beq     @done
        lda     (src),y
        sta     (dst),y
        inc     src
        bne     :+
        inc     src+1
:       inc     dst
        bne     :+
        inc     dst+1
:       lda     cnt
        bne     :+
        dec     cnt+1
:       dec     cnt
        jmp     @copy
@done:  rts

; -- the program, at $A400 -----------------------------------------------------
        .code
main:   ldx     #23             ; the bitmap as it is, given back on the
:       lda     BITMAP,x        ; way out
        sta     savebm,x
        dex
        bpl     :-
        lda     mpath
        bne     :+
        lda     #<nopath
        ldx     #>nopath
        jmp     refuse
:       jsr     MLI             ; OPEN
        .byte   $C8
        .word   openp
        jcs     rderr
        lda     openref
        sta     eofref
        sta     readref
        jsr     MLI             ; GET_EOF
        .byte   $D1
        .word   eofp
        jcs     rdclose
        lda     eofw+2          ; 513 to 9,216 bytes
        jne     szclose
        lda     eofw+1
        cmp     #>MAXLEN
        bcc     :+
        jne     szclose
        lda     eofw
        jne     szclose
:       lda     eofw+1
        cmp     #>513
        jcc     szclose
        bne     :+
        lda     eofw
        cmp     #<513
        jcc     szclose
:       lda     eofw
        sta     rdlen
        lda     eofw+1
        sta     rdlen+1
        jsr     MLI             ; READ, all of it
        .byte   $CA
        .word   readp
        jcs     rdclose
        lda     rdgot           ; a short read is an error, not an end
        cmp     rdlen
        jne     rdclose
        lda     rdgot+1
        cmp     rdlen+1
        jne     rdclose
        jsr     close
        jcs     rderr
        ldx     #$0C            ; the movie read: mark $0C00-$BEFF in use
:       txa                     ; (not before: ProDOS will not READ into
        lsr                     ; marked pages)
        lsr
        lsr
        tay
        txa
        and     #7
        sty     cnt
        tay
        lda     bits,y
        ldy     cnt
        ora     BITMAP,y
        sta     BITMAP,y
        inx
        cpx     #$BF
        bne     :-
        lda     #<MOVIE
        sta     fv_movie
        lda     #>MOVIE
        sta     fv_movie+1
        lda     eofw
        sta     fv_len
        lda     eofw+1
        sta     fv_len+1
        jsr     fv_check
        beq     play
        clc                     ; code 1-6: the reason
        adc     #'0'
        sta     notfv+whyofs
        lda     #<notfv
        ldx     #>notfv
        jmp     refuse
szclose:
        jsr     close
        lda     #1 + '0'
        sta     notfv+whyofs
        lda     #<notfv
        ldx     #>notfv
        jmp     refuse
rdclose:
        jsr     close
rderr:  lda     #<cantread
        ldx     #>cantread
        jmp     refuse

close:  jsr     MLI             ; CLOSE
        .byte   $CC
        .word   closep
        rts

; -- playing ---------------------------------------------------------------------
play:   jsr     fv_begin
        jsr     fv_first
        sta     STORE80OFF      ; plain 40-column hi-res, page 1, full screen
        sta     CLR80VID
        sta     SETAN3
        sta     HIRES
        sta     MIXCLR
        sta     LOWSCR
        sta     TXTCLR
@loop:  jsr     keys
        jsr     fv_next
        bne     @end
        lda     mode
        beq     @fast
        jsr     fv_timing       ; original speed: hold the frame
        jsr     waitorig
        jmp     @show
@fast:  jsr     pause
@show:  lda     fv_shown
        cmp     #$20
        beq     :+
        sta     HISCR
        jmp     @loop
:       sta     LOWSCR
        jmp     @loop
@end:   jsr     getkey          ; the last frame stays until a key
        jmp     back

; Reads a key if there is one: Escape returns, Space pauses, Tab switches
; the speed, a digit sets the delay.
keys:   lda     KBD
        bpl     @none
        sta     KBDSTRB
        jsr     key
        cmp     #' '
        bne     @none
@pause: jsr     getkey          ; paused: until Space again (or Escape)
        jsr     key
        cmp     #' '
        bne     @pause
@none:  rts

; One key in A (high bit set): acts on it, returns it without the high bit.
key:    and     #$7F
        cmp     #$1B
        bne     :+
        jmp     back
:       cmp     #$09
        bne     :+
        pha
        lda     mode
        eor     #1
        sta     mode
        sta     fv_count        ; the engine counts at the original speed
        pla
        rts
:       cmp     #'0'
        bcc     :+
        cmp     #'9' + 1
        bcs     :+
        pha
        and     #$0F
        sta     delay
        pla
:       rts

getkey: lda     KBD
        bpl     getkey
        sta     KBDSTRB
        rts

; Accelerated: delay * about 10,000 cycles.
pause:  ldy     delay
        beq     @done
@d:     ldx     #40
:       jsr     unit
        dex
        bne     :-
        dey
        bne     @d
@done:  rts

; About 250 cycles with the jsr and rts; X and Y kept.
unit:   lda     #33
:       sec
        sbc     #1
        bne     :-
        rts

; Original speed: fv_wait cycles, in units of 257 (the bits below are left).
waitorig:
        lda     fv_wait+3
        ora     fv_wait+2
        beq     :+
        lda     #$FF            ; over 16 million cycles: clipped
        sta     wl
        sta     wl+1
        bne     @loop
:       lda     fv_wait+1
        sta     wl
        lda     fv_wait+2
        sta     wl+1
@loop:  lda     wl              ; 3
        ora     wl+1            ; 3
        beq     @done           ; 2
        ldx     #47             ; 2
:       dex                     ; 47 * 5 - 1
        bne     :-
        lda     wl              ; 3
        bne     :+              ; 3 (or 2 + 5)
        dec     wl+1
:       dec     wl              ; 5
        jmp     @loop           ; 3: 257 a unit
@done:  rts

; -- leaving ---------------------------------------------------------------------
; A/X: a message for the text screen; then a key, then the way back.
refuse: sta     msgp
        stx     msgp+1
        sta     STORE80OFF
        sta     CLR80VID
        sta     TXTSET
        sta     LOWSCR
        ldx     #23             ; clear the 40 columns of 24 rows
@clr:   jsr     textrow
        lda     #$A0
        ldy     #39
:       sta     (dst),y
        dey
        bpl     :-
        dex
        bpl     @clr
        ldx     #10             ; the message on row 10, the key on 12
        jsr     textrow
        ldy     #0
:       lda     (msgp),y
        beq     :+
        ora     #$80
        sta     (dst),y
        iny
        bne     :-
:       ldx     #12
        jsr     textrow
        ldy     #0
:       lda     presskey,y
        beq     :+
        ora     #$80
        sta     (dst),y
        iny
        bne     :-
:       jsr     getkey
        ;jmp    back

; Back to A2 File Cmd: text screen, the bitmap as it was, then the thunk.
back:   ldx     #$FF
        txs
        sta     TXTSET
        sta     LOWSCR
        ldx     #23
:       lda     savebm,x
        sta     BITMAP,x
        dex
        bpl     :-
        ldy     #0              ; (more than 128 bytes: counted up)
:       lda     thunk_src,y
        sta     $0300,y
        iny
        cpy     #thunk_len
        bne     :-
        jmp     $0300

; dst = the start of text row X (page 1).
textrow:
        txa
        and     #7
        lsr
        sta     dst+1
        lda     #0
        ror
        sta     dst
        txa
        lsr
        lsr
        lsr
        tay
        lda     dst
        clc
        adc     rowx40,y
        sta     dst
        lda     dst+1
        adc     #$04
        sta     dst+1
        rts

; -- MLI parameters ----------------------------------------------------------------
openp:  .byte   3
        .word   mpath
        .word   IOBUF
openref:
        .byte   0
eofp:   .byte   2
eofref: .byte   0
eofw:   .res    3
readp:  .byte   4
readref:
        .byte   0
        .word   MOVIE
rdlen:  .word   0
rdgot:  .word   0
closep: .byte   1
        .byte   0               ; every file: only ours is open

        .rodata
bits:   .byte   $80, $40, $20, $10, $08, $04, $02, $01
rowx40: .byte   $00, $28, $50
nopath: .byte   "FANTAVISION: NO MOVIE WAS GIVEN.", 0
cantread:
        .byte   "FANTAVISION: THE MOVIE CANNOT BE READ.", 0
notfv:  .byte   "NOT A FANTAVISION MOVIE (CHECK "
whyofs  = * - notfv
        .byte   "0).", 0
presskey:
        .byte   "PRESS A KEY TO RETURN.", 0

; The way back, run from page 3: A2FILE.SYSTEM from the prefix, read whole
; to $2000 with the I/O buffer at $BB00 (this program is over by then). A
; failure goes to ProDOS's QUIT.
thunk_src:
        .org    $0300
thunk:  jsr     MLI             ; OPEN
        .byte   $C8
        .word   t_open
        bcs     t_quit
        lda     t_ref
        sta     t_eofref
        sta     t_rdref
        jsr     MLI             ; GET_EOF
        .byte   $D1
        .word   t_eofp
        bcs     t_close
        lda     t_eof+2         ; up to $BB00 - $2000
        bne     t_close
        lda     t_eof+1
        cmp     #$9B
        bcs     t_close
        sta     t_len+1
        lda     t_eof
        sta     t_len
        jsr     MLI             ; READ
        .byte   $CA
        .word   t_read
        bcs     t_close
        lda     t_got
        cmp     t_len
        bne     t_close
        lda     t_got+1
        cmp     t_len+1
        bne     t_close
        jsr     MLI             ; CLOSE
        .byte   $CC
        .word   t_closep
        bcs     t_quit
        bit     ROMIN
        jmp     $2000
t_close:
        jsr     MLI
        .byte   $CC
        .word   t_closep
t_quit: jsr     MLI             ; QUIT
        .byte   $65
        .word   t_quitp
t_open: .byte   3
        .word   t_name
        .word   $BB00
t_ref:  .byte   0
t_eofp: .byte   2
t_eofref:
        .byte   0
t_eof:  .res    3
t_read: .byte   4
t_rdref:
        .byte   0
        .word   $2000
t_len:  .word   0
t_got:  .word   0
t_closep:
        .byte   1, 0
t_quitp:
        .byte   4, 0
        .word   0
        .byte   0
        .word   0
t_name: .byte   13, "A2FILE.SYSTEM"
thunk_end:
        .reloc
thunk_len = thunk_end - thunk
        .assert thunk_len <= $D0, error, "the return thunk overflows page 3"
