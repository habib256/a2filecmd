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
;   t1_wait    the original speed's hold: t1_hold cycles to wait (32 bits;
;              A/X = n, the original's frame wait it includes). Called
;              before each frame is shown (the work since the last one,
;              the wait that one owes), right after a frame with a $FC
;              element (its wait alone, before the pause or sound) and at
;              a scene's end. The accelerated speed ignores it
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
        .export t1_dest, t1_max, t1_len, t1_hold
        .export MOVIE_MAX, SCENE_MAX, t1_txc3
        .import __TXC3_LOAD__, __TXC3_RUN__, __TXC3_SIZE__
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

; The original speed (docs, "Original speed"): after a frame is shown the
; caller holds it t1_hold cycles: the original's modelled time for the
; frame's work (MC_*, docs "Timing") plus its exact frame wait, less this
; engine's own cost for the same work, OWN_BASE + OWN_* per counter
; (fitted on this code: tools/test_take1.py --calibrate; the reference,
; tools/take1_ref.py, reads them from here), never negative.
MC_CODES  = 140
MC_BYTES  = 55
MC_SNAPS  = 1700
MC_SHAPES = 280
MC_ERASED = 20
MC_FULLS  = 79000
OWN_BASE   = 3868
OWN_CODES  = 134
OWN_BYTES  = 166
OWN_SNAPS  = 1743
OWN_SHAPES = 478
OWN_ERASED = 28
OWN_FULLS  = 79393
OWN_ROWS   = 194
OWN_OBJS   = 1066
OWN_STB    = -143

; Counts a screen byte written by a row.
.macro  CNTW                            ; a whole byte of a run: both
        inc     kstb
        bne     *+4
        inc     kstb+1
        CNTB
.endmacro
.macro  CNTB                            ; (no label: cheap labels go on)
        inc     kbyt
        bne     *+4                     ; (past the zero-page inc)
        inc     kbyt+1
