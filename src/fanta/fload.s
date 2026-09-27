; fload.s -- FANTA.SYSTEM: the command, the movie and its backdrop.
;
; The command in the startup buffer (path0, length first) is the movie's
; full path, optionally followed by a comma and a backdrop's name, 1 to 15
; characters, a file of the movie's directory (docs/FANTAVISION-FORMAT.md,
; "Backdrops" and the player's design):
;
;   /HD/FV/M.PARADIES            the movie; backdrop PARADIES if it is there
;   /HD/FV/M.PARADIES,STREAM     the movie and the backdrop STREAM
;
; fload reads the movie (513 to 9,216 bytes) to MOVIE, has the engine check
; it (fv_check), then reads the backdrop into the background copy ($6000):
; exactly 8,192 or 8,184 bytes by GET_EOF, whatever its type, the 8 bytes a
; short save lacks (screen holes, never shown) set to zero. A backdrop
; named after the comma that cannot be opened, measured, read or closed, or
; has another size, refuses the movie; the same-name backdrop is then
; simply not used. A read error is never taken for a picture: fv_bdrop is
; set only once everything has succeeded.
;
; C = 0: loaded (fv_movie, fv_len, fv_bdrop set). C = 1: A/X = the message.
;
; Reads only: OPEN, GET_EOF, READ, CLOSE, one file at a time, the I/O
; buffer at $0800. Runs where FANTA.SYSTEM's file was loaded (segment
; LOADER, $2000 on), before the pages are used. tools/test_fantavision.py
; runs it under sim65 with a fake MLI that injects errors.

        .export fload
        .import path0, fv_check, fv_movie, fv_len, fv_bdrop

MLI     = $BF00
IOBUF   = $0800
BDROP   = $6000
.ifdef MOVIE_AT
MOVIE   = MOVIE_AT
.else
MOVIE   = $8000
.endif
MAXLEN  = 9216
NAMEMAX = 15

        .segment "LOADER"
; -- the command ----------------------------------------------------------------
fload:  lda     #0
        sta     fv_bdrop
        sta     nlen
        lda     path0
        sta     mlen
        beq     @nomov
        ldx     #0                      ; a comma?
@f:     inx
        lda     path0,x
        cmp     #','
        beq     @comma
        cpx     path0
        bne     @f
        beq     @movie                  ; (always) none
@comma: dex                             ; the movie: before it
        stx     mlen
        inx
        stx     t                       ; the name: after it, 1 to 15
        lda     path0
        sec
        sbc     t
        beq     @badnm
        cmp     #NAMEMAX + 1
        bcs     @badnm
        sta     nlen
        inx
        stx     nsrc
        lda     mlen
        bne     @movie
@nomov: lda     #<nopath
        ldx     #>nopath
        sec
        rts
@badnm: jmp     bdfail
@movie: lda     mlen                    ; path0 becomes the movie's path
        sta     path0
; -- the movie ------------------------------------------------------------------
        lda     #<path0
        ldx     #>path0
        jsr     open
        bcs     @rderr
        jsr     geteof
        bcs     @rdcl
        lda     eof+2                   ; 513 to 9,216 bytes
        bne     @size
        lda     eof+1
        cmp     #>MAXLEN
        bcc     :+
        bne     @size
        lda     eof
        bne     @size
:       lda     eof+1
        cmp     #>513
        bcc     @size
        bne     :+
        lda     eof
        cmp     #<513
        bcc     @size
:       lda     #<MOVIE
        ldx     #>MOVIE
        jsr     read
        bcs     @rdcl
        jsr     close
        bcs     @rderr
        lda     #<MOVIE
        sta     fv_movie
        lda     #>MOVIE
        sta     fv_movie+1
        lda     eof
        sta     fv_len
        lda     eof+1
        sta     fv_len+1
        jsr     fv_check
        beq     backdrop
        bne     @why                    ; (always)
@size:  jsr     close
        lda     #1
@why:   clc                             ; code 1-5: the reason
        adc     #'0'
        sta     notfv+whyofs
        lda     #<notfv
        ldx     #>notfv
        sec
        rts
@rdcl:  jsr     close
@rderr: lda     #<cantread
        ldx     #>cantread
        sec
        rts

; -- the backdrop -----------------------------------------------------------------
; bpath: the movie's directory (up to its last '/'), then the name.
backdrop:
        ldx     mlen                    ; the directory
