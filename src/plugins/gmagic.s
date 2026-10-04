; gmagic.s -- GMAGIC: Graphics Magician pictures (Penguin Software,
; 1982-1984) drawn on hi-res page 1 as the original routines draw them.
;
; Clean-room: written from docs/GRAPHICS-MAGICIAN-FORMAT.md alone, the
; reference being tools/gmagic_ref.py (written from the same text). A
; picture is the list of PICEDIT's drawing commands, a byte each with its
; arguments: line colour $2c, brush $4b, pattern $60 p, line start $8x,
; line $Ax, brush stamp $Cx, flood fill $Ex (x: the X high part, then X
; low and Y), and in 1984 (V84) text: cursor $1x, characters $30/$50 c.
; $00 ends a picture; a file holds one or more pictures back to back.
;
; Every picture of the file is checked before anything is drawn (section
; 3 of the spec: strict commands, a line start among the lines, a line,
; brush or fill command, the first command $2x/$4x/$6x/$8x/$Ax); the first
; one must pass, the following ones are kept while they pass (a later
; picture that draws nothing ends the list, as any other refusal does). The same checking routine (getcmd) reads
; every command again as it is drawn, so no unchecked value ever reaches
; the drawing code. Every byte the drawing touches is addressed through
; rowad, which answers "outside" for the rows the originals send out of
; the page (section 11): nothing is ever written outside $2000-$3FFF.
; Read-only; main bank only: no auxiliary memory, no disk write.
;
; The dialect: V84 when a picture of the file uses $1x, $3x or $5x (D does
; nothing then); otherwise V82, and D redraws in the other one -- the two
; differ by their flood fill only. N (or the space bar) shows the next
; picture on a cleared page, O draws it over the one shown (a room and its
; overlays); Left/Right, S and Escape are the core's (media_key, and the
; core's cgetc runs the slideshow).
;
; Text is drawn with A2FC's substitute font, BOLD.SET (gmagic_text.inc),
; not Penguin's: a picture with text is not byte-identical to the
; original. No known picture has text.
;
; Memory (sdk/gmagic.cfg). The file is loaded at $1B00 and runs from:
;   $1B00-$1FFF  header, CODE, RODATA: in place;
;   $0C00-$0FFF  GMLOW, copied there by the entry, and GMBSS after it. It
;                is the ProDOS buffer of a SECOND open file: GMAGIC keeps
;                one;
;   copy_buf     the patterns' row-pattern numbers and the brushes (472 of
;                its 512 bytes), copied by the entry;
;   $0400-$07FF  the font and the row patterns, in the main text page,
;                written once the hi-res page is on the screen (as the
;                lo-res viewers do; the screen holes and the activity cell
;                $06F7 are left alone): 112 bytes at the head of each
;                128-byte block (gmagic_text.inc). The core redraws the
;                text screen when the overlay returns;
;   the note     the core's 80-byte note buffer is the read buffer until
;                the overlay returns (and then the note itself);
;   $2000-       COLD: the entry, the checks and the tables' sources, run
;                in place before the page is cleared over them.
;
; Plain 6502 throughout: the 6502 edition assembles this file too.
; tools/test_gmagic.py runs all of it under sim65 on both processors;
; tools/test_gmagic_writes.py runs the 6502 edition's GMAGIC.PLG in
; tools/mos6502.py, which records every address written.

        .macpack longbranch
        .export _plugin_entry
        .import pushax, pusha0, pusheax, jmpvec
        .import __GMLOW_LOAD__, __GMLOW_RUN__, __GMLOW_SIZE__
        .importzp ptr1, ptr2, tmp1, tmp2, tmp3, tmp4, sreg

; The service table and the entry (checked by gmagic.c).
API_FULL    = 6
API_CBUF    = 12
API_FOPEN   = 46
API_FREAD   = 48
API_FCLOSE  = 52
API_FSEEK   = 54
API_CGETC   = 74
API_STRCPY  = 80
API_RESEL   = 90
API_NOTE    = 92
API_SEL     = 94
API_MKEY    = 100
E_TYPE      = 17
SEEK_SET    = 2
FERROR      = 4                         ; cc65's FILE: f_flags (+1), _FERROR
RBLEN       = 64                        ; the read buffer: the note's 80 bytes
ROWS        = $0680                     ; the row patterns, text page block 5

        .segment "GMBSS"