.endmacro

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
dq:     .res 1          ; the row's distance: groups, saturated at 255
dr:     .res 1          ;                     dots, 0-6
lp:     .res 2          ; a literal's bytes
wrap:   .res 1
wrapx:  .res 1          ; wrap with X >= 0: the 280-dot return counts
kcod:   .res 2          ; the frame's work, 16-bit counters (reset when a
kbyt:   .res 2          ; frame is shown): row codes, screen bytes written,
ksnp:   .res 2          ; snapshots, text shape bytes, bytes erased, full
kshp:   .res 2          ; page copies, snapshot rows
kera:   .res 2
kful:   .res 2
krow:   .res 2
kobj:   .res 2          ; objects drawn (or tried), whole bytes of runs
kstb:   .res 2          ; stored at once (the engine's own cost only)
hn:     .res 2          ; the frame wait n, n / 4
hn4:    .res 2
cntf:   .res 1          ; $80: skiprow counts the codes (a dead row)
mv:     .res 2          ; hold's multiplication
mc:     .res 4
prod:   .res 4
hacc:   .res 4
owed:   .res 2          ; the frame wait n the last frame shown owes
hpure:  .res 1          ; hold: nonzero, the wait n alone
rhi:    .res 1          ; rowad: the row's high byte
rx:     .res 1
strp:   .res 2          ; text: the string, the shape
shp:    .res 2
t0:     .res 1
t1:     .res 1
t2:     .res 1
t3:     .res 1
ox:     .res 2          ; the object: x16, y16
oy:     .res 2
ocol:   .res 1          ;             its rectangle's column, width
owid:   .res 1
stop:   .res 1          ;             its first row
sy:     .res 1          ; the row drawn
back:   .res 1          ; the back page, $20 / $40
pagehi: .res 1          ; the page drawn into
wb:     .res 1          ; a snapshot's width in columns
mprod:  .res 2          ; multiplication
t4tab:  .res 4          ; a run's whole bytes: the pattern's four phases
nn:     .res 1          ; the run's N (bits 3-6)
fk:     .res 1          ; lists, fades: an index, a count
fcnt:   .res 1
m8a:    .res 1          ; mul8's last factors
m8x:    .res 1

; In TAKE1.SYSTEM these go to text page 1 (never shown while a movie
; plays, its screen holes avoided: take1.cfg); the refusal message clears
; it, after which none of them is used.
        .segment "TXT0"
rcol:   .res 40         ; list L, entry i at 20 L + i
rwid:   .res 40
rtop:   .res 40
        .segment "TXT1"
rhgt:   .res 40
abase_l: .res 10        ; actor j: address, length, count, snapshots
abase_h: .res 10
alen_l: .res 10
alen_h: .res 10
acnt:   .res 10
anum:   .res 10         ; its own count n
lcount: .res 2          ; rectangle lists, per page (0: $20, 1: $40)
lareal: .res 2
lareah: .res 2
lfull:  .res 2
srows:  .res 1
        .segment "TXT3"
t1_mlen:  .res 2        ; the movie's length
t1_hold:  .res 4        ; after a frame shown: cycles to hold it
t1_dest:  .res 2
t1_max:   .res 2
t1_len:   .res 2
savesp: .res 1
rowsp:  .res 1          ; the stack in a row (off the right: rest skipped)
nsc:    .res 1          ; scenes in the movie
kidx:   .res 1          ; the entry played
fin:    .res 1          ; its fades
fout:   .res 1
snl:    .res 2          ; the scene's length
room:   .res 2          ; memory left for its files
freep:  .res 2          ; where the next one goes
nact:   .res 1          ; actors
aidx:   .res 1
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
ry:     .res 1          ; frowp: Y kept
        .segment "TXT2"
ent:    .res 42         ; the entry played
bsl:    .res 8          ; block (fades 16, 17): the rows' pointers
bsh:    .res 8
bdl:    .res 8
bdh:    .res 8
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
fs0:    .res 1
okr:    .res 1          ; the object drawn has a rectangle
otop:   .res 1
ohgt:   .res 1
oxl:    .res 1          ; the element
of:     .res 1
oyl:    .res 1
oo:     .res 1
sh:     .res 1          ; snapshot: height, width, byte 4, syncs
sw:     .res 1
sb4:    .res 1
ssx:    .res 1
ssy:    .res 1
sskip:  .res 1
sskc:   .res 1
scol48: .res 1          ; the start of every row
sbit:   .res 1
        .bss
t1_name:  .res 24       ; length, then the DOS name (23 characters)
t1_err:   .res 1
t1_front: .res 1
wsw:    .res 1          ; the last snapshot width: sw, its parity,
wsb:    .res 1          ; the columns (zeroed: width 0, even, 0)
wwb:    .res 1

        .code
; -- the movie ------------------------------------------------------------------
t1_play:
        tsx
        stx     savesp
        jsr     kclear
        lda     #0                      ; (zero page is not cleared)
        sta     cntf
        sta     m8a                     ; (mul8's last product: 0 * 0)
        sta     m8x
        sta     mprod
        sta     mprod+1
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

; Stores A in page 3 at row sy, column t3; sy + 1. X kept. (The rows of a
; column come in order: + $400 within a group of 8.)
bkput:  pha
        lda     sy
        and     #7
        beq     :+
        lda     dp1+1
        clc
        adc     #4
        sta     dp1+1
        bne     :++                     ; (always)
:       ldy     sy
        jsr     rowad
        sta     dp1
        lda     rhi
        ora     #PAGE3
        sta     dp1+1
:       ldy     t3
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

; -- routines run from text page 1's rows (TAKE1.SYSTEM: $05B0, $0680, $0700,
; $0780, copied once the hi-res screen is shown; take1.cfg) ---------------------------
        .segment "TXC3"
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
@p:     txa                             ; pphase: 16 (j - 3) + N
        asl
        asl
        asl
        asl
        ora     nn
        tax
        lda     pphase,x
        rts

        .segment "TXC5"
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

; Off the right edge without wrap: nothing more in the row has an effect;
; its remaining codes are passed over.
dead:   ldx     rowsp
        txs
        lda     #$80
        sta     cntf
        jsr     skiprow
        lda     #0
        sta     cntf
        rts

; Past column 39 (col48 88): column 0 with wrap, else dead.
wrapcol:
        lda     wrap
        jeq     dead
        lda     #48
        sta     col48
        rts

        .segment "TXC6"
; One literal byte (bval): 7 dots, its own palette; the cursor's bit is
; kept, the column moves on.
lit1:   lda     bval
        and     #$80
        sta     regor
        lda     wrapx
        beq     :+
        lda     #1
        sta     mq
        lda     #0
        sta     mr
        jsr     addd
:       lda     bval
        and     #$7F
        sta     t0
        ldx     cbit
        bne     @split
        ldy     col48                   ; a whole byte
        cpy     #48
        bcc     :+
        cpy     #88
        bcs     :+
        ora     regor
        sta     (rowp),y
        CNTB
:       jmp     nextcol
@split: asl                             ; its first 7 - bit dots, here
        dex
        bne     @split
        ldx     cbit
        and     himask,x
        ora     adata
        sta     adata
        lda     himask,x
        ora     amask
        sta     amask
        jsr     flnext
        lda     #7                      ; the other bit dots, in the next
        sec                             ; byte: T >> (7 - bit)
        sbc     cbit
        tax
        lda     t0
:       lsr
        dex
        bne     :-
        sta     adata
        ldx     cbit
        lda     lomask,x
        sta     amask
        rts

        .segment "TXC7"
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
        jmp     flnext                  ; (it holds the black dot)
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

; Passes over one row of codes at dp.
skiprow:
@c:     jsr     nextb
        bit     cntf                    ; (a dead row: its codes count)
        bpl     @nc
        inc     kcod
        bne     @nc
        inc     kcod+1
@nc:    tax
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

        .code

; -- the cold checks (TAKE1.SYSTEM: low memory, $0200 on) --------------------------
        .segment "LOWC"
; Row Y's address in a page: A = low byte, rhi = high (rows 8 g + k:
; lo24/hi24 of g, + $400 k). X and Y kept.
rowad:  stx     rx
        tya
        lsr
        lsr
        lsr
        tax
        tya
        and     #7
        asl
        asl
        ora     hi24,x
        sta     rhi
        lda     lo24,x
        ldx     rx
        rts

; rowp = row sy of pagehi, minus 48 (indexed by col48).
rowaddr:
        ldy     sy
        jsr     rowad
        sec
        sbc     #48
        sta     rowp
        lda     rhi
        sbc     #0
        clc
        adc     pagehi
        sta     rowp+1
        rts


; The work counters to 0.
kclear: lda     #0
        ldx     #17
:       sta     kcod,x
        dex
        bpl     :-
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

        .code

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
        sta     owed
        sta     owed+1
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
@flip:  lda     owed                    ; the original speed's hold: the
        ldx     owed+1                  ; work since the last frame, the
        jsr     hold                    ; wait it owes (the counters to 0)
        jsr     t1_wait
        lda     back
        sta     t1_front
        eor     #$60
        sta     back
        lda     t1_front
        jsr     t1_show
        jsr     fwait                   ; the wait this one owes
        sta     owed
        stx     owed+1
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
        lda     fcg                     ; a $FC element: the wait first, alone
        beq     @fcs
        lda     owed
        ldx     owed+1
        jsr     holdp
        jsr     t1_wait
        lda     #0
        sta     owed
        sta     owed+1
