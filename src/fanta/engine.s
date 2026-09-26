; engine.s -- the Fantavision movie engine of FANTA.SYSTEM: checks, tweening
; and drawing (docs/FANTAVISION-FORMAT.md; tools/fantavision_ref.py is its
; reference model and states the rules the spec leaves open).
;
; Plain 6502 throughout. The engine reads the movie and writes only its own
; variables (segments ZEROPAGE and BSS) and three fixed 8 KB buffers:
; hi-res page 1 ($2000), page 2 ($4000) and the background copy ($6000).
; It never calls ProDOS or the ROM: FANTA.SYSTEM (fanta.s) loads the movie,
; flips the pages and reads the keys; tools/test_fantavision.py links this
; same file with a C harness under sim65.
;
; Interface (all variables in BSS, the routines preserve nothing):
;   fv_movie, fv_len  the movie's address and length, set by the caller
;   fv_check   A = 0 if the movie is accepted, else a reason code 1-6
;   fv_begin   builds the background and copies it to both pages
;   fv_first   draws key frame 0 on page 1 (fv_shown = $20)
;   fv_next    builds the next frame on the hidden page and sets fv_shown;
;              A = 1 (nothing built) once a counted movie has ended
;   fv_timing  after a frame: fv_orig, the original player's time for it,
;              fv_own, this engine's estimated time, fv_wait = the
;              difference, never negative (cycles, 32 bits)
;
; Speed: spans are filled a byte at a time from tables (row addresses, edge
; masks by x, colour patterns); solids use a scan-line fill with an active
; edge list; tweened points and edge crossings are 8.8 sums, added and
; never recomputed; an erased object restores only its bounding box (rows
; and byte columns) from the background copy.

        .macpack longbranch
        .export fv_check, fv_begin, fv_first, fv_next, fv_timing
        .export fv_movie, fv_len, fv_shown, fv_done, fv_frames
        .export fv_counts, fv_orig, fv_own, fv_wait

PAGE1   = $20
BGPAGE  = $60
MAXPTS  = 32

; The original player's time for a frame (docs, "How long the original
; takes"), and this engine's own, calibrated with sim65 on the synthetic set
; (tools/test_fantavision.py --calibrate). tools/fantavision_ref.py carries
; the same numbers.
ORIG_BASE  = 6300
OWN_BASE   = 1500
OWN_TIMING = 0

; The per-frame counters, 24 bits each (fv_counts + offset).
C_SPANS   = 0           ; row segments drawn on the page built
C_BYTES   = 3           ; the byte columns they cover
C_ESPANS  = 6           ; row segments of the normal objects of the frame before
C_EBYTES  = 9
C_EDGES   = 12          ; points of the line and solid objects drawn
O_SPANS   = 15          ; the same, over every buffer drawn into
O_BYTES   = 18
O_EROWS   = 21          ; rows of the bounding boxes erased
O_EBYTES  = 24          ; bytes restored
O_EDGES   = 27
O_IPOINTS = 30          ; tweened points stepped
O_OBJECTS = 33          ; object drawings (one per buffer)
NCOUNTS   = 36

        .zeropage
mov:    .res 2          ; the movie
rp:     .res 2          ; a record
pa:     .res 2          ; key k's record (tweening set-up)
pb:     .res 2          ; key k+1's record
xp:     .res 2          ; the x coordinates of the object drawn
yp:     .res 2          ; its y coordinates
rowp:   .res 2          ; the row being written
bgp:    .res 2          ; the same row in the background copy
pagehi: .res 1          ; the buffer drawn into: $20, $40 or $60
counting: .res 1        ; nonzero: spans count (the page built only)
sy:     .res 1          ; span: row
sxa:    .res 1          ;       first movie x
sxb:    .res 1          ;       last movie x
scol:   .res 1          ;       its first byte column
ccb:    .res 1          ;       its last byte column
mr:     .res 1          ;       mask of the last byte
msk:    .res 1
p0:     .res 1          ; the pattern of this row, even and odd columns
p1:     .res 1
pd:     .res 1          ; p0 ^ p1
ce0:    .res 1          ; the object's patterns: even rows
ce1:    .res 1
co0:    .res 1          ; odd rows
co1:    .res 1
cl:     .res 1          ; clip window
cr:     .res 1
ct:     .res 1
cbot:   .res 1          ; bottom, 191 at most
dcx:    .res 1          ; dot: centre and size
dcy:    .res 1
dsz:    .res 1
drl:    .res 1          ; its row, 16 bits
drh:    .res 1
ddi:    .res 1
dcnt:   .res 1
gx0:    .res 1          ; segment
gy0:    .res 1
gx1:    .res 1
gy1:    .res 1
gsg:    .res 1          ; sign of x1 - x0
gadx:   .res 1          ; |x1 - x0|
gdy:    .res 1
gsl:    .res 2          ; slope, 8.8
gac:    .res 2          ; sum, 8.8
gcur:   .res 1
gnxt:   .res 1
gy:     .res 1
okind:  .res 1          ; the object drawn
omode:  .res 1
ocol:   .res 1
oanim:  .res 1
onp:    .res 1
oi:     .res 1
oseg:   .res 1
odash:  .res 1
t0:     .res 1
t1:     .res 1
t2:     .res 1
t3:     .res 1

        .bss