errsp:  .res    1
fh:     .res    2                       ; the picture file, 0 = closed
sel:    .res    2                       ; the selected entry
msg:    .res    2
bpos:   .res    1                       ; read buffer: next byte, bytes in it
blen:   .res    1
cmd:    .res    1                       ; the command getcmd read ...
t:      .res    1                       ; ... its high nibble
arg:    .res    1                       ; ... its low nibble (X high part)
val:    .res    1                       ; ... the next byte (X low, pattern, character)
yy:     .res    1                       ; ... Y
nparts: .res    1                       ; pictures in the file (1 to 255)
v84only: .res   1                       ; a picture uses V84 commands
dialect: .res   1                       ; 0 V82, 1 V84
base:   .res    1                       ; the view: picture base on a cleared
cur:    .res    1                       ; page, then base+1..cur over it
key:    .res    1
; the drawing state
colour: .res    1                       ; the colour byte of the last $2c
cb:     .res    1                       ; the line's colour bits (section 6)
alt:    .res    1                       ; $7F for the colours that alternate
m:      .res    1                       ; the pen's pixel mask, bit 7 set
col:    .res    1                       ; the pen's byte column
penxl:  .res    1
penxh:  .res    1
peny:   .res    1
pat8:   .res    8                       ; the pattern: even rows, odd rows
brush:  .res    1
txl:    .res    1                       ; the text cursor
txh:    .res    1
ty:     .res    1
xorf:   .res    1                       ; text in XOR mode
rowpar: .res    1                       ; 4 x (row AND 1), set by rowad
; The handlers' own variables, sharing one area: a command's handler
; runs to its end before the next one starts, and the checks of COLD
; come before any drawing.
work:   .res    13
; COLD's checks of a picture
lines   = work+0
starts  = work+1
v84p    = work+2
draws   = work+3
; bitmaps
bsh     = work+0                        ; shift (pixel offset)
bcol    = work+1                        ; byte column
btop    = work+2                        ; top row
brow    = work+3
bq      = work+4
wl      = work+5
wh      = work+6
scol    = work+7                        ; the brush's column
; lines
axl     = work+0                        ; |dx|
axh     = work+1
bb      = work+2                        ; |dy|
sx      = work+3                        ; 1: towards the left
sy      = work+4                        ; +1 or -1
el      = work+5                        ; the error term
eh      = work+6
nl      = work+7                        ; steps left
nh      = work+8
; fills
fy      = work+0
fc      = work+1
fp      = work+2
fs      = work+3
lp      = work+4                        ; left border + 1 (0: none in the start byte)
rr      = work+5                        ; right border (7: none, or the right edge)
lc      = work+6
rc      = work+7
lst     = work+8                        ; the left border was in the start byte
va      = work+9                        ; V82's middle: A, Rc, Ls, half
vrc     = work+10
vls     = work+11
half    = work+12

; ---------------------------------------------------------------------------
        .segment "COLD"

; void plugin_entry(const struct A2fcApi* api)
_plugin_entry:
        sta     fl1+1                   ; field reads the table from there
        stx     fl1+2
        sta     fl2+1
        stx     fl2+2
        lda     #<__GMLOW_LOAD__        ; GMLOW to $0C00 (whole pages: the
                                        ; BSS after it is set from here on)
        sta     ptr1
        lda     #>__GMLOW_LOAD__
        sta     ptr1+1
        lda     #<__GMLOW_RUN__
        sta     ptr2
        lda     #>__GMLOW_RUN__
        sta     ptr2+1
        ldx     #>(__GMLOW_SIZE__+255)
        jsr     copyx
        tsx
        stx     errsp
        lda     #0
        sta     fh
        sta     fh+1
        sta     bpos
        sta     blen
        sta     nparts
        sta     v84only
        ldy     #API_CBUF               ; the patterns and the brushes
        jsr     field
        sta     ptr2
        stx     ptr2+1
        sta     hpe+1                   ; pate at copy_buf,
        stx     hpe+2
        clc
        adc     #108                    ; pato at copy_buf + 108,
        sta     hpo+1
        txa
        adc     #0
        sta     hpo+2
        tax
        lda     hpo+1
        clc
        adc     #108                    ; the brushes at copy_buf + 216
        sta     bbase
        txa
        adc     #0
        sta     bbase+1
        lda     #<cbtab
        sta     ptr1
        lda     #>cbtab
        sta     ptr1+1
        ldx     #2
        jsr     copyx
        ldy     #API_NOTE               ; the read buffer
        jsr     field
        sta     rdb+4
        stx     rdb+5
        sta     rbuf
        stx     rbuf+1
        ldy     #API_SEL
        jsr     field
        sta     sel
        stx     sel+1
        sta     ptr1
        stx     ptr1+1
        ldy     #E_TYPE                 ; a BIN file
        lda     (ptr1),y
        cmp     #6
        jne     bad
        ldy     #API_FULL               ; fopen(full, "rb")
        jsr     field
        jsr     pushax
        lda     #<s_rb
        ldx     #>s_rb
        ldy     #API_FOPEN
        jsr     call
        sta     fh
        stx     fh+1
        ora     fh+1
        jeq     ioerr

        ; The pictures, each checked to its end byte.
part:   jsr     getb                    ; the first command (put back)
        bcs     parts
        dec     bpos
.ifndef GM_LAX
        cmp     #$20                    ; $2x $4x $6x $8x $Ax
        bcc     parts
        cmp     #$B0
        bcs     parts
        and     #$10
        bne     parts
.endif
        lda     #0
        sta     lines
        sta     starts
        sta     v84p
        sta     draws