@fcs:   lda     fcg                     ; 6. $FC
        beq     :+
        sec
        sbc     #1
        ldx     fct
        jsr     t1_fc
:       lda     #1
        sta     fnum
        jmp     @frame
@done:  lda     owed                    ; the scene's end: the last frame's
        ldx     owed+1                  ; wait, the work since it
        jsr     hold
        jsr     t1_wait
        lda     fout                    ; fade-out: from a black back page
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

; Applies list X to the back page (from page 3): cost += its cost; empty.
apply:  lda     lfull,x
        beq     @rects
        stx     t3
        lda     #PAGE3
        sta     t0
        lda     back
        sta     t1
        jsr     cpypage
        inc     kful
        bne     :+
        inc     kful+1
:       ldx     t3
        lda     #<FULLCOST
        ldy     #>FULLCOST
        jsr     addcost
        jmp     @clear
@rects: lda     lareal,x
        clc
        adc     kera
        sta     kera
        lda     lareah,x
        adc     kera+1
        sta     kera+1
        lda     lareal,x
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
@rnew:  ldy     sy                      ; the row's pointers (+ $400 within
        jsr     rowad                   ; a group of 8 rows)
        sta     sp1
        sta     dp1
        lda     rhi
        ora     #PAGE3
        sta     sp1+1
        eor     #PAGE3
        ora     back
        sta     dp1+1
@row:   ldy     t0
        ldx     t1
:       lda     (sp1),y
        sta     (dp1),y
        iny
        cpy     #40
        bne     :+
        ldy     #0
:       dex
        bne     :--
        dec     t2
        beq     @nextr
        inc     sy
        lda     sy
        cmp     #192
        bne     :+
        lda     #0
        sta     sy
:       and     #7
        beq     @rnew
        lda     sp1+1
        clc
        adc     #4
        sta     sp1+1
        lda     dp1+1
        clc
        adc     #4
        sta     dp1+1
        bne     @row                    ; (always)
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

; Before a frame is shown, A/X = the frame wait n the last one owes:
; t1_hold = the original's modelled time for the work since (MC_* per
; counter) + 350 n + 18 (n / 4), less this engine's estimate (OWN_BASE +
; OWN_* per counter), 0 if negative; the counters to 0. holdp: 350 n +
; 18 (n / 4) alone (the counters kept). A/X = n again.
holdp:  ldy     #1
        bne     hold2                   ; (always)
hold:   ldy     #0
hold2:  sty     hpure
        sta     hn
        stx     hn+1
        txa
        lsr
        sta     hn4+1
        lda     hn
        ror
        sta     hn4
        lsr     hn4+1
        ror     hn4
        lda     #<(-OWN_BASE)
        sta     hacc
        lda     #>(-OWN_BASE)
        sta     hacc+1
        lda     #^(-OWN_BASE)
        sta     hacc+2
        lda     #((-OWN_BASE) >> 24) & $FF
        sta     hacc+3
        ldx     #0
        lda     hpure
        beq     @term
        stx     hacc                    ; the wait alone: its two terms
        stx     hacc+1
        stx     hacc+2
        stx     hacc+3
        ldx     #5 * (NTERMS - 2)
@term:  ldy     hterms,x                ; the value (zero page), 16 bits
        lda     a:0,y
        sta     mv
        lda     a:1,y
        sta     mv+1
        lda     hterms+1,x              ; its coefficient, 24 bits, sign
        sta     mc
        lda     hterms+2,x
        sta     mc+1
        lda     hterms+3,x
        sta     mc+2
        lda     #0
        sta     mc+3
        sta     prod
        sta     prod+1
        sta     prod+2
        sta     prod+3
@bit:   lda     mv                      ; prod = mv * mc
        ora     mv+1
        beq     @sum
        lsr     mv+1
        ror     mv
        bcc     :+
        clc
        lda     prod
        adc     mc
        sta     prod
        lda     prod+1
        adc     mc+1
        sta     prod+1
        lda     prod+2
        adc     mc+2
        sta     prod+2
        lda     prod+3
        adc     mc+3
        sta     prod+3
:       asl     mc
        rol     mc+1
        rol     mc+2
        rol     mc+3
        jmp     @bit
@sum:   lda     hterms+4,x
        bmi     @sub
        clc
        lda     hacc
        adc     prod
        sta     hacc
        lda     hacc+1
        adc     prod+1
        sta     hacc+1
        lda     hacc+2
        adc     prod+2
        sta     hacc+2
        lda     hacc+3
        adc     prod+3
        sta     hacc+3
        jmp     @next
@sub:   sec
        lda     hacc
        sbc     prod
        sta     hacc
        lda     hacc+1
        sbc     prod+1
        sta     hacc+1
        lda     hacc+2
        sbc     prod+2
        sta     hacc+2
        lda     hacc+3
        sbc     prod+3
        sta     hacc+3
@next:  txa
        clc
        adc     #5
        tax
        cpx     #5 * NTERMS
        jne     @term
        ldx     #3                      ; t1_hold, never negative
        lda     hacc+3
        bpl     :+
        lda     #0
        sta     hacc
        sta     hacc+1
        sta     hacc+2
        sta     hacc+3
:       lda     hacc,x
        sta     t1_hold,x
        dex
        bpl     :-
        lda     hpure
        bne     :+
        jsr     kclear
:
        lda     hn
        ldx     hn+1
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