fv_movie: .res 2
fv_len:   .res 2
fv_shown: .res 1
fv_done:  .res 1
fv_frames: .res 1
fv_counts: .res NCOUNTS
fv_orig:  .res 4
fv_own:   .res 4
fv_wait:  .res 4
ftlo:   .res 127        ; the frames' addresses
fthi:   .res 127
steps:  .res 1          ; S
shift:  .res 1          ; log2(256 / S)
forever: .res 1
rem:    .res 2          ; transitions left, counted movie
kf:     .res 1          ; key frame k
kf1:    .res 1          ; k + 1
tstep:  .res 1          ; step t of the transition, 0 on a key
vkey:   .res 1          ; nonzero: build draws key vframe as stored
vframe: .res 1
obj:    .res 1
bpage:  .res 1          ; page built
opage:  .res 1          ; the other one
targets: .res 1
snap:   .res 6          ; C_SPANS and C_BYTES before an object
delta:  .res 6          ; what the object added
normal: .res 6          ; spans and bytes of the normal objects
prevn:  .res 6          ; the same, frame before
acc:    .res 4          ; fv_timing
mulv:   .res 4
mulk:   .res 2
qm:     .res 1          ; a solid's points, deduplicated
qx:     .res MAXPTS
qy:     .res MAXPTS
ne:     .res 1          ; its edges
nact:   .res 1
nxt:    .res 1
exa:    .res MAXPTS     ; x at the top end
eya:    .res MAXPTS     ; top row
eyb:    .res MAXPTS     ; bottom row, excluded
esl:    .res MAXPTS     ; slope, 8.8
esh:    .res MAXPTS
esg:    .res MAXPTS     ; $FF: x decreases downwards
eal:    .res MAXPTS     ; running sum, 8.8
eah:    .res MAXPTS
ord:    .res MAXPTS     ; edges by top row
act:    .res MAXPTS     ; active edges
xs:     .res MAXPTS     ; their crossings on this row
bval:   .res 16         ; erase boxes: 8 objects x 2 pages
br0:    .res 16
br1:    .res 16
bc0:    .res 16
bc1:    .res 16
tfl:    .res 8          ; object tweened in this transition
tal:    .res 8          ; its key k record
tah:    .res 8
tn:     .res 8          ; its point count
srcq:   .res 1
srcr:   .res 1
dstq:   .res 1
dstr:   .res 1
na:     .res 1
nb:     .res 1
axl:    .res 256        ; per object o, point i at o * 32 + i: x, 8.8
axh:    .res 256
ayl:    .res 256
ayh:    .res 256
sxl:    .res 256        ; the step added per frame
sxh:    .res 256
syl:    .res 256
syh:    .res 256

        .rodata
; Row y of a page starts at page + (y & 7) * $400 + ((y >> 3) & 7) * $80
; + (y >> 6) * $28.
rowlo:
        .repeat 192, R
        .byte <(((R .mod 8) * $400) + (((R / 8) .mod 8) * $80) + ((R / 64) * $28))
        .endrep
rowhi:
        .repeat 192, R
        .byte >(((R .mod 8) * $400) + (((R / 8) .mod 8) * $80) + ((R / 64) * $28))
        .endrep
; Movie x is screen x + 14: its byte column, and the masks of the dots from
; x to the end of its byte (left end of a span) and from the start of its
; byte to x (right end). Bit 7 is always in: the byte takes the palette.
colof:
        .repeat 256, I
        .byte (I + 14) / 7
        .endrep
lmx:
        .repeat 256, I
        .byte $80 | (($7F << ((I + 14) .mod 7)) & $7F)
        .endrep
rmx:
        .repeat 256, I
        .byte $80 | ((2 << ((I + 14) .mod 7)) - 1)
        .endrep
; Colour nibble -> byte at an even and at an odd column.
pate:   .byte $00, $55, $2A, $7F, $36, $49, $2D, $56
        .byte $80, $D5, $AA, $FF, $B6, $C9, $AD, $D6
pato:   .byte $00, $2A, $55, $7F, $36, $49, $2B, $55
        .byte $80, $AA, $D5, $FF, $B6, $C9, $AB, $D5
; A dot of size s: 2s rows, half-widths from the top (a disc of radius s).
dhoff:  .byte 0, 0, 2, 6, 12, 20, 30, 42, 56, 72
dhw:    .byte 1, 1
        .byte 1, 2, 2, 1
        .byte 2, 3, 3, 3, 3, 2
        .byte 2, 3, 4, 4, 4, 4, 3, 2
        .byte 2, 4, 4, 5, 5, 5, 5, 4, 4, 2
        .byte 2, 4, 5, 5, 6, 6, 6, 6, 5, 5, 4, 2
        .byte 3, 4, 5, 6, 7, 7, 7, 7, 7, 7, 6, 5, 4, 3
        .byte 3, 5, 6, 7, 7, 8, 8, 8, 8, 8, 8, 7, 7, 6, 5, 3
        .byte 3, 5, 6, 7, 8, 8, 9, 9, 9, 9, 9, 9, 8, 8, 7, 6, 5, 3
; fv_timing's terms: counter offset, then cycles per unit (16 bits).
origt:  .byte C_SPANS
        .word 230
        .byte C_BYTES
        .word 20
        .byte C_ESPANS
        .word 270
        .byte C_EBYTES
        .word 45
        .byte C_EDGES
        .word 1100
        .byte $FF
ownt:   .byte O_SPANS
        .word 150
        .byte O_BYTES
        .word 17
        .byte O_EROWS
        .word 60
        .byte O_EBYTES
        .word 16
        .byte O_EDGES
        .word 300
        .byte O_IPOINTS
        .word 60
        .byte O_OBJECTS
        .word 400
        .byte $FF

        .code

; -- the checks -------------------------------------------------------------
; Everything is checked before anything is drawn; no byte past fv_len is
; read. Codes: 1 size, 2 header, 3 clip window, 4 record length,
; 5 truncated, 6 frame count.
fv_check:
        lda     fv_movie
        sta     mov
        lda     fv_movie+1
        sta     mov+1
        lda     #0
        sta     fv_frames
        lda     fv_len+1                ; 513 <= len <= 9216 ($2400)
        cmp     #>513
        jcc     bad1
        bne     :+
        lda     fv_len
        cmp     #<513
        jcc     bad1
:       lda     fv_len+1
        cmp     #$24
        bcc     :+
        jne     bad1
        lda     fv_len
        jne     bad1
:       ldy     #3
        lda     (mov),y
        cmp     #4
        jne     bad2
        ldy     #5
        lda     (mov),y
        cmp     #8
        jne     bad2
        ldy     #9                      ; left <= right
        lda     (mov),y
        ldy     #8
        cmp     (mov),y
        jcc     bad3
        ldy     #11                     ; top <= bottom
        lda     (mov),y
        ldy     #10
        cmp     (mov),y
        jcc     bad3
        ; rp walks the records; t0/t1 = bytes left from rp.
        clc
        lda     mov
        adc     #<$1A0
        sta     rp
        lda     mov+1
        adc     #>$1A0
        sta     rp+1
        sec
        lda     fv_len
        sbc     #<$1A0
        sta     t0
        lda     fv_len+1
        sbc     #>$1A0
        sta     t1
