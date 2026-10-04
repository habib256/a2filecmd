; fanta.s -- FANTA.SYSTEM, the Fantavision movie player of A2 File Cmd.
;
; A ProDOS interpreter (JMP, $EE $EE, buffer length, path at $2006): A2 File
; Cmd loads it at $2000 with the movie's full path, the prefix set to its own
; directory. The program moves itself to $A400 (both hi-res pages are
; needed), reads the movie to $8000, has the engine (engine.s) check it and
; plays it. Escape, or a refused movie followed by a key, return to A2 File
; Cmd: A2FILE.SYSTEM is loaded again from the prefix, the way src/chain.s
; does it; QUIT to ProDOS only if that fails.
;
; Ctrl-Reset returns too: once the bitmap is saved, the reset vector is
; set to the way back. Until then it is the monitor's OLDRST ($FF59, in
; ROM), set first thing: A2 File Cmd's chain thunk leaves that one, but the
; way on (FANTA.SYSTEM loaded again) leaves the previous instance's `back`,
; whose bitmap copy the start zeroes.
;
; Keys while playing: Escape returns, Space pauses and resumes, Tab switches
; between the original speed (the default: each frame held until the
; original player's time for it has passed, fv_timing) and the accelerated
; one (as fast as the engine draws, plus a delay per frame set by the
; digits 1-9, 0 for none), S starts or stops the slideshow.
;
; The end: a movie always starts again. A counted movie stays two seconds
; on its last frame, then plays from the start: in place, or, with a
; backdrop (Background objects are drawn into it), read again from the
; disk. In a slideshow each movie plays once round (a looping one until
; frame 0 comes back), stays two seconds, and the next movie of the
; directory follows (fload.s, scan), the first after the last. The next
; one, or the same one read again, is played by FANTA.SYSTEM loaded anew
; by the return thunk, its command given the slideshow and the speed. A
; movie refused during a slideshow is shown three seconds, then the next.
;
; Data safety: the only MLI calls are OPEN, GET_EOF, READ and CLOSE (and
; QUIT); nothing is ever written to a disk. Main memory only: no auxiliary
; memory, so /RAM is untouched. The pages the program uses are marked in
; the ProDOS system bitmap while it runs and the bitmap is given back as it
; was before A2FILE.SYSTEM is loaded. Memory map: fanta.cfg.
;
; Plain 6502: the same file serves both editions.

        .import fv_check, fv_begin, fv_first, fv_next, fv_timing
        .import fv_shown, fv_wait, fv_count, fv_bdrop, fv_frames
        .import fv_vkey, fv_vframe, fload
        .import cmdbuf, ocl, cdl, nextn, mode, delay, slide
        .export path0
        .import __CODE_LOAD__, __CODE_RUN__, __CODE_SIZE__, __RODATA_SIZE__
        .import __BSS_RUN__, __BSS_SIZE__
        .import __TABLES_LOAD__, __TABLES_RUN__, __TABLES_SIZE__
        .import __FCOLD_SIZE__
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
SOFTEV  = $03F2                 ; the reset vector, then its check byte
PWREDUP = $03F4
OLDRST  = $FF59                 ; the monitor's reset entry, in ROM
PATHMAX = 64

        .zeropage
src:    .res 2
dst:    .res 2
cnt:    .res 2
wl:     .res 2                  ; wait, in units of 257 cycles
msgp:   .res 2

        .bss
savebm: .res 24                 ; the system bitmap as it was

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
        lda     #<OLDRST        ; Ctrl-Reset: not into the previous
        sta     SOFTEV          ; instance's code (the way on) before
        lda     #>OLDRST        ; savebm is filled again
        sta     SOFTEV+1
        eor     #$A5
        sta     PWREDUP
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
@path:  lda     #<__CODE_LOAD__ ; the program, to $A400
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
        lda     #<(__TABLES_SIZE__ + __FCOLD_SIZE__)
        sta     cnt                     ; (FCOLD follows TABLES)
        lda     #>(__TABLES_SIZE__ + __FCOLD_SIZE__)
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

; A/X: a message for the text screen; then a key, then the way back. In a
; slideshow, three seconds without a key go on to the next movie.
refuse: pha
        txa
        pha
        jsr     textscr
        pla
        tay
        pla
        ldx     #10             ; the message on row 10, the key on 12
        jsr     print           ; (40 columns at most)
        ldx     #12
        lda     #<presskey
        ldy     #>presskey
        jsr     print
        lda     slide
        beq     @key
        lda     nextn
        beq     @key
        lda     #12             ; 12 x 256 x ~1,000 cycles
        sta     wl
@w:     ldx     #0
:       lda     KBD
        bmi     @key
        jsr     unit
        jsr     unit
        jsr     unit
        jsr     unit
        dex
        bne     :-
        dec     wl
        bne     @w
        jmp     next
@key:   jsr     getkey
        jmp     back

presskey:
        .byte   "PRESS A KEY TO RETURN.", 0

        .import __FCOLD_LOAD__, __FCOLD_RUN__
        .assert __FCOLD_LOAD__ = __TABLES_LOAD__ + __TABLES_SIZE__, error, "FCOLD must follow TABLES"
        .assert __FCOLD_RUN__ = __TABLES_RUN__ + __TABLES_SIZE__, error, "FCOLD must follow TABLES"

; -- the program, at $A400 -----------------------------------------------------
        .code
main:   ldx     #23             ; the bitmap as it is, given back on the
:       lda     BITMAP,x        ; way out
        sta     savebm,x
        dex
        bpl     :-
        ldx     #<back          ; Ctrl-Reset: back to A2 File Cmd, the
        lda     #>back          ; bitmap given back (A2FC's $400C is in
        jsr     setsoftev       ; hi-res page 2 here)
        jsr     fload           ; the command, the movie, the backdrop
        bcc     :+              ; (fload.s, where the file was loaded)
        jmp     refuse
