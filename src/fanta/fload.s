; fload.s -- FANTA.SYSTEM: the command, the movie and its backdrop, and the
; movie that comes next.
;
; The command in the startup buffer (path0, length first) is the movie's
; full path, optionally followed by a comma and a backdrop's name, 1 to 15
; characters, a file of the movie's directory (docs/FANTAVISION-FORMAT.md,
; "Backdrops" and the player's design):
;
;   /HD/FV/M.PARADIES            the movie; backdrop PARADIES if it is there
;   /HD/FV/M.PARADIES,STREAM     the movie and the backdrop STREAM
;   *O/HD/FV/M.STREAM            FANTA.SYSTEM relaunched by itself: a
;                                slideshow ('*'; '+' none) and the speed
;                                ('O' original, 'A'-'J' accelerated with
;                                the delay 0-9) come before the path
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
; Before the movie, one pass over its directory (scan) finds the movie
; after it, for the slideshow, and for M.NAME without a named backdrop a
; picture named NAME, or else whose name begins with NAME (CHECKERBOARD
; for M.CHECKER). The command is kept (cmdbuf) for the way on: fanta.s
; relaunches FANTA.SYSTEM with the next movie, or with the same one.
;
; C = 0: loaded (fv_movie, fv_len, fv_bdrop set). C = 1: A/X = the message.
;
; Reads only: OPEN, GET_EOF, READ, CLOSE, one file at a time, the I/O
; buffer at $0800. Runs where FANTA.SYSTEM's file was loaded (segment
; LOADER, $2000 on), before the pages are used. tools/test_fantavision.py
; runs it under sim65 with a fake MLI that injects errors.

        .export fload, cmdbuf, ocl, cdl, nextn, mode, delay, slide
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
PATHMAX = 64
ELEN    = $27                   ; a ProDOS directory entry
EPB     = 13                    ; entries in a block

        .zeropage
dp:     .res    2               ; the directory entry
dd:     .res    2               ; a name's destination, or bname's source
cp:     .res    2               ; the movie's name, from its index 1
bp:     .res    2               ; M.NAME's NAME, from its index 1

        .bss
mode:   .res    1               ; 0 accelerated, 1 original speed
delay:  .res    1               ; 0-9: per-frame delay, accelerated
slide:  .res    1               ; nonzero: the slideshow

; The way on (fanta.s): in the program's memory below $BB00, which the
; return thunk's I/O buffer covers, since the thunk copies the command.
        .segment "CMDBUF"
cmdbuf: .res    3 + PATHMAX     ; length, marker, speed, then the command
ocl:    .res    1               ; the command's length (movie and ",NAME")
cdl:    .res    1               ; its directory's, the last '/' included
nextn:  .res    NAMEMAX + 1     ; the next movie's name, length first; 0: none

        .segment "LOADER"
; -- the command ----------------------------------------------------------------
fload:  lda     #0
        sta     fv_bdrop
        sta     nlen
        sta     slide
        sta     delay
        sta     nextn
        sta     bdn
        lda     #1                      ; the original speed unless told
        sta     mode
        lda     path0                   ; relaunched: "*" or "+", the speed
        cmp     #3
        bcc     @keep
        lda     path0+1
        cmp     #'*'
        beq     :+
        cmp     #'+'
        bne     @keep
:       eor     #'+'                    ; '*': 1
        sta     slide
        lda     path0+2
        cmp     #'O'
        beq     @drop
        sec
        sbc     #'A'
        cmp     #10
        bcs     @drop                   ; unknown: the defaults
        sta     delay
        lda     #0
        sta     mode
@drop:  ldx     #0                      ; the path moves over them
:       lda     path0+3,x
        sta     path0+1,x
        inx
        cpx     path0
        bcc     :-
        dec     path0
        dec     path0
@keep:  ldx     path0                   ; the command, for the way on
        stx     ocl
        beq     :++
:       lda     path0,x
        sta     cmdbuf+2,x
        dex
        bne     :-
:       lda     path0
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
        ldx     mlen                    ; its directory: up to the last '/'
:       lda     path0,x
        cmp     #'/'
        beq     :+
        dex
        bne     :-
:       stx     dlen
        stx     cdl
        txa                             ; cp: the movie's name
        clc
        adc     #<path0
        sta     cp
        lda     #>path0
        adc     #0
        sta     cp+1
        lda     mlen
        sec
        sbc     dlen
        sta     curl
        lda     #0                      ; M.NAME, no name after the comma:
        sta     bnl                     ; NAME (bp, bnl)
        lda     nlen
        bne     :+
        lda     curl
        cmp     #3
        bcc     :+
        ldy     #1
        lda     (cp),y
        cmp     #'M'
        bne     :+
        iny
        lda     (cp),y
        cmp     #'.'
        bne     :+
        lda     curl
        sbc     #2                      ; (carry set by the cmp)
        sta     bnl
        lda     cp
        clc
        adc     #2
        sta     bp
        lda     cp+1
        adc     #0
        sta     bp+1