@frame: lda     t0                      ; the end of the file: the end
        ora     t1
        beq     @end
        ldy     #0
        lda     (rp),y
        beq     @end                    ; 0 where a frame starts: the end
        ldx     fv_frames
        cpx     #127
        jeq     bad6
        lda     rp
        sta     ftlo,x
        lda     rp+1
        sta     fthi,x
        lda     #8
        sta     t2
@rec:   lda     t0
        ora     t1
        jeq     bad5
        ldy     #0
        lda     (rp),y
        cmp     #1
        beq     @adv
        cmp     #4
        jcc     bad4
        cmp     #4 + 2 * MAXPTS + 1
        jcs     bad4
        lsr
        jcs     bad4
        asl
        ldx     t1                      ; more than 255 left: it fits
        bne     @adv
        cmp     t0
        beq     @adv
        jcs     bad5
@adv:   sta     t3                      ; rp += L, left -= L
        clc
        adc     rp
        sta     rp
        bcc     :+
        inc     rp+1
:       sec
        lda     t0
        sbc     t3
        sta     t0
        bcs     :+
        dec     t1
:       dec     t2
        bne     @rec
        inc     fv_frames
        jmp     @frame
@end:   lda     fv_frames
        jeq     bad6
        lda     #0
        rts
bad1:   lda     #1
        rts
bad2:   lda     #2
        rts
bad3:   lda     #3
        rts
bad4:   lda     #4
        rts
bad5:   lda     #5
        rts
bad6:   lda     #6
        rts

; -- start ------------------------------------------------------------------
fv_begin:
        lda     fv_movie
        sta     mov
        lda     fv_movie+1
        sta     mov+1
        ldy     #0                      ; S and log2(256 / S)
        lda     (mov),y
        and     #7
        bne     :+
        lda     #4                      ; e = 0: S = 8, as e = 4
:       tax
        lda     #1
        ldy     #9
@s:     dex
        beq     :+
        asl
        dey
        bne     @s                      ; (always)
:       sta     steps
        dey
        sty     shift
        ldy     #1                      ; play count: the low nibble, 0 loops
        lda     (mov),y
        and     #$0F
        sta     t0
        lda     #0
        sta     forever
        sta     rem
        sta     rem+1
        lda     t0
        bne     @count
        inc     forever
        bne     @clip                   ; (always)
@count: ldx     t0                      ; rem = count * frames - 1
:       clc
        lda     rem
        adc     fv_frames
        sta     rem
        bcc     :+
        inc     rem+1
:       dex
        bne     :--
        lda     rem
        bne     :+
        dec     rem+1
:       dec     rem
@clip:  ldy     #8
        lda     (mov),y
        sta     cl
        iny
        lda     (mov),y
        sta     cr
        iny
        lda     (mov),y
        sta     ct
        iny
        lda     (mov),y
        cmp     #191
        bcc     :+
        lda     #191
:       sta     cbot
        lda     #0
        sta     fv_done
        sta     kf
        sta     tstep
        sta     counting
        ldx     #5
:       sta     prevn,x
        dex
        bpl     :-
        ldx     #15
:       sta     bval,x
        dex
        bpl     :-
        ldx     #7
:       sta     tfl,x
        dex
        bpl     :-
        ; The background: black, the rectangle x 5-250, rows 12-159 in the
        ; colour of header byte 4, not clipped.
        lda     #BGPAGE
        sta     rowp+1
        ldx     #$20
        jsr     clear
        lda     cl
        pha
        lda     cr
        pha
        lda     ct
        pha
        lda     cbot
        pha
        lda     #0
        sta     cl
        sta     ct
        lda     #255
        sta     cr
        lda     #191
        sta     cbot
        lda     #BGPAGE
        sta     pagehi
        ldy     #4
        lda     (mov),y
        jsr     setcol
        lda     #12
        sta     gy
@bg:    lda     gy
        sta     sy
        lda     #5
        sta     sxa
        lda     #250
        sta     sxb
        jsr     span
        inc     gy
        lda     gy
        cmp     #160
        bne     @bg
        pla
        sta     cbot
        pla
        sta     ct
        pla
        sta     cr
        pla
        sta     cl
        lda     #PAGE1
        jsr     bgcopy
        lda     #PAGE1 + $20
        ;jmp    bgcopy

; Copies the background to the page A (hi byte).
bgcopy: sta     rowp+1
        lda     #BGPAGE
        sta     bgp+1
        ldy     #0
        sty     rowp
        sty     bgp
        ldx     #$20
:       lda     (bgp),y
        sta     (rowp),y
        iny
        bne     :-
        inc     bgp+1
        inc     rowp+1
        dex
        bne     :-
        rts

; Zeroes X pages from rowp+1.
clear:  lda     #0
        tay
        sta     rowp
:       sta     (rowp),y
        iny
        bne     :-
        inc     rowp+1
        dex
        bne     :-
        rts

fv_first:
        lda     #1
        sta     vkey
        lda     #0
        sta     vframe
        lda     #PAGE1
        sta     fv_shown
        jsr     build
        lda     fv_frames
        cmp     #1
        bne     :+
        sta     fv_done                 ; a single frame is just shown
:       rts

; -- the next frame ---------------------------------------------------------
fv_next:
        lda     fv_done
        beq     :+
        lda     #1
        rts
:       inc     tstep
        lda     tstep
        cmp     #1
        bne     @built
        ldx     kf                      ; a transition starts
        inx
        cpx     fv_frames
        bne     :+
        ldx     #0
:       stx     kf1
        lda     steps
        cmp     #1
        beq     @built
        jsr     setup
@built: lda     #0
        sta     vkey
        lda     tstep
        cmp     steps
        bne     :+
        inc     vkey                    ; the last step is key k+1 as stored
        lda     kf1
        sta     vframe
:       lda     fv_shown
        eor     #$60                    ; $20 <-> $40
        sta     fv_shown
        jsr     build
        lda     tstep
        cmp     steps
        bne     @ok
        lda     kf1
        sta     kf
        lda     #0
        sta     tstep
        lda     forever
        bne     @ok
        lda     rem
        bne     :+
        dec     rem+1