:       lda     mode            ; the engine counts at the original speed
        sta     fv_count
        ldx     #$0C
        bne     mark            ; (always)
                                ; read: mark $0C00-$BEFF in use (not
mark:   txa                     ; before: ProDOS will not READ into
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
        bne     mark
        ;jmp    play

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
        bne     @slide          ; (always)
:       sta     LOWSCR
@slide: lda     slide           ; a slideshow: once round, key frame 0
        beq     @loop           ; is shown again
        lda     fv_vkey
        beq     @loop
        lda     fv_vframe
        bne     @loop
        jsr     hold
        lda     slide           ; (S may have stopped it)
        beq     @loop
        lda     nextn
        beq     @loop           ; the only movie: it goes on
        jmp     next
@end:   jsr     hold            ; a counted movie: its last frame
        lda     slide
        beq     :+
        lda     nextn
        beq     :+
        jmp     next
:       lda     fv_frames       ; a single frame stays
        cmp     #1
        beq     @end
        lda     fv_bdrop        ; a backdrop may hold Background objects:
        beq     :+              ; read again from the disk
        jmp     same
:       jmp     play            ; else from the start, in place

; About two seconds at 1 MHz (30 x 256 units) on the frame shown, the keys
; read.
hold:   lda     #30
        sta     wl
@o:     jsr     keys
        ldx     #0
:       jsr     unit
        dex
        bne     :-
        dec     wl
        bne     @o
        rts

; Reads a key if there is one: Escape returns, Space pauses, Tab switches
; the speed, a digit sets the delay, S starts or stops the slideshow.
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
:       pha
        and     #$5F            ; S or s
        cmp     #'S'
        bne     :+
        lda     slide
        eor     #1
        sta     slide
:       pla
        cmp     #'0'
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
; wl is bytes 1 and 2 of the wait: only byte 3 makes it too long. Byte 2
; set is a wait of 65,536 cycles or more, which a frame of large solids
; takes (up to 240,000), not one to clip to 16 million.
waitorig:
        lda     fv_wait+3
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

; -- the way on ---------------------------------------------------------------------
; FANTA.SYSTEM loaded again by the return thunk, with a command (fload.s):
; "*" and the next movie of the directory (next), or "+" and this one with
; its backdrop (same), after the speed. The command is kept in cmdbuf: the
; path as given from cmdbuf+3, its directory cdl characters long. Too long
; for the startup buffer (64): back to A2 File Cmd instead.
next:   lda     cdl
        clc
        adc     nextn
        cmp     #PATHMAX - 1
        bcs     back
        tax
        ldy     nextn           ; the name after the directory
:       lda     nextn,y
        sta     cmdbuf+2,x
        dex
        dey
        bne     :-
        lda     cdl
        clc
        adc     nextn
        tax
        lda     #'*'
        bne     relaunch        ; (always)
same:   ldx     ocl
        cpx     #PATHMAX - 1
        bcs     back
        lda     #'+'
; A: the marker, X: the path's length.
relaunch:
        sta     cmdbuf+1
        inx
        inx
        stx     cmdbuf
        lda     #'O'            ; the speed
        ldx     mode
        bne     :+
        lda     delay
        clc
        adc     #'A'
:       sta     cmdbuf+2
        jsr     textscr         ; a clean screen while it loads
        lda     cmdbuf
        bne     leave           ; (always)

; -- leaving ---------------------------------------------------------------------
; Back to A2 File Cmd (back, A = 0), or FANTA.SYSTEM again (leave, A = the
; command's length): text screen, the bitmap as it was, then the thunk.
back:   lda     #0
leave:  ldx     #$FF
        txs
        pha
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
        pla
        sta     t_cmd
        beq     :+
        lda     #<t_fanta
        sta     t_open+1
        lda     #>t_fanta
        sta     t_open+2
:       ldx     #<OLDRST        ; the thunk's I/O buffer covers $BB00-$BEFF,
        lda     #>OLDRST        ; thunk_src among it: a reset from now on
        jsr     setsoftev       ; goes to the monitor, not to back
        jmp     $0300

; The reset vector to X (low) / A (high), with its check byte.
setsoftev:
        stx     SOFTEV
        sta     SOFTEV+1
        eor     #$A5
        sta     PWREDUP
        rts

; The text screen, 40 columns, cleared, the title on row 8.
textscr:
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
        ldx     #8
        lda     #<title
        ldy     #>title
; The string at A/Y on text row X, 40 characters at most.
print:  sta     msgp
        sty     msgp+1
        jsr     textrow
        ldy     #0
:       lda     (msgp),y
        beq     :+
        ora     #$80
        sta     (dst),y
        iny
        cpy     #40
        bne     :-
:       rts

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

        .rodata
bits:   .byte   $80, $40, $20, $10, $08, $04, $02, $01
rowx40: .byte   $00, $28, $50
title:  .byte   "FANTAVISION", 0

; The way back, run from page 3: A2FILE.SYSTEM from the prefix, read whole
; to $2000 with the I/O buffer at $BB00 (this program is over by then). A
; failure goes to ProDOS's QUIT. The way on (t_cmd nonzero): FANTA.SYSTEM
; from A2FILE/ instead, then the command's t_cmd + 1 bytes from cmdbuf
; (below $BB00, and above anything the read writes) to its startup buffer;
; if FANTA.SYSTEM cannot be read, A2FILE.SYSTEM as above.
thunk_src:
        .org    $0300
thunk:  jsr     MLI             ; OPEN
        .byte   $C8
        .word   t_open
        bcs     t_fail
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
        ldy     t_cmd           ; the way on: the startup buffer
        beq     t_go
:       lda     cmdbuf,y
        sta     $2006,y
        dey
        bpl     :-
t_go:   bit     ROMIN
        jmp     $2000
t_close:
        jsr     MLI
        .byte   $CC
        .word   t_closep
t_fail: lda     t_cmd           ; FANTA.SYSTEM failed: A2 File Cmd
        beq     t_quit
        lda     #0
        sta     t_cmd
        lda     #<t_name
        sta     t_open+1
        lda     #>t_name
        sta     t_open+2
        jmp     thunk
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
t_cmd:  .byte   0
t_name: .byte   13, "A2FILE.SYSTEM"
t_fanta:
        .byte   19, "A2FILE/FANTA.SYSTEM"
thunk_end:
        .reloc
thunk_len = thunk_end - thunk
        .assert thunk_len <= $D0, error, "the return thunk overflows page 3"
        .assert cmdbuf + 3 + PATHMAX + 18 <= $BB00, error, "cmdbuf under the thunk's I/O buffer"
        ; The way on reads FANTA.SYSTEM from $2000 before it copies cmdbuf:
        ; the file must end below it (FCOLD is the file's last segment).
        .assert __FCOLD_LOAD__ + __FCOLD_SIZE__ <= cmdbuf, error, "FANTA.SYSTEM's read would cover cmdbuf"
        .assert $2006 + 1 + PATHMAX <= start, error, "the startup buffer"