; Copies the page t0 (high byte) onto the page t1: four passes of eight
; pages, absolute indexed (9.6 cycles a byte, the original's 79,000 a
; page; the operands patched).
cpypage:
        lda     #4
        sta     fcnt
@pass:  lda     t0
        clc
        sta     @s0+2
        adc     #1
        sta     @s1+2
        adc     #1
        sta     @s2+2
        adc     #1
        sta     @s3+2
        adc     #1
        sta     @s4+2
        adc     #1
        sta     @s5+2
        adc     #1
        sta     @s6+2
        adc     #1
        sta     @s7+2
        adc     #1
        sta     t0
        lda     t1
        sta     @d0+2
        adc     #1
        sta     @d1+2
        adc     #1
        sta     @d2+2
        adc     #1
        sta     @d3+2
        adc     #1
        sta     @d4+2
        adc     #1
        sta     @d5+2
        adc     #1
        sta     @d6+2
        adc     #1
        sta     @d7+2
        adc     #1
        sta     t1
        ldy     #0
@l:
@s0:    lda     $FF00,y
@d0:    sta     $FF00,y
@s1:    lda     $FF00,y
@d1:    sta     $FF00,y
@s2:    lda     $FF00,y
@d2:    sta     $FF00,y
@s3:    lda     $FF00,y
@d3:    sta     $FF00,y
@s4:    lda     $FF00,y
@d4:    sta     $FF00,y
@s5:    lda     $FF00,y
@d5:    sta     $FF00,y
@s6:    lda     $FF00,y
@d6:    sta     $FF00,y
@s7:    lda     $FF00,y
@d7:    sta     $FF00,y
        iny
        bne     @l
        dec     fcnt
        jne     @pass
        rts

; -- objects ------------------------------------------------------------------------
; Draws the element at ep into pagehi: okr, ocol, owid, otop, ohgt; cost.
drawobj:
        inc     kobj
        bne     :+
        inc     kobj+1