:       dec     rem
        lda     rem
        ora     rem+1
        bne     @ok
        inc     fv_done
@ok:    lda     #0
        rts

; rp = record of object X in frame A.
record: tay
        lda     ftlo,y
        sta     rp
        lda     fthi,y
        sta     rp+1
        cpx     #0
        beq     @done
        ldy     #0
@walk:  lda     (rp),y
        clc
        adc     rp
        sta     rp
        bcc     :+
        inc     rp+1
:       dex
        bne     @walk
@done:  rts

; The tweening of the transition kf -> kf1: for each object present with
; points in both keys, N = max(nA, nB) points; point i goes from
; A[i * nA / N] to B[i * nB / N], in 8.8 with 1/2 added for the rounding,
; by (B - A) * 256 / S a step.
setup:  lda     #0
        sta     obj
@obj:   ldx     obj
        lda     #0
        sta     tfl,x
        lda     kf
        jsr     record
        lda     rp
        sta     pa
        lda     rp+1
        sta     pa+1
        ldx     obj
        lda     kf1
        jsr     record
        lda     rp
        sta     pb
        lda     rp+1
        sta     pb+1
        ldy     #0
        lda     (pa),y
        cmp     #6                      ; absent (1) or no points (4)
        jcc     @next
        sec
        sbc     #4
        lsr
        sta     na
        lda     (pb),y
        cmp     #6
        jcc     @next
        sec
        sbc     #4
        lsr
        sta     nb
        ldx     obj
        cmp     na
        bcs     :+
        lda     na
:       sta     tn,x
        lda     #1
        sta     tfl,x
        lda     pa
        sta     tal,x
        lda     pa+1
        sta     tah,x
        lda     #0
        sta     srcq
        sta     srcr
        sta     dstq
        sta     dstr
        txa                             ; X = obj * 32 + i
        asl
        asl
        asl
        asl
        asl
        tax
        lda     #0
        sta     oi
@pt:    ; x
        lda     srcq
        clc
        adc     #4
        tay
        lda     (pa),y
        sta     t0                      ; A.x
        lda     dstq
        clc
        adc     #4
        tay
        lda     (pb),y                  ; B.x
        jsr     @init
        sta     axh,x
        lda     t2
        sta     sxl,x
        lda     t3
        sta     sxh,x
        lda     #128
        sta     axl,x
        sta     ayl,x
        ; y
        lda     srcq
        clc
        adc     #4
        adc     na
        tay
        lda     (pa),y
        sta     t0
        lda     dstq
        clc
        adc     #4
        adc     nb
        tay
        lda     (pb),y
        jsr     @init
        sta     ayh,x
        lda     t2
        sta     syl,x
        lda     t3
        sta     syh,x
        ; the next source and destination indexes
        ldy     obj
        lda     srcr
        clc
        adc     na
:       cmp     tn,y
        bcc     :+
        sbc     tn,y
        inc     srcq
        bcs     :-                      ; (always)
:       sta     srcr
        lda     dstr
        clc
        adc     nb
:       cmp     tn,y
        bcc     :+
        sbc     tn,y
        inc     dstq
        bcs     :-
:       sta     dstr
        inx
        inc     oi
        lda     oi
        cmp     tn,y
        jne     @pt
@next:  inc     obj
        lda     obj
        cmp     #8
        jne     @obj
        rts
; A = B, t0 = A: t2/t3 = (B - A) << shift, 16 bits; returns A = t0.
@init:  sec
        sbc     t0
        sta     t2
        lda     #0
        sbc     #0
        sta     t3
        ldy     shift
:       asl     t2
        rol     t3
        dey
        bne     :-
        lda     t0
        rts

; -- a frame ------------------------------------------------------------------
; Builds the frame on page fv_shown: erases what the normal objects left on
; it two frames ago, then draws the eight objects in order.
build:  lda     fv_shown
        sta     bpage
        eor     #$60
        sta     opage
        lda     #0
        ldx     #NCOUNTS - 1
:       sta     fv_counts,x
        dex
        bpl     :-
        ldx     #5
:       sta     normal,x
        dex
        bpl     :-
        lda     prevn
        sta     fv_counts+C_ESPANS
        lda     prevn+1
        sta     fv_counts+C_ESPANS+1
        lda     prevn+2
        sta     fv_counts+C_ESPANS+2
        lda     prevn+3
        sta     fv_counts+C_EBYTES
        lda     prevn+4
        sta     fv_counts+C_EBYTES+1
        lda     prevn+5
        sta     fv_counts+C_EBYTES+2
        jsr     erase
        lda     #0
        sta     obj
@obj:   jsr     version
        jcs     @next
        lda     oanim
        cmp     #3
        bcc     :+
        lda     #3
        sta     oanim
:       ldx     #1                      ; buffers: 1, 2 (trace), 3 (background)
        cmp     #1
        beq     :+
        cmp     #2
        bne     :++
        inx
:       inx
:       stx     targets
        ldx     #O_OBJECTS
        lda     targets
        jsr     cadd
        lda     okind                   ; lines and solids: n edges
        beq     :++
        ldx     #C_EDGES
        lda     onp
        jsr     cadd
        ldy     targets
:       ldx     #O_EDGES
        lda     onp
        jsr     cadd
        dey
        bne     :-
:       ldx     #5
:       lda     fv_counts+C_SPANS,x     ; C_SPANS then C_BYTES: 6 bytes
        sta     snap,x
        dex
        bpl     :-
        lda     bpage
        sta     pagehi
        lda     #1
        sta     counting
        jsr     drawobj
        lda     #0
        sta     counting
        lda     targets
        cmp     #1
        beq     @drawn
        lda     opage
        sta     pagehi
        jsr     drawobj
        lda     targets
        cmp     #3
        bne     @drawn
        lda     #BGPAGE
        sta     pagehi
        jsr     drawobj
@drawn: sec                             ; delta = counts - snap
        ldx     #0
:       lda     fv_counts+C_SPANS,x
        sbc     snap,x
        sta     delta,x
        inx
        txa
        eor     #6
        bne     :-
        ldy     targets
@own:   clc
        ldx     #0