pcmd:   jsr     getcmd
        bcs     parts
        lda     cmd
        beq     pend
        lda     t
        cmp     #$0A                    ; $Ax $Cx $Ex draw something
        bcc     pc0
        sta     draws
pc0:    cmp     #8                      ; a line start
        bne     pc1
        sta     starts
pc1:    cmp     #$0A                    ; a line
        beq     pc2
        cmp     #8
        bne     pc3
pc2:    sta     lines
pc3:    cmp     #6                      ; $1x $3x $5x: V84
        bcs     pcmd
        lsr     a
        bcc     pcmd
        lda     #1
        sta     v84p
        bne     pcmd                    ; always
pend:
.ifndef GM_LAX
        lda     draws                   ; something drawn (rule 5)
        beq     parts
        lda     lines                   ; lines need a line start
        beq     pe1
        lda     starts
        beq     parts
pe1:
.endif
        lda     v84p
        ora     v84only
        sta     v84only
        inc     nparts
        lda     nparts
        cmp     #255
        bne     part

        ; A read error is never taken for the end of the file.
parts:  lda     fh
        sta     ptr1
        lda     fh+1
        sta     ptr1+1
        ldy     #1
        lda     (ptr1),y
        and     #FERROR
        jne     ioerr
        lda     nparts
        jeq     bad
        lda     v84only
        beq     pd
        lda     #1
pd:     sta     dialect
        lda     #0
        sta     base
        sta     cur
        jsr     rewind                  ; (a failure: still nothing drawn)
        jcs     ioerr
        ; The page white past COLD (the text screen still on), the hi-res
        ; screen on, then the font and the row patterns into the text
        ; page; view clears COLD's part first.
        lda     #>__GMLOW_LOAD__        ; (a test link may put it elsewhere)
        cmp     #$40
        bcs     pw2
        ldy     #<__GMLOW_LOAD__
        lda     #0
        sta     ptr1
        lda     #>__GMLOW_LOAD__
        sta     ptr1+1
        lda     #$FF
pw1:    sta     (ptr1),y
        iny
        bne     pw1
        inc     ptr1+1
        ldx     ptr1+1
        cpx     #$40
        bne     pw1
pw2:    jsr     show
        lda     #<txtimg
        sta     ptr1
        lda     #>txtimg
        sta     ptr1+1
        lda     #$00
        sta     ptr2
        lda     #$04
        sta     ptr2+1
        ldx     #8                      ; eight blocks of 112 bytes
pt1:    ldy     #111
pt2:    lda     (ptr1),y
        sta     (ptr2),y
        dey
        bpl     pt2
        lda     ptr1
        clc
        adc     #112
        sta     ptr1
        bcc     pt3
        inc     ptr1+1
pt3:    lda     ptr2
        eor     #$80                    ; the next 128-byte block
        sta     ptr2
        bne     pt4
        inc     ptr2+1
pt4:    dex
        bne     pt1
        jmp     view                    ; never back: the page covers this

; Copies X pages from (ptr1) to (ptr2).
copyx:  ldy     #0
cx1:    lda     (ptr1),y
        sta     (ptr2),y
        iny
        bne     cx1
        inc     ptr1+1
        inc     ptr2+1
        dex
        bne     cx1
        rts

s_rb:   .asciiz "rb"

; What goes to copy_buf (pate, pato, brushes: gmagic_tables.inc), padded
; to its 512 bytes, and the text page image (gmagic_text.inc).
cbtab:
        .include "gmagic_tables.inc"
        .res    512 - 472
txtimg:
        .include "gmagic_text.inc"

; ---------------------------------------------------------------------------
        .segment "CODE"

; The view: a cleared page, picture base, then base+1..cur over it.
view:   jsr     rewind
        jcs     ioerr
        jsr     clear
        ldx     base
        beq     vw2
        stx     cnt
vw1:    jsr     skippic
        jcs     ioerr
        dec     cnt
        bne     vw1
vw2:    lda     base
        sta     k
vw3:    jsr     drawpic
        bcs     ioerr
        lda     k
        cmp     cur
        bcs     keys
        inc     k
        bne     vw3                     ; always

; The keys, once the picture is whole.
keys:   ldy     #API_CGETC              ; the core's: S, the slideshow
        jsr     call
        sta     key
        cmp     #' '
        beq     knext
        and     #$5F                    ; either case, Open-Apple or not
        cmp     #'D'
        beq     kdia
        cmp     #'N'
        beq     knext
        cmp     #'O'
        beq     kover
        lda     key                     ; Escape, Left, Right
        ldx     #0
        ldy     #API_MKEY
        jsr     call
        tax
        beq     keys
        lda     #0                      ; no note
        tax
        beq     leave                   ; always

kdia:   lda     v84only                 ; V84 data: no V82
        bne     keys
        lda     dialect
        eor     #1
        sta     dialect
        jmp     view
