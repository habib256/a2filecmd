; engine.s -- the Fantavision movie engine of FANTA.SYSTEM: checks, tweening
; and drawing (docs/FANTAVISION-FORMAT.md; tools/fantavision_ref.py is its
; reference model and states the rules the spec leaves open).
;
; Plain 6502 throughout. The engine reads the movie and writes only its own
; variables (segments ZEROPAGE, BSS and EBSS), some of its own code (operands
; patched per frame: the page's extents arrays, the erase copy addresses,
; the fill's span writer) and three fixed 8 KB buffers: hi-res page 1
; ($2000), page 2 ($4000) and the background copy ($6000). It never calls
; ProDOS or the ROM: FANTA.SYSTEM (fanta.s) loads the movie, flips the pages
; and reads the keys; tools/test_fantavision.py links this same file with a
; C harness under sim65. Segments TABLES and FCOLD (constant tables, the
; once-a-movie code) run from low memory in FANTA.SYSTEM (fanta.cfg).
;
; Interface (all variables in BSS, the routines preserve nothing):
;   fv_movie, fv_len  the movie's address and length, set by the caller
;   fv_count   nonzero: count each frame's work, for fv_timing (the
;              original speed); the picture is the same either way
;   fv_check   A = 0 if the movie is accepted, else a reason code 1-5; a
;              damaged tail is cut: fv_frames whole frames, ending at fv_end
;   fv_begin   builds the background and copies it to both pages; with
;              fv_bdrop set, the background is the backdrop the caller
;              has read into $6000 (8,192 bytes)
;   fv_first   draws key frame 0 on page 1 (fv_shown = $20)
;   fv_next    builds the next frame on the hidden page and sets fv_shown;
;              A = 1 (nothing built) once a counted movie has ended
;   fv_timing  after a frame: fv_orig, the original player's time for it,
;              fv_own, this engine's estimated time, fv_wait = the
;              difference, never negative (cycles, 32 bits)
;
; Speed: spans are filled a byte at a time from tables (row addresses, edge
; masks by x, colour patterns), full bytes by unrolled chains; solids use a
; scan-line fill with an active edge list kept sorted; tweened points and
; edge crossings are 8.8 sums, added and never recomputed; erasing restores,
; row by row, only the byte columns the normal objects covered (their
; extents) from the background copy. At the accelerated speed (fv_count 0),
; objects inside the clip window take fast paths: segment rows, dot rows
; (top and bottom together) and fill rows written inline, unrolled by row
; parity so that each row's colour patterns are known; the counting speed
; uses the common clipped writer. Both draw the same bytes.

        .macpack longbranch
        .export fv_check, fv_begin, fv_first, fv_next, fv_timing
        .export fv_movie, fv_len, fv_shown, fv_done, fv_frames, fv_count, fv_end
        .export fv_bdrop
        .export fv_counts, fv_orig, fv_own, fv_wait

PAGE1   = $20
BGPAGE  = $60
MAXPTS  = 32

; The original player's time for a frame (docs, "How long the original
; takes"), and this engine's own, calibrated with sim65 on the synthetic set
; (tools/test_fantavision.py --calibrate: least squares on 1,000 frames,
; relative error, no negative cost). The reference carries the original's.
ORIG_BASE  = 6300
OWN_BASE    = 9983      ; per frame, fv_timing included
OWN_SPANS   = 172       ; cycles per unit of each counter
OWN_BYTES   = 34
OWN_EROWS   = 261
OWN_EBYTES  = 6
OWN_EDGES   = 93
OWN_IPOINTS = 243
OWN_OBJECTS = 1725
OWN_LROWS   = 132
OWN_FROWS   = 0
OWN_ASTEP   = 158

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
O_LROWS   = 36          ; rows stepped along segments
O_FROWS   = 39          ; rows stepped by the fill
O_ASTEP   = 42          ; active edges stepped by the fill
NCOUNTS   = 45

        .zeropage
jv:     .res 2          ; jump vector (kept off a page end: first in ZP)
mov:    .res 2          ; the movie
rp:     .res 2          ; a record
pa:     .res 2          ; key k's record (tweening set-up)
pb:     .res 2          ; key k+1's record
xp:     .res 2          ; the x coordinates of the object drawn
yp:     .res 2          ; its y coordinates
rowp:   .res 2          ; the row being written
bgp:    .res 2          ; the same row in the background copy
pagehi: .res 1          ; the buffer drawn into: $20, $40 or $60
counting: .res 1        ; 1: spans count (page built); $81: and extents too
crow:   .res 1          ; the row set by srow
pidx:   .res 1          ; page built: 0 (page 1) or 1 (page 2)
scol:   .res 1          ; span: its first byte column
ccb:    .res 1          ;       its last byte column
mr:     .res 1          ;       mask of the last byte
ml:     .res 1          ;       mask of the first byte
dt0:    .res 1          ; dot: the two rows drawn together
dt1:    .res 1
dfast:  .res 1          ; the dots of this object are all inside the window
msk:    .res 1
p0:     .res 1          ; the pattern of this row, even and odd columns
p1:     .res 1
pd:     .res 1          ; p0 ^ p1
ce0:    .res 1          ; the object's patterns: even rows
ce1:    .res 1
co0:    .res 1          ; odd rows
co1:    .res 1
pde:    .res 1          ; ce0 ^ ce1
pdo:    .res 1          ; co0 ^ co1
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
krp:    .res 2          ; version: the next record of the key frame
gcv:    .res 1          ; seg: nonzero, gcsl/gcsh is the slope to use
gcsl:   .res 1
gcsh:   .res 1
gstop:  .res 1          ; segfast: the row to stop at
glast:  .res 1          ;          the row before the last
gxc:    .res 1          ;          x, or ~x going left
fstop:  .res 1          ; fill, two edges: the row to stop at
frow:   .res 1          ;                  the row started from
fla:    .res 1          ;                  edge a: fraction, crossing,
xca:    .res 1          ;                  slope, sign
sla:    .res 1
sha:    .res 1
sga:    .res 1
flb:    .res 1          ;                  edge b
xcb:    .res 1
slb:    .res 1
shb:    .res 1
sgb:    .res 1
osp:    .res 2          ; spans and bytes of the object being drawn
oby:    .res 2
erw:    .res 2          ; rows and bytes erased this frame
eby:    .res 2

        .bss
