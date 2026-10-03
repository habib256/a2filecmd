; engine.s -- the Take 1 movie engine of TAKE1.SYSTEM: checks, backgrounds,
; snapshots, text, frames and fades (docs/TAKE1-FORMAT.md; tools/take1_ref.py
; is its reference model and states the rules the spec leaves open).
;
; Plain 6502 throughout. The engine reads the files it has loaded and
; writes only its own variables (ZEROPAGE, BSS) and three fixed 8 KB
; buffers: hi-res page 1 ($2000), page 2 ($4000) and page 3 ($6000, the
; scene's background and its planted objects). At each scene the movie,
; then the background, then the scene, its actors and character set are
; read to SCENE_AT (SCENE_MAX bytes) by the caller's t1_mload and t1_load;
; the movie's entry and the background are used before the scene is read
; over them. It never calls ProDOS or the ROM itself:
; TAKE1.SYSTEM (take1.s, dos.s) reads the files, flips the pages, waits and
; reads the keys through the hooks below; tools/test_take1.py links this same
; file with a C harness under sim65.
;
; Interface (variables in BSS; the routines preserve nothing):
;   t1_play    plays the movie once: C = 0 at its end; C = 1 refused, A =
;              t1_err = E_NOTFOUND / E_READ / E_BIG / E_BAD, t1_name = the
;              DOS name of the file (length first)
;   t1_front   the page shown, $20 or $40 (set it to $20 before the
;              movie is loaded: t1_load's caller may use the other page)
; Interrupts are not used. A C = 1 refusal can come from any depth: the
; stack is reset to t1_play's entry.
; Hooks (the caller's; any registers):
;   t1_mload   reads the movie (the MV. file's data) to t1_dest, t1_max
;              bytes at most, and sets t1_name to its name: C = 0, t1_len =
;              its length; C = 1, A = the E_ code. Called at the start of
;              every scene: the movie is read into the scene buffer, its
;              entry kept, then the scene's files are read over it.
;   t1_load    reads the file named t1_name to t1_dest, t1_max bytes at
;              most: C = 0, t1_len = its length; C = 1, A = the E_ code.
;              It is only called between scenes, when the page that is
;              not shown (t1_front ^ $60) is free: TAKE1.SYSTEM keeps its
;              I/O buffers there
;   t1_show    A = the page just made the front page ($20 / $40): show it
;   t1_wait    A/X = n, the frame wait in steps of 350 cycles
;   t1_fc      A = the $FC kind (g & $7F), X = t
;   t1_delay   A = a: D(a) of a fade (0 counts as 256)
;   t1_tick    fade 14's step (no delay in the original)
;
; Speed: a snapshot row is drawn a screen byte at a time (a whole byte of a
; run in one store, partial bytes gathered in an accumulator), erasing
; copies rows of rectangles, the fades copy rows or bytes as their
; procedures say. The cost and the frame wait are computed exactly as the
; original's (the caller waits), and the same erasing and drawing is done.

        .macpack longbranch
        .export t1_play, t1_name, t1_err, t1_front
        .export t1_dest, t1_max, t1_len
        .export MOVIE_MAX, SCENE_MAX
        .import t1_load, t1_mload, t1_show, t1_wait, t1_fc, t1_delay, t1_tick

PAGE1   = $20
PAGE3   = $60
.ifdef SCENE_ADDR
SCENE_AT = SCENE_ADDR
.else
SCENE_AT = $8000
.endif
SCENE_MAX = $3000               ; scene + actors + character set
MOVIE_MAX = SCENE_MAX           ; the movie (1 + 42 n bytes: 10,711 at most)
BK_MAX  = $2000
FULLCOST = 3430
P3OR    = $03                   ; the palette register before any run

E_NOTFOUND = 1
E_READ  = 2
E_BIG   = 3
E_BAD   = 4

        .zeropage
ep:     .res 2          ; the scene element
mp:     .res 2          ; the movie entry
dp:     .res 2          ; snapshot codes / data checked
rowp:   .res 2          ; the row drawn, minus 48 (indexed by col48)
tp:     .res 2          ; temporary pointer
sp1:    .res 2          ; copies: source row
dp1:    .res 2          ;         destination row
endp:   .res 2          ; the end of the data checked
col48:  .res 1          ; cursor: screen column + 48 (48-87 on the screen)
cbit:   .res 1          ;         its dot in the byte, 0-6
amask:  .res 1          ; accumulator: the dots put in the cursor's byte
adata:  .res 1          ;              their values
regor:  .res 1          ; palette register: $00, $80, or P3OR
first:  .res 1          ; nonzero: no skip, fill or literal yet in the row
ext:    .res 1          ; extensions pending (groups of 7)
mq:     .res 1          ; a count: groups of 7 ...
mr:     .res 1          ; ... and dots, 0-6
bval:   .res 1          ; the run's byte
jj:     .res 1          ; the run's dot index (3-6 stands for any j >= 3)
nlo:    .res 1          ; N | N << 4 (N = bits 3-6 of the run's byte)
nhi:    .res 1
dq:     .res 1          ; the row's distance: groups, saturated at 255
dr:     .res 1          ;                     dots, 0-6
lp:     .res 2          ; a literal's bytes
strp:   .res 2          ; text: the string, the shape
shp:    .res 2
t0:     .res 1
t1:     .res 1
t2:     .res 1
t3:     .res 1

        .bss
t1_mlen:  .res 2        ; the movie's length
ent:      .res 42       ; the entry played
t1_name:  .res 24       ; length, then the DOS name (23 characters)
t1_err:   .res 1
t1_front: .res 1
t1_dest:  .res 2
t1_max:   .res 2
t1_len:   .res 2
savesp: .res 1
rowsp:  .res 1          ; the stack in a row (off the right: rest skipped)
nsc:    .res 1          ; scenes in the movie
kidx:   .res 1          ; the entry played
fin:    .res 1          ; its fades
fout:   .res 1
back:   .res 1          ; the back page, $20 / $40
pagehi: .res 1          ; the page drawn into
snl:    .res 2          ; the scene's length
room:   .res 2          ; memory left for its files
freep:  .res 2          ; where the next one goes
nact:   .res 1          ; actors
aidx:   .res 1
abase_l: .res 10        ; actor j: address, length, count, snapshots
abase_h: .res 10
alen_l: .res 10
alen_h: .res 10
acnt:   .res 10
anum:   .res 10         ; its own count n
nsnap:  .res 1          ; the snapshots of the scene (sum of the counts)
csb:    .res 2          ; character set: address, length, shapes
csl:    .res 2
csn:    .res 1
usecs:  .res 1
nstr:   .res 1          ; strings
bodyl:  .res 2          ; the body's length
speed:  .res 1
cost:   .res 2
shown:  .res 1          ; a frame was shown in this scene
fnum:   .res 1          ; the frame's index: 0 first, 1 after
fend:   .res 1          ; the frame ended in the plant prefix
fcg:    .res 1          ; $FC: g + 1 (0 none), t
fct:    .res 1
lcount: .res 2          ; rectangle lists, per page (0: $20, 1: $40)
lareal: .res 2
lareah: .res 2
lfull:  .res 2
rcol:   .res 40         ; list L, entry i at 20 L + i
rwid:   .res 40
rtop:   .res 40
rhgt:   .res 40
okr:    .res 1          ; the object drawn has a rectangle
ocol:   .res 1          ; its rectangle
owid:   .res 1
otop:   .res 1
ohgt:   .res 1
ox:     .res 2          ; x16, y16
oy:     .res 2
oxl:    .res 1          ; the element
of:     .res 1
oyl:    .res 1
oo:     .res 1
wrap:   .res 1
wrapx:  .res 1          ; wrap with X >= 0: the 280-dot return counts
sh:     .res 1          ; snapshot: height, width, byte 4, syncs
sw:     .res 1
sb4:    .res 1
ssx:    .res 1
ssy:    .res 1
sskip:  .res 1
sskc:   .res 1
stop:   .res 1
scol48: .res 1          ; the start of every row
sbit:   .res 1
srows:  .res 1
sy:     .res 1
wb:     .res 1
mprod:  .res 2          ; multiplication
pen:    .res 1          ; text: pen column, dot, row
pbit:   .res 1
py:     .res 1
lcol:   .res 1          ;       leftmost, rightmost positions
lbit:   .res 1
rcl:    .res 1
rbit:   .res 1
ttop:   .res 1
tbot:   .res 1
twid:   .res 1
thgt:   .res 1
tbytes: .res 2
slen:   .res 1
sidx:   .res 1
fsrc:   .res 1          ; fades: source and destination pages
fdst:   .res 1
fx:     .res 1
fy:     .res 1
fup:    .res 1
fdn:    .res 1
fstep:  .res 1
fdel:   .res 1
f5:     .res 1
f6:     .res 1
f7:     .res 1
f8:     .res 1
f9:     .res 1
fa:     .res 1
fcnt:   .res 1
fk:     .res 1
fs0:    .res 1

        .code
; -- the movie ------------------------------------------------------------------
t1_play:
        tsx
        stx     savesp
        jsr     mload
        lda     t1_len
        sta     t1_mlen
        lda     t1_len+1
        sta     t1_mlen+1
        jsr     chkmovie
        lda     #PAGE1
        jsr     clrpage
        lda     #$40
        jsr     clrpage
        lda     #PAGE3
        jsr     clrpage
        lda     #PAGE1
        sta     t1_front
        lda     #0
        sta     kidx
@entry: lda     kidx                    ; the movie again (the scene buffer
        beq     :+                      ; held the last scene): its length
        jsr     mload                   ; unchanged
        lda     t1_len
        cmp     t1_mlen
        bne     @read
        lda     t1_len+1
        cmp     t1_mlen+1
        bne     @read
:       jsr     entryp                  ; the entry, kept
        ldy     #41
:       lda     (mp),y
        sta     ent,y
        dey
        bpl     :-
        lda     #<ent
        sta     mp
        lda     #>ent
        sta     mp+1
        lda     ent+40
        sta     fin
        lda     ent+41
        sta     fout
        jsr     background
        jsr     loadscene
        jsr     playscene
        inc     kidx
        lda     kidx
        cmp     nsc
        bne     @entry
        clc
        rts
@read:  lda     #E_READ
        jmp     refuse

; The movie to the scene buffer (t1_name: its name).
mload:  lda     #<SCENE_AT
        sta     t1_dest
        lda     #>SCENE_AT
        sta     t1_dest+1
        lda     #<MOVIE_MAX
        sta     t1_max
        lda     #>MOVIE_MAX
        sta     t1_max+1
        jsr     t1_mload
        bcc     :+
        jmp     refuse
:       rts

; Refuses: A = the code; back to t1_play's caller, C = 1.
bad:    lda     #E_BAD
refuse: sta     t1_err
        ldx     savesp
        txs
        sec
        rts

; mp = the entry kidx in the movie: SCENE_AT + 1 + 42 kidx.
entryp: lda     #<(SCENE_AT + 1)
        sta     mp
        lda     #>(SCENE_AT + 1)
        sta     mp+1
        ldx     kidx
        beq     @done
:       lda     mp
        clc
        adc     #42
        sta     mp
        bcc     :+
        inc     mp+1
:       dex
        bne     :--
@done:  rts

; The movie: 1 + 42 n bytes, n >= 1, fades 1-17.
chkmovie:
        lda     t1_mlen+1
        cmp     #>(MOVIE_MAX + 1)
        bcc     :+
        bne     @big
        lda     t1_mlen
        cmp     #<(MOVIE_MAX + 1)
        bcc     :+
@big:   lda     #E_BIG
        jmp     refuse
:       lda     t1_mlen
        ora     t1_mlen+1
        beq     bad
        lda     SCENE_AT
        beq     bad
        sta     nsc
        lda     #1                      ; 1 + 42 n
        sta     t0
        lda     #0
        sta     t1
        ldx     nsc
:       lda     t0
        clc
        adc     #42
        sta     t0
        bcc     :+
        inc     t1
:       dex
        bne     :--
        lda     t0
        cmp     t1_mlen
        bne     bad
        lda     t1
        cmp     t1_mlen+1
        jne     bad
        lda     #0
        sta     kidx
@f:     jsr     entryp
        ldy     #40
        jsr     @fade
        iny
        jsr     @fade
        inc     kidx
        lda     kidx
        cmp     nsc
        bne     @f
        rts
@fade:  lda     (mp),y
        beq     :+
        cmp     #18
        bcs     :+
        rts
:       jmp     bad

; t1_name = the prefix at A/X (3 characters) + the name field at (tp), low 7
; bits, trailing spaces removed.
setname:
        sta     t2
        stx     t3
        ldy     #2
:       lda     (t2),y
        sta     t1_name+1,y
        dey
        bpl     :-
        jsr     fieldlen
        tax
        clc
        adc     #3
        sta     t1_name
        txa
        beq     @done
        tay
:       dey
        lda     (tp),y
        and     #$7F
        sta     t1_name+4,y
        tya
        bne     :-
@done:  rts

; A = the length of the field at (tp) without its trailing spaces.
fieldlen:
        ldy     #20
:       dey
        bmi     :+
        lda     (tp),y
        and     #$7F
        cmp     #' '
        beq     :-
:       iny
        tya
        rts

; Z = 1 if the field at (tp) is the string at A/X (length first).
fieldis:
        sta     t2
        stx     t3
        jsr     fieldlen
        ldy     #0
        cmp     (t2),y
        bne     @no
        tax
        beq     @no                     ; (never: the specials are not empty)
:       lda     (tp),y
        and     #$7F
        iny
        cmp     (t2),y
        bne     @no
        dex
        bne     :-
        rts                             ; Z = 1
@no:    lda     #1                      ; Z = 0
        rts

; -- the background ---------------------------------------------------------------
background:
        lda     mp
        clc
        adc     #20
        sta     tp
        lda     mp+1
        adc     #0
        sta     tp+1
        lda     #<sblack
        ldx     #>sblack
        jsr     fieldis
        bne     :+
        lda     #PAGE3
        jmp     clrpage
:       lda     #<sunch
        ldx     #>sunch
        jsr     fieldis
        bne     :+
        rts
:       lda     #<pbk
        ldx     #>pbk
        jsr     setname
        lda     #<SCENE_AT              ; (free until the scene is loaded)
        sta     t1_dest
        lda     #>SCENE_AT
        sta     t1_dest+1
        lda     #<BK_MAX
        sta     t1_max
        lda     #>BK_MAX
        sta     t1_max+1
        jsr     load
        ; decode: from the scene buffer, t1_len bytes, into page 3
        lda     #<SCENE_AT
        sta     dp
        lda     #>SCENE_AT
        sta     dp+1
        lda     t1_len
        clc
        adc     dp
        sta     endp
        lda     t1_len+1
        adc     dp+1
        sta     endp+1
        jsr     getb
        cmp     #$FF
        jne     bad
        lda     #39
        sta     t3                      ; the column
@col:   lda     #0
        sta     sy                      ; the row
@code:  lda     sy
        cmp     #192
        beq     @next
        jsr     getb
        cmp     #$80
        bcs     @pat
        tax
        bne     :+
        jsr     getb                    ; $00: a count follows, 1-255
        tax
        jeq     bad
:       stx     t0
        txa                             ; row + m <= 192
        clc
        adc     sy
        jcs     bad
        cmp     #193
        jcs     bad
:       jsr     getb
        jsr     bkput
        dec     t0
        bne     :-
        beq     @code                   ; (always)
@pat:   tax
        and     #3
        tay
        lda     pow2,y
        sta     t2                      ; p
        txa
        and     #$7C
        lsr
        lsr
        sta     t0                      ; q, 0: the next byte (0: 256)
        bne     :+
        jsr     getb
        sta     t0
:       lda     dp                      ; the pattern, p bytes
        sta     tp
        lda     dp+1
        sta     tp+1
        ldx     t2
:       jsr     getb
        dex
        bne     :-
        lda     t0                      ; row + q <= 192 (q 0 = 256: never)
        beq     @badj
        clc
        adc     sy
        bcs     @badj
        cmp     #193
        bcs     @badj
        ldx     t2
        dex
        stx     t1                      ; p - 1
        ldx     #0
:       txa                             ; pattern byte i & (p - 1)
        and     t1
        tay
        lda     (tp),y
        jsr     bkput
        inx
        cpx     t0
        bne     :-
        jmp     @code
@next:  dec     t3
        jpl     @col
        rts
@badj:  jmp     bad

; Stores A in page 3 at row sy, column t3; sy + 1. X kept.
bkput:  pha
        ldy     sy
        lda     rowlo,y
        sta     dp1
        lda     rowhi,y
        ora     #PAGE3
        sta     dp1+1
        ldy     t3
        pla
        sta     (dp1),y
        inc     sy
        rts

; A = the next byte at dp, dp + 1; refused at endp.
getb:   lda     dp
        cmp     endp
        lda     dp+1
        sbc     endp+1
        bcs     @bad
        ldy     #0
        lda     (dp),y
        inc     dp
        bne     :+
        inc     dp+1
:       ora     #0                      ; (N, Z of the byte)
        rts
@bad:   jmp     bad

; t1_load, refused on an error.
load:   jsr     t1_load
        bcc     :+
        jmp     refuse
:       rts

; -- the scene, its actors and character set --------------------------------------
loadscene:
        lda     mp
        sta     tp
        lda     mp+1
        sta     tp+1
        lda     #<psn
        ldx     #>psn
        jsr     setname
        lda     #<SCENE_AT
        sta     t1_dest
        sta     freep
        lda     #>SCENE_AT
        sta     t1_dest+1
        sta     freep+1
        lda     #<SCENE_MAX
        sta     t1_max
        sta     room
        lda     #>SCENE_MAX
        sta     t1_max+1
        sta     room+1
        jsr     loadin
        lda     t1_len
        sta     snl
        lda     t1_len+1
        sta     snl+1
        bne     :+                      ; $103 bytes at least
        jmp     bad
:       cmp     #1
        bne     :+
        lda     snl
        cmp     #3
        bcs     :+
        jmp     bad
:       lda     SCENE_AT+2
        sta     speed
        lda     SCENE_AT+3
        sta     usecs
        lda     SCENE_AT+$18
        cmp     #11
        bcc     :+
        jmp     bad
:       sta     nact
        ldx     #0
@act:   cpx     nact
        beq     @cs
        stx     aidx
        jsr     actname
        lda     freep
        sta     abase_l,x
        lda     freep+1
        sta     abase_h,x
        jsr     roomin
        ldx     aidx
        lda     t1_len
        sta     alen_l,x
        lda     t1_len+1
        sta     alen_h,x
        inx
        bne     @act
@cs:    lda     usecs
        beq     @check
        jsr     csname
        lda     freep
        sta     csb
        lda     freep+1
        sta     csb+1
        jsr     roomin
        lda     t1_len
        sta     csl
        lda     t1_len+1
        sta     csl+1
@check: lda     #0                      ; the actors
        sta     nsnap
        ldx     #0
@chk:   cpx     nact
        beq     @chcs
        stx     aidx
        jsr     actname
        jsr     chkactor
        ldx     aidx
        lda     nsnap
        clc
        adc     acnt,x
        bcc     :+
        lda     #255                    ; (above any snapshot number)
:       sta     nsnap
        inx
        bne     @chk
@chcs:  lda     usecs
        beq     :+
        jsr     csname
        jsr     chkcs
:       lda     mp                      ; the body
        sta     tp
        lda     mp+1
        sta     tp+1
        lda     #<psn
        ldx     #>psn
        jsr     setname
        jmp     chkbody

; Loads the next file at freep, within room; freep, room move on.
roomin: lda     freep
        sta     t1_dest
        lda     freep+1
        sta     t1_dest+1
        lda     room
        sta     t1_max
        lda     room+1
        sta     t1_max+1
loadin: jsr     load
        lda     freep
        clc
        adc     t1_len
        sta     freep
        lda     freep+1
        adc     t1_len+1
        sta     freep+1
        lda     room
        sec
        sbc     t1_len
        sta     room
        lda     room+1
        sbc     t1_len+1
        sta     room+1
        rts

; t1_name = AC. + actor X's name (X kept); acnt,x = its count.
actname:
        txa
        pha
        asl                             ; $19 + 22 j
        sta     t1
        asl
        asl
        asl
        clc
        adc     t1
        sta     t1                      ; 18 j
        txa
        asl
        asl                             ; 4 j
        clc
        adc     t1
        adc     #$19
        tay
        iny
        lda     SCENE_AT,y              ; count
        sta     acnt,x
        iny
        tya
        clc
        adc     #<SCENE_AT
        sta     tp
        lda     #>SCENE_AT
        adc     #0
        sta     tp+1
        lda     #<pac
        ldx     #>pac
        jsr     setname
        pla
        tax
        rts

csname: lda     #<(SCENE_AT + 4)
        sta     tp
        lda     #>(SCENE_AT + 4)
        sta     tp+1
        lda     #<pcs
        ldx     #>pcs
        jmp     setname

; Actor X: at least 1 byte; snapshots 1 to min(count, n) parse within it.
chkactor:
        lda     abase_l,x
        sta     tp
        clc
        adc     alen_l,x
        sta     endp
        lda     abase_h,x
        sta     tp+1
        adc     alen_h,x
        sta     endp+1
        lda     alen_l,x
        ora     alen_h,x
        bne     :+
        jmp     bad
:       ldy     #0
        lda     (tp),y
        sta     anum,x
        cmp     acnt,x
        bcc     :+
        lda     acnt,x
:       sta     t1                      ; min(count, n)
        lda     #1
        sta     t2                      ; i
@snap:  lda     t1
        cmp     t2
        bcs     :+
        rts
:       lda     t2                      ; 2 i < length
        asl
        sta     dp
        lda     #0
        rol
        sta     dp+1
        lda     dp
        clc
        adc     tp
        sta     dp
        lda     dp+1
        adc     tp+1
        sta     dp+1
        lda     dp
        cmp     endp
        lda     dp+1
        sbc     endp+1
        bcc     :+
        jmp     bad
:       ldy     #0                      ; the offset: bytes 2i-1, 2i
        lda     (dp),y
        sta     t3
        lda     dp
        bne     :+
        dec     dp+1
:       dec     dp
        lda     (dp),y
        clc
        adc     tp
        sta     dp
        lda     t3
        adc     tp+1
        sta     dp+1
        bcc     :+
        jmp     bad
:       jsr     getb                    ; the header (7 bytes)
        sta     t0
        ldx     #6
:       jsr     getb
        dex
        bne     :-
@row:   lda     t0
        beq     @nexts
        jsr     chkrow
        dec     t0
        jmp     @row
@nexts: inc     t2
        bne     @snap
        rts

; One row at dp, checked against endp.
chkrow: lda     #0
        sta     ext
@code:  jsr     getb
        tax
        beq     @end
        cmp     #7
        beq     @end
        and     #7
        cmp     #7
        bne     @run
        txa
        lsr
        lsr
        lsr
        cmp     #26
        bcs     @lit
        clc
        adc     ext
        bcc     :+
        lda     #255
:       sta     ext
        jmp     @code
@lit:   sbc     #25                     ; (carry set)
        tax
:       jsr     getb
        dex
        bne     :-
        beq     @code                   ; (always)
@run:   txa
        lsr
        lsr
        lsr
        and     #15
        clc
        adc     ext
        bcs     @bad
        cmp     #128
        bcs     @bad
        lda     #0
        sta     ext
        txa
        bmi     @code                   ; a skip
        jsr     getb                    ; a fill: its byte
        jmp     @code
@end:   rts
@bad:   jmp     bad

; The character set: N >= 1, every shape's offset and bytes within it.
chkcs:  lda     csb
        sta     tp
        clc
        adc     csl
        sta     endp
        lda     csb+1
        sta     tp+1
        adc     csl+1
        sta     endp+1
        lda     csl
        ora     csl+1
        beq     @bad
        ldy     #0
        lda     (tp),y
        beq     @bad
        sta     csn
        lda     #1
        sta     t2
@shape: jsr     shapeptr                ; dp = the offset's address
        lda     dp                      ; 2 i + 1 < length
        clc
        adc     #1
        sta     t0
        lda     dp+1
        adc     #0
        sta     t1
        lda     t0
        cmp     endp
        lda     t1
        sbc     endp+1
        bcs     @bad
        ldy     #0
        lda     (dp),y
        clc
        adc     tp
        tax
        iny
        lda     (dp),y
        adc     tp+1
        sta     dp+1
        stx     dp
        bcs     @bad
:       jsr     getb                    ; up to its 0
        cmp     #0
        bne     :-
        lda     t2
        cmp     csn
        beq     @done
        inc     t2
        bne     @shape
@done:  rts
@bad:   jmp     bad

; dp = tp + 2 * t2.
shapeptr:
        lda     t2
        asl
        sta     dp
        lda     #0
        rol
        sta     dp+1
        lda     dp
        clc
        adc     tp
        sta     dp
        lda     dp+1
        adc     tp+1
        sta     dp+1
        rts

; The body: frames inside, strings and elements within the scene, an end
; marker, objects that can be drawn.
chkbody:
        lda     snl
        sec
        sbc     #0
        sta     bodyl
        lda     snl+1
        sbc     #1
        sta     bodyl+1
        lda     #<(SCENE_AT + $100)
        sta     dp
        lda     #>(SCENE_AT + $100)
        sta     dp+1
        lda     #<SCENE_AT
        clc
        adc     snl
        sta     endp
        lda     #>SCENE_AT
        adc     snl+1
        sta     endp+1
        lda     SCENE_AT+$100           ; the first frame: inside
        cmp     bodyl
        lda     SCENE_AT+$101
        sbc     bodyl+1
        jcs     @bad
        lda     SCENE_AT+$102
        sta     nstr
        lda     #<(SCENE_AT + $103)
        sta     dp
        lda     #>(SCENE_AT + $103)
        sta     dp+1
        ldx     nstr
        beq     @elems
@str:   jsr     getb                    ; its length
        beq     @nexts
        tay                             ; length bytes within: dp + len <= end
        clc
        adc     dp
        sta     t0
        lda     dp+1
        adc     #0
        sta     t1
        lda     endp
        cmp     t0
        lda     endp+1
        sbc     t1
        bcc     @bad
        lda     t0
        sta     dp
        lda     t1
        sta     dp+1
@nexts: dex
        bne     @str
@elems: jsr     firstel
        lda     ep
        sta     dp
        lda     ep+1
        sta     dp+1
@el:    jsr     getb
        cmp     #$FF
        beq     @ok
        cmp     #0
        beq     @bad
        cmp     #$FC
        beq     @four
        cmp     #$FE
        beq     @four
        cmp     #$F0
        bcs     @el                     ; one byte, ignored
        sta     oo                      ; an object
        jsr     getb
        sta     oxl
        jsr     getb
        sta     of
        jsr     getb
        sta     oyl
        jsr     chkobj
        jmp     @el
@four:  jsr     getb
        jsr     getb
        jsr     getb
        jmp     @el
@ok:    rts
@bad:   jmp     bad

; ep = the scene's first frame.
firstel:
        lda     SCENE_AT+$100
        clc
        adc     #<(SCENE_AT + $100)
        sta     ep
        lda     SCENE_AT+$101
        adc     #>(SCENE_AT + $100)
        sta     ep+1
        rts

; The object oo, oxl, of, oyl: a string or a snapshot that exists.
chkobj: lda     of
        and     #$40
        beq     @snap
        lda     usecs                   ; text: a character set, string 1-s,
        beq     @bad                    ; wrap, 280 <= x16 < 560,
        lda     nstr                    ; 192 < y16 < 384
        cmp     oo
        bcc     @bad
        lda     of
        and     #$10
        beq     @bad
        jsr     coords
        lda     ox                      ; x16 - 280 < 280
        sec
        sbc     #<280
        tax
        lda     ox+1
        sbc     #>280
        bcc     @bad
        tay
        txa
        cmp     #<280
        tya
        sbc     #>280
        bcs     @bad
        lda     oy                      ; y16 - 193 < 191
        sec
        sbc     #193
        tax
        lda     oy+1
        sbc     #0
        bcc     @bad
        bne     :+
        cpx     #191
        bcc     @ok
:       cmp     #0
        bne     @bad
        cpx     #191
        bcs     @bad
@ok:    rts
@bad:   jmp     bad
@snap:  lda     nsnap
        cmp     oo
        bcc     @bad
        jsr     findsnap                ; X = the actor, t1 = its snapshot
        lda     anum,x
        cmp     t1
        bcs     @ok
        jsr     actname                 ; refused in the actor's name
        jmp     bad

; ox, oy = x16, y16 of the element.
coords: lda     oxl
        sta     ox
        lda     of
        and     #3
        sta     ox+1
        lda     oyl
        sta     oy
        lda     of
        lsr
        lsr
        lsr
        and     #1
        sta     oy+1
        rts

; The snapshot oo: X = its actor, t1 = its number in the actor.
findsnap:
        lda     oo
        ldx     #0
:       cmp     acnt,x
        bcc     :+
        beq     :+
        sec
        sbc     acnt,x
        inx
        bne     :-
:       sta     t1
        rts

; -- one scene ---------------------------------------------------------------------
playscene:
        lda     t1_front
        eor     #$60
        sta     back
        sta     t1                      ; page 3 onto the back page
        lda     #PAGE3
        sta     t0
        jsr     cpypage
        lda     #0
        sta     lcount
        sta     lcount+1
        sta     lareal
        sta     lareal+1
        sta     lareah
        sta     lareah+1
        sta     lfull
        sta     lfull+1
        sta     cost
        sta     cost+1
        sta     shown
        sta     fnum
        jsr     backl
        lda     #1
        sta     lfull,x
        jsr     firstel
@frame: ldy     #0
        lda     (ep),y
        cmp     #$FF
        jeq     @done
        lda     t1_front
        eor     #$60
        sta     back
        lda     #0
        sta     fend
        sta     fcg
@plant: ldy     #0                      ; 1. plant
        lda     (ep),y
        beq     @pdone
        cmp     #$F0
        bcs     @pdone
        ldy     #2
        lda     (ep),y
        and     #$20
        beq     @pdone
        lda     #PAGE3
        sta     pagehi
        jsr     drawobj
        lda     okr
        beq     :+
        ldx     #0
        jsr     addrect
        ldx     #1
        jsr     addrect
:       jsr     nextel4
        lda     of
        bpl     @plant
        inc     fend
@pdone: jsr     backl                   ; 2. erase
        jsr     apply
        lda     fend                    ; 3. draw
        bne     @show
@draw:  ldy     #0
        lda     (ep),y
        cmp     #$FF
        beq     @show                   ; (an unterminated last frame)
        cmp     #$FE
        beq     @empty
        cmp     #$FC
        beq     @fc
        cmp     #$F0
        bcc     @obj
        jsr     nextel1
        jmp     @draw
@empty: jsr     nextel4
        jmp     @show
@fc:    ldy     #1
        lda     (ep),y
        sta     fct
        iny
        lda     (ep),y
        sta     t0
        and     #$7F
        clc
        adc     #1
        sta     fcg
        jsr     nextel4
        lda     t0
        bmi     @show
        bpl     @draw                   ; (always)
@obj:   lda     back
        sta     pagehi
        jsr     drawobj
        lda     okr
        beq     :+
        jsr     backl
        jsr     addrect
:       jsr     nextel4
        lda     of
        bpl     @draw
@show:  lda     fnum                    ; 4. show
        bne     @flip
        lda     fin
        cmp     #2
        bcc     @flip
        lda     back                    ; the first frame, faded in
        sta     fsrc
        lda     t1_front
        sta     fdst
        lda     fin
        jsr     fade
        jsr     backl
        jsr     apply
        jmp     @fcs
@flip:  lda     back
        sta     t1_front
        eor     #$60
        sta     back
        lda     t1_front
        jsr     t1_show
        jsr     fwait
        jsr     t1_wait
        lda     #0
        sta     cost
        sta     cost+1
        jsr     backl                   ; 5. the new back page
        lda     shown
        bne     :+
        inc     shown
        lda     #1
        sta     lfull,x
:       jsr     apply
@fcs:   lda     fcg                     ; 6. $FC
        beq     :+
        sec
        sbc     #1
        ldx     fct
        jsr     t1_fc
:       lda     #1
        sta     fnum
        jmp     @frame
@done:  lda     fout                    ; fade-out: from a black back page
        cmp     #2
        bcc     @end
        lda     t1_front
        eor     #$60
        sta     fsrc
        jsr     clrpage
        lda     t1_front
        sta     fdst
        lda     fout
        jsr     fade
        lda     #PAGE3
        jmp     clrpage
@end:   rts

nextel4:
        lda     ep
        clc
        adc     #4
        sta     ep
        bcc     :+
        inc     ep+1
:       rts
nextel1:
        inc     ep
        bne     :+
        inc     ep+1
:       rts

; X = the back page's list (0: page $20, 1: $40).
backl:  ldx     #0
        lda     back
        cmp     #PAGE1
        beq     :+
        inx
:       rts

; Adds the rectangle ocol, owid, otop, ohgt to list X (X kept).
addrect:
        lda     lfull,x
        bne     @done
        lda     lcount,x
        cmp     #20
        bne     :+
        lda     #1
        sta     lfull,x
@done:  rts
:       clc                             ; entry 20 X + count
        adc     l20,x
        tay
        lda     ocol
        sta     rcol,y
        lda     owid
        sta     rwid,y
        lda     otop
        sta     rtop,y
        lda     ohgt
        sta     rhgt,y
        inc     lcount,x
        stx     t3
        lda     owid
        ldx     ohgt
        jsr     mul8
        ldx     t3
        lda     lareal,x
        clc
        adc     mprod
        sta     lareal,x
        lda     lareah,x
        adc     mprod+1
        sta     lareah,x
        cmp     #$0D
        bcc     :+
        lda     #1
        sta     lfull,x
:       rts

; Applies list X to the back page (from page 3): cost += its cost; empty.
apply:  lda     lfull,x
        beq     @rects
        stx     t3
        lda     #PAGE3
        sta     t0
        lda     back
        sta     t1
        jsr     cpypage
        ldx     t3
        lda     #<FULLCOST
        ldy     #>FULLCOST
        jsr     addcost
        jmp     @clear
@rects: lda     lareal,x
        ldy     lareah,x
        jsr     addcost
        lda     lcount,x
        beq     @clear
        sta     fcnt
        lda     l20,x
        sta     fk
@r:     ldy     fk
        lda     rhgt,y
        beq     @nextr
        sta     t2
        lda     rtop,y
        sta     sy
        lda     rcol,y
        sta     t0
        lda     rwid,y
        sta     t1
@row:   ldy     sy
        lda     rowlo,y
        sta     sp1
        sta     dp1
        lda     rowhi,y
        ora     #PAGE3
        sta     sp1+1
        eor     #PAGE3
        ora     back
        sta     dp1+1
        ldy     t0
        ldx     t1
:       lda     (sp1),y
        sta     (dp1),y
        iny
        cpy     #40
        bne     :+
        ldy     #0
:       dex
        bne     :--
        inc     sy
        lda     sy
        cmp     #192
        bne     :+
        lda     #0
        sta     sy
:       dec     t2
        bne     @row
@nextr: inc     fk
        dec     fcnt
        bne     @r
        jsr     backl
@clear: lda     #0
        sta     lcount,x
        sta     lareal,x
        sta     lareah,x
        sta     lfull,x
        rts

; cost += A/Y, saturated at 65,535 (X kept).
addcost:
        clc
        adc     cost
        sta     cost
        tya
        adc     cost+1
        sta     cost+1
        bcc     :+
        lda     #$FF
        sta     cost
        sta     cost+1
:       rts

; mprod = A * X (8 x 8 bits).
mul8:   sta     t0
        stx     t1
        lda     #0
        sta     mprod+1
        ldx     #8
:       asl
        rol     mprod+1
        asl     t1
        bcc     :+
        clc
        adc     t0
        bcc     :+
        inc     mprod+1
:       dex
        bne     :--
        sta     mprod
        rts

; A/X = the frame wait: ceil((256 speed - 4 cost) / 64) if positive and
; 4 cost < 65,536, else 0.
fwait:  lda     cost+1
        cmp     #$40
        bcs     @zero
        lda     cost                    ; t0/t1 = 4 cost
        asl
        sta     t0
        lda     cost+1
        rol
        sta     t1
        asl     t0
        rol     t1
        lda     #0                      ; 256 speed - 4 cost
        sec
        sbc     t0
        sta     t0
        lda     speed
        sbc     t1
        sta     t1
        bcc     @zero
        ora     t0
        beq     @zero
        lda     t0                      ; + 63, / 64
        clc
        adc     #63
        sta     t0
        lda     t1
        adc     #0
        ldx     #6
:       lsr
        ror     t0
        dex
        bne     :-
        tax
        lda     t0
        rts
@zero:  lda     #0
        tax
        rts

; Copies the page t0 (high byte) onto the page t1.
cpypage:
        lda     #0
        sta     sp1
        sta     dp1
        lda     t0
        sta     sp1+1
        lda     t1
        sta     dp1+1
        ldx     #32
        ldy     #0
:       lda     (sp1),y
        sta     (dp1),y
        iny
        bne     :-
        inc     sp1+1
        inc     dp1+1
        dex
        bne     :-
        rts

; Clears the page A (high byte).
clrpage:
        sta     dp1+1
        lda     #0
        sta     dp1
        ldx     #32
        tay
:       sta     (dp1),y
        iny
        bne     :-
        inc     dp1+1
        dex
        bne     :-
        rts

; -- objects ------------------------------------------------------------------------
; Draws the element at ep into pagehi: okr, ocol, owid, otop, ohgt; cost.
drawobj:
        ldy     #0
        lda     (ep),y
        sta     oo
        iny
        lda     (ep),y
        sta     oxl
        iny
        lda     (ep),y
        sta     of
        iny
        lda     (ep),y
        sta     oyl
        lda     #0
        sta     okr
        jsr     coords
        lda     of
        and     #$40
        beq     :+
        jmp     drawtext
:       lda     of
        and     #$10
        sta     wrap
        jsr     findsnap                ; dp = the snapshot
        lda     t1
        sta     t2
        lda     abase_l,x
        sta     tp
        lda     abase_h,x
        sta     tp+1
        jsr     shapeptr                ; dp = actor + 2 i
        ldy     #0
        lda     (dp),y                  ; offset high (byte 2i)
        pha
        lda     dp
        bne     :+
        dec     dp+1
:       dec     dp
        lda     (dp),y                  ; low (2i - 1)
        clc
        adc     tp
        sta     dp
        pla
        adc     tp+1
        sta     dp+1
        ldy     #0
        lda     (dp),y
        sta     sh
        iny
        lda     (dp),y
        sta     sw
        ldy     #4
        lda     (dp),y
        sta     sb4
        iny
        lda     (dp),y
        sta     ssx
        iny
        lda     (dp),y
        sta     ssy
        lda     dp                      ; the rows
        clc
        adc     #7
        sta     dp
        bcc     :+
        inc     dp+1
        ; sync x
:       lda     ssx
        beq     @sy
        ldx     #0
        cmp     #$80
        bcc     :+
        dex
:       clc
        adc     ox
        sta     ox
        txa
        adc     ox+1
        sta     ox+1
        bpl     :+
        lda     #0
        sta     ox
        sta     ox+1
:       lda     wrap
        beq     @xnw
        lda     ox+1                    ; below 280: + 280
        cmp     #>280
        bne     :+
        lda     ox
        cmp     #<280
:       bcs     :+
        lda     ox
        adc     #<280                   ; (carry clear)
        sta     ox
        lda     ox+1
        adc     #>280
        sta     ox+1
        jmp     @sy
:       lda     ox+1                    ; 560 and over: - 280
        cmp     #>560
        bne     :+
        lda     ox
        cmp     #<560
:       bcc     @sy
        lda     ox
        sbc     #<280                   ; (carry set)
        sta     ox
        lda     ox+1
        sbc     #>280
        sta     ox+1
        jmp     @sy
@xnw:   lda     ox+1                    ; over 687: 687
        cmp     #>688
        bne     :+
        lda     ox
        cmp     #<688
:       bcc     @sy
        lda     #<687
        sta     ox
        lda     #>687
        sta     ox+1
@sy:    lda     ssy
        beq     @place
        ldx     #0
        cmp     #$80
        bcc     :+
        dex
:       clc
        adc     oy
        sta     oy
        txa
        adc     oy+1
        sta     oy+1
        bpl     :+
        lda     #0
        sta     oy
        sta     oy+1
:       lda     wrap
        beq     @ynw
        lda     oy+1                    ; below 192: + 192
        bne     :+
        lda     oy
        cmp     #192
        bcs     :+
        adc     #192
        sta     oy
        lda     #0
        adc     #0
        sta     oy+1
        jmp     @place
:       lda     oy+1                    ; 384 and over: - 192
        cmp     #>384
        bne     :+
        lda     oy
        cmp     #<384
:       bcc     @place
        lda     oy
        sbc     #192                    ; (carry set)
        sta     oy
        lda     oy+1
        sbc     #0
        sta     oy+1
        jmp     @place
@ynw:   lda     oy+1                    ; over 511: 511
        cmp     #2
        bcc     @place
        lda     #<511
        sta     oy
        lda     #>511
        sta     oy+1
@place: jsr     div7                    ; x16 / 7: col48 = q + 8, bit = r
        clc
        adc     #8
        sta     scol48
        stx     sbit
        ; the first row
        lda     #0
        sta     sskip
        lda     wrap
        bne     @yw
        lda     oy+1                    ; y16 <= 192: skip 192 - y16 rows
        bne     @below
        lda     oy
        cmp     #193
        bcs     @below
        lda     #192
        sec
        sbc     oy
        sta     sskip
        lda     #0
        sta     stop
        jmp     @rect
@below: lda     oy                      ; top = y16 - 192 (192 and more: none)
        sec
        sbc     #192
        tax
        lda     oy+1
        sbc     #0
        jne     @none
        stx     stop
        jmp     @rect
@yw:    lda     oy+1
        beq     @ylo
        cmp     #1                      ; 256-383: top = y16 - 192
        jne     @none
        lda     oy
        cmp     #<384
        jcs     @none
        adc     #64                     ; (y16 - 192 = low + 64)
        sta     stop
        jmp     @rect
@ylo:   lda     oy
        cmp     #192
        bcs     :+
        adc     #64                     ; y16 < 192: top = y16 + 64
        sta     stop
        jmp     @rect
:       sbc     #192                    ; 192-255
        sta     stop
@rect:  lda     stop
        cmp     #192
        bcs     @none
        ; the width in columns
        lda     sw
        sta     t0
        lda     #0
        sta     t1
        sta     wb
        lda     sb4
        lsr
        bcc     :+
        lda     t0
        adc     #3                      ; (+ 4 with the carry)
        sta     t0
        rol     t1
        lda     #36
        sta     wb
:       lda     t1                      ; while A >= 8: wb + 1, A - 7
        bne     :+
        lda     t0
        cmp     #8
        bcc     :++
:       lda     t0
        sec
        sbc     #7
        sta     t0
        lda     t1
        sbc     #0
        sta     t1
        inc     wb
        jmp     :--
:       lda     wb
        clc
        adc     #2
        cmp     #41
        bcc     :+
        lda     #40
:       sta     wb
        ; the column: c = q - 40, capped at 40
        lda     scol48
        sec
        sbc     #48
        bcc     @neg
        cmp     #40
        bcs     @none
        sta     ocol
        lda     wb
        sta     owid
        jmp     @clip
@neg:   sta     t0                      ; width wb + c + 1
        lda     #0
        sta     ocol
        lda     wb
        clc
        adc     t0
        bcc     @none                   ; (wb + c < 0)
        clc
        adc     #1
        bmi     @none
        beq     @none
        sta     owid
        bne     @clip2                  ; (always: col 0, no cut needed)
@none:  rts
@clip:  lda     wrap
        bne     @clip2
        lda     ocol
        clc
        adc     owid
        cmp     #40
        bcc     @clip2
        lda     #40
        sec
        sbc     ocol
        sta     owid
@clip2: lda     stop
        sta     otop
        lda     sh                      ; height h - skip
        sec
        sbc     sskip
        bcc     @none
        sta     ohgt
        sta     srows
        inc     okr
        lda     owid
        ldx     ohgt
        jsr     mul8
        asl     mprod
        rol     mprod+1
        lda     mprod
        ldy     mprod+1
        jsr     addcost
        ; draw: the rows above the screen first
        lda     srows
        beq     @done
        lda     sskip
        beq     :++
        sta     sskc
:       jsr     skiprow
        dec     sskc
        bne     :-
:       lda     srows
        beq     @done
        lda     #P3OR
        sta     regor
        lda     #0                      ; wrap with X >= 0 (x16 >= 280)
        sta     wrapx
        lda     wrap
        beq     :+
        lda     scol48
        cmp     #48
        bcc     :+
        inc     wrapx
:       lda     stop
        sta     sy
@rows:  lda     wrap
        bne     :+
        lda     sy
        cmp     #192
        bcs     @done
:       jsr     drawrow
        inc     sy
        lda     wrap
        beq     :+
        lda     sy
        cmp     #192
        bne     :+
        lda     #0
        sta     sy
:       dec     srows
        bne     @rows
@done:  rts

; A = x16 (ox) / 7, X = the remainder.
div7:   lda     ox
        sta     t0
        lda     ox+1
        sta     t1
        lda     #0                      ; 10-bit dividend: 16 steps
        ldx     #16
:       asl     t0
        rol     t1
        rol
        cmp     #7
        bcc     :+
        sbc     #7
        inc     t0
:       dex
        bne     :--
        tax
        lda     t0
        rts

; Passes over one row of codes at dp.
skiprow:
@c:     jsr     nextb
        tax
        beq     @end
        cmp     #7
        beq     @end
        and     #7
        cmp     #7
        bne     @run
        txa
        lsr
        lsr
        lsr
        cmp     #26
        bcc     @c
        sbc     #25
        tax
:       jsr     nextb
        dex
        bne     :-
        beq     @c                      ; (always)
@run:   txa
        bmi     @c
        jsr     nextb                   ; a fill's byte
        jmp     @c
@end:   rts

; A = the byte at dp, dp + 1.
nextb:  ldy     #0
        lda     (dp),y
        inc     dp
        bne     :+
        inc     dp+1
:       rts

; -- a row -----------------------------------------------------------------------
; Draws the row at dp on row sy of pagehi; dp moves to the next row.
drawrow:
        tsx
        stx     rowsp
        ldy     sy
        lda     rowlo,y
        sec
        sbc     #48
        sta     rowp
        lda     rowhi,y
        sbc     #0
        clc
        adc     pagehi
        sta     rowp+1
        lda     scol48
        sta     col48
        lda     sbit
        sta     cbit
        lda     #0
        sta     amask
        sta     adata
        sta     ext
        sta     dq
        sta     dr
        lda     #1
        sta     first
@code:  ldy     #0
        lda     (dp),y
        inc     dp
        bne     :+
        inc     dp+1
:       tax
        bne     :+
        jmp     @end0
:       cmp     #7
        bne     :+
        jmp     @end7
:       and     #7
        cmp     #7
        bne     @run
        txa                             ; extension or literal
        lsr
        lsr
        lsr
        cmp     #26
        bcs     @lit
        adc     ext
        bcc     :+
        lda     #255
:       sta     ext
        jmp     @code
@lit:   sbc     #25                     ; k bytes: dp past them first (the
        sta     t3                      ; row may end off the right edge)
        lda     dp
        sta     lp
        clc
        adc     t3
        sta     dp
        lda     dp+1
        sta     lp+1
        adc     #0
        sta     dp+1
:       ldy     #0
        lda     (lp),y
        inc     lp
        bne     :+
        inc     lp+1
:       sta     bval
        lda     #1
        sta     mq
        lda     #0
        sta     mr
        jsr     run
        dec     t3
        bne     :--
        lda     #0
        sta     first
        jmp     @code
@run:   txa                             ; the count
        and     #7
        sta     mr
        txa
        lsr
        lsr
        lsr
        and     #15
        clc
        adc     ext
        sta     mq
        lda     #0
        sta     ext
        txa
        bmi     @skip
        ldy     #0                      ; a fill
        lda     (dp),y
        inc     dp
        bne     :+
        inc     dp+1
:       sta     bval
        jsr     run
        lda     #0
        sta     first
        jmp     @code
@skip:  jsr     addd                    ; d + n + 1
        inc     dr
        lda     dr
        cmp     #7
        bcc     :+
        lda     #0
        sta     dr
        jsr     incdq
:       lda     first
        beq     @skip2
        lda     #0
        sta     first
        jsr     move                    ; first: n untouched, then black
        jsr     putblk
        jsr     adv1k
        jmp     @code
@skip2: jsr     putblk                  ; black under the cursor
        jsr     adv1r
        lda     mq
        ora     mr
        bne     :+
        jmp     @code                   ; skip 0: that dot alone
:       lda     mr                      ; n - 1 untouched, then black
        bne     :+
        dec     mq
        lda     #7
:       sec
        sbc     #1
        sta     mr
        jsr     move
        jsr     putblk
        jsr     adv1k
        jmp     @code
@end0:  lda     first
        bne     @ret
        lda     wrapx                   ; back on its first byte after 280 dots
        beq     :+
        lda     dq
        cmp     #40
        bne     :+
        lda     dr
        bne     :+
        jsr     flushf
        jmp     @ret
:       jsr     putblk
        jsr     flush
@ret:   rts
@end7:  lda     cbit
        beq     @ret
        jmp     flushf

; Off the right edge without wrap: nothing more in the row has an effect;
; its remaining codes are passed over.
dead:   ldx     rowsp
        txs
        jmp     skiprow

; d += mq groups, mr dots.
addd:   lda     dr
        clc
        adc     mr
        cmp     #7
        bcc     :+
        sbc     #7
        sta     dr
        jsr     incdq
        jmp     :++
:       sta     dr
:       lda     dq
        clc
        adc     mq
        bcc     :+
        lda     #255
:       sta     dq
        rts
incdq:  inc     dq
        bne     :+
        dec     dq
:       rts

; A black dot under the cursor.
putblk: ldx     cbit
        lda     bitm,x
        ora     amask
        sta     amask
        rts

; The cursor one dot on; leaving the byte writes it, the register's palette
; (adv1r) or bit 7 kept (adv1k).
adv1r:  inc     cbit
        lda     cbit
        cmp     #7
        bne     :+
        lda     #0
        sta     cbit
        jsr     flush
        jmp     nextcol
:       rts
adv1k:  inc     cbit
        lda     cbit
        cmp     #7
        bne     :+
        lda     #0
        sta     cbit
        jsr     flushk
        jmp     nextcol
:       rts

; The next column (wrapping from 39 to 0, or off the right: dead).
nextcol:
        inc     col48
        lda     col48
        cmp     #88
        bcc     :+
        lda     wrap
        beq     dead
        lda     #48
        sta     col48
:       rts

; The cursor mq groups and mr dots on, nothing drawn; a byte left is
; written (register palette).
move:   lda     cbit
        clc
        adc     mr
        ldx     mq
        cmp     #7
        bcc     :+
        sbc     #7
        inx
:       sta     cbit
        txa
        beq     @done
        stx     t0
        jsr     flush
        lda     col48
        clc
        adc     t0
        sta     col48
@norm:  lda     col48
        cmp     #88
        bcc     @done
        lda     wrap
        jeq     dead
        lda     col48
        sbc     #40
        sta     col48
        jmp     @norm
@done:  rts

; Writes the accumulator if it holds dots: flush (register palette),
; flushf (the same, forced: even without dots), flushk (bit 7 kept).
flush:  lda     amask
        beq     fclr
flushf: ldy     col48
        cpy     #48
        bcc     fclr
        cpy     #88
        bcs     fclr
        lda     amask
        eor     #$FF
        and     (rowp),y
        ora     adata
        and     #$7F
        ora     regor
        sta     (rowp),y
fclr:   lda     #0
        sta     amask
        sta     adata
        rts
flushk: lda     amask
        beq     fclr
        ldy     col48
        cpy     #48
        bcc     fclr
        cpy     #88
        bcs     fclr
        lda     amask
        eor     #$FF
        and     (rowp),y
        ora     adata
        sta     (rowp),y
        jmp     fclr

; A run of mq groups and mr dots of the byte bval: dot j is bit j for j < 7,
; then bits 3-6 over and over. The palette register takes its palette.
run:    lda     bval
        and     #$80
        sta     regor
        jsr     addd
        lda     bval                    ; N | N << 4, N
        lsr
        lsr
        lsr
        and     #15
        sta     nhi
        sta     t0
        asl
        asl
        asl
        asl
        ora     t0
        sta     nlo
        lda     #0
        sta     jj
@loop:  lda     mq
        bne     @some
        lda     mr
        bne     :+
        rts
:
@some:  lda     cbit
        bne     @part
        lda     mq                      ; a whole byte
        beq     @part
        jsr     tval
        ldy     col48
        cpy     #48
        bcc     :+
        cpy     #88
        bcs     :+
        ora     regor
        sta     (rowp),y
:       dec     mq
        lda     jj                      ; j + 7: the same as j + 3
        clc
        adc     #7
        jsr     jnorm
        jsr     nextcol
        jmp     @loop
@part:  lda     #7                      ; k = 7 - bit, or what is left
        sec
        sbc     cbit
        sta     t1
        lda     mq
        bne     :+
        lda     mr
        cmp     t1
        bcs     :+
        sta     t1
:       jsr     tval                    ; (T << bit) & the k dots' mask
        ldx     cbit
        beq     :++
:       asl
        dex
        bne     :-
:       sta     t0
        lda     cbit
        clc
        adc     t1
        tax
        lda     lomask,x
        ldx     cbit
        and     himask,x
        tax
        ora     amask
        sta     amask
        txa
        and     t0
        ora     adata
        sta     adata
        lda     jj
        clc
        adc     t1
        jsr     jnorm
        lda     mr                      ; what is left - k
        sec
        sbc     t1
        bcs     :+
        adc     #7
        dec     mq
:       sta     mr
        lda     cbit
        clc
        adc     t1
        cmp     #7
        bne     :+
        lda     #0
        sta     cbit
        jsr     flush
        jsr     nextcol
        jmp     @loop
:       sta     cbit
        jmp     @loop

; jj = A, kept within 0-6 (j and j - 4 are the same dots from 7 on).
jnorm:  cmp     #7
        bcc     :+
        sbc     #4
        bcs     jnorm                   ; (always)
:       sta     jj
        rts

; A = the run's next 7 dots from dot jj.
tval:   ldx     jj
        cpx     #3
        bcs     @p
        cpx     #1
        beq     @t1
        bcs     @t2
        lda     bval
        and     #$7F
        rts
@t1:    lda     bval                    ; bits 1-6, then bit 3
        and     #$08
        asl
        asl
        asl
        sta     t2
        lda     bval
        lsr
        and     #$3F
        ora     t2
        rts
@t2:    lda     bval                    ; bits 2-6, then bits 3, 4
        and     #$18
        asl
        asl
        sta     t2
        lda     bval
        lsr
        lsr
        and     #$1F
        ora     t2
        rts
@p:     lda     nhi                     ; (N N N) >> (j - 3)
        sta     t2
        lda     nlo
        dex
        dex
        dex
        beq     :++
:       lsr     t2
        ror
        dex
        bne     :-
:       and     #$7F
        rts

; -- text --------------------------------------------------------------------------
drawtext:
        lda     #<(SCENE_AT + $103)     ; string oo
        sta     strp
        lda     #>(SCENE_AT + $103)
        sta     strp+1
        ldx     oo
        ldy     #0
@find:  lda     (strp),y
        dex
        beq     :+
        sec                             ; + length + 1
        adc     strp
        sta     strp
        bcc     @find
        inc     strp+1
        bne     @find                   ; (always)
:       sta     slen
        inc     strp
        bne     :+
        inc     strp+1
:       lda     ox                      ; the pen: x16 - 280, y16 - 192
        sec
        sbc     #<280
        sta     ox
        lda     ox+1
        sbc     #>280
        sta     ox+1
        jsr     div7
        sta     pen
        stx     pbit
        sta     lcol
        sta     rcl
        stx     lbit
        stx     rbit
        lda     oy
        sec
        sbc     #192
        sta     py
        sta     ttop
        sta     tbot
        lda     #1
        sta     twid
        sta     thgt
        lda     #0
        sta     tbytes
        sta     tbytes+1
        sta     sidx
        jsr     penrow
@char:  lda     sidx
        cmp     slen
        jeq     @done
        tay
        lda     (strp),y
        inc     sidx
        sec                             ; shape ch - 31, else 1
        sbc     #31
        bcc     @one
        beq     @one
        cmp     csn
        beq     :+
        bcc     :+
@one:   lda     #1
:       sta     t2
        lda     csb
        sta     tp
        lda     csb+1
        sta     tp+1
        jsr     shapeptr
        ldy     #0
        lda     (dp),y
        clc
        adc     csb
        sta     shp
        iny
        lda     (dp),y
        adc     csb+1
        sta     shp+1
@byte:  ldy     #0
        lda     (shp),y
        beq     @char
        inc     shp
        bne     :+
        inc     shp+1
:       sta     t1
        inc     tbytes
        bne     :+
        inc     tbytes+1
:       lda     t1                      ; A
        jsr     vector
        lda     t1
        lsr
        lsr
        lsr
        beq     @byte
        sta     t1
        jsr     vector                  ; B
        lda     t1
        lsr
        lsr
        lsr
        beq     @byte
        and     #3                      ; C: a move
        jsr     pmove
        jmp     @byte
@done:  lda     lcol                    ; the rectangle
        sta     ocol
        lda     twid
        cmp     #41
        bcc     :+
        lda     #40
:       sta     owid
        lda     ttop
        sta     otop
        lda     thgt
        cmp     #193
        bcc     :+
        lda     #192
:       sta     ohgt
        inc     okr
        lda     #11                     ; cost 11 per shape byte (saturated)
        sta     t0
:       lda     tbytes
        ldy     tbytes+1
        jsr     addcost
        dec     t0
        bne     :-
        rts

; One vector (A, low 3 bits): bit 2 inverts the dot under the pen, then the
; pen moves.
vector: pha
        and     #4
        beq     :+
        ldy     pen
        ldx     pbit
        lda     bitm,x
        eor     (rowp),y
        sta     (rowp),y
:       pla
        and     #3
; Moves the pen: A = 0 up, 1 right, 2 down, 3 left; the rectangle follows.
pmove:  cmp     #1
        beq     @right
        bcs     :+
        jmp     @up
:       cmp     #2
        beq     @down
        lda     pen                     ; left: from the leftmost position?
        cmp     lcol
        bne     @lgo
        lda     pbit
        cmp     lbit
        bne     @lgo
        jsr     pleft
        lda     pen
        cmp     lcol
        beq     :+
        jsr     incw
:       lda     pen
        sta     lcol
        lda     pbit
        sta     lbit
        rts
@lgo:   jmp     pleft
@right: lda     pen
        cmp     rcl
        bne     @rgo
        lda     pbit
        cmp     rbit
        bne     @rgo
        jsr     pright
        lda     pen
        cmp     rcl
        beq     :+
        jsr     incw
:       lda     pen
        sta     rcl
        lda     pbit
        sta     rbit
        rts
@rgo:   jmp     pright
@down:  lda     py
        cmp     tbot
        php
        inc     py
        lda     py
        cmp     #192
        bne     :+
        lda     #0
        sta     py
:       plp
        bne     penrow
        lda     py
        sta     tbot
        jsr     inch
        jmp     penrow
@up:    lda     py
        cmp     ttop
        php
        dec     py
        lda     py
        cmp     #$FF
        bne     :+
        lda     #191
        sta     py
:       plp
        bne     penrow
        lda     py
        sta     ttop
        jsr     inch
; rowp = the pen's row in pagehi.
penrow: ldy     py
        lda     rowlo,y
        sta     rowp
        lda     rowhi,y
        ora     pagehi
        sta     rowp+1
        rts
pleft:  dec     pbit
        bpl     :+
        lda     #6
        sta     pbit
        dec     pen
        bpl     :+
        lda     #39
        sta     pen
:       rts
pright: inc     pbit
        lda     pbit
        cmp     #7
        bne     :+
        lda     #0
        sta     pbit
        inc     pen
        lda     pen
        cmp     #40
        bne     :+
        lda     #0
        sta     pen
:       rts
incw:   inc     twid
        bne     :+
        dec     twid
:       rts
inch:   inc     thgt
        bne     :+
        dec     thgt
:       rts

; -- fades ---------------------------------------------------------------------------
        .segment "HICODE"               ; (TAKE1.SYSTEM: above the scene)
; Fade A (2-17) from page fsrc onto page fdst (shown).
fade:   asl
        tax
        lda     fades-4,x
        sta     tp
        lda     fades-3,x
        sta     tp+1
        jmp     (tp)

; Row X: fs/fd pointers sp1, dp1.
frowp:  lda     rowlo,x
        sta     sp1
        sta     dp1
        lda     rowhi,x
        ora     fsrc
        sta     sp1+1
        eor     fsrc
        ora     fdst
        sta     dp1+1
        rts
; Copies row X, columns 39 down to 0.
frow:   jsr     frowp
        ldy     #39
:       lda     (sp1),y
        sta     (dp1),y
        dey
        bpl     :-
        rts
; Copies (X, Y).
fbyte:  jsr     frowp
        lda     (sp1),y
        sta     (dp1),y
        rts
; Stripes row X ($AA odd columns, $D5 even, 39 down), then D(30).
fstripe:
        jsr     frowp
        ldy     #39
:       lda     #$AA
        sta     (dp1),y
        dey
        lda     #$D5
        sta     (dp1),y
        dey
        bpl     :-
        lda     #30
        jmp     t1_delay

; 2, 3: column by column (0 up, 39 down), rows 0-191, D(40).
fade2:  lda     #0
        sta     fy
        lda     #1
        bne     f23                     ; (always)
fade3:  lda     #39
        sta     fy
        lda     #$FF
f23:    sta     fstep
@col:   ldx     #0
:       ldy     fy
        jsr     fbyte
        inx
        cpx     #192
        bne     :-
        lda     #40
        jsr     t1_delay
        lda     fy
        clc
        adc     fstep
        sta     fy
        cmp     #40
        bcc     @col
        rts

; 4, 6: rows up / down, D(30) after each; 5, 7: a stripe, then the row.
fade4:  lda     #191
        sta     fx
:       ldx     fx
        jsr     frow
        lda     #30
        jsr     t1_delay
        dec     fx
        lda     fx
        cmp     #$FF
        bne     :-
        rts
fade6:  lda     #0
        sta     fx
:       ldx     fx
        jsr     frow
        lda     #30
        jsr     t1_delay
        inc     fx
        lda     fx
        cmp     #192
        bne     :-
        rts
fade5:  lda     #191
        sta     fx
:       ldx     fx
        jsr     fstripe
        ldx     fx
        jsr     frow
        dec     fx
        lda     fx
        cmp     #$FF
        bne     :-
        rts
fade7:  lda     #0
        sta     fx
:       ldx     fx
        jsr     fstripe
        ldx     fx
        jsr     frow
        inc     fx
        lda     fx
        cmp     #192
        bne     :-
        rts

; 8 / 13: centre out, by ones / twos.
fade8:  lda     #1
        ldx     #30
        bne     f813                    ; (always)
fade13: lda     #2
        ldx     #45
f813:   sta     fstep
        stx     fdel
        lda     #96
        sta     fup
        sta     fdn
        sta     fx
@loop:  ldx     fx
        jsr     frow
        lda     fdel
        jsr     t1_delay
        lda     fx
        cmp     #96
        bcc     @dn
        lda     fup
        sec
        sbc     fstep
        sta     fup
        sta     fx
        cmp     #128
        bcc     @loop
@dn:    lda     fdn
        clc
        adc     fstep
        sta     fdn
        sta     fx
        cmp     #192
        bcc     @loop
        bne     @end
        lda     fstep                   ; 13: x = 192, the odd rows
        cmp     #2
        bne     @end
        lda     #97
        sta     fup
        lda     #95
        sta     fdn
        sta     fx
        bne     @loop                   ; (always)
@end:   rts

; 9: stripes from the centre.
fade9:  ldx     #95
        jsr     fstripe
        ldx     #96
        jsr     fstripe
        lda     #0
        sta     fk
@k:     lda     #96
        clc
        adc     fk
        tax
        jsr     frow
        lda     #97
        clc
        adc     fk
        cmp     #192
        bcs     :+
        tax
        jsr     fstripe
:       lda     #95
        sec
        sbc     fk
        tax
        jsr     frow
        lda     #94
        sec
        sbc     fk
        bcc     :+
        tax
        jsr     fstripe
:       inc     fk
        lda     fk
        cmp     #96
        bne     @k
        rts

; band(x) of fades 10 and 11: (x, f5) and (x, f6) with fa, else the
; columns f5 down to f6.
band:   lda     fa
        beq     @all
        ldy     f5
        jsr     fbyte
        ldx     fx
        ldy     f6
        jmp     fbyte
@all:   jsr     frowp
        ldy     f5
:       lda     (sp1),y
        sta     (dp1),y
        cpy     f6
        beq     :+
        dey
        bpl     :-
:       rts

; 10: shrink in.
fade10: lda     #186
        sta     f7
        lda     #0
        sta     f6
        sta     fa
        lda     #39
        sta     f5
        ldx     #0
        jsr     frow
@pass:  lda     #186                    ; f9 = min(186 - f7, 95)
        sec
        sbc     f7
        cmp     #96
        bcc     :+
        lda     #95
:       sta     f9
        lda     f7                      ; f8 = max(f7 + 5, 96)
        clc
        adc     #5
        cmp     #96
        bcs     :+
        lda     #96
:       sta     f8
        sta     fx
@loop:  ldx     fx
        jsr     band
        lda     #1
        jsr     t1_delay
        lda     fx
        cmp     #97
        bcc     :+
        inc     f9
        lda     f9
        sta     fx
        jmp     @loop
:       dec     f8
        lda     f8
        sta     fx
        cmp     #96
        bcc     @endp
        cmp     f7
        bne     @loop
        lda     #1
        sta     fa
        bne     @loop                   ; (always)
@endp:  lda     f7
        sec
        sbc     #5
        sta     f7
        lda     #0
        sta     fa
        inc     f6
        lda     f6
        asl
        asl
        jsr     t1_delay
        dec     f5
        lda     f5
        cmp     #20
        bcs     @pass
        rts

; 11: split, from the centre.
fade11: lda     #5
        sta     f7
        lda     #19
        sta     f6
        lda     #20
        sta     f5
        lda     #0
        sta     fa
@pass:  lda     #96
        sta     f9
        sta     f8
        sta     fx
@loop:  ldx     fx
        jsr     band
        lda     #2
        jsr     t1_delay
@test:  lda     fx
        cmp     #96
        bcc     @dn
        dec     f9
        lda     f9
        sta     fx
        cmp     #128
        bcc     @loop
@dn:    inc     f8
        lda     f8
        sta     fx
        sec
        sbc     #96
        cmp     f7
        bcc     @loop
        lda     fa
        beq     @endp
        lda     f7
        clc
        adc     #5
        cmp     #97
        bcc     :+
        lda     #96
:       sta     f7
        lda     #0
        sta     fa
        beq     @loop                   ; (always, with this same x)
@endp:  lda     #1
        sta     fa
        dec     f6
        inc     f5
        lda     f5
        cmp     #40
        bcc     @pass
        rts

; 12: interlace, top and bottom rows alternately, 384 rows.
fade12: lda     #0
        sta     fk                      ; the top side's row
@pair:  ldx     fk
        jsr     frowp
        ldy     #39
:       lda     (sp1),y
        sta     (dp1),y
        dey
        dey
        bpl     :-
        lda     #24
        jsr     t1_delay
        lda     #191
        sec
        sbc     fk
        tax
        jsr     frowp
        ldy     #38
:       lda     (sp1),y
        sta     (dp1),y
        dey
        dey
        bpl     :-
        lda     #24
        jsr     t1_delay
        inc     fk
        lda     fk
        cmp     #192
        bne     @pair
        rts

; 14: diagonal staircases of six bytes.
fade14: lda     #191
        sta     f7
        lda     #39
        sta     f6
@loop:  jsr     t1_tick
        lda     f7
        sta     fx
        lda     f6
        sta     fy
@col:   lda     #6
        sta     fcnt
:       ldx     fx
        ldy     fy
        jsr     fbyte
        lda     fx
        beq     :+
        dec     fx
        dec     fcnt
        bne     :-
:       inc     fy
        lda     fy
        cmp     #40
        bne     @col
        dec     f6
        bpl     @loop
        lda     #0
        sta     f6
        lda     f7
        cmp     #6
        bcc     :+
        sbc     #6
        sta     f7
        jmp     @loop
:       rts

; 15: checkerboard, strips of 8 bytes.
fade15: lda     #39
        jsr     @pass
        lda     #31
@pass:  sta     fs0
        lda     #0
        sta     f8                      ; g
@g:     lda     #0
        sta     fk
@k:     lda     fk                      ; strip (g + 32 k, y0 or y0 ^ 56)
        asl
        asl
        asl
        asl
        asl
        clc
        adc     f8
        tax
        lda     fk
        lsr
        lda     fs0
        bcc     :+
        eor     #56
:       tay
        jsr     frowp
        lda     #3                      ; three groups of 8, 16 apart
        sta     fcnt
@grp:   ldx     #8
:       lda     (sp1),y
        sta     (dp1),y
        dey
        bmi     @sdone
        dex
        bne     :-
        tya                             ; 8 skipped
        sec
        sbc     #8
        bcc     @sdone
        tay
        dec     fcnt
        bne     @grp
@sdone: inc     fk
        lda     fk
        cmp     #6
        bne     @k
        lda     #25
        jsr     t1_delay
        inc     f8
        lda     f8
        cmp     #32
        bne     @g
        lda     #48
        jmp     t1_delay

; 16 / 17: scroll up / down by blocks of 8 rows.
fade16: lda     #0
        ldx     #8
        ldy     #184
        bne     f1617                   ; (always)
fade17: lda     #184
        ldx     #$F8
        ldy     #0
f1617:  sta     f5                      ; first
        stx     fstep
        sty     f6                      ; last
        sta     fs0                     ; s
@pass:  lda     f5
        sta     fx
@rep:   lda     fdst                    ; block (x <- x + step, destination)
        sta     fa
        lda     fx
        clc
        adc     fstep
        jsr     block
        lda     fx
        clc
        adc     fstep
        sta     fx
        cmp     f6
        beq     :+
        lda     #20
        jsr     t1_delay
        jmp     @rep
:       lda     fsrc                    ; block (x <- s, source)
        sta     fa
        lda     fs0
        jsr     block
        lda     fs0
        clc
        adc     fstep
        sta     fs0
        cmp     #192
        beq     :+
        cmp     #$F8
        beq     :+
        lda     #20
        jsr     t1_delay
        jmp     @pass
:       rts

; Copies the 8 rows from A of page fa to the rows from fx of fdst, column
; 39 down to 0, row by row in each column.
block:  sta     f9
        lda     #39
        sta     fy
@col:   ldx     #0
:       stx     fcnt
        txa
        clc
        adc     f9
        tay
        lda     rowlo,y
        sta     sp1
        lda     rowhi,y
        ora     fa
        sta     sp1+1
        txa
        clc
        adc     fx
        tay
        lda     rowlo,y
        sta     dp1
        lda     rowhi,y
        ora     fdst
        sta     dp1+1
        ldy     fy
        lda     (sp1),y
        sta     (dp1),y
        ldx     fcnt
        inx
        cpx     #8
        bne     :-
        dec     fy
        bpl     @col
        rts

        .rodata
fades:  .word   fade2, fade3, fade4, fade5, fade6, fade7, fade8, fade9
        .word   fade10, fade11, fade12, fade13, fade14, fade15, fade16, fade17
sblack: .byte   9, "< BLACK >"
sunch:  .byte   13, "< UNCHANGED >"
pbk:    .byte   "BK."
psn:    .byte   "SN."
pac:    .byte   "AC."
pcs:    .byte   "CS."
pow2:   .byte   1, 2, 4, 8
l20:    .byte   0, 20
bitm:   .byte   $01, $02, $04, $08, $10, $20, $40
himask: .byte   $7F, $7E, $7C, $78, $70, $60, $40     ; dots bit..6
lomask: .byte   $00, $01, $03, $07, $0F, $1F, $3F, $7F ; dots 0..m-1
rowlo:
        .repeat 192, yy
        .byte   <(((yy .mod 8) * $400) + (((yy / 8) .mod 8) * $80) + ((yy / 64) * $28))
        .endrepeat
rowhi:
        .repeat 192, yy
        .byte   >(((yy .mod 8) * $400) + (((yy / 8) .mod 8) * $80) + ((yy / 64) * $28))
        .endrepeat