:       lda     fv_counts+O_SPANS,x
        adc     delta,x
        sta     fv_counts+O_SPANS,x
        inx
        txa
        eor     #6
        bne     :-
        dey
        bne     @own
        lda     oanim
        bne     @next
        clc                             ; a normal object: counted and boxed
        ldx     #0
:       lda     normal,x
        adc     delta,x
        sta     normal,x
        inx
        txa
        eor     #6
        bne     :-
        jsr     bbox
@next:  inc     obj
        lda     obj
        cmp     #8
        jne     @obj
        ldx     #5
:       lda     normal,x
        sta     prevn,x
        dex
        bpl     :-
        rts

; The version of object obj in this frame: okind, omode, ocol, oanim, onp,
; xp, yp. C = 1 when it is not drawn.
version:
        lda     vkey
        beq     @tween
        ldx     obj
        lda     vframe
        jsr     record
        ldy     #0
        lda     (rp),y
        cmp     #1
        bne     :+
        sec
        rts
:       sec
        sbc     #4
        lsr
        sta     onp
        jsr     attrs
        clc
        lda     rp
        adc     #4
        sta     xp
        lda     rp+1
        adc     #0
        sta     xp+1
        clc
        lda     xp
        adc     onp
        sta     yp
        lda     xp+1
        adc     #0
        sta     yp+1
        clc
        rts
@tween: ldx     obj
        lda     tfl,x
        bne     :+
        sec
        rts
:       lda     tal,x
        sta     rp
        lda     tah,x
        sta     rp+1
        lda     tn,x
        sta     onp
        jsr     attrs
        ldx     #O_IPOINTS
        lda     onp
        jsr     cadd
        lda     obj                     ; step every point: 8.8 sums
        asl
        asl
        asl
        asl
        asl
        tax
        sta     xp
        sta     yp
        ldy     onp
:       clc
        lda     axl,x
        adc     sxl,x
        sta     axl,x
        lda     axh,x
        adc     sxh,x
        sta     axh,x
        clc
        lda     ayl,x
        adc     syl,x
        sta     ayl,x
        lda     ayh,x
        adc     syh,x
        sta     ayh,x
        inx
        dey
        bne     :-
        clc
        lda     xp
        adc     #<axh
        sta     xp
        lda     #>axh
        adc     #0
        sta     xp+1
        clc
        lda     yp
        adc     #<ayh
        sta     yp
        lda     #>ayh
        adc     #0
        sta     yp+1
        clc
        rts

; Attributes of the record at rp.
attrs:  ldy     #1
        lda     (rp),y
        and     #3
        sta     okind
        lda     (rp),y
        lsr
        lsr
        lsr
        lsr
        sta     omode
        iny
        lda     (rp),y
        sta     ocol
        iny
        lda     (rp),y
        sta     oanim
        rts

; Adds A to the 24-bit counter at fv_counts + X.
cadd:   clc
        adc     fv_counts,x
        sta     fv_counts,x
        bcc     :+
        inc     fv_counts+1,x
        bne     :+
        inc     fv_counts+2,x
:       rts

; -- erasing --------------------------------------------------------------------
; The bounding box of a normal object: its points' extent, widened by the
; dot size (dots) or by one dot left and right and one row up (lines,
; solids), clipped, in byte columns. Stored for page bpage, object obj.
bbox:   ldx     onp
        jeq     @none
        lda     okind
        bne     :+
        lda     omode                   ; dots: size 1-9 only
        jeq     @none
        cmp     #10
        jcs     @none
        sta     t3
        bcc     :++
:       lda     #1
        sta     t3
:       ldy     #0                      ; min and max: t0 x0, t1 x1, gx0 y0, gx1 y1
        lda     (xp),y
        sta     t0
        sta     t1
        lda     (yp),y
        sta     gx0
        sta     gx1
@mm:    iny
        cpy     onp
        beq     @ext
        lda     (xp),y
        cmp     t0
        bcs     :+
        sta     t0
:       cmp     t1
        bcc     :+
        sta     t1
:       lda     (yp),y
        cmp     gx0
        bcs     :+
        sta     gx0
:       cmp     gx1
        bcc     @mm
        sta     gx1
        bcs     @mm                     ; (always)
@ext:   ldx     obj                     ; box slot
        lda     bpage
        cmp     #PAGE1
        beq     :+
        txa
        ora     #8
        tax
:       lda     t0                      ; x0 = max(xmin - w, cl)
        sec
        sbc     t3
        bcc     :+
        cmp     cl
        bcs     :++
:       lda     cl
:       sta     t0
        ; x1 = min(xmax + w - 1, cr) (dots) or min(xmax + 1, cr)
        lda     okind
        beq     :+
        lda     t1
        clc
        adc     #1
        bcs     @xr
        bcc     @xc                     ; (always)
:       lda     t1
        clc
        adc     t3
        bcs     @xr                     ; >= 256: the right side
        sbc     #0                      ; C = 0: - 1
@xc:    cmp     cr
        bcc     :+
@xr:    lda     cr
:       sta     t1
        cmp     t0
        bcc     @none
        lda     gx0                     ; y0 = max(ymin - w, ct)
        sec
        sbc     t3
        bcc     :+
        cmp     ct
        bcs     :++
:       lda     ct
:       sta     gx0
        lda     okind                   ; y1 = min(ymax + w - 1 or ymax, cbot)
        bne     @y1
        lda     gx1
        clc
        adc     t3
        bcs     @yb
        sbc     #0
        jmp     @yc
@y1:    lda     gx1
@yc:    cmp     cbot
        bcc     :+
@yb:    lda     cbot
:       cmp     gx0
        bcc     @none
        sta     br1,x
        lda     gx0
        sta     br0,x
        ldy     t0
        lda     colof,y
        sta     bc0,x
        ldy     t1
        lda     colof,y
        sta     bc1,x
        lda     #1
        sta     bval,x
@none:  rts

; Restores the boxes recorded for page bpage from the background copy.
erase:  ldx     #0
        lda     bpage
        cmp     #PAGE1
        beq     :+
        ldx     #8
:       stx     t3
        txa
        clc
        adc     #8
        sta     t2                      ; end slot