knext:  ldx     cur                     ; the next picture, alone
        inx
        cpx     nparts
        bcc     kn1
        ldx     #0                      ; after the last, the first
        cpx     cur
        beq     keys                    ; (a single picture)
        stx     base
        stx     cur
        jmp     view
kn1:    stx     base
        stx     cur
        jsr     clear                   ; the file is already there
        jmp     kdraw
kover:  ldx     cur                     ; the next one over this one
        inx
        cpx     nparts
        bcs     keys
        stx     cur
kdraw:  jsr     drawpic
        bcc     keys
        ; fall through: a read error

ioerr:
bad:    lda     #<m_bad
        ldx     #>m_bad

; The end, good (A/X = 0) or bad (A/X = the note): the file closed, the
; entry reselected, the note written (the read buffer becomes the note
; again), back to the core from wherever the overlay is.
leave:  sta     msg
        stx     msg+1
        ldx     errsp
        txs
        lda     fh
        ora     fh+1
        beq     lv1
        lda     fh
        ldx     fh+1
        ldy     #API_FCLOSE
        jsr     call
lv1:    ldy     #API_RESEL              ; strcpy(reselect, selected->name)
        jsr     field
        jsr     pushax
        lda     sel
        ldx     sel+1
        ldy     #API_STRCPY
        jsr     call
        ldy     #API_NOTE               ; strcpy(note, msg or "")
        jsr     field
        jsr     pushax
        lda     msg
        ldx     msg+1
        bne     lv2
        lda     #<lim                   ; "" (lim starts with 0)
        ldx     #>lim
lv2:    ldy     #API_STRCPY
        ; fall through

; The service at offset Y of the table, A/X its last argument.
call:   pha
        txa
        pha
        jsr     field
        sta     jmpvec+1
        stx     jmpvec+2
        pla
        tax
        pla
        jmp     jmpvec

; A/X = the word at offset Y of the table.
field:  iny
fl2:    lda     $FFFF,y
        tax
        dey
fl1:    lda     $FFFF,y
        rts

; The next byte of the file, carry set at its end or on a read error.
getb:   ldy     bpos
        cpy     blen
        bcc     rdb
        lda     rbuf                    ; fread(note, 1, RBLEN, fh)
        ldx     rbuf+1
        jsr     pushax
        lda     #1
        jsr     pusha0
        lda     #RBLEN
        jsr     pusha0
        lda     fh
        ldx     fh+1
        ldy     #API_FREAD
        jsr     call
        sta     blen
        ldy     #0
        sty     bpos
        cmp     #1                      ; nothing: the end, or an error
        bcs     rdb
        sec
        rts
rdb:    inc     bpos                    ; (Y keeps the byte's place)
        lda     $FFFF,y                 ; the flags are the byte's
        clc
        rts

; fseek(fh, 0, SEEK_SET), the buffer emptied; carry set on a failure.
rewind: lda     fh
        ldx     fh+1
        jsr     pushax
        lda     #0
        sta     sreg
        sta     sreg+1
        sta     bpos
        sta     blen
        tax
        jsr     pusheax
        lda     #SEEK_SET
        ldx     #0
        ldy     #API_FSEEK
        jsr     call
        cmp     #1                      ; 0: done
        txa
        sbc     #0                      ; carry set unless A/X = 0
        rts

; Reads one command and checks it (sections 3, 4, 11): cmd, t, arg, and
; for longer commands val (X low, pattern, character) and yy (Y). Carry
; set on a malformed command, the end of the file or a read error.
getcmd: jsr     getb
        bcs     gc9
        sta     cmd
        beq     gc8                     ; the end byte
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        sta     t
        tax
        lda     cmd
        and     #$0F
        sta     arg
        cmp     lim,x                   ; the argument nibble's limit (0: no
        bcs     gc9                     ; such command)
        lda     lim,x
        cmp     #8
        beq     gc8                     ; one byte: $2c, $4b
        jsr     getb
        bcs     gc9
        sta     val
        ldx     t
        lda     lim,x
        cmp     #2
        beq     gc3                     ; three bytes
        cpx     #6
        lda     val
        bcc     gc2
        cmp     #108                    ; a pattern 0-107
        rts
gc2:    cmp     #$20                    ; a character $20-$7F
        bcc     gcb
        cmp     #$80
        rts
gc3:    lda     arg                     ; X <= 279
        beq     gc4
        lda     val
        cmp     #24
        bcs     gc9
gc4:    jsr     getb
        bcs     gc9
        sta     yy
        cmp     #192                    ; Y <= 191
        rts
gc8:    clc
        rts
gcb:    sec
gc9:    rts

; Skips a picture (already checked); carry set on a read error.
skippic: jsr    getcmd
        bcs     sp9
        lda     cmd
        bne     skippic
sp9:    rts

; Draws the picture at the read position: the state of section 5, then
; each command until the end byte. Carry set on a read error.
drawpic: lda    #$80                    ; black
        sta     colour
        lda     #0
        sta     txl
        sta     txh
        sta     ty
        sta     val                     ; pattern 0
        jsr     hpat
        lda     #5
        sta     brush
        lda     #140                    ; the pen at (140, 6)
        ldx     #0
        ldy     #6
        jsr     lstart