:       lda     path0,x
        cmp     #'/'
        beq     :+
        dex
        bne     :-
:       stx     dlen
        txa
        beq     :++                     ; (a path without a directory)
:       lda     path0,x
        sta     bpath,x
        dex
        bne     :-
:
        lda     nlen
        beq     @same
        ldy     nsrc                    ; the name after the comma
        jsr     bname
        jsr     bread
        bcs     bdfail                  ; named: refused if it cannot be used
        rts
@same:  lda     mlen                    ; M.NAME: NAME, if it is there
        sec
        sbc     dlen
        cmp     #3
        bcc     @none
        sbc     #2
        sta     nlen
        ldx     dlen
        lda     path0+1,x
        cmp     #'M'
        bne     @none
        lda     path0+2,x
        cmp     #'.'
        bne     @none
        txa
        clc
        adc     #3
        tay
        jsr     bname
        jsr     bread                   ; not a picture, or unreadable: none
@none:  clc
        rts
bdfail: lda     #<cantbd
        ldx     #>cantbd
        sec
        rts

; bpath += nlen characters of path0 from Y.
bname:  ldx     dlen
:       lda     path0,y
        sta     bpath+1,x
        inx
        iny
        dec     nlen
        bne     :-
        stx     bpath
        rts

; Reads the file bpath into the background copy: exactly 8,192 or 8,184
; bytes, the read and the close checked. C = 1: not used.
bread:  lda     #<bpath
        ldx     #>bpath
        jsr     open
        bcs     @no
        jsr     geteof
        bcs     @cl
        lda     eof+2
        bne     @cl
        lda     eof+1
        ldx     eof
        cmp     #$20                    ; 8,192
        bne     :+
        cpx     #0
        beq     @ok
:       cmp     #$1F                    ; 8,184
        bne     @cl
        cpx     #$F8
        bne     @cl
@ok:    lda     #0                      ; a short save: its last 8 bytes
        ldx     #7                      ; (screen holes) zero; a whole one
:       sta     BDROP+$1FF8,x           ; is read over them
        dex
        bpl     :-
        lda     #<BDROP
        ldx     #>BDROP
        jsr     read
        bcs     @cl
        jsr     close
        bcs     @no
        inc     fv_bdrop
        clc
        rts
@cl:    jsr     close
@no:    sec
        rts

; -- MLI ----------------------------------------------------------------------
; OPEN the path at A/X; C = 1 on an error.
open:   sta     openp+1
        stx     openp+2
        jsr     MLI
        .byte   $C8
        .word   openp
        bcs     :+
        lda     openp+5
        sta     eofp+1
        sta     readp+1
:       rts
; GET_EOF into eof.
geteof: jsr     MLI
        .byte   $D1
        .word   eofp
        rts
; READ eof bytes (16 bits) to A/X; C = 1 on an error or a short read.
read:   sta     readp+2
        stx     readp+3
        lda     eof
        sta     readp+4
        lda     eof+1
        sta     readp+5
        jsr     MLI
        .byte   $CA
        .word   readp
        bcs     :+
        lda     readp+6
        cmp     readp+4
        bne     :++
        lda     readp+7
        cmp     readp+5
        bne     :++
        clc
:       rts
:       sec
        rts
; CLOSE every file (only ours is open); C = 1 on an error.
close:  jsr     MLI
        .byte   $CC
        .word   closep
        rts

openp:  .byte   3
        .word   0
        .word   IOBUF
        .byte   0
eofp:   .byte   2
        .byte   0
eof:    .res    3
readp:  .byte   4, 0
        .word   0, 0, 0
closep: .byte   1, 0

mlen:   .res    1               ; the movie's path length
nlen:   .res    1               ; the backdrop name's length
nsrc:   .res    1               ; where it starts in path0
dlen:   .res    1               ; the directory's length
t:      .res    1
bpath:  .res    65              ; the backdrop's path, length first

nopath: .byte   "FANTAVISION: NO MOVIE WAS GIVEN.", 0
cantread:
        .byte   "FANTAVISION: THE MOVIE CANNOT BE READ.", 0
cantbd: .byte   "FANTAVISION: THE BACKDROP CANNOT BE USED.", 0
notfv:  .byte   "NOT A FANTAVISION MOVIE (CHECK "
whyofs  = * - notfv
        .byte   "0).", 0