@box:   ldx     t3
        lda     bval,x
        beq     @next
        lda     #0
        sta     bval,x
        lda     br0,x
        sta     gy
        lda     bc0,x
        sta     t0
        dec     t0                      ; column before the first (>= 1)
        lda     bc1,x
        sta     t1
        sec
        sbc     t0
        sta     gcur                    ; columns
        lda     br1,x
        sta     gnxt
@row:   ldx     gy
        lda     rowlo,x
        sta     rowp
        sta     bgp
        lda     rowhi,x
        ora     #BGPAGE
        sta     bgp+1
        eor     #BGPAGE
        ora     bpage
        sta     rowp+1
        ldy     t1
:       lda     (bgp),y
        sta     (rowp),y
        dey
        cpy     t0
        bne     :-
        ldx     #O_EROWS
        lda     #1
        jsr     cadd
        ldx     #O_EBYTES
        lda     gcur
        jsr     cadd
        lda     gy
        inc     gy
        cmp     gnxt
        bne     @row
@next:  inc     t3
        lda     t3
        cmp     t2
        bne     @box
        rts

; -- objects ------------------------------------------------------------------
; Draws the object (okind, omode, ocol, onp points at xp/yp) into pagehi.
drawobj:
        lda     ocol
        jsr     setcol
        lda     onp
        beq     @ret
        lda     okind
        beq     @dots
        cmp     #1
        beq     @lines
        jmp     shape
@dots:  lda     omode                   ; size 1-9; others draw nothing
        beq     @ret
        cmp     #10
        bcs     @ret
        sta     dsz
        ldy     #0
:       lda     (xp),y
        sta     dcx
        lda     (yp),y
        sta     dcy
        sty     oi
        jsr     dot
        ldy     oi
        iny
        cpy     onp
        bne     :-
@ret:   rts
@lines: lda     onp
        cmp     #1
        bne     :+
        ldy     #0
        jmp     dot1
:       sta     oseg                    ; n - 1 segments, n when closed (11)
        lda     omode
        cmp     #11
        beq     :+
        dec     oseg
:       lda     #0
        sta     oi
        sta     odash
@seg:   lda     omode                   ; dashed 1-9: every (m+1)th left out
        beq     @draw
        cmp     #10
        bcs     @draw
        cmp     odash
        bne     :+
        lda     #0
        sta     odash
        beq     @skip                   ; (always)
:       inc     odash
@draw:  ldy     oi
        lda     (xp),y
        sta     gx0
        lda     (yp),y
        sta     gy0
        iny
        cpy     onp
        bne     :+
        ldy     #0
:       lda     (xp),y
        sta     gx1
        lda     (yp),y
        sta     gy1
        jsr     seg
@skip:  inc     oi
        lda     oi
        cmp     oseg
        bne     @seg
        rts

; A smallest dot at point Y of the object.
dot1:   lda     (xp),y
        sta     dcx
        lda     (yp),y
        sta     dcy
dot1c:  lda     #1
        sta     dsz
        jmp     dot

; A solid: the points without consecutive repeats (nor the last equal to the
; first), filled, then its outline.
shape:  ldy     #0
        lda     (xp),y
        sta     qx
        lda     (yp),y
        sta     qy
        ldx     #1
@dd:    iny
        cpy     onp
        beq     @ddn
        lda     (xp),y
        cmp     qx-1,x
        bne     :+
        lda     (yp),y
        cmp     qy-1,x
        beq     @dd
:       lda     (xp),y
        sta     qx,x
        lda     (yp),y
        sta     qy,x
        inx
        bne     @dd                     ; (always)
@ddn:   cpx     #2
        bcc     @one
        lda     qx-1,x
        cmp     qx
        bne     @kept
        lda     qy-1,x
        cmp     qy
        bne     @kept
        dex
        bne     @ddn                    ; (always)
@one:   lda     qx
        sta     dcx
        lda     qy
        sta     dcy
        jmp     dot1c
@kept:  stx     qm
        cpx     #2
        bne     :+
        ldx     #0
        jsr     qseg
        jmp     @outl
:       jsr     fill
@outl:  lda     omode                   ; 0: no outline
        beq     @ret
        lsr                             ; odd black, even white
        lda     #0
        bcs     :+
        lda     #$33
:       sta     t0
        lda     ocol                    ; the same palettes
        and     #$88
        ora     t0
        jsr     setcol
        lda     qm                      ; 1, 2 closed; 3 and more open
        ldx     omode
        cpx     #3
        bcc     :+
        sec
        sbc     #1
:       sta     oseg
        lda     #0
        sta     oi
:       ldx     oi
        jsr     qseg
        inc     oi
        lda     oi
        cmp     oseg
        bne     :-
@ret:   rts

; The segment from q[X] to q[X + 1] (wrapping).
qseg:   lda     qx,x
        sta     gx0
        lda     qy,x
        sta     gy0
        inx
        cpx     qm
        bne     :+
        ldx     #0
:       lda     qx,x
        sta     gx1
        lda     qy,x
        sta     gy1
        ;jmp    seg

; -- lines ------------------------------------------------------------------------
; The segment (gx0, gy0) - (gx1, gy1), two dots wide: on each row y from the
; top one to the one before the bottom, x(y) to x(y + 1) and one dot more;
; on the bottom row x1, x1 + 1. x(y) = x0 +- (128 + slope * (y - y0)) >> 8.
seg:    lda     gx0
        cmp     gx1
        bne     @line
        lda     gy0
        cmp     gy1
        bne     @line
        lda     gx0                     ; a point: a smallest dot
        sta     dcx
        lda     gy0
        sta     dcy
        jmp     dot1c
@line:  lda     gy1                     ; downwards
        cmp     gy0
        bcs     :+
        ldx     gy0
        sta     gy0
        stx     gy1
        lda     gx0
        ldx     gx1
        sta     gx1
        stx     gx0
:       lda     gy0
        cmp     gy1
        bne     @slope
        sta     sy                      ; horizontal: one span
        lda     gx0
        ldx     gx1
        cmp     gx1
        bcc     :+
        stx     sxa
        tax
        bcs     :++                     ; (always)
:       sta     sxa
:       inx
        bne     :+
        dex
:       stx     sxb
        jmp     span