fv_movie: .res 2
fv_count: .res 1        ; nonzero: count the work (original speed)
fv_bdrop: .res 1        ; nonzero: the background copy holds a backdrop
lastcnt: .res 1         ; the frame before was counted
fv_len:   .res 2
fv_shown: .res 1
fv_done:  .res 1
fv_frames: .res 1
fv_end:   .res 2        ; fv_check: where the movie ends (offset)
fv_counts: .res NCOUNTS
normal: .res 6          ; spans and bytes of the normal objects (fv_counts + 36)
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
prevn:  .res 6          ; the same, frame before
acc:    .res 4          ; fv_timing
mulv:   .res 4
mulk:   .res 2
qm:     .res 1          ; a solid's points, deduplicated
qstamp: .res 1          ; the shape being drawn, for the slope cache
qv:     .res MAXPTS     ; edge i's slope cached for shape qstamp
qsl:    .res MAXPTS
qsh:    .res MAXPTS
qx:     .res MAXPTS
qy:     .res MAXPTS
ne:     .res 1          ; its edges
nact:   .res 1
nxt:    .res 1
nend:   .res 1          ; the first row where an active edge ends
exa:    .res MAXPTS     ; x at the top end
eya:    .res MAXPTS     ; top row
eyb:    .res MAXPTS     ; bottom row, excluded
esl:    .res MAXPTS     ; slope, 8.8
esh:    .res MAXPTS
esg:    .res MAXPTS     ; $FF: x decreases downwards
eal:    .res MAXPTS     ; running sum, fraction
ord:    .res MAXPTS     ; edges by top row
act:    .res MAXPTS     ; active edges
xs:     .res MAXPTS     ; their crossings on this row
erlo:   .res 2          ; rows with extents, per page: first
erhi:   .res 2          ; and last ($FF, 0 when none)
exc:    .res MAXPTS     ; an edge's crossing on this row, x or ~x
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

        .segment "EBSS"                 ; (FANTA.SYSTEM: $0800, free once
emin1:  .res 256        ; the movie is read) per row, the first and last
emin2:  .res 256        ; byte columns the normal objects covered, page 1
emax1:  .res 256        ; then page 2: 256 bytes apart (rows 0-191 used)
emax2:  .res 256

        .segment "TABLES"               ; (FANTA.SYSTEM: in low memory)
; Movie x is screen x + 14: its byte column, and the masks of the dots from
; x to the end of its byte (left end of a span) and from the start of its
; byte to x (right end). Bit 7 is always in: the byte takes the palette.
; (Segment TABLES: FANTA.SYSTEM runs it in low memory, see fanta.cfg.)
        .segment "TABLES"
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
; Entries into the unrolled chains for n full bytes.
chlo:
        .repeat 37, N
        .byte <(chaince - 5 * N)
        .endrep
chhi:
        .repeat 37, N
        .byte >(chaince - 5 * N)
        .endrep
cplo:
        .repeat 37, N
        .byte <(chainpe - 3 * N)
        .endrep
cphi:
        .repeat 37, N
        .byte >(chainpe - 3 * N)
        .endrep
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
        .word OWN_SPANS
        .byte O_BYTES
        .word OWN_BYTES
        .byte O_EROWS
        .word OWN_EROWS
        .byte O_EBYTES
        .word OWN_EBYTES
        .byte O_EDGES
        .word OWN_EDGES
        .byte O_IPOINTS
        .word OWN_IPOINTS
        .byte O_OBJECTS
        .word OWN_OBJECTS
        .byte O_LROWS
        .word OWN_LROWS
        .byte O_FROWS
        .word OWN_FROWS
        .byte O_ASTEP
        .word OWN_ASTEP
        .byte $FF

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

; The same with the patterns of a known row parity.
.macro  PUTP    pe, po
        tya
        lsr
        lda     pe
        bcc     :+
        lda     po
:       eor     (rowp),y
        and     msk
        eor     (rowp),y
        sta     (rowp),y
.endmacro

        .code

        .segment "FCOLD"                ; (FANTA.SYSTEM: in low memory)
; -- the checks -------------------------------------------------------------
; Everything is checked before anything is drawn; no byte past fv_len is
; read. A damaged tail is cut: the movie ends before the first frame that
; is not whole (fv_frames frames, fv_end its offset). Codes: 1 size,
; 2 header, 3 clip window, 4 not even one whole frame, 5 more than 127.
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
@frame: lda     rp                      ; where this frame starts: the end
        sta     pa                      ; if it is not whole
        lda     rp+1
        sta     pa+1
        lda     t0                      ; the end of the file: the end
        ora     t1
        beq     @end
        ldy     #0
        lda     (rp),y
        beq     @end                    ; 0 where a frame starts: the end
        ldx     fv_frames
        cpx     #127
        beq     :+                      ; a 128th frame: only looked at
        lda     rp
        sta     ftlo,x
        lda     rp+1
        sta     fthi,x
:       lda     #8
        sta     t2
@rec:   lda     t0                      ; A damaged frame cuts the movie
        ora     t1                      ; before it: the end of the file
        beq     @cut                    ; inside a frame,
        ldy     #0
        lda     (rp),y
        cmp     #1
        beq     @adv
        cmp     #4                      ; a length 0, 2, 3,
        bcc     @cut
        cmp     #4 + 2 * MAXPTS + 1     ; above 68,
        bcs     @cut
        lsr                             ; odd,
        bcs     @cut
        asl
        ldx     t1                      ; more than 255 left: it fits
        bne     @adv
        cmp     t0                      ; or past the end of the file
        beq     @adv
        bcs     @cut
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
        lda     fv_frames               ; a whole frame
        cmp     #127
        beq     bad5                    ; the 128th: refused
        inc     fv_frames
        jmp     @frame
@cut:   lda     pa                      ; the end: where the damaged frame
        sta     rp                      ; starts
        lda     pa+1
        sta     rp+1
@end:   sec                             ; fv_end: the offset of the end
        lda     rp
        sbc     mov
        sta     fv_end
        lda     rp+1
        sbc     mov+1
        sta     fv_end+1
        lda     fv_frames
        beq     bad4                    ; not even one whole frame
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
        sta     dfast
        ldx     #1                      ; frame 0: nothing to erase, known
        stx     lastcnt
        ldx     #5
:       sta     prevn,x
        dex
        bpl     :-
        ldx     #191                    ; no extents
:       sta     emax1,x
        sta     emax2,x
        dex
        cpx     #$FF
        bne     :-
        sta     erhi
        sta     erhi+1
        lda     #$FF
        sta     erlo
        sta     erlo+1
        ldx     #191
:       sta     emin1,x
        sta     emin2,x
        dex
        cpx     #$FF
        bne     :-
        lda     #0
        ldx     #7
:       sta     tfl,x
        dex
        bpl     :-
        ; The background: a backdrop the caller has read into the copy
        ; (fv_bdrop), or else black, the rectangle x 5-250, rows 12-159
        ; in the colour of header byte 4, not clipped.
        lda     fv_bdrop
        bne     @pages
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
@bg:    ldy     gy
        jsr     srow
        ldx     #5
        ldy     #250
        jsr     sx
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
@pages: lda     #PAGE1
        jsr     bgcopy
        lda     #PAGE1 + $20
        jmp     bgcopy                  ; (in the other segment)

        .code
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
        ldx     #0                      ; the page's extents: page 2's
        lda     bpage                   ; arrays are 256 bytes above page
        cmp     #PAGE1                  ; 1's, only the high bytes of the
        beq     :+                      ; operands that use them change
        inx
:       stx     pidx
        txa
        clc
        adc     #>emin1
        sta     gmin1e+2
        sta     gmin2e+2
        sta     gmin1o+2
        sta     gmin2o+2
        sta     dmin1e+2
        sta     dmin2e+2
        sta     dmin1o+2
        sta     dmin2o+2
        sta     tmin1+2
        sta     tmin2+2
        sta     fmin1e+2
        sta     fmin2e+2
        sta     fmin1o+2
        sta     fmin2o+2
        sta     ermn1+2
        sta     ermn2+2
        txa
        clc
        adc     #>emax1
        sta     gmax1e+2
        sta     gmax2e+2
        sta     gmax1o+2
        sta     gmax2o+2
        sta     dmax1e+2
        sta     dmax2e+2
        sta     dmax1o+2
        sta     dmax2o+2
        sta     tmax1+2
        sta     tmax2+2
        sta     fmax1e+2
        sta     fmax2e+2
        sta     fmax1o+2
        sta     fmax2o+2
        sta     ermx1+2
        sta     ermx2+2
        lda     #0
        ldx     #5                      ; normal, and the counters when