dp1:    jsr     getcmd
        bcs     sp9
        lda     cmd
        beq     sp9                     ; (carry clear)
        jsr     dp2
        jmp     dp1
dp2:    ldx     t                       ; to the handler, back to dp1
        lda     jhi-1,x
        pha
        lda     jlo-1,x
        pha
        rts

; $2c: the colour, used from the next line start.
hcol:   ldx     arg
        lda     coltab,x
        sta     colour
        rts

; $4b: the brush.
hbrush: lda     arg
        sta     brush
        rts

; $1x: the text cursor.
htpos:  lda     val
        sta     txl
        lda     arg
        sta     txh
        lda     yy
        sta     ty
        rts

; $60 p: the pattern, its two row patterns into pat8.
hpat:   ldy     #0
        ldx     val
hpe:    lda     $FFFF,x                 ; pate (copy_buf)
        jsr     hp1
        ldx     val
hpo:    lda     $FFFF,x                 ; pato (copy_buf + 108)
hp1:    asl     a
        asl     a
        tax
        lda     #4
        sta     tmp1
hp2:    lda     ROWS,x
        sta     pat8,y
        inx
        iny
        dec     tmp1
        bne     hp2
        rts

; $8x: the line start (A = X low, X = X high, Y = Y).
hlstart: lda    val
        ldx     arg
        ldy     yy
lstart: sty     peny
        sta     penxl
        stx     penxh
        jsr     div7
        sty     col
        tax
        lda     bitv,x
        ora     #$80
        sta     m
        lda     colour                  ; $2A $55 $AA $D5 alternate
        and     #$7F
        cmp     #$2A
        beq     ls1
        cmp     #$55
        beq     ls1
        lda     #0
        .byte   $2C                     ; BIT abs: skips the lda #$7F
ls1:    lda     #$7F
        sta     alt
        lda     col                     ; an odd column: the other one
        lsr     a
        lda     colour
        bcc     ls2
        eor     alt
ls2:    sta     cb
        rts

; $Ax: a line from the pen (section 6).
hline:  lda     #0
        sta     sx
        sec                             ; |dx|, sx
        lda     val
        sbc     penxl
        sta     axl
        lda     arg
        sbc     penxh
        sta     axh
        bpl     hl1
        inc     sx
        lda     #0
        sec
        sbc     axl
        sta     axl
        lda     #0
        sbc     axh
        sta     axh
hl1:    ldx     #1                      ; |dy|, sy
        lda     yy
        sec
        sbc     peny
        bcs     hl2
        ldx     #$FF
        eor     #$FF                    ; (carry clear)
        adc     #1
hl2:    sta     bb
        stx     sy
        lda     axl                     ; e = |dx| - |dy|
        sec
        sbc     bb
        sta     el
        lda     axh
        sbc     #0
        sta     eh
        lda     axl                     ; |dx| + |dy| steps
        clc
        adc     bb
        sta     nl
        lda     axh
        adc     #0
        sta     nh
        jsr     plot
hl3:    lda     nl
        ora     nh
        beq     hl9
        lda     nl
        bne     hl4
        dec     nh
hl4:    dec     nl
        lda     eh
        bmi     hlv
        lda     el                      ; e >= 0: a pixel across
        sec
        sbc     bb
        sta     el
        bcs     hl5
        dec     eh
hl5:    lda     sx
        bne     hll
        lda     m                       ; right
        asl     a
        bmi     hlr
        ora     #$80
        bne     hlm                     ; always
hlr:    inc     col
        lda     #$81
        bne     hlc                     ; always
hll:    lda     m                       ; left
        lsr     a
        bcs     hlw
        eor     #$C0
        bne     hlm                     ; always
hlw:    dec     col
        lda     #$C0
hlc:    pha                             ; a new byte: the colour bits follow
        lda     cb                      ; the column's parity
        eor     alt
        sta     cb
        pla
hlm:    sta     m
        jmp     hl6
hlv:    lda     el                      ; e < 0: a row down or up
        clc
        adc     axl
        sta     el
        lda     eh
        adc     axh
        sta     eh
        lda     peny
        clc
        adc     sy
        sta     peny
hl6:    jsr     plot
        jmp     hl3
hl9:    lda     val
        sta     penxl
        lda     arg
        sta     penxh
        rts

; The pen's pixel: (old AND NOT m) OR (cb AND m).
plot:   lda     peny
        jsr     rowad
        bcs     pl9
        ldy     col
        lda     m
        sta     tmp3
        lda     cb
        jmp     mix2
pl9:    rts

; A = x mod 7, Y = x div 7, for x = A + 256 X (X 0 or 1). X kept.
div7:   ldy     #0
        cpx     #0
        beq     dv1
        ldy     #36                     ; 256 = 36 x 7 + 4
        clc
        adc     #4