@slope: lda     #0
        sta     gsg
        lda     gx1
        sec
        sbc     gx0
        bcs     :+
        eor     #$FF                    ; |dx|
        adc     #1
        dec     gsg
:       sta     gadx
        lda     gy1
        sec
        sbc     gy0
        sta     gdy
        jsr     slope
        lda     #128
        sta     gac
        lda     #0
        sta     gac+1
        lda     gx0
        sta     gcur
        lda     gy0
        sta     gy
@row:   lda     gy
        cmp     cbot
        beq     :+
        bcs     @done                   ; below the window: nothing more
:       clc
        lda     gac
        adc     gsl
        sta     gac
        lda     gac+1
        adc     gsl+1
        sta     gac+1
        ldx     gy
        inx
        cpx     gy1
        bne     :+
        lda     gx1
        jmp     @have
:       lda     gsg
        bmi     :+
        lda     gx0
        clc
        adc     gac+1
        jmp     @have
:       lda     gx0
        sec
        sbc     gac+1
@have:  sta     gnxt
        cmp     gcur
        bcs     :+
        sta     sxa                     ; next < current
        lda     gcur
        jmp     :++
:       ldx     gcur
        stx     sxa
:       clc
        adc     #1
        bcc     :+
        lda     #255
:       sta     sxb
        lda     gy
        sta     sy
        jsr     span
        lda     gnxt
        sta     gcur
        inc     gy
        lda     gy
        cmp     gy1
        bne     @row
        sta     sy                      ; the bottom row
        lda     gx1
        sta     sxa
        clc
        adc     #1
        bcc     :+
        lda     #255
:       sta     sxb
        jmp     span
@done:  rts

; gsl = gadx * 256 / gdy, 16 bits (gdy > 0).
slope:  lda     gadx
        sta     gsl+1
        lda     #0
        sta     gsl
        ldx     #16
:       asl     gsl
        rol     gsl+1
        rol
        bcs     :+
        cmp     gdy
        bcc     :++
:       sbc     gdy
        inc     gsl
:       dex
        bne     :---
        rts

; -- dots ---------------------------------------------------------------------------
; A spot of size dsz at (dcx, dcy): rows dcy - s .. dcy + s - 1, on the
; i-th of them x - w .. x + w - 1, w from dhw.
dot:    lda     dcy
        sec
        sbc     dsz
        sta     drl
        lda     #0
        sbc     #0
        sta     drh
        ldx     dsz
        lda     dhoff,x
        sta     ddi
        txa
        asl
        sta     dcnt
@row:   lda     drh                     ; rows 0-255 only
        bne     @next
        ldx     ddi
        lda     dcx
        sec
        sbc     dhw,x
        bcs     :+
        lda     #0
:       sta     sxa
        lda     dcx
        clc
        adc     dhw,x
        bcs     :+
        sbc     #0                      ; C = 0: - 1
        jmp     :++
:       lda     #255
:       sta     sxb
        lda     drl
        sta     sy
        jsr     span
@next:  inc     drl
        bne     :+
        inc     drh
:       inc     ddi
        dec     dcnt
        bne     @row
        rts

; -- solids -----------------------------------------------------------------------
; Scan-line fill, even-odd, of q[0..qm-1] (qm >= 3). An edge covers the rows
; ya <= y < yb; its crossing is xa +- (128 + slope * (y - ya)) >> 8, kept
; as a running 8.8 sum. The active edges' crossings, sorted, pair into spans.
fill:   lda     #0
        sta     ne
        sta     oi
@edge:  ldx     oi                      ; edge oi -> oi + 1
        ldy     oi
        iny
        cpy     qm
        bne     :+
        ldy     #0
:       lda     qy,x
        cmp     qy,y
        jeq     @flat
        bcc     :+
        stx     t0                      ; upwards: take it the other way
        tya
        tax
        ldy     t0
:       stx     t0                      ; X top, Y bottom
        sty     t1
        ldx     ne
        ldy     t0
        lda     qx,y
        sta     exa,x
        lda     qy,y
        sta     eya,x
        ldy     t1
        lda     qy,y
        sta     eyb,x
        sec
        ldy     t0
        sbc     qy,y
        sta     gdy
        lda     #0
        sta     esg,x
        ldy     t1
        lda     qx,y
        ldy     t0
        sec
        sbc     qx,y
        bcs     :+
        eor     #$FF
        adc     #1
        dec     esg,x
:       sta     gadx
        jsr     slope
        ldx     ne
        lda     gsl
        sta     esl,x
        lda     gsl+1
        sta     esh,x
        ; insertion into ord by top row
        lda     eya,x
        sta     t2
        ldy     ne
:       cpy     #0
        beq     :+
        ldx     ord-1,y
        lda     eya,x
        cmp     t2
        bcc     :+
        beq     :+
        txa
        sta     ord,y
        dey
        jmp     :-
:       lda     ne
        sta     ord,y
        inc     ne
@flat:  inc     oi
        lda     oi
        cmp     qm
        jne     @edge
        lda     ne
        bne     :+
        rts
:       lda     #0
        sta     nact
        sta     nxt
        ldx     ord
        lda     eya,x
        sta     gy
@row:   ldy     nxt                     ; edges starting on this row
        cpy     ne
        beq     @rm
        ldx     ord,y
        lda     eya,x
        cmp     gy
        bne     @rm
        lda     #128
        sta     eal,x
        lda     #0
        sta     eah,x
        txa
        ldy     nact
        sta     act,y
        inc     nact
        inc     nxt
        bne     @row                    ; (always)
@rm:    ldy     #0                      ; edges ending on this row
        sty     t0
:       cpy     nact
        beq     :++
        ldx     act,y
        lda     eyb,x
        cmp     gy
        beq     :+
        txa
        ldx     t0
        sta     act,x
        inc     t0
:       iny
        bne     :--                     ; (always)
:       lda     t0
        sta     nact
        bne     @work
        lda     nxt
        cmp     ne
        jeq     @done
        jmp     @step
@work:  lda     gy
        cmp     cbot
        beq     :+
        jcs     @done
:       cmp     ct
        bcc     @step
        ldy     #0                      ; crossings