:       sta     normal,x                ; counting (the original speed)
        dex
        bpl     :-
        ldx     fv_count
        beq     :++
        ldx     #NCOUNTS - 1
:       sta     fv_counts,x
        dex
        bpl     :-
:
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
:       lda     #0
        sta     osp
        sta     osp+1
        sta     oby
        sta     oby+1
        lda     bpage
        sta     pagehi
        lda     fv_count                ; counts at the original speed only;
        ldx     oanim                   ; a normal object leaves extents
        bne     :+
        jsr     rows
        lda     fv_count
        ora     #$80
:       sta     counting
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
@drawn: clc                             ; one byte a span, plus the extra ones
        lda     oby
        adc     osp
        sta     oby
        lda     oby+1
        adc     osp+1
        sta     oby+1
        ldx     #C_SPANS
        jsr     addo
        ldy     targets
:       ldx     #O_SPANS
        jsr     addo
        dey
        bne     :-
        lda     oanim
        bne     @next
        ldx     #NCOUNTS                ; a normal object: counted
        jsr     addo
@next:  inc     obj
        lda     obj
        cmp     #8
        jne     @obj
        lda     fv_count                ; the first frame counted after some
        beq     @prev                   ; were not (Tab): what the frame
        lda     lastcnt                 ; before left to erase is unknown;
        bne     @prev                   ; this frame's own normal objects
        ldx     #5                      ; stand in for it
:       lda     normal,x
        sta     fv_counts+C_ESPANS,x
        dex
        bpl     :-
@prev:  lda     fv_count
        sta     lastcnt
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
        ldx     obj                     ; the records one after the other
        bne     :+
        ldy     vframe
        lda     ftlo,y
        sta     krp
        lda     fthi,y
        sta     krp+1
:       lda     krp
        sta     rp
        lda     krp+1
        sta     rp+1
        ldy     #0
        lda     (rp),y
        clc
        adc     krp
        sta     krp
        bcc     :+
        inc     krp+1
:       lda     (rp),y
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

; The rows a normal object may touch, from its points: widened by the dot
; size or by one row, added to the page's range erlo..erhi (erase looks
; there for extents).
rows:   ldy     #0
        lda     (yp),y
        sta     t0                      ; min
        sta     t1                      ; max
:       iny
        cpy     onp
        bcs     :++
        lda     (yp),y
        cmp     t0
        bcs     :+
        sta     t0
:       cmp     t1
        bcc     :--
        sta     t1
        bcs     :--                     ; (always)
:       lda     #1
        ldx     okind
        bne     :+
        lda     omode
:       sta     t2                      ; margin
        ldx     pidx
        lda     t0
        sec
        sbc     t2
        bcs     :+
        lda     #0
:       cmp     erlo,x
        bcs     :+
        sta     erlo,x
:       lda     t1
        clc
        adc     t2
        bcs     :+
        cmp     #192
        bcc     :++
:       lda     #191
:       cmp     erhi,x
        bcc     :+
        sta     erhi,x
:       rts

; Adds the object's osp and oby to the counters at fv_counts + X, + X + 3.
addo:   clc
        lda     fv_counts,x
        adc     osp
        sta     fv_counts,x
        lda     fv_counts+1,x
        adc     osp+1
        sta     fv_counts+1,x
        bcc     :+
        inc     fv_counts+2,x
:       clc
        lda     fv_counts+3,x
        adc     oby
        sta     fv_counts+3,x
        lda     fv_counts+4,x
        adc     oby+1
        sta     fv_counts+4,x
        bcc     :+
        inc     fv_counts+5,x
:       rts

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
; Restores, row by row, the byte columns the normal objects covered on page
; bpage (its extents) from the background copy, and clears the extents.
; The copy loop's two addresses are written into it for each row.
erase:  lda     #0
        sta     erw
        sta     erw+1
        sta     eby
        sta     eby+1
        ldx     pidx
        lda     erlo,x
        sta     gy
        lda     erhi,x
        sta     gnxt
        lda     #$FF
        sta     erlo,x
        lda     #0
        sta     erhi,x
        lda     gnxt
        cmp     gy
        bcc     edone                   ; none
        lda     bpage                   ; page = (background | row) ^ this
        eor     #BGPAGE
        sta     epg+1
        lda     #<esrc                  ; the counting only at the original
        ldy     #>esrc                  ; speed: a jump over it otherwise
        ldx     fv_count
        beq     :+
        lda     #<ecount
        ldy     #>ecount
:       sta     ecj+1
        sty     ecj+2
        ldx     gy
        inc     gnxt                    ; the row after the last
erow:
ermn1:  lda     emin1,x                 ; (the addresses of the page's arrays
        sta     t0                      ; are written in by build)
ermx1:  lda     emax1,x
        sec
        sbc     t0
        bcc     enext                   ; nothing on this row
        tay                             ; columns - 1
        lda     #$FF
ermn2:  sta     emin1,x
        lda     #0
ermx2:  sta     emax1,x
        lda     rowlo,x                 ; (a row's start plus a column never
        clc                             ; crosses a page)
        adc     t0
        sta     esrc+1
        sta     edst+1
        lda     rowhi,x
        ora     #BGPAGE
        sta     esrc+2
epg:    eor     #$00                    ; (written above)
        sta     edst+2
ecj:    jmp     esrc                    ; (or ecount)
ecount: inc     erw
        bne     :+
        inc     erw+1
:       tya
        sec
        adc     eby
        sta     eby
        bcc     esrc
        inc     eby+1
esrc:   lda     $FFFF,y
edst:   sta     $FFFF,y
        dey
        bpl     esrc
enext:  inx
        cpx     gnxt
        bne     erow
edone:  lda     erw
        sta     fv_counts+O_EROWS
        lda     erw+1
        sta     fv_counts+O_EROWS+1
        lda     eby
        sta     fv_counts+O_EBYTES
        lda     eby+1
        sta     fv_counts+O_EBYTES+1
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
        jsr     dotsin                  ; all inside the window? (dfast)
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
        lda     #0
        sta     dfast
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
        lda     #0
        sta     gcv
        jsr     seg
@skip:  inc     oi
        lda     oi
        cmp     oseg
        bne     @seg
        rts

; dfast = 1 when every spot of the dot object (size dsz) lies inside the
; window: min x - s >= cl, max x + s - 1 <= cr, the same for the rows.
dotsin: lda     #0
        sta     dfast
        ldy     #0
        lda     (xp),y
        sta     gx0
        sta     gx1
        lda     (yp),y
        sta     gy0
        sta     gy1
:       iny
        cpy     onp
        bcs     :++++
        lda     (xp),y
        cmp     gx0
        bcs     :+
        sta     gx0
:       cmp     gx1
        bcc     :+
        sta     gx1