:       ldy     #0
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
        jcs     @none
        lda     sb4                     ; the width in columns (kept: the
        and     #1                      ; same width and parity again)
        tax
        lda     sw
        cmp     wsw
        bne     :+
        cpx     wsb
        beq     @wk
:       sta     wsw
        stx     wsb
        sta     t0
        lda     #0
        sta     t1
        sta     wb
        txa
        lsr
        bcc     :+
        lda     t0
        adc     #3                      ; (+ 4 with the carry)
        sta     t0
        rol     t1
        lda     #36
        sta     wb
:       lda     t0                      ; while A >= 8: wb + 1, A - 7, that
        ora     t1                      ; is wb + (A - 1) / 7 when A >= 1
        beq     :+
        lda     t0
        bne     *+4
        dec     t1
        dec     t0
        jsr     dv7
        clc
        adc     wb
        sta     wb
:       lda     wb
        sta     wwb
@wk:    lda     wwb
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
        inc     ksnp
        bne     :+
        inc     ksnp+1
:
        lda     owid
        ldx     ohgt
        jsr     mul8                    ; (mprod kept for addrect)
        lda     mprod
        asl
        tax
        lda     mprod+1
        rol
        tay
        txa
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
        jsr     rowaddr
@rows:  inc     krow
        bne     :+
        inc     krow+1
:       jsr     drawrow
        inc     sy                      ; the next row: + $400 within a group
        lda     sy                      ; of 8, else from the tables
        and     #7
        beq     :+
        lda     rowp+1
        clc
        adc     #4
        sta     rowp+1
        bne     @next                   ; (always)
:       lda     sy
        cmp     #192
        bcc     :+
        lda     wrap                    ; past row 191: the end, or row 0
        beq     @done
        lda     #0
        sta     sy
:       jsr     rowaddr
@next:  dec     srows
        bne     @rows
@done:  rts

; mprod = A * X (8 x 8 bits), the last product kept: an object's area
; is asked again when its rectangle is listed.
mul8:   cmp     m8a
        bne     :+
        cpx     m8x
        beq     @done
:       sta     m8a
        stx     m8x
        sta     t0
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
@done:  rts

; A = x16 (ox) / 7, X = the remainder.
div7:   lda     ox
        sta     t0
        lda     ox+1
        sta     t1
; A = t0/t1 (under 1,792) / 7, X = the remainder: 7 << k taken off, k = 7
; down to 0.
dv7:    lda     #0
        sta     t2
        ldy     #7
@k:     lda     t1                      ; under 256: 8 bits for the rest
        beq     @b
        lda     t0
        sec
        sbc     dvl,y
        tax
        lda     t1
        sbc     dvh,y
        bcc     @n
        sta     t1
        stx     t0
@n:     rol     t2                      ; (the carry: the quotient's bit k)
        dey
        bpl     @k
        ldx     t0
        lda     t2
        rts
@b:     cpy     #6                      ; (7 << 6 and over: above it)
        bcc     @b1
        asl     t2
        dey
        bpl     @b                      ; (always)
@b1:    lda     t0
@b2:    cmp     dvl,y
        bcc     :+
        sbc     dvl,y
:       rol     t2
        dey
        bpl     @b2
        tax
        lda     t2
        rts

; -- a row -----------------------------------------------------------------------
; Draws the row at dp on row sy of pagehi; dp moves to the next row.
drawrow:
        tsx
        stx     rowsp
        lda     scol48
        sta     col48
        lda     sbit
        sta     cbit
        lda     #0
        sta     amask
        sta     adata
        sta     ext
        sta     dq                      ; (the distance: wrapx only)
        sta     dr
        lda     #1
        sta     first
@code:  ldy     #0
        lda     (dp),y
        inc     dp
        bne     :+
        inc     dp+1
:       inc     kcod
        bne     :+
        inc     kcod+1
:       cmp     #7                      ; 1-6: a short fill, the quick way
        bcs     @c7
        tax
        jeq     @end0                   ; (code 0)
        ldy     ext
        bne     @c7
        sta     mr
        sty     mq                      ; (Y: 0)
        jmp     @fill
@c7:    tax                             ; r = code & 7 (7: an extension, a
        and     #7                      ; literal, the row's end)
        cmp     #7
        beq     @sev
        sta     mr
        txa                             ; code >> 3: q, + 16 for a skip
        lsr
        lsr
        lsr
        ldy     ext
        bne     @ext
        cmp     #16
        jcs     @skq
        sta     mq                      ; (q >= 1: not the end)
        jmp     @fill
@ext:   cpx     #0                      ; q + the extension
        jeq     @end0
        and     #15
        clc
        adc     ext
        sta     mq
        lda     #0
        sta     ext
        txa
        jmi     @skip
        clc
        jmp     @fill
@sev:   cpx     #7
        bne     :+
        jmp     @end7
:       txa                             ; extension or literal
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
@lls:   lda     dp                      ; the long way: dp past the bytes
        sta     lp                      ; first (the row may end off the
        clc                             ; right edge)
        adc     t3
        sta     dp
        lda     dp+1
        sta     lp+1
        adc     #0
        sta     dp+1
@ll:    ldy     #0
        lda     (lp),y
        inc     lp
        bne     :+
        inc     lp+1
:       sta     bval
        jsr     lit1
        dec     t3
        bne     @ll
        jmp     @code
@lit:   sbc     #25                     ; k bytes
        sta     t3
        lda     #0
        sta     first
        lda     wrapx                   ; the short way: on the screen, the
        bne     @lls                    ; bytes and a spill within it, read
        lda     col48                   ; from dp as they go
        cmp     #48
        bcc     @lls
        adc     t3                      ; (carry set: + 1)
        cmp     #89
        bcs     @lls
@lf:    ldy     #0
        lda     (dp),y
        inc     dp
        bne     :+
        inc     dp+1
:       ldy     col48
        ldx     cbit
        bne     @lsp
        sta     (rowp),y                ; on bit 0: the byte itself
        and     #$80
        sta     regor
        CNTB
        inc     col48
        dec     t3
        bne     @lf
        jmp     @code
@lsp:   sta     t0                      ; its palette, its dots
        and     #$80
        sta     regor
        eor     t0
        cpx     #4                      ; split at the bit, the shorter way
        bcs     @lr
:       asl                             ; << bit, 16 bits: t1 the spill
        rol     t1                      ; (above it: masked below)
        dex
        bne     :-
        sta     t0
        asl
        rol     t1
        jmp     @lw
@lr:    ldy     jfirst,x                ; or >> (7 - bit): A the spill, t1
:       lsr                             ; the first byte's dots (<< 1)
        ror     t1
        dey
        bne     :-
        tax
        lda     t1
        lsr
        sta     t0
        stx     t1
        ldy     col48
@lw:    ldx     cbit                    ; its first 7 - bit dots here
        lda     t0
        and     himask,x
        ora     adata
        sta     t0
        lda     himask,x
        ora     amask
        eor     #$FF
        and     (rowp),y
        ora     t0
        and     #$7F
        ora     regor
        sta     (rowp),y
        CNTB
        lda     lomask,x                ; the other bit dots, gathered
        sta     amask
        and     t1
        sta     adata
        inc     col48
        dec     t3
        jne     @lf
        jmp     @code
@fill:  ldy     #0                      ; a fill
        lda     (dp),y
        inc     dp
        bne     :+
        inc     dp+1
:       sta     bval
        sty     first                   ; (Y: 0)
        and     #$80
        sta     regor
        lda     wrapx
        beq     :+
        jsr     addd                    ; (wrap: the distance)
:       lda     cbit                    ; e: the dot it ends on, q: the
        clc                             ; bytes moved on
        adc     mr
        ldx     mq
        jne     @fq
        cmp     #7
        bcs     @fq1
        sta     t3                      ; within the byte: dots bit to e - 1
        lda     bval                    ; into the accumulator, T(0) << bit
        ldx     cbit
        beq     :++
:       asl
        dex
        bne     :-
:       sta     t0
        ldy     t3
        lda     lomask,y
        ldx     cbit
        and     himask,x
        tax
        ora     amask
        sta     amask
        txa
        and     t0
        ora     adata
        sta     adata
        sty     cbit
        jmp     @code
@fslow: jsr     run
        jmp     @code
@fq1:   sbc     #7                      ; 7 dots at most over two bytes
        sta     t3                      ; (bit >= 1): T(0) split there, its
        ldy     col48                   ; dots from 7 - bit on the spill (bit
        cpy     #48                     ; 7, shifted, falls under the masks)
        bcc     @fslow
        cpy     #87
        bcs     @fslow
        ldx     cbit
        cpx     #4
        bcs     @fr
        lda     bval
:       asl                             ; << bit, 16 bits: t1 the spill
        rol     t1                      ; (above it: masked below)
        dex
        bne     :-
        sta     t0
        asl
        rol     t1
        jmp     @fw
@fr:    lda     jfirst,x                ; or >> (7 - bit): A the spill, t1
        tax                             ; the first byte's dots (<< 1)
        lda     bval
:       lsr
        ror     t1
        dex
        bne     :-
        tax
        lda     t1
        lsr
        sta     t0
        stx     t1
@fw:    ldx     cbit                    ; the first byte, written
        lda     t0
        and     himask,x
        ora     adata
        sta     t0
        lda     himask,x
        ora     amask
        eor     #$FF
        and     (rowp),y
        ora     t0
        and     #$7F
        ora     regor
        sta     (rowp),y
        CNTB
        iny
        sty     col48
        ldx     t3                      ; the spill's e dots, gathered
        stx     cbit
        lda     lomask,x
        sta     amask
        and     t1
        sta     adata
        jmp     @code
@fs2:   jsr     run
        jmp     @code
@fq:    cmp     #7
        bcc     :+
        sbc     #7
        inx
:       sta     t3
        ldy     col48                   ; the short way: on the screen, ending
        cpy     #48                     ; 2 bytes on at most
        bcc     @fs2
        cpx     #3
        bcs     @fs2   
        stx     t2
        txa
        adc     col48                   ; (carry clear)
        cmp     #88
        bcs     @fs2   
        lda     bval                    ; T(0) << bit (bit 7 masked below)
        ldx     cbit
        beq     :++
:       asl
        dex
        bne     :-
:       ldx     cbit
        sta     t0
@fx:    lda     t0                      ; the byte: written now
        and     himask,x
        ora     adata
        sta     t0
        lda     himask,x
        ora     amask
        eor     #$FF
        and     (rowp),y
        ora     t0
        and     #$7F
        ora     regor
        sta     (rowp),y
        txa
        bne     :+
        CNTW                            ; (a whole one)
        jmp     :++
:       CNTB
:       lda     bval                    ; N, for T(j) (j = 7 - bit, 7 is 3)
        lsr
        lsr
        lsr
        and     #15
        sta     nn
        lda     jfirst,x
        sta     jj
        lda     #0
        sta     amask
        sta     adata
        iny
        dec     t2
        beq     @ftl
        jsr     tval                    ; one whole byte
        ora     regor
        sta     (rowp),y
        CNTW
        iny
        ldx     jj
        lda     jnext,x
        sta     jj
@ftl:   sty     col48                   ; the last dots, gathered
        lda     t3
        sta     cbit
        beq     :+
        jsr     tval
        ldx     t3
        and     lomask,x
        sta     adata
        lda     lomask,x
        sta     amask
:       jmp     @code
@skq:   and     #15
        sta     mq
@skip:  lda     wrapx                   ; d + n + 1
        jne     @sd
        lda     cbit                    ; the short way (e: the closing dot,
        clc                             ; q: bytes on)
        adc     mr
        ldx     mq
        bne     @sq
        cmp     #7
        bcs     @sq1
        sta     t3                      ; within the byte: nothing written
        tax                             ; but at bit 6
        lda     first
        bne     @sf
        lda     mr
        beq     @sslow                  ; (skip 0: one dot)
        lda     bitm,x                  ; black under the cursor and at e
        ldx     cbit
        ora     bitm,x
        ora     amask
        ldx     t3
        jmp     @scl2
@sf:    lda     #0                      ; the row's first: n untouched
        sta     first
        beq     @scl                    ; (always)
@sq:    cmp     #7
        bcc     :+
@sq1:   sbc     #7
        inx
:       sta     t3
        stx     t2
        ldy     col48                   ; on the screen
        cpy     #48
        bcc     @sslow
        txa
        clc
        adc     col48
        cmp     #88
        bcs     @sslow
        lda     first
        beq     :+
        lda     #0                      ; the row's first: n untouched
        sta     first
        beq     @sto                    ; (always)
:       ldx     cbit                    ; black under the cursor, its byte
        lda     bitm,x                  ; left: written
        ora     amask
        eor     #$FF
        and     (rowp),y
        ora     adata
        and     #$7F
        ora     regor
        sta     (rowp),y
        CNTB
        lda     #0
        sta     amask
        sta     adata
@sto:   lda     t2
        clc
        adc     col48
        sta     col48
@scl:   ldx     t3                      ; the closing black
        lda     bitm,x
        ora     amask
@scl2:  sta     amask
        inx
        cpx     #7
        beq     :+
        stx     cbit
        jmp     @code
:       lda     #0                      ; (bit 6: written, bit 7 as said)
        sta     cbit
        jsr     flushk
        jsr     nextcol
        jmp     @code
@sslow: lda     wrapx
        beq     :+
@sd:    jsr     addd
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
@skip2: ldx     cbit                    ; black under the cursor
        lda     bitm,x
        ora     amask
        sta     amask
        lda     mq
        ora     mr
        bne     :+
        jsr     adv1r                   ; skip 0: that dot alone
        jmp     @code
:       jsr     move                    ; n - 1 untouched, black n on
        ldx     cbit
        lda     bitm,x
        ora     amask
        sta     amask
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

; The accumulator, holding dots, written (register palette), then the next
; column.
flnext: ldy     col48
        cpy     #48
        bcc     :+
        cpy     #88
        bcs     :+
        lda     amask
        eor     #$FF
        and     (rowp),y
        ora     adata
        and     #$7F
        ora     regor
        sta     (rowp),y
        CNTB
:       lda     #0
        sta     amask
        sta     adata
; The next column (wrapping from 39 to 0, or off the right: dead).
nextcol:
        inc     col48
        lda     col48
        cmp     #88
        bcc     :+
        lda     wrap
        jeq     dead
        lda     #48
        sta     col48
:       rts

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
        CNTB
fclr:   lda     #0
        sta     amask
        sta     adata
        rts
flushk: lda     amask                   ; (bit 6: the skip's closing dot)
        beq     fclr
        and     #$3F                    ; earlier dots of the row here: they
        bne     flushf                  ; gave the byte the register's bit 7
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
        CNTB
        jmp     fclr

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

; A run of mq groups and mr dots of the byte bval: dot j is bit j for j < 7,
; then bits 3-6 over and over (drawrow has set the palette register and the
; distance, and kept the runs ending in the cursor's byte). A byte at a
; time: the first partial byte written with the accumulator's dots, whole
; bytes stored directly (the first from T(j), the others from a pattern of
; four values by column, since bits 3-6 repeat every 4 dots and 7 = 3 mod
; 4: at once when on the screen, up to the right edge without wrap), the
; last partial byte into the accumulator.
run:    lda     #0
        sta     jj
        ldx     cbit
        jeq     @n8
        txa                             ; the first byte: k = 7 - bit
        eor     #7
        sta     t1
        lda     bval                    ; the run fills it: T(0) << bit, the
:       asl                             ; dots from bit on, with those
        dex                             ; gathered: the byte written now
        bne     :-
        ldx     cbit
        and     himask,x
        ora     adata
        sta     t0
        lda     himask,x
        ora     amask
        eor     #$FF
        sta     t2
        ldy     col48
        cpy     #48
        bcc     :+
        cpy     #88
        bcs     :+
        lda     (rowp),y
        and     t2
        ora     t0
        and     #$7F
        ora     regor
        sta     (rowp),y
        CNTB
:       lda     #0
        sta     amask
        sta     adata
        sta     cbit
        lda     t1
        sta     jj                      ; (1-6)
        lda     mr                      ; what is left - k
        sec
        sbc     t1
        bcs     :+
        adc     #7
        dec     mq
:       sta     mr
        inc     col48
        lda     col48
        cmp     #88
        bcc     @n8
        jsr     wrapcol
        jmp     @n8
@n8:    lda     mq                      ; N (bits 3-6), for what goes on
        ora     mr
        bne     :+
        rts
:       lda     bval
        lsr
        lsr
        lsr
        and     #15
        sta     nn
@full:  lda     mq                      ; whole bytes
        jeq     @tail
        lda     jj
        cmp     #3
        bcs     @pat
        jsr     tval                    ; the first from T(j), j < 3
        ldy     col48
        cpy     #48
        bcc     :+
        cpy     #88
        bcs     :+
        ora     regor
        sta     (rowp),y
        CNTW
:       dec     mq
        lda     jj                      ; (j + 7, then - 4: j + 3)
        clc
        adc     #3
        sta     jj
        inc     col48
        lda     col48
        cmp     #88
        bcc     :+
        jsr     wrapcol
:       lda     mq
        jeq     @tail
@pat:   lda     mq                      ; one: by itself
        cmp     #2
        jcc     @few
        lda     col48                   ; the end column + 1 (88: the edge)
        clc
        adc     mq
        cmp     #89
        bcc     @p1
        ldx     wrap                    ; past it: with wrap, a byte at a
        jne     @few                    ; time; else up to it, then dead
        lda     #88
@p1:    sta     t3
        jsr     pat4                    ; t4tab, from phase 3 down; jj on
        ldx     #3                      ; (the phase entered)
        lda     col48
        cmp     #48
        bcs     @p2
        lda     t3                      ; off the left: nothing on the
        cmp     #49                     ; screen, or k = 48 - c bytes passed
        bcs     :+
        sta     col48
        lda     #0
        sta     mq
        jmp     @tail
:       lda     #48
        sec
        sbc     col48
        and     #3
        eor     #3
        tax
        lda     #48
        sta     col48
@p2:    lda     t3                      ; the bytes written, at once
        sec
        sbc     col48
        sta     t1
        clc
        adc     kbyt
        sta     kbyt
        bcc     :+
        inc     kbyt+1
:       lda     t1
        clc
        adc     kstb
        sta     kstb
        bcc     :+
        inc     kstb+1
:       ldy     col48
        cpx     #3
        beq     @st3
        lda     @jl,x
        sta     tp
        lda     @jh,x
        sta     tp+1
        jmp     (tp)                    ; unrolled: 17 cycles a byte
@st3:   lda     t4tab+3
        sta     (rowp),y
        iny
        cpy     t3
        beq     @sd
@st2:   lda     t4tab+2
        sta     (rowp),y
        iny
        cpy     t3
        beq     @sd
@st1:   lda     t4tab+1
        sta     (rowp),y
        iny
        cpy     t3
        beq     @sd
@st0:   lda     t4tab
        sta     (rowp),y
        iny
        cpy     t3
        bne     @st3
@sd:    sty     col48
        lda     #0
        sta     mq
        cpy     #88
        bcc     @tail
        jsr     wrapcol
        jmp     @tail
@jl:    .byte   <@st0, <@st1, <@st2
@jh:    .byte   >@st0, >@st1, >@st2
@few:   jsr     tval                    ; one byte from T(j)
        ldy     col48
        cpy     #48
        bcc     :+
        cpy     #88
        bcs     :+
        ora     regor
        sta     (rowp),y
        CNTW
:       lda     jj                      ; j + 7: j + 3 if under 7, else j - 1
        clc
        adc     #3
        cmp     #7
        bcc     :+
        sbc     #4
:       sta     jj
        inc     col48
        lda     col48
        cmp     #88
        bcc     :+
        jsr     wrapcol
:       dec     mq
        bne     @few
@tail:  lda     mr                      ; the last dots, into the accumulator
        beq     @done
        jsr     tval
        ldx     mr
        and     lomask,x
        sta     adata
        lda     lomask,x
        sta     amask
        stx     cbit
@done:  rts

; -- text --------------------------------------------------------------------------
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
        jsr     rowad
        sta     rowp
        lda     rhi
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

; -- page copies, the frame wait (TAKE1.SYSTEM: above the scene) ------------------
        .segment "HICODE"
; TXC3 into text page 1's row 3 (by main, with TXC5-7).
t1_txc3:
        ldx     #<__TXC3_SIZE__
:       lda     __TXC3_LOAD__-1,x
        sta     __TXC3_RUN__-1,x
        dex
        bne     :-
        rts

; t4tab[3 - m] = the run's byte m from here (dot jj, 3-6, then + 7 a byte:
; pattern phase jj - 3 - m), with the palette; jj moves past the mq bytes.
pat4:   lda     jj                      ; byte m: phase (jj - 3 - m) & 3,
        asl                             ; from pphase (16 jj + N, then 16
        asl                             ; less a byte)
        asl
        asl
        ora     nn
        tax
        lda     pphase,x
        ora     regor
        sta     t4tab+3
        lda     pphase-16,x
        ora     regor
        sta     t4tab+2
        lda     pphase-32,x
        ora     regor
        sta     t4tab+1
        lda     pphase-48,x
        ora     regor
        sta     t4tab
        lda     jj                      ; jj = 3 + ((jj - 3 - mq) & 3)
        sec
        sbc     mq
        clc
        adc     #1
        and     #3
        clc
        adc     #3
        sta     jj
        rts

; A text: the string oo with the character set (XDRAW), its rectangle.
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
        lda     tbytes                  ; the shape bytes counted
        clc
        adc     kshp
        sta     kshp
        lda     tbytes+1
        adc     kshp+1
        sta     kshp+1
        lda     #11                     ; cost 11 per shape byte (saturated)
        sta     t0
:       lda     tbytes
        ldy     tbytes+1
        jsr     addcost
        dec     t0
        bne     :-
        rts

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

csname: lda     #<(SCENE_AT + 4)
        sta     tp
        lda     #>(SCENE_AT + 4)
        sta     tp+1
        lda     #<pcs
        ldx     #>pcs
        jmp     setname

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

; -- fades ---------------------------------------------------------------------------
; Fade A (2-17) from page fsrc onto page fdst (shown).
fade:   asl
        tax
        lda     fades-4,x
        sta     tp
        lda     fades-3,x
        sta     tp+1
        jmp     (tp)

; Row X: fs/fd pointers sp1, dp1.
frowp:  sty     ry                      ; (X and Y kept)
        txa
        tay
        jsr     rowad
        ldy     ry
        sta     sp1
        sta     dp1
        lda     rhi
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
        ldx     #7                      ; the 16 rows' pointers first
@pre:   txa
        clc
        adc     f9
        tay
        jsr     rowad
        sta     bsl,x
        lda     rhi
        ora     fa
        sta     bsh,x
        txa
        clc
        adc     fx
        tay
        jsr     rowad
        sta     bdl,x
        lda     rhi
        ora     fdst
        sta     bdh,x
        dex
        bpl     @pre
        lda     #39
        sta     fy
@col:   ldx     #0
:       lda     bsl,x
        sta     sp1
        lda     bsh,x
        sta     sp1+1
        lda     bdl,x
        sta     dp1
        lda     bdh,x
        sta     dp1+1
        ldy     fy
        lda     (sp1),y
        sta     (dp1),y
        inx
        cpx     #8
        bne     :-
        dec     fy
        bpl     @col
        rts

        .rodata
; hold's terms: the value's zero-page address, the coefficient's magnitude
; (24 bits) and its sign ($80: subtracted).
.macro  TERM    v, c
        .if (c) < 0
        .byte   v, <(-(c)), >(-(c)), ^(-(c)), $80
        .else
        .byte   v, <(c), >(c), ^(c), 0
        .endif
.endmacro
hterms: TERM    kcod, MC_CODES - OWN_CODES
        TERM    kbyt, MC_BYTES - OWN_BYTES
        TERM    ksnp, MC_SNAPS - OWN_SNAPS
        TERM    kshp, MC_SHAPES - OWN_SHAPES
        TERM    kera, MC_ERASED - OWN_ERASED
        TERM    kful, MC_FULLS - OWN_FULLS
        TERM    krow, 0 - OWN_ROWS
        TERM    kobj, 0 - OWN_OBJS
        TERM    kstb, 0 - OWN_STB
        TERM    hn, 350
        TERM    hn4, 18
NTERMS  = 11
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
jfirst: .byte   3, 6, 5, 4, 3, 2, 1      ; the dot after the first byte: 7 - bit
jnext:  .byte   3, 4, 5, 6, 3, 4, 5      ; j + 7, kept within 0-6 (j >= 7: - 4)
dvl:    .byte   <7, <14, <28, <56, <112, <224, <448, <896
dvh:    .byte   >7, >14, >28, >56, >112, >224, >448, >896
pphase:                                 ; 16 j + N (j = 0-6): N's pattern from
        .repeat 112, iv                 ; dot j >= 3, phase f = (j - 3) & 3
        .byte   ((((iv & 15) | ((iv & 15) << 4) | ((iv & 15) << 8)) >> (((iv >> 4) + 1) & 3)) & $7F)
        .endrepeat
himask: .byte   $7F, $7E, $7C, $78, $70, $60, $40     ; dots bit..6
lomask: .byte   $00, $01, $03, $07, $0F, $1F, $3F, $7F ; dots 0..m-1
lo24:                                   ; row 8 g's address, g = 0-23
        .repeat 24, gg
        .byte   <(((gg .mod 8) * $80) + ((gg / 8) * $28))
        .endrepeat
hi24:
        .repeat 24, gg
        .byte   >(((gg .mod 8) * $80) + ((gg / 8) * $28))
        .endrepeat