:       jsr     scan
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
        ldx     dlen                    ; the directory
        beq     :++                     ; (a path without a directory)
:       lda     path0,x
        sta     bpath,x
        dex
        bne     :-
:
        lda     nlen
        beq     @same
        lda     nsrc                    ; the name after the comma
        ldx     #0
        jsr     bnamep
        jsr     bread
        bcs     bdfail                  ; named: refused if it cannot be used
        rts
@same:  lda     bdn                     ; the scan's: NAME, or begins with it
        beq     @exact
        sta     nlen
        lda     #<(bdn + 1)
        sta     dd
        lda     #>(bdn + 1)
        sta     dd+1
        jsr     bname
        jmp     @read
@exact: lda     bnl                     ; M.NAME: NAME, if it is there (the
        beq     @none                   ; directory could not be scanned)
        sta     nlen
        lda     dlen
        ldx     #3
        jsr     bnamep
@read:  jsr     bread                   ; not a picture, or unreadable: none
@none:  clc
        rts
bdfail: lda     #<cantbd
        ldx     #>cantbd
        sec
        rts

; bpath += nlen characters of path0 from index A + X.
bnamep: stx     t
        clc
        adc     t
        adc     #<path0
        sta     dd
        lda     #>path0
        adc     #0
        sta     dd+1
; bpath += nlen characters from (dd). Too long for bpath -- a backdrop
; found by the scan, up to 15 characters, after a deep directory -- an
; empty path, which OPEN refuses: no backdrop, nothing written past bpath.
bname:  lda     dlen
        clc
        adc     nlen
        ldx     #0
        cmp     #PATHMAX + 1
        bcs     @end
        ldx     dlen
        ldy     #0
:       lda     (dd),y
        sta     bpath+1,x
        inx
        iny
        cpy     nlen
        bne     :-
@end:   stx     bpath
        rts

; -- the directory --------------------------------------------------------------
; One pass over the movie's directory, a block at a time into BDROP (the
; backdrop, if any, is read over it afterwards):
;   nextn  the movie after this one in the directory's order, or else the
;          first one; none if there is no other
;   bdn    (M.NAME, nothing after the comma) a picture of exactly 8,192 or
;          8,184 bytes by the entry's EOF, not a movie, named NAME -- or
;          else the first whose name begins with NAME, when NAME has 4
;          characters or more (CHECKERBOARD for M.CHECKER)
; A movie is what A2 File Cmd hands to FANTA.SYSTEM (display.s,
; named_kind): BIN, aux $8400, 513 to 9,216 bytes; the movie itself is
; neither. Only a clean end ($4C) counts: an error, a short block, a header
; that is not ProDOS's 13 entries of 39 bytes, a failed close, and neither
; is used (the same-name backdrop is then tried as before).
scan:   ldx     dlen                    ; the directory, its last '/' cut
        cpx     #2
        bcs     :+
        rts
:       dex
        stx     bpath
:       lda     path0,x
        sta     bpath,x
        dex
        bne     :-
        lda     #<bpath
        ldx     #>bpath
        jsr     open
        bcc     :+
        rts
:       lda     #0
        sta     seen
        sta     nfirst
        sta     bdx
        sta     blk
@blk:   lda     #<BDROP
        sta     readp+2
        lda     #>BDROP
        sta     readp+3
        lda     #<512
        sta     readp+4
        lda     #>512
        sta     readp+5
        jsr     MLI
        .byte   $CA
        .word   readp
        bcc     :+
        cmp     #$4C                    ; the end of the directory
        beq     @end
        bne     @fail
:       lda     readp+6                 ; a whole block
        bne     @fail
        lda     readp+7
        cmp     #>512
        bne     @fail
        lda     #<(BDROP + 4)
        sta     dp
        lda     #>(BDROP + 4)
        sta     dp+1
        ldx     #EPB
        lda     blk
        bne     @ents
        lda     BDROP + 4 + $1F         ; the key block: its header
        cmp     #ELEN
        bne     @fail
        lda     BDROP + 4 + $20
        cmp     #EPB
        bne     @fail
        dex                             ; the header is not a file
        jsr     @nxt