dv1:    cmp     #7
        bcc     dv2
        sbc     #7
        iny
        bne     dv1                     ; always
dv2:    rts

; A = low byte of 7 A, tmp4 = its high byte (A <= 78).
mul7:   sta     tmp2
        lda     #0
        sta     tmp4
        lda     tmp2
        asl     a
        rol     tmp4
        asl     a
        rol     tmp4
        asl     a
        rol     tmp4
        sec
        sbc     tmp2
        bcs     mu1
        dec     tmp4
mu1:    rts

; Z set when the dot (fc, fp) of row fy is white: its bit and the one at
; its left set (bits 0 and 1 at offset 0); a row outside is not white.
fwhite: lda     fy
        jsr     rowad
        bcs     fw9
        ldx     fp
        lda     wmask,x
        sta     tmp3
        ldy     fc
        and     (ptr1),y
        cmp     tmp3
        rts
fw9:    lda     #1
        rts

; ---------------------------------------------------------------------------
        .segment "GMLOW"

; $Cx: the brush, its four quarters (section 8).
hstamp: lda     val
        ldx     arg
        jsr     div7
        sta     bsh
        sty     scol
        lda     #0
        sta     xorf
        sta     bq
        lda     brush                   ; ptr2 = its first quarter
        asl     a
        asl     a
        asl     a
        asl     a
        asl     a
        adc     bbase                   ; (carry clear: brush <= 7)
        sta     ptr2
        lda     bbase+1
        adc     #0
        sta     ptr2+1
hs1:    lda     bq                      ; right quarters one column on
        and     #1
        clc
        adc     scol
        sta     bcol
        lda     bq                      ; lower quarters eight rows down
        and     #2
        asl     a
        asl     a
        adc     yy
        sta     btop
        jsr     stamp
        lda     ptr2
        clc
        adc     #8
        sta     ptr2
        bcc     hs2
        inc     ptr2+1
hs2:    inc     bq
        lda     bq
        cmp     #4
        bne     hs1
        rts

; $30 c / $50 c: a character at the text cursor, which moves 8 dots on.
hxtext: lda     #1
        .byte   $2C                     ; BIT abs: skips the lda #0
htext:  lda     #0
        sta     xorf
        lda     txh                     ; past the right edge: not drawn
        cmp     #2
        bcs     ht2
        tax
        lda     txl
        jsr     div7
        cpy     #41
        bcs     ht2
        sta     bsh
        sty     bcol
        lda     ty
        sta     btop
        lda     val                     ; glyph g = c - $20: the text page,
        sec                             ; 14 glyphs a block, block 5 skipped
        sbc     #$20                    ; (the row patterns)
        ldx     #0
ht0:    cmp     #14
        bcc     ht1
        sbc     #14
        inx
        bne     ht0                     ; always
ht1:    asl     a
        asl     a
        asl     a
        sta     ptr2
        cpx     #5
        bcc     ht4
        inx
ht4:    txa                             ; $0400 + 128 block + 8 (g mod 14)
        lsr     a
        ora     #$04
        sta     ptr2+1
        bcc     htd
        lda     ptr2
        ora     #$80
        sta     ptr2
htd:    jsr     stamp
ht2:    lda     txl
        clc
        adc     #8
        sta     txl
        bcc     ht3
        inc     txh
ht3:    rts

; Stamps the 8-row bitmap at (ptr2) at column bcol, shifted by bsh dots,
; from row btop (section 8): each dot takes the pattern's bit and its byte
; the pattern's bit 7, or (xorf) is XORed in.
stamp:  lda     #0
        sta     brow
st1:    ldy     brow
        lda     (ptr2),y
        and     #$7F
        sta     wl
        lda     #0
        sta     wh
        ldx     bsh
        beq     st3
st2:    asl     wl
        rol     wh
        dex
        bne     st2
st3:    asl     wl                      ; wh = the dots of the next column,
        rol     wh                      ; wl = those of this one
        lsr     wl
        lda     btop
        clc
        adc     brow
        jsr     rowad
        bcs     st4                     ; a row out of the page: dropped
        ldy     bcol
        lda     wl
        jsr     put
        iny
        lda     wh
        jsr     put
st4:    inc     brow
        lda     brow
        cmp     #8
        bne     st1
        rts

; One byte of a bitmap: A = its dots, Y = the column; none: untouched.
put:    beq     pu9
        ldx     xorf
        bne     pux
        ora     #$80
        ; fall through

; (ptr1),y = old XOR ((old XOR P) AND A), P the pattern byte of column Y
; on the row rowad set: the bits of A take the pattern's.
mixp:   sta     tmp3
        tya
        and     #3
        ora     rowpar
        tax
        lda     pat8,x
mix2:   eor     (ptr1),y                ; the same with A as the source
        and     tmp3
        eor     (ptr1),y
        sta     (ptr1),y
pu9:    rts
pux:    eor     (ptr1),y
        sta     (ptr1),y
        rts