:       lda     (yp),y
        cmp     gy0
        bcs     :+
        sta     gy0
:       cmp     gy1
        bcc     :----
        sta     gy1
        bcs     :----                   ; (always)
:       lda     gx0
        sec
        sbc     dsz
        bcc     @no
        cmp     cl
        bcc     @no
        lda     gy0
        sec
        sbc     dsz
        bcc     @no
        cmp     ct
        bcc     @no
        lda     gx1
        clc
        adc     dsz
        bcs     @no
        sbc     #0                      ; C = 0: - 1
        cmp     cr
        beq     :+
        bcs     @no
:       lda     gy1
        clc
        adc     dsz
        bcs     @no
        sbc     #0
        cmp     cbot
        beq     :+
        bcs     @no
:       inc     dfast                   ; 1: all inside
        rts
@no:    lda     #2                      ; 2: some maybe not
        sta     dfast
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
shape:  inc     qstamp                  ; this shape's slopes, cached by fill
        bne     :++
        ldx     #MAXPTS - 1             ; (after 255 shapes: all stale)
        lda     #0
        sta     qstamp
        inc     qstamp
:       sta     qv,x
        dex
        bpl     :-
:       ldy     #0
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
qseg:   lda     qv,x                    ; the fill's slope for this edge
        cmp     qstamp
        bne     :+
        lda     qsl,x
        sta     gcsl
        lda     qsh,x
        sta     gcsh
        lda     #1
        .byte   $2C                     ; (bit abs: skips the lda #0)
:       lda     #0
        sta     gcv
        lda     qx,x
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
        bne     seg_line
        lda     gy0
        cmp     gy1
        bne     seg_line
        lda     gx0                     ; a point: a smallest dot
        sta     dcx
        lda     gy0
        sta     dcy
        jmp     dot1c
seg_line:  lda     gy1                     ; downwards
        cmp     gy0
        bcs     :+
        ldx     gy0
        sta     gy0
        stx     gy1
        lda     gx0
        ldx     gx1
        sta     gx1
        stx     gx0
:       lda     gy1                     ; outside the window: nothing
        cmp     ct
        jcc     seg_done
        lda     gy0
        cmp     cbot
        beq     :+
        jcs     seg_done
:       lda     gx0
        cmp     gx1
        bcc     :+
        lda     gx1                     ; t0 = left, A = right
        sta     t0
        lda     gx0
        jmp     :++
:       sta     t0
        lda     gx1
:       clc
        adc     #1
        bcs     :+
        cmp     cl
        jcc     seg_done
:       lda     t0
        cmp     cr
        beq     :+
        jcs     seg_done
:       lda     gy0
        cmp     gy1
        bne     seg_slope
        cmp     ct                      ; horizontal: one span
        jcc     seg_done
        cmp     cbot
        beq     :+
        jcs     seg_done
:       tay
        jsr     srow
        ldx     gx0
        ldy     gx1
        cpx     gx1
        bcc     :+
        ldx     gx1
        ldy     gx0
:       iny
        bne     :+
        dey
:       jmp     sx
seg_slope: lda     #0
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
        lda     gcv                     ; a solid's outline: its fill's slope
        beq     :+
        lda     gcsl
        sta     gsl
        lda     gcsh
        sta     gsl+1
        bne     :++                     ; (skip; gsl+1 may be 0: see below)
        beq     :++
:       jsr     slope
:       lda     #128
        sta     gac
        lda     #0
        sta     gac+1
        lda     gx0
        sta     gcur
        lda     gy0
        sta     gy
        lda     ct                      ; starting above the window: straight
        sec                             ; to its top row
        sbc     gy0
        bcc     seg_fchk
        beq     seg_fchk
        ldx     ct
        cpx     gy1
        bcc     :+
        lda     gy1                     ; only the bottom row is in it
        jmp     seg_bottom
:       jsr     mulac
        lda     ct
        sta     gy
        lda     gsg
        bmi     :+
        lda     gx0
        clc
        adc     gac+1
        jmp     :++
:       lda     gx0
        sec
        sbc     gac+1
:       sta     gcur
seg_fchk:
        ; Accelerated (not counting), steep (|dx| <= dy: a row's run is 2
        ; or 3 dots, 2 bytes at most), x inside the window: the rows are
        ; written here directly.
        lda     counting
        lsr
        bcs     seg_row
        lda     gx0                     ; min x >= cl
        cmp     gx1
        bcc     :+
        lda     gx1
:       cmp     cl
        bcc     seg_row
        lda     gx0                     ; max x < cr
        cmp     gx1
        bcs     :+
        lda     gx1
:       cmp     cr
        bcs     seg_row
        jmp     segfast
seg_row:   lda     gy
        cmp     cbot
        beq     :+
        jcs     seg_done                   ; below the window: nothing more
:       lda     fv_count                ; (counted at the original speed)
        beq     :+
        inc     fv_counts+O_LROWS
        bne     :+
        inc     fv_counts+O_LROWS+1
        bne     :+
        inc     fv_counts+O_LROWS+2
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
        jmp     seg_have
:       lda     gsg
        bmi     :+
        lda     gx0
        clc
        adc     gac+1
        jmp     seg_have
:       lda     gx0
        sec
        sbc     gac+1
seg_have:  sta     gnxt
        ldy     gy
        cpy     ct
        bcc     seg_skip                   ; above the window: stepped only
        jsr     srow
        lda     gnxt
        cmp     gcur
        bcs     :+
        tax                             ; next < current
        ldy     gcur
        jmp     :++
:       ldx     gcur
        tay
:       iny
        bne     :+
        dey
:       jsr     sx
seg_skip:  lda     gnxt
        sta     gcur
        inc     gy
        lda     gy
        cmp     gy1
        bne     seg_row
seg_bottom:
segbot: cmp     ct                      ; the bottom row
        bcc     seg_done
        cmp     cbot
        beq     :+
        bcs     seg_done
:       tay
        jsr     srow
        ldx     gx1
        ldy     gx1
        iny
        bne     :+
        dey
:       jmp     sx
seg_done:  rts

; The fast rows of seg (see there): gy .. min(gy1, cbot + 1) - 1, then the
; bottom row as seg does it.
segfast:
        ldx     cbot
        inx
        cpx     gy1
        bcc     :+
        ldx     gy1
:       stx     gstop
        ldx     gy1
        dex
        stx     glast
        lda     gx0                     ; x, or ~x going left: always added to
        eor     gsg
        clc
        adc     gac+1
        sta     gxc
        lda     gy
        cmp     gstop
        jcs     sf_end
        lsr                             ; (A = gy) rows alternate: an even
        bcc     sf_e                    ; row, an odd row, each with its
        jmp     sf_o                    ; own patterns
sf_e:  clc                             ; an even row: the next row's x
        lda     gac
        adc     gsl
        sta     gac
        lda     gxc
        adc     gsl+1
        sta     gxc
        eor     gsg
        tax
        lda     gy
        cmp     glast
        bne     :+
        ldx     gx1                     ; the last: x1 itself
:       ldy     gy                      ; the row
        lda     rowlo,y
        sta     rowp
        lda     rowhi,y
        ora     pagehi
        sta     rowp+1
        stx     gnxt                    ; the run: min .. max + 1
        cpx     gcur
        bcc     :+
        ldx     gcur
        ldy     gnxt
        iny
        jmp     :++
:       ldy     gcur
        iny
:       lda     colof,y
        sta     ccb
        lda     rmx,y
        sta     mr
        lda     lmx,x
        ldy     colof,x
        sty     scol
        cpy     ccb
        bne     sf_2e
        and     mr
        sta     msk
        PUTP    ce0, ce1
        jmp     sf_te
sf_2e: iny                            ; more than two bytes: the writer
        cpy     ccb
        beq     :+
        sta     ml
        lda     gy                      ; (its extent: row crow)
        sta     crow
        lda     ce0
        sta     p0
        lda     ce1
        sta     p1
        jsr     wbody
        jmp     sf_ne
:       dey
        sta     msk
        PUTP    ce0, ce1
        iny
        lda     mr
        sta     msk
        PUTP    ce0, ce1
sf_te: bit    counting                ; a normal object: the extent
        bpl     sf_ne
        ldy     gy
        lda     scol
fmin1e: cmp   emin1,y
        bcs     :+
fmin2e: sta   emin1,y
:       lda     ccb
fmax1e: cmp   emax1,y
        bcc     sf_ne
fmax2e: sta   emax1,y
sf_ne: lda    gnxt
        sta     gcur
        inc     gy
        lda     gy
        cmp     gstop
        jeq     sf_end
sf_o:  clc                             ; an odd row: the next row's x
        lda     gac
        adc     gsl
        sta     gac
        lda     gxc
        adc     gsl+1
        sta     gxc
        eor     gsg
        tax
        lda     gy
        cmp     glast
        bne     :+
        ldx     gx1                     ; the last: x1 itself
:       ldy     gy                      ; the row
        lda     rowlo,y
        sta     rowp
        lda     rowhi,y
        ora     pagehi
        sta     rowp+1
        stx     gnxt                    ; the run: min .. max + 1
        cpx     gcur
        bcc     :+
        ldx     gcur
        ldy     gnxt
        iny
        jmp     :++
:       ldy     gcur
        iny
:       lda     colof,y
        sta     ccb
        lda     rmx,y
        sta     mr
        lda     lmx,x
        ldy     colof,x
        sty     scol
        cpy     ccb
        bne     sf_2o
        and     mr
        sta     msk
        PUTP    co0, co1
        jmp     sf_to
sf_2o: iny                            ; more than two bytes: the writer
        cpy     ccb
        beq     :+
        sta     ml
        lda     gy                      ; (its extent: row crow)
        sta     crow
        lda     co0
        sta     p0
        lda     co1
        sta     p1
        jsr     wbody
        jmp     sf_no
:       dey
        sta     msk
        PUTP    co0, co1
        iny
        lda     mr
        sta     msk
        PUTP    co0, co1
sf_to: bit    counting                ; a normal object: the extent
        bpl     sf_no
        ldy     gy
        lda     scol
fmin1o: cmp   emin1,y
        bcs     :+
fmin2o: sta   emin1,y
:       lda     ccb
fmax1o: cmp   emax1,y
        bcc     sf_no
fmax2o: sta   emax1,y
sf_no: lda    gnxt
        sta     gcur
        inc     gy
        lda     gy
        cmp     gstop
        beq     sf_end
        jmp     sf_e
sf_end:   lda     gy
        cmp     gy1
        bne     :+
        jmp     segbot
:       rts

; The fill's two-edge rows gy .. fstop - 1 at the accelerated speed, the
; shape inside the window: written here, unrolled by row parity.
tfast:  lda     gy
        lsr
        bcc     tf_e
        jmp     tf_o
tf_e:  ldy     gy                      ; an even row
        lda     rowlo,y
        sta     rowp
        lda     rowhi,y
        ora     pagehi
        sta     rowp+1
        lda     xca                     ; the run between the two edges
        eor     sga
        sta     t3
        lda     xcb
        eor     sgb
        cmp     t3
        bcs     :+
        tax
        ldy     t3
        jmp     :++
:       tay
        ldx     t3
:       jsr     fspane
tf_se: clc                            ; both edges one row down
        lda     fla
        adc     sla
        sta     fla
        lda     xca
        adc     sha
        sta     xca
        clc
        lda     flb
        adc     slb
        sta     flb
        lda     xcb
        adc     shb
        sta     xcb
        inc     gy
        lda     gy
        cmp     fstop
        jeq     tf_x
tf_o:  ldy     gy                      ; an odd row
        lda     rowlo,y
        sta     rowp
        lda     rowhi,y
        ora     pagehi
        sta     rowp+1
        lda     xca                     ; the run between the two edges
        eor     sga
        sta     t3
        lda     xcb
        eor     sgb
        cmp     t3
        bcs     :+
        tax
        ldy     t3
        jmp     :++
:       tay
        ldx     t3
:       jsr     fspano
tf_so: clc                            ; both edges one row down
        lda     fla
        adc     sla
        sta     fla
        lda     xca
        adc     sha
        sta     xca
        clc
        lda     flb
        adc     slb
        sta     flb
        lda     xcb
        adc     shb
        sta     xcb
        inc     gy
        lda     gy
        cmp     fstop
        beq     tf_x
        jmp     tf_e
tf_x:   rts

; The span writer of the fill's two-edge rows, chosen per shape.
ftjmp:
ftj:    jmp     sx

; mulac: gac = 128 + gsl * A, 16 bits (the callers' products fit). X is kept.
mulac:  sta     t0
        lda     gsl
        sta     t1
        lda     gsl+1
        sta     t2
        lda     #128
        sta     gac
        lda     #0
        sta     gac+1
:       lsr     t0
        bcc     :+
        clc
        lda     gac
        adc     t1
        sta     gac
        lda     gac+1
        adc     t2
        sta     gac+1
:       asl     t1
        rol     t2
        lda     t0
        bne     :--
        rts

; gsl = gadx * 256 / gdy, 16 bits (gdy > 0).
slope:  lda     #0
        sta     gsl
        lda     gadx
        cmp     gdy
        bcs     @full
        ldx     #0                      ; |dx| < dy: the integer part is 0,
@frac:  stx     gsl+1                   ; the remainder A: 8 steps
        ldx     #8
:       asl     gsl
        asl
        bcs     :+
        cmp     gdy
        bcc     :++
:       sbc     gdy
        inc     gsl
:       dex
        bne     :---
        rts
@full:  ldx     #0                      ; integer part below 8: by subtraction
@sub:   sbc     gdy                     ; (C = 1)
        inx
        cpx     #8
        beq     @long
        cmp     gdy
        bcs     @sub
        bcc     @frac                   ; (always)
@long:  lda     gadx                    ; 8 or more: the long division
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
        lda     dfast                   ; 1: the object inside, 2: look at
        beq     @row                    ; each spot
        lsr
        bcs     @fast
        lda     drh                     ; this spot inside?
        bne     @row
        lda     drl
        cmp     ct
        bcc     @row
        adc     dcnt                    ; (C = 1: top + 2s + 1)
        bcs     @row
        sbc     #1                      ; C = 0: - 2, the bottom row
        cmp     cbot
        beq     :+
        bcs     @row
:       lda     dcx
        sec
        sbc     dsz
        bcc     @row
        cmp     cl
        bcc     @row
        lda     dcx
        clc
        adc     dsz
        bcs     @row
        sbc     #0
        cmp     cr
        beq     @fast
        bcc     @fast
@row:   lda     drh                     ; rows 0-255 only
        bne     @next
        ldy     drl
        cpy     ct
        bcc     @next
        cpy     cbot
        beq     :+
        bcs     @done                   ; below the window: no more
:       jsr     srow
        ldy     ddi
        lda     dcx
        sec
        sbc     dhw,y
        bcs     :+
        lda     #0
:       tax
        lda     dcx
        clc
        adc     dhw,y
        bcs     :+
        sbc     #0                      ; C = 0: - 1
        tay
        jmp     :++
:       ldy     #255
:       jsr     sx
@next:  inc     drl
        bne     :+
        inc     drh
:       inc     ddi
        dec     dcnt
        bne     @row
@done:  rts
; Inside the window: the top and bottom rows at once, with the same bytes
; and masks, row i and row 2s-1-i.
@fast:  lda     drl
        sta     dt0
        clc
        adc     dcnt
        sta     dt1
        dec     dt1
        lda     dsz
        sta     dcnt
@fh:    ldy     ddi
        lda     dcx
        sec
        sbc     dhw,y
        tax
        lda     dcx
        clc
        adc     dhw,y
        tay
        dey
        lda     rmx,y
        sta     mr
        lda     colof,y
        sta     ccb
        lda     lmx,x
        sta     ml
        lda     colof,x
        sta     scol
        lda     counting                ; counting: the common writer
        lsr
        bcs     @fc
        lda     dt0                     ; the top row even: the bottom odd
        lsr
        ldy     dt0
        bcs     :+
        jsr     drowe
        ldy     dt1
        jsr     drowo
        jmp     @fn
:       jsr     drowo
        ldy     dt1
        jsr     drowe
        jmp     @fn
@fc:    ldy     dt0
        jsr     srow
        jsr     wbody
        ldy     dt1
        jsr     srow
        jsr     wbody
@fn:    inc     dt0
        dec     dt1
        inc     ddi
        dec     dcnt
        bne     @fh
        rts

; A dot's row Y of even parity: bytes scol..ccb, masks ml, mr, at the
; accelerated speed (no counting); the extent when tracking.
drowe: sty    crow
        lda     rowlo,y
        sta     rowp
        lda     rowhi,y
        ora     pagehi
        sta     rowp+1
        ldy     scol
        cpy     ccb
        bne     dme
        lda     ml
        and     mr
        sta     msk
        PUTP    ce0, ce1
        jmp     dte
dme:  lda     ml
        sta     msk
        PUTP    ce0, ce1
        iny
        cpy     ccb
        beq     dre
        tya                             ; the full bytes (two at most)
        lsr
        lda     ce0
        bcc     :+
        lda     ce1
:       sta     (rowp),y
        eor     pde
        iny
        cpy     ccb
        bne     :-
dre:  lda     mr
        sta     msk
        PUTP    ce0, ce1
dte:  bit     counting
        bpl     dxe
        ldy     crow
        lda     scol
dmin1e: cmp   emin1,y
        bcs     :+
dmin2e: sta   emin1,y
:       lda     ccb
dmax1e: cmp   emax1,y
        bcc     dxe
dmax2e: sta   emax1,y
dxe:  rts

; A dot's row Y of odd parity: bytes scol..ccb, masks ml, mr, at the
; accelerated speed (no counting); the extent when tracking.
drowo: sty    crow
        lda     rowlo,y
        sta     rowp
        lda     rowhi,y
        ora     pagehi
        sta     rowp+1
        ldy     scol
        cpy     ccb
        bne     dmo
        lda     ml
        and     mr
        sta     msk
        PUTP    co0, co1
        jmp     dto
dmo:  lda     ml
        sta     msk
        PUTP    co0, co1
        iny
        cpy     ccb
        beq     dro
        tya                             ; the full bytes (two at most)
        lsr
        lda     co0
        bcc     :+
        lda     co1
:       sta     (rowp),y
        eor     pdo
        iny
        cpy     ccb
        bne     :-
dro:  lda     mr
        sta     msk
        PUTP    co0, co1
dto:  bit     counting
        bpl     dxo
        ldy     crow
        lda     scol
dmin1o: cmp   emin1,y
        bcs     :+
dmin2o: sta   emin1,y
:       lda     ccb
dmax1o: cmp   emax1,y
        bcc     dxo
dmax2o: sta   emax1,y
dxo:  rts

; A fill span X..Y on row gy of even parity (rowp set), inside the
; window, at the accelerated speed; the extent when tracking.
fspane:
        lda     colof,y
        sta     ccb
        lda     rmx,y
        sta     mr
        lda     lmx,x
        ldy     colof,x
        sty     scol
        cpy     ccb
        bne     fme
        and     mr
        sta     msk
        PUTP    ce0, ce1
        jmp     fte
fme:  sta     msk                     ; the first byte,
        PUTP    ce0, ce1
        iny
        cpy     ccb
        beq     fre
        sty     t2                      ; the full bytes (chains),
        lda     ccb
        sec
        sbc     t2
        tax
        lda     pde
        beq     :++
        sta     pd
        lda     chlo,x
        sta     jv
        lda     chhi,x
        sta     jv+1
        tya
        lsr
        lda     ce0
        bcc     :+
        lda     ce1
:       jsr     sxjump
        jmp     fre
:       lda     cplo,x
        sta     jv
        lda     cphi,x
        sta     jv+1
        lda     ce0
        jsr     sxjump
fre:  lda     mr                      ; the last byte
        sta     msk
        PUTP    ce0, ce1
fte:  bit     counting                ; a normal object: the extent
        bpl     fxe
        ldy     gy
        lda     scol
gmin1e: cmp   emin1,y
        bcs     :+
gmin2e: sta   emin1,y
:       lda     ccb
gmax1e: cmp   emax1,y
        bcc     fxe
gmax2e: sta   emax1,y
fxe:  rts

; A fill span X..Y on row gy of odd parity (rowp set), inside the
; window, at the accelerated speed; the extent when tracking.
fspano:
        lda     colof,y
        sta     ccb
        lda     rmx,y
        sta     mr
        lda     lmx,x
        ldy     colof,x
        sty     scol
        cpy     ccb
        bne     fmo
        and     mr
        sta     msk
        PUTP    co0, co1
        jmp     fto
fmo:  sta     msk                     ; the first byte,
        PUTP    co0, co1
        iny
        cpy     ccb
        beq     fro
        sty     t2                      ; the full bytes (chains),
        lda     ccb
        sec
        sbc     t2
        tax
        lda     pdo
        beq     :++
        sta     pd
        lda     chlo,x
        sta     jv
        lda     chhi,x
        sta     jv+1
        tya
        lsr
        lda     co0
        bcc     :+
        lda     co1
:       jsr     sxjump
        jmp     fro
:       lda     cplo,x
        sta     jv
        lda     cphi,x
        sta     jv+1
        lda     co0
        jsr     sxjump
fro:  lda     mr                      ; the last byte
        sta     msk
        PUTP    co0, co1
fto:  bit     counting                ; a normal object: the extent
        bpl     fxo
        ldy     gy
        lda     scol
gmin1o: cmp   emin1,y
        bcs     :+
gmin2o: sta   emin1,y
:       lda     ccb
gmax1o: cmp   emax1,y
        bcc     fxo
gmax2o: sta   emax1,y
fxo:  rts

; The fill: the row where the next edge ends or starts, or the window's
; bottom + 1 (fstop).
fstopc: lda     nend
        sta     fstop
        ldy     nxt
        cpy     ne
        beq     :+
        ldx     ord,y
        lda     eya,x
        cmp     fstop
        bcs     :+
        sta     fstop
:       ldx     cbot
        inx
        cpx     fstop
        bcs     :+
        stx     fstop
:       rts

; The fill's active edges sorted by crossing (they were on the row before:
; this is quick).
xsort:  ldx     #1
@is:    cpx     nact
        bcs     @isd
        lda     xs,x
        cmp     xs-1,x
        bcs     @isn                    ; in place already
        sta     t0
        lda     act,x
        sta     t1
        txa
        tay
:       lda     xs-1,y
        cmp     t0
        bcc     :+
        beq     :+
        sta     xs,y
        lda     act-1,y
        sta     act,y
        dey
        bne     :-
:       lda     t0
        sta     xs,y
        lda     t1
        sta     act,y
@isn:   inx
        bne     @is                     ; (always)
@isd:   rts

; The fill span writer of this row's parity.
fsj:    jmp     fspane

; -- solids -----------------------------------------------------------------------
; Scan-line fill, even-odd, of q[0..qm-1] (qm >= 3). An edge covers the rows
; ya <= y < yb; its crossing is xa +- (128 + slope * (y - ya)) >> 8, kept
; as a running 8.8 sum. The active edges' crossings, sorted, pair into spans.
fill:   ldx     qm                      ; the extent: outside the window,
        dex                             ; nothing to fill
        lda     qx,x
        sta     gx0                     ; x min
        sta     gx1                     ; x max
        lda     qy,x
        sta     gy0                     ; y min
        sta     gy1                     ; y max
:       dex
        bmi     :++++
        lda     qx,x
        cmp     gx0
        bcs     :+
        sta     gx0
:       cmp     gx1
        bcc     :+
        sta     gx1
:       lda     qy,x
        cmp     gy0
        bcs     :+
        sta     gy0
:       cmp     gy1
        bcc     :----
        sta     gy1
        bcs     :----                   ; (always)
:       lda     gy1                     ; rows ymin .. ymax - 1
        cmp     ct
        beq     :+
        bcc     :+
        lda     gy0
        cmp     cbot
        beq     :++
        bcc     :++
:       rts
:       lda     gx1
        cmp     cl
        bcc     :--
        lda     gx0
        cmp     cr
        beq     :+
        bcs     :--
:
        ldy     gx0                     ; x min, max of the shape (gx0, gx1,
        cpy     cl                      ; from fill's start) inside the
        bcc     @tcl                    ; window: no clipping on the rows
        ldy     gx1
        cpy     cr
        beq     @tnc
        bcs     @tcl
@tnc:   lda     #<sxnc
        ldx     #>sxnc
        bne     @tset                   ; (always)
@tcl:   lda     #<sx
        ldx     #>sx
@tset:  sta     ftj+1
        stx     ftj+2
        lda     #0
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
        ldx     oi                      ; kept for the outline: edge oi
        lda     gsl
        sta     qsl,x
        lda     gsl+1
        sta     qsh,x
        lda     qstamp
        sta     qv,x
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
        lda     #$FF
        sta     nend
        ldx     ord
        lda     eya,x
        cmp     ct                      ; from the window's top at the latest
        bcs     :+
        lda     ct
:       sta     gy
@row:   ldy     nxt                     ; edges starting on this row
        cpy     ne
        beq     @rm
        ldx     ord,y
        lda     eya,x
        cmp     gy
        beq     :+
        bcs     @rm                     ; later
        lda     eyb,x                   ; begun above the window: ended
        cmp     gy                      ; there already?
        beq     @gone
        bcc     @gone
:       lda     esl,x                   ; its sum on this row
        sta     gsl
        lda     esh,x
        sta     gsl+1
        lda     gy
        sec
        sbc     eya,x
        jsr     mulac
        lda     gac
        sta     eal,x
        lda     eyb,x                   ; the next row where an edge ends
        cmp     nend
        bcs     :+
        sta     nend
:       lda     exa,x                   ; x, or ~x going left: always added to
        eor     esg,x
        clc
        adc     gac+1
        sta     exc,x
        eor     esg,x
        ldy     nact
        sta     xs,y
        txa
        sta     act,y
        inc     nact
@gone:  inc     nxt
        jmp     @row
@rm:    lda     gy                      ; edges ending on this row, looked
        cmp     nend                    ; for only when one does
        bne     @kept
        lda     #$FF
        sta     nend
        ldy     #0
        sty     t0
:       cpy     nact
        beq     :+++
        ldx     act,y
        lda     eyb,x
        cmp     gy
        beq     :++
        cmp     nend
        bcs     :+
        sta     nend
:       txa
        ldx     t0
        sta     act,x
        lda     xs,y
        sta     xs,x
        inc     t0
:       iny
        bne     :---                    ; (always)
:       lda     t0
        sta     nact
@kept:  lda     nact
        bne     @work
        lda     nxt
        cmp     ne
        jeq     @done
        jmp     @inc
@work:  lda     gy
        cmp     cbot
        beq     :+
        jcs     @done
:       cmp     ct
        jcc     @step
        lda     nact
        cmp     #2
        jeq     @two
        jsr     xsort
@isd:   lda     counting                ; accelerated, the shape inside:
        lsr                             ; the spans below
        bcs     @isg
        lda     ftj+1
        cmp     #<sxnc
        bne     @isg
        jsr     fstopc                  ; rows up to the next edge event
@mrow:  ldy     gy
        lda     rowlo,y
        sta     rowp
        lda     rowhi,y
        ora     pagehi
        sta     rowp+1
        tya
        lsr
        lda     #<fspane
        ldx     #>fspane
        bcc     :+
        lda     #<fspano
        ldx     #>fspano
:       sta     fsj+1
        stx     fsj+2
        ldy     #1
@pf:    cpy     nact
        bcs     @mstep
        sty     t3
        ldx     xs-1,y
        lda     xs,y
        tay
        jsr     fsj
        ldy     t3
        iny
        iny
        bne     @pf                     ; (always)
@mstep: ldy     nact                    ; (not counting) the next row
        dey
:       ldx     act,y
        clc
        lda     eal,x
        adc     esl,x
        sta     eal,x
        lda     exc,x
        adc     esh,x
        sta     exc,x
        eor     esg,x
        sta     xs,y
        dey
        bpl     :-
        inc     gy
        lda     gy
        cmp     fstop
        beq     :+
        jsr     xsort
        jmp     @mrow
:       jmp     @row
@isg:   ldy     gy                      ; pairs
        jsr     srow
        ldy     #1
@pr:    cpy     nact
        bcs     @step
        sty     t3
        ldx     xs-1,y
        lda     xs,y
        tay
        jsr     ftjmp
        ldy     t3
        iny
        iny
        bne     @pr                     ; (always)
@step:  lda     fv_count                ; next row: sums and crossings
        beq     :++
        inc     fv_counts+O_FROWS
        bne     :+
        inc     fv_counts+O_FROWS+1
:       lda     nact
        ldx     #O_ASTEP
        jsr     cadd
:       ldy     nact
        dey
:       ldx     act,y
        clc
        lda     eal,x
        adc     esl,x
        sta     eal,x
        lda     exc,x
        adc     esh,x
        sta     exc,x
        eor     esg,x
        sta     xs,y
        dey
        bpl     :-
@inc:   inc     gy
        jmp     @row
@done:  rts

; Two active edges (every convex shape): row after row with the two edges
; in the zero page, up to the next row where an edge ends or starts, or the
; window's bottom.
@two:   jsr     fstopc
        lda     gy
        sta     frow
        ldx     act
        lda     eal,x
        sta     fla
        lda     exc,x
        sta     xca
        lda     esl,x
        sta     sla
        lda     esh,x
        sta     sha
        lda     esg,x
        sta     sga
        ldx     act+1
        lda     eal,x
        sta     flb
        lda     exc,x
        sta     xcb
        lda     esl,x
        sta     slb
        lda     esh,x
        sta     shb
        lda     esg,x
        sta     sgb
        lda     counting                ; accelerated, the shape inside the
        lsr                             ; window: the rows below
        bcs     @tr
        lda     ftj+1
        cmp     #<sxnc
        bne     @tr
        lda     ftj+2
        cmp     #>sxnc
        bne     @tr
        jsr     tfast
        jmp     @tback
@tr:    ldy     gy
        jsr     srow
        lda     xca
        eor     sga
        sta     t3
        lda     xcb
        eor     sgb
        cmp     t3
        bcs     :+
        tax                             ; b left of a
        ldy     t3
        jmp     :++
:       tay
        ldx     t3
:       jsr     ftjmp                   ; sx, or sxnc when the shape is inside
        clc
        lda     fla
        adc     sla
        sta     fla
        lda     xca
        adc     sha
        sta     xca
        clc
        lda     flb
        adc     slb
        sta     flb
        lda     xcb
        adc     shb
        sta     xcb
        inc     gy
        lda     gy
        cmp     fstop
        bne     @tr
@tback: ldx     act                     ; back into the edge list
        lda     fla
        sta     eal,x
        lda     xca
        sta     exc,x
        eor     esg,x
        sta     xs
        ldx     act+1
        lda     flb
        sta     eal,x
        lda     xcb
        sta     exc,x
        eor     esg,x
        sta     xs+1
        lda     fv_count
        beq     :+
        lda     gy                      ; rows and edge steps, counted
        sec
        sbc     frow
        pha
        ldx     #O_FROWS
        jsr     cadd
        pla
        asl
        php
        ldx     #O_ASTEP
        jsr     cadd
        plp
        bcc     :+
        inc     fv_counts+O_ASTEP+1
        bne     :+
        inc     fv_counts+O_ASTEP+2
:       jmp     @row

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
        eor     pato,x
        sta     pdo
        lda     pato,x
        sta     co1
        lda     ce0
        eor     ce1
        sta     pde
        rts


; Sets up row Y (0-191, inside the window) of pagehi: rowp, and the row's
; patterns p0 (even columns) and p1 (odd columns).
srow:   sty     crow
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
        sta     p1
        rts
:       lda     co0
        sta     p0
        lda     co1
        sta     p1
        rts

; Fills movie x X..Y on the row set by srow, within cl..cr; counts the
; span and its bytes in osp, oby when counting.
sx:     cpx     cl
        bcs     :+
        ldx     cl
:       cpy     cr
        bcc     :+
        ldy     cr
:       sty     t2
        cpx     t2
        beq     sxnc
        bcs     sx_out
; The same without the clipping: X <= Y, both inside the window.
sxnc:   lda     rmx,y
        sta     mr
        lda     colof,y
        sta     ccb
        lda     lmx,x
        sta     ml
        lda     colof,x
        sta     scol
; The same from the byte columns scol..ccb and their masks ml, mr.
wbody:  ldy     scol
        cpy     ccb
        bne     sx_multi
        lda     ml
        and     mr
        sta     msk
        PUT
        ldx     counting                ; 0, 1 count, $80 extents, $81 both
        jne     sx_one
sx_out:   rts
sx_multi: lda    ml
        sta     msk
        PUT
        iny
        cpy     ccb
        beq     sx_right
        lda     p0                      ; full bytes: ccb - y of them,
        eor     p1                      ; the two patterns alternating
        sta     pd
        sty     t2
        lda     ccb
        sec
        sbc     t2
        tax
        cpx     #3
        bcs     sx_chain
        tya
        lsr
        lda     p0
        bcc     :+
        lda     p1
:       sta     (rowp),y
        eor     pd
        iny
        dex
        bne     :-
        beq     sx_right                  ; (always)
sx_chain: lda     pd                      ; unrolled: one colour or two
        beq     sx_plain
        lda     chlo,x
        sta     jv
        lda     chhi,x
        sta     jv+1
        tya
        lsr
        lda     p0
        bcc     :+
        lda     p1
:       jsr     sxjump
        jmp     sx_right
sx_plain: lda     cplo,x
        sta     jv
        lda     cphi,x
        sta     jv+1
        lda     p0
        jsr     sxjump
sx_right: lda     mr
        sta     msk
        PUT
        ldx     counting
        jeq     sx_out
        cpx     #$80
        beq     sx_track
        lda     ccb                     ; bytes beyond the first: ccb - scol
        sec                             ; (build adds one a span)
        sbc     scol
        clc
        adc     oby
        sta     oby
        bcc     sx_inc
        inc     oby+1
        bcs     sx_inc                    ; (always)
sx_one:   cpx     #$80
        beq     sx_track
sx_inc:   inc     osp
        bne     :+
        inc     osp+1
:       txa
        bpl     sxret
sx_track:
        ldy     crow                    ; the row's extent (the addresses
        lda     scol                    ; of the page's arrays are written
tmin1:  cmp     emin1,y                 ; in by build)
        bcs     :+
tmin2:  sta     emin1,y
:       lda     ccb
tmax1:  cmp     emax1,y
        bcc     sxret
tmax2:  sta     emax1,y
sxret:   rts
sxjump:  jmp     (jv)

; Full bytes from Y on, A the pattern: entered n copies before the end.
chainc:
        .repeat 36
        sta     (rowp),y
        eor     pd
        iny
        .endrep
chaince:
        rts
chainp:
        .repeat 36
        sta     (rowp),y
        iny
        .endrep
chainpe:
        rts

; -- timing ---------------------------------------------------------------------------
; fv_orig = ORIG_BASE + the terms of origt, fv_own = OWN_BASE + the terms
; of ownt, fv_wait = max(0, fv_orig - fv_own).
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
        lda     #<OWN_BASE
        ldx     #>OWN_BASE
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
@bit:   lda     mulk
        ora     mulk+1
        beq     @nextt                  ; no bits left
        lsr     mulk+1
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
        jmp     @bit
@nextt: iny
        iny
        iny
        bne     @term                   ; (always)
@done:  rts