@ents:  stx     k
        jsr     entry
        jsr     @nxt
        ldx     k
        dex
        bne     @ents
        inc     blk
        bne     @blk                    ; (a directory under 256 blocks)
@fail:  jsr     close
@drop:  lda     #0                      ; neither is used
        sta     nextn
        sta     bdn
@none:  rts
@end:   jsr     close
        bcs     @drop
        lda     nextn                   ; none after it: the first one
        bne     @none
        ldx     nfirst
:       lda     nfirst,x
        sta     nextn,x
        dex
        bpl     :-
        rts
@nxt:   lda     dp                      ; the next entry
        clc
        adc     #ELEN
        sta     dp
        bcc     :+
        inc     dp+1
:       rts

; One entry at dp.
entry:  ldy     #0
        lda     (dp),y
        tax
        and     #$F0                    ; a file: storage type 1 to 3
        beq     @skip
        cmp     #$40
        bcs     @skip
        txa
        and     #$0F
        beq     @skip
        sta     el
        lda     #0                      ; a movie? BIN, aux $8400,
        sta     ismov                   ; 513 to 9,216 bytes
        ldy     #$10
        lda     (dp),y
        cmp     #$06
        bne     :+
        ldy     #$1F
        lda     (dp),y
        bne     :+
        iny
        lda     (dp),y
        cmp     #$84
        bne     :+
        ldy     #$17
        lda     (dp),y
        bne     :+
        ldy     #$15                    ; EOF - 513 below $2200
        lda     (dp),y
        sec
        sbc     #<513
        iny
        lda     (dp),y
        sbc     #>513
        bcc     :+
        cmp     #$22
        bcs     :+
        inc     ismov
:       lda     el                      ; the movie itself?
        cmp     curl
        bne     @other
        tay
:       lda     (dp),y
        cmp     (cp),y
        bne     @other
        dey
        bne     :-
        inc     seen
@skip:  rts
@other: lda     ismov
        beq     @pic
        lda     nfirst                  ; the first movie
        bne     :+
        lda     #<nfirst
        ldx     #>nfirst
        jsr     cpname
:       lda     seen                    ; the first one after it
        beq     @skip
        lda     nextn
        bne     @skip
        lda     #<nextn
        ldx     #>nextn
        jmp     cpname
@pic:   lda     bnl                     ; a backdrop for M.NAME
        beq     @skip
        lda     bdx                     ; NAME itself was found
        bne     @skip
        ldy     #$17                    ; 8,192 or 8,184 bytes
        lda     (dp),y
        bne     @skip
        dey
        lda     (dp),y
        tax
        dey
        lda     (dp),y
        cpx     #$20
        bne     :+
        cmp     #0
        beq     @size
:       cpx     #$1F
        bne     @skip
        cmp     #$F8
        bne     @skip
@size:  lda     el                      ; begins with NAME
        cmp     bnl
        bcc     @skip
        ldy     bnl
:       lda     (dp),y
        cmp     (bp),y
        bne     @skip
        dey
        bne     :-
        lda     el
        cmp     bnl
        bne     :+
        inc     bdx                     ; NAME: this one, whatever came before
        bne     @bd
:       lda     bnl                     ; longer: 4 characters or more of
        cmp     #4                      ; NAME, and the first such
        bcc     @skip
        lda     bdn
        bne     @skip
@bd:    lda     #<bdn
        ldx     #>bdn
; The entry's name, length first, to A/X.
cpname: sta     dd
        stx     dd+1
        ldy     el
:       lda     (dp),y
        sta     (dd),y
        dey
        bne     :-
        lda     el
        sta     (dd),y
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
curl:   .res    1               ; the movie's name's length
bnl:    .res    1               ; M.NAME: NAME's length; 0: no such name
seen:   .res    1               ; scan: the movie itself went by
blk:    .res    1               ; scan: blocks read
k:      .res    1               ; scan: entries left in the block
el:     .res    1               ; scan: the entry's name's length
ismov:  .res    1               ; scan: the entry is a movie
bdx:    .res    1               ; scan: bdn is NAME itself
nfirst: .res    NAMEMAX + 1     ; scan: the first movie
bdn:    .res    NAMEMAX + 1     ; scan: the backdrop found, length first
bpath:  .res    65              ; the backdrop's path, length first

nopath: .byte   "NO MOVIE WAS GIVEN.", 0
cantread:
        .byte   "THE MOVIE CANNOT BE READ.", 0
cantbd: .byte   "THE BACKDROP CANNOT BE USED.", 0
notfv:  .byte   "NOT A FANTAVISION MOVIE (CHECK "
whyofs  = * - notfv
        .byte   "0).", 0