; ptr1 = row A's first byte, rowpar = 4 x (A AND 1); carry set when the
; row is outside the page. Rows 192-255 as PICDRAWF and PICDRAWH address
; them (section 11): row 192 + k at $2020 + 4 (k AND 7) + (k / 16 AND 3)
; when bit 3 of k is clear, outside ($A0xx) otherwise. X and Y kept.
rowad:  sta     tmp1
        and     #1
        asl     a
        asl     a
        sta     rowpar
        lda     tmp1
        cmp     #192
        bcs     ra2
        jsr     ra4                     ; $20 + 4 (y AND 7) + (y / 16 AND 3)
        sta     ptr1+1
        lda     tmp1                    ; + $80 for bit 3, + 40 (y / 64)
        and     #8
        beq     ra1
        lda     #$80
ra1:    bit     tmp1
        bmi     ra3
        bvc     ra5
        ora     #40
        bne     ra5                     ; always
ra3:    ora     #80
ra5:    sta     ptr1
        clc
        rts
ra2:    sbc     #192                    ; (carry set) k
        sta     tmp1
        and     #8
        bne     ra9                     ; outside (carry still set)
        lda     tmp1
        jsr     ra4
        sta     ptr1
        lda     #$20
        sta     ptr1+1
        clc
ra9:    rts
ra4:    pha
        and     #7
        asl     a
        asl     a
        sta     tmp2
        pla
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        and     #3
        ora     tmp2
        ora     #$20
        rts

; $Ex: the flood fill of the dialect (sections 9 and 10).
hfill:  lda     val
        ldx     arg
        jsr     div7
        sta     fp
        sty     fc
        lda     yy
        sta     fy
        lda     dialect
        beq     hf82
hf1:    jsr     fwhite                  ; V84: up while white; a non-white
        bne     hf2                     ; pixel: the row below, untested
        lda     fy
        beq     hfrow
        dec     fy
        jmp     hf1
hf2:    inc     fy
        bne     hfrow                   ; always (<= 192)
hf82:   lda     fy                      ; V82: row 0 starts on row X mod 7
        bne     hf3
        lda     fp
        sta     fy
        bpl     hftest                  ; always
hf3:    lda     fy                      ; up while the pixel above is white
        beq     hftest
        dec     fy
        jsr     fwhite
        beq     hf3
        inc     fy
hftest: lda     fy                      ; V84 stops at row 192, V82 from it
        cmp     #192
        bcc     hf4
        bne     hf5
hf9:    rts
hf5:    lda     dialect
        beq     hf9
hf4:    jsr     fwhite
        bne     hf9
hfrow:  jsr     frow
        bcs     hf9
        lda     dialect
        bne     hfn84

        ; V82: the middle in 8-bit arithmetic (section 10).
        lda     #7                      ; A = 7 when rc - lc - 1 < 0,
        ldx     rc                      ; else 7 (rc - lc + 1) mod 256
        cpx     lc
        beq     hfa
        txa
        sec
        sbc     lc
        clc
        adc     #1
        jsr     mul7
hfa:    sta     va
        lda     #7                      ; Rc = 7 - right border
        sec
        sbc     rr
        sta     vrc
        ldx     lp                      ; Ls: lo in the start byte, else
        lda     lst                     ; the border itself
        bne     hfb
        dex
hfb:    stx     vls
        lda     va                      ; (A - Rc - Ls - (A < Rc)) mod 256:
        sec                             ; the borrow of the first subtraction
        sbc     vrc                     ; is that last term
        sbc     vls
        lsr     a
        sta     half
        lda     lc                      ; X' = 7 lc + Ls + half
        jsr     mul7
        clc
        adc     vls
        bcc     hfc
        inc     tmp4
hfc:    clc
        adc     half
        bcc     hfd
        inc     tmp4
        bcs     hfd                     ; always

        ; V84: the middle of the two border dots (section 9).
hfn84:  lda     lc
        clc
        adc     rc
        jsr     mul7
        ldx     lp                      ; + L = lp - 1
        dex
        stx     tmp2
        clc
        adc     tmp2
        bcc     hfe
        inc     tmp4
hfe:    ldx     rr                      ; + R (6 at the right edge)
        cpx     #7
        bne     hff
        dex
hff:    stx     tmp2
        clc
        adc     tmp2
        bcc     hfg
        inc     tmp4
hfg:    lsr     tmp4
        ror     a
hfd:    ldx     tmp4                    ; X' (always on the screen; a value
        cpx     #2                      ; past it would end the fill)
        jcs     hf9
        jsr     div7
        cpy     #40
        jcs     hf9
        sta     fp
        sty     fc
        inc     fy
        jmp     hftest

; Fills the run of row fy through (fc, fp) (the same for both dialects:
; the dot is white for V82, and V84's untested row starts the scan on the
; dot itself): lc, rc, lp, rr and lst for the middle. Carry set if the
; row is outside the page.
frow:   lda     fy
        jsr     rowad
        jcs     fr9
        ldy     fc
        lda     (ptr1),y
        sta     fs
        ldx     fp                      ; the highest clear bit in 0..p