@cx:    ldx     act,y
        lda     esg,x
        bmi     :+
        lda     exa,x
        clc
        adc     eah,x
        jmp     :++
:       lda     exa,x
        sec
        sbc     eah,x
:       sta     xs,y
        iny
        cpy     nact
        bne     @cx
        ldx     #1                      ; sorted
@is:    cpx     nact
        bcs     @isd
        lda     xs,x
        sta     t0
        txa
        tay
:       lda     xs-1,y
        cmp     t0
        bcc     :+
        beq     :+
        sta     xs,y
        dey
        bne     :-
:       lda     t0
        sta     xs,y
        inx
        bne     @is                     ; (always)
@isd:   ldy     #1                      ; pairs
@pr:    cpy     nact
        bcs     @step
        lda     xs-1,y
        sta     sxa
        lda     xs,y
        sta     sxb
        lda     gy
        sta     sy
        sty     t3
        jsr     span
        ldy     t3
        iny
        iny
        bne     @pr                     ; (always)
@step:  ldy     nact
        beq     @inc
        dey
:       ldx     act,y
        clc
        lda     eal,x
        adc     esl,x
        sta     eal,x
        lda     eah,x
        adc     esh,x
        sta     eah,x
        dey
        bpl     :-
@inc:   inc     gy
        jmp     @row
@done:  rts

; -- spans ---------------------------------------------------------------------------
; The object's colour byte A: patterns for even rows (high nibble) and odd
; rows (low nibble).
setcol: pha
        lsr
        lsr
        lsr
        lsr
        tax
        lda     pate,x
        sta     ce0
        lda     pato,x
        sta     ce1
        pla
        and     #$0F
        tax
        lda     pate,x
        sta     co0
        lda     pato,x
        sta     co1
        rts

; Writes the pattern into the covered dots of one byte: Y column, msk.
.macro  PUT
        tya
        lsr
        lda     p0
        bcc     :+
        lda     p1
:       eor     (rowp),y
        and     msk
        eor     (rowp),y
        sta     (rowp),y
.endmacro

; Fills movie x sxa..sxb (sxa <= sxb expected) on row sy of pagehi, within
; the clip window.
span:   lda     sy
        cmp     ct
        bcc     @out
        cmp     cbot
        beq     :+
        bcs     @out
:       lda     sxa
        cmp     cl
        bcs     :+
        lda     cl
:       sta     t2                      ; left
        lda     sxb
        cmp     cr
        bcc     :+
        lda     cr
:       cmp     t2
        bcc     @out
        tax
        lda     colof,x
        sta     ccb
        lda     rmx,x
        sta     mr
        ldy     sy
        lda     rowlo,y
        sta     rowp
        lda     rowhi,y
        ora     pagehi
        sta     rowp+1
        tya
        lsr
        bcs     :+
        lda     ce0
        sta     p0
        lda     ce1
        bcc     :++                     ; (always)
:       lda     co0
        sta     p0
        lda     co1
:       sta     p1
        eor     p0
        sta     pd
        ldx     t2
        lda     lmx,x
        ldy     colof,x
        sty     scol
        cpy     ccb
        bne     @multi
        and     mr
        sta     msk
        PUT
        jmp     @count
@out:   rts
@multi: sta     msk
        PUT
        iny
        cpy     ccb
        beq     @right
        tya
        lsr
        lda     p0
        bcc     @full
        lda     p1
@full:  sta     (rowp),y
        eor     pd
        iny
        cpy     ccb
        bne     @full
@right: lda     mr
        sta     msk
        PUT
@count: lda     counting
        beq     @out
        inc     fv_counts+C_SPANS
        bne     :+
        inc     fv_counts+C_SPANS+1
        bne     :+
        inc     fv_counts+C_SPANS+2
:       lda     ccb                     ; bytes: ccb - scol + 1
        sec
        sbc     scol
        sec
        adc     fv_counts+C_BYTES
        sta     fv_counts+C_BYTES
        bcc     @out
        inc     fv_counts+C_BYTES+1
        bne     @out
        inc     fv_counts+C_BYTES+2
        rts

; -- timing ---------------------------------------------------------------------------
; fv_orig = ORIG_BASE + the terms of origt, fv_own = OWN_BASE + OWN_TIMING
; + the terms of ownt, fv_wait = max(0, fv_orig - fv_own).
fv_timing:
        lda     #<ORIG_BASE
        ldx     #>ORIG_BASE
        ldy     #0
        jsr     terms
        ldx     #3
:       lda     acc,x
        sta     fv_orig,x
        dex
        bpl     :-
        lda     #<(OWN_BASE + OWN_TIMING)
        ldx     #>(OWN_BASE + OWN_TIMING)
        ldy     #ownt - origt
        jsr     terms
        sec
        ldx     #0
        ldy     #4
:       lda     acc,x
        sta     fv_own,x
        lda     fv_orig,x
        sbc     acc,x
        sta     fv_wait,x
        inx
        dey
        bne     :-
        bcs     :+
        lda     #0
        sta     fv_wait
        sta     fv_wait+1
        sta     fv_wait+2
        sta     fv_wait+3
:       rts

; acc = A/X + sum of counter * cycles over the terms from origt + Y.
terms:  sta     acc
        stx     acc+1
        lda     #0
        sta     acc+2
        sta     acc+3
@term:  ldx     origt,y
        bmi     @done
        lda     origt+1,y
        sta     mulk
        lda     origt+2,y
        sta     mulk+1
        lda     fv_counts,x
        sta     mulv
        lda     fv_counts+1,x
        sta     mulv+1
        lda     fv_counts+2,x
        sta     mulv+2
        lda     #0
        sta     mulv+3
        ldx     #16
@bit:   lsr     mulk+1
        ror     mulk
        bcc     :+
        clc
        lda     acc
        adc     mulv
        sta     acc
        lda     acc+1
        adc     mulv+1
        sta     acc+1
        lda     acc+2
        adc     mulv+2
        sta     acc+2
        lda     acc+3
        adc     mulv+3
        sta     acc+3
:       asl     mulv
        rol     mulv+1
        rol     mulv+2
        rol     mulv+3
        dex
        bne     @bit
        iny
        iny
        iny
        bne     @term                   ; (always)
@done:  rts