fr1:    lda     bitv,x
        and     fs
        beq     fr2
        dex
        bpl     fr1
fr2:    inx
        stx     lp                      ; + 1 (0: none)
        stx     lst
        ldx     fp                      ; the lowest clear bit in p..6
fr3:    lda     bitv,x
        and     fs
        beq     fr4
        inx
        cpx     #7
        bne     fr3
fr4:    stx     rr                      ; (7: none)
        ldx     lp                      ; the dots between (none when the
        lda     lowm,x                  ; dot itself is clear), and bit 7
        eor     #$FF
        ldx     rr
        and     lowm,x
        ora     #$80
        jsr     mixp
        lda     fc
        sta     lc
        sta     rc
        lda     lst
        bne     fr8
        ldy     fc                      ; to the left: whole bytes take the
fr5:    dey                             ; pattern, the border byte its dots
        bmi     fr7                     ; above the border
        lda     (ptr1),y
        ora     #$80
        cmp     #$FF
        bne     fr6
        jsr     mixp
        jmp     fr5
fr6:    sta     fs
        ldx     #6
fr61:   lda     bitv,x
        and     fs
        beq     fr62
        dex
        bpl     fr61
fr62:   inx
        stx     lp
        sty     lc
        lda     lowm,x
        eor     #$FF
        jsr     mixp
        jmp     fr8
fr7:    lda     #1                      ; past column 0: L = 0
        sta     lp
        lda     #0
        sta     lc
fr8:    ldx     rr
        cpx     #7
        bne     fr10
        ldy     fc                      ; to the right
fr81:   iny
        cpy     #40
        beq     fr84
        lda     (ptr1),y
        ora     #$80
        cmp     #$FF
        bne     fr82
        jsr     mixp
        jmp     fr81
fr82:   sta     fs
        ldx     #0
fr83:   lda     bitv,x
        and     fs
        beq     fr85
        inx
        bne     fr83
fr85:   stx     rr
        sty     rc
        lda     lowm,x
        ora     #$80
        jsr     mixp
        clc
        rts
fr84:   lda     #39                     ; past column 39 (rr stays 7)
        sta     rc
fr10:   clc
fr9:    rts

; The whole of page 1 white ($FF, the screen holes too), the main bank's
; routing.
clear:  lda     #0
        sta     $C000                   ; 80STORE off
        sta     $C002                   ; RAMRD main
        sta     $C004                   ; RAMWRT main
        sta     $C054                   ; PAGE2 off
        sta     ptr1
        lda     #$20
        sta     ptr1+1
        ldy     #0
        lda     #$FF
cl1:    sta     (ptr1),y
        iny
        bne     cl1
        inc     ptr1+1
        ldx     ptr1+1
        cpx     #$40
        bne     cl1
        ; fall through: on the screen, drawn as it is built

; Full-screen hi-res page 1, forty columns (newsroom.s's sequence).
show:   lda     #0
        sta     $C000
        sta     $C00D
        sta     $C05E
        sta     $C05F
        sta     $C05E
        sta     $C05F
        sta     $C00C
        sta     $C057
        sta     $C054
        sta     $C052
        sta     $C050
        rts

        .segment "RODATA"
m_bad:  .asciiz "Not a whole Graphics Magician picture, or I/O error."
; The argument nibble's limit + 1 by command (0: not a command): $1x
; X high 0-1, $2c $4b 0-7, $30 $50 $60 0, $8x $Ax $Cx $Ex 0-1. Three
; bytes for 2, two for 1, one for 8.
lim:    .byte   0, 2, 8, 1, 8, 1, 1, 0, 2, 0, 2, 0, 2, 0, 2, 0
; The handlers, minus one (rts), by high nibble 1-14.
jlo:    .byte   <(htpos-1), <(hcol-1), <(hxtext-1), <(hbrush-1), <(htext-1), <(hpat-1), 0
        .byte   <(hlstart-1), 0, <(hline-1), 0, <(hstamp-1), 0, <(hfill-1)
jhi:    .byte   >(htpos-1), >(hcol-1), >(hxtext-1), >(hbrush-1), >(htext-1), >(hpat-1), 0
        .byte   >(hlstart-1), 0, >(hline-1), 0, >(hstamp-1), 0, >(hfill-1)
; The Applesoft HCOLOR= bytes (section 5).
coltab: .byte   $00, $2A, $55, $7F, $80, $AA, $D5, $FF
bitv:   .byte   $01, $02, $04, $08, $10, $20, $40
lowm:   .byte   $00, $01, $03, $07, $0F, $1F, $3F, $7F   ; bits below n
wmask:  .byte   $03, $03, $06, $0C, $18, $30, $60        ; a dot and its left one


        .segment "GMBSS"
rbuf:   .res    2
bbase:  .res    2                       ; the brushes, in copy_buf
k:      .res    1                       ; the picture being drawn
cnt:    .res    1
