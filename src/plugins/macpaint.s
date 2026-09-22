; macpaint.s -- the decoder of the MacPaint viewer, and the screen around it.
;
; A MacPaint picture is 720 lines of 72 bytes, each packed on its own with
; PackBits (tools/macpaint_ref.py has the format). mp_scan unpacks all of
; them without storing anything, and notes where every 48th line starts;
; mp_draw unpacks 192 of them from one of those places and writes dots 8 to
; 567 to the double hi-res page: the auxiliary byte with RAMWRT on for its
; single store, interrupts off, as in arlequin.s. Only writes move, so this
; code, in the main bank below $2000, keeps running where it is.
; Plain 6502 throughout: the 6502 edition assembles this file too.
;
; The entry point is here as well, and reaches the program through the
; service table the way cc65 code would: arguments pushed on the C stack,
; the last one in A/X. Built with MP_TEST (tools/test_macpaint.py), only
; the decoder is assembled, and the harness supplies mp_read.

        .export _mp_scan, _mp_draw
        .export _mp_pos, _mp_ck
        .importzp ptr1, ptr4, tmp1, tmp2, sreg
        .segment "CODE"

.ifdef MP_TEST
        .import _mp_read, _mp_buf
.else
        .export _plugin_entry
        .import pushax, pusheax, jmpvec
        .import _mp_ofs                 ; macpaint.c: the table offsets
MPO_FULL    = _mp_ofs+0
MPO_BUF     = _mp_ofs+1
MPO_NOTE    = _mp_ofs+2
MPO_RESELECT= _mp_ofs+3
MPO_SELECTED= _mp_ofs+4
MPO_FOPEN   = _mp_ofs+5
MPO_FREAD   = _mp_ofs+6
MPO_FSEEK   = _mp_ofs+7
MPO_FCLOSE  = _mp_ofs+8
MPO_STRCPY  = _mp_ofs+9
MPO_CGETC   = _mp_ofs+10
MPO_MKEY    = _mp_ofs+11
MPO_RAMFMT  = _mp_ofs+12
MPO_SET     = _mp_ofs+13

; The refusal, and strcpy(api->note, A/X).
bad:    lda     #<m_bad
        ldx     #>m_bad
note:   pha                             ; strcpy(api->note, A/X)
        txa
        pha
        ldy     MPO_NOTE
        jsr     field
        jsr     pushax
        pla
        tax
        pla
        ldy     MPO_STRCPY
        jmp     call

; void plugin_entry(const struct A2fcApi* api)
_plugin_entry:
        sta     api
        stx     api+1
        ldy     MPO_BUF
        jsr     field
        sta     _mp_buf
        stx     _mp_buf+1
        ldy     MPO_FULL
        jsr     field
        jsr     pushax
        lda     #<rb
        ldx     #>rb
        ldy     MPO_FOPEN
        jsr     call
        sta     in
        stx     in+1
        ora     in+1
        beq     bad                     ; nothing opened, nothing to close
        ; The header: a MacBinary one says PNTG at +65; a MacPaint one
        ; starts with a version, 0 or 2, on four bytes.
        lda     #128
        jsr     readn
        cmp     #128
        bne     badc
        lda     _mp_buf
        sta     ptr4
        lda     _mp_buf+1
        sta     ptr4+1
        ldy     #0
        lda     (ptr4),y
        bne     badc
        ldy     #68
        ldx     #3
mbin:   lda     (ptr4),y
        cmp     pntg,x
        bne     mpnt
        dey
        dex
        bpl     mbin
        lda     #<640
        ldx     #>640
        bne     start                   ; always
badc:   jsr     close                   ; within a branch of the checks
        jmp     bad
mpnt:   ldy     #1
        lda     (ptr4),y
        iny
        ora     (ptr4),y
        bne     badc
        iny
        lda     (ptr4),y
        and     #$FD
        bne     badc
        lda     #<512
        ldx     #>512
start:  jsr     seek
        bcs     badc
        jsr     _mp_scan
        bcs     badc

        ; From here on the auxiliary bank is written: /RAM is rebuilt,
        ; whatever comes next. The first view is drawn behind the text
        ; screen and lit up whole.
        jsr     _mp_main_bank
        lda     #0
        sta     top
        jsr     view
        bcs     cut
        jsr     _mp_show
keys:   ldy     MPO_CGETC
        jsr     call
        sta     key
        ldy     MPO_MKEY               ; Escape, or a neighbour: 1
        jsr     call
        tax
        bne     done
        lda     key
        and     #$7F
        cmp     #$0B                    ; Up, as cc65 reads it
        beq     up
        cmp     #$0A                    ; Down
        bne     keys
        lda     top                     ; in 48 lines: 0 to 11
        cmp     #11
        beq     keys
        adc     #2                      ; carry clear: below 11
        cmp     #12
        bcc     move
        lda     #11
        bne     move
up:     lda     top
        beq     keys
        sbc     #2                      ; carry set by the cmp
        bcs     move
        lda     #0
move:   sta     top
        jsr     view
        bcc     keys
        bcs     cut
done:   clc
cut:    php                             ; carry: a view could not be read
        jsr     close
        ldy     MPO_RESELECT
        jsr     field
        jsr     pushax
        ldy     MPO_SELECTED           ; the entry starts with its name
        jsr     field
        ldy     MPO_STRCPY
        jsr     call
        ldy     MPO_RAMFMT
        jsr     call
        tax
        beq     kept
        lda     #<m_ram
        ldx     #>m_ram
        jsr     note
kept:   plp
        bcc     out
        lda     #<m_cut
        ldx     #>m_cut
        jmp     note
out:    rts

; The view from line top * 48: its position set, then drawn. Carry set on
; a failure.
view:   lda     top
        asl     a
        tax
        lda     _mp_ck,x
        pha
        lda     _mp_ck+1,x
        tax
        pla
        jsr     seek
        bcs     out
        jmp     _mp_draw

; fseek(in, A/X, SEEK_SET); carry set unless it answered 0. mp_pos
; follows: getb counts from there, and refuses to pass 64 KB.
seek:   sta     _mp_pos
        stx     _mp_pos+1
        pha
        txa
        pha
        jsr     pushin
        lda     #0
        sta     sreg
        sta     sreg+1
        pla
        tax
        pla
        jsr     pusheax
        lda     MPO_SET
        ldx     #0
        ldy     MPO_FSEEK
        jsr     call
        stx     tmp1
        ora     tmp1
        cmp     #1                      ; carry: not zero
        rts

pushin: lda     in
        ldx     in+1
        jmp     pushax

; fclose(in)
close:  lda     in
        ldx     in+1
        ldy     MPO_FCLOSE
        bne     call                    ; always

; The refill getb calls: up to 255 bytes into copy_buf, 0 at the end of the
; file or on an error -- either way the stream is over.
mp_read:
        lda     #255
; fread(copy_buf, 1, A, in): the count in A. Every read also turns the
; resident's activity cell ($06F7, row 21) between / and \: the scan and
; the drawing are seconds behind the Loading screen (see spin.h).
readn:  pha
        lda     #$AF
        cmp     $06F7
        bne     spun
        lda     #$DC
spun:   sta     $06F7
        lda     _mp_buf
        ldx     _mp_buf+1
        jsr     pushax
        lda     #1
        ldx     #0
        jsr     pushax
        pla
        ldx     #0
        jsr     pushax
        lda     in
        ldx     in+1
        ldy     MPO_FREAD
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
field:  lda     api
        sta     ptr1
        lda     api+1
        sta     ptr1+1
        lda     (ptr1),y
        pha
        iny
        lda     (ptr1),y
        tax
        pla
        rts

        .segment "RODATA"
rb:     .asciiz "rb"
pntg:   .byte   "PNTG"
m_bad:  .asciiz "Not a whole MacPaint picture."
m_cut:  .asciiz "Picture could not be read."
m_ram:  .asciiz "/RAM rebuilt."
        .segment "CODE"
_mp_read = mp_read
.endif

; unsigned char mp_scan(void): the 720 lines from the file position in
; mp_pos, which is kept up to date. 1 when every line unpacked to exactly 72
; bytes; 0 otherwise -- a cut stream, a packet that runs past its line, or a
; file past 64 KB; the carry is set with the 0. mp_ck gets the position of lines 0, 48, 96... 672.
_mp_scan:
        jsr     reset
        sta     grp                     ; A = 0
sgrp:   ldx     grp
        lda     _mp_pos
        sta     _mp_ck,x
        lda     _mp_pos+1
        sta     _mp_ck+1,x
        lda     #48
        sta     sub
sline:  jsr     line
        bcs     fail
        dec     sub
        bne     sline
        lda     grp
        adc     #2                      ; carry clear from line
        sta     grp
        cmp     #30                     ; fifteen groups: 720 lines
        bne     sgrp
ok:     lda     #1
        ldx     #0
        clc
        rts
fail:   lda     #0
        tax
        rts

; unsigned char mp_draw(void): 192 lines from the file position the caller
; has just set, to screen rows 0-191. 1 when all came, 0 (carry set)
; otherwise.
_mp_draw:
        jsr     reset
        sta     row                     ; A = 0
drow:   jsr     line
        bcs     fail
        lda     row
        jsr     setrow
        ; Line bytes 1 to 70, eight dots each, leftmost first, become 80
        ; bytes of seven dots, leftmost in bit 0, 1 lit where MacPaint has
        ; 1 black. A carries the source bits over a sentinel bit, tmp1
        ; gathers the output ones from the top, tmp2 counts them.
        ldy     #0                      ; the byte column
        sty     half
        ldx     #1
        lda     #7
        sta     tmp2
cbyte:  lda     lbuf,x
        inx
        eor     #$FF
        sec
        rol     a                       ; the first dot in carry, a sentinel in bit 0
cbit:   ror     tmp1
        dec     tmp2
        bne     cnext
        pha
        lda     #7
        sta     tmp2
        lda     tmp1
        lsr     a                       ; seven dots in bits 0-6, bit 7 clear
        sta     outb
        lda     half
        eor     #1
        sta     half
        beq     wmain                   ; 1: the auxiliary byte, 0: the main one
        lda     outb
        php
        sei
        sta     $C005                   ; RAMWRT on: the auxiliary byte
storea: sta     $2000,y                 ; patched: this row
        sta     $C004                   ; RAMWRT off
        plp
        pla
        jmp     cnext
wmain:  lda     outb
storem: sta     $2000,y                 ; patched: this row, the main byte
        iny
        pla
cnext:  asl     a
        bne     cbit                    ; zero: the sentinel went out
        cpx     #71
        bne     cbyte
        inc     row
        lda     row
        cmp     #192
        bne     drow
        beq     ok

; Unpacks one line into lbuf. Carry set when the stream ran out or a packet
; ran past the 72 bytes; X and Y are lost.
line:   ldx     #0
lnext:  jsr     getb
        bcs     lerr
        tay
        bmi     lrun
        iny                             ; n + 1 bytes as they are
        sty     cnt
llit:   jsr     getb
        bcs     lerr
        cpx     #72
        bcs     lerr
        sta     lbuf,x
        inx
        dec     cnt
        bne     llit
        beq     lchk
lrun:   cpy     #$80
        beq     lnext                   ; $80: nothing
        tya
        eor     #$FF
        adc     #1                      ; carry set from cpy: 257 - n
        sta     cnt
        jsr     getb
        bcs     lerr
lrl:    cpx     #72
        bcs     lerr
        sta     lbuf,x
        inx
        dec     cnt
        bne     lrl
lchk:   cpx     #72
        bne     lnext
        clc
lerr:   rts

; A = 0; the buffer is empty, the next getb reads.
reset:  lda     #0
        sta     at
        sta     have
        rts

; The next stream byte in A, carry clear; carry set at the end, or when the
; position would pass 64 KB. A refill is the C of mp_read (macpaint.c),
; which may use any register and the zero page: X, the line position, is
; put back after it.
getb:   ldy     at
        cpy     have
        bne     fetch
        stx     savex
        jsr     _mp_read
        ldx     savex
        sta     have
        lda     _mp_buf
        sta     ptr4
        lda     _mp_buf+1
        sta     ptr4+1
        ldy     #0
        sty     at
        lda     have
        bne     fetch
        sec
        rts
fetch:  inc     at
        inc     _mp_pos
        bne     got
        inc     _mp_pos+1
        bne     got
        sec
        rts
got:    lda     (ptr4),y
        clc
        rts

; setrow: A = the screen row; both stores patched with its address. A hi-res
; row is $2000 + (y AND 7) * $400 + the text row base of y / 8, which is
; ((y / 8) MOD 8) * $80 + (y / 64) * $28.
setrow: pha
        lsr     a
        lsr     a
        lsr     a
        tay                             ; y / 8
        and     #7
        lsr     a                       ; carry: an odd text row, + $80
        sta     hi
        lda     #0
        bcc     even
        lda     #$80
even:   sta     lo
        tya
        lsr     a
        lsr     a
        lsr     a
        tay                             ; y / 64, 0 to 2
        beq     third
tl:     lda     lo
        clc
        adc     #$28
        sta     lo
        dey
        bne     tl
third:  pla
        and     #7
        asl     a
        asl     a
        clc
        adc     hi
        adc     #$20
        sta     storem+2
.ifdef MP_TEST
        adc     #$40                    ; sim65 has no auxiliary bank: $6000 up
.endif
        sta     storea+2
        lda     lo
        sta     storea+1
        sta     storem+1
        rts

; void mp_show(void): the picture on the air, double hi-res in black and
; white. On an RGB card (Le Chat Mauve, Video-7) the AN3 latch, clocked by
; the $C05E -> $C05F edge with 80COL as its data, is given 0 twice: BW560,
; as purple.s sets it. $C05E is then written once more, alone, to arm
; DHIRES with 80COL on. Without such a card the page shows in the
; machine's own double hi-res, where the dots come out as they would in
; any black and white picture.
_mp_show:
        lda     #0
        sta     $C000                   ; 80STORE off
        sta     $C00C                   ; 80COL off: the latch data, 0
        sta     $C05E
        sta     $C05F                   ; one edge
        sta     $C05E
        sta     $C05F                   ; two: the latch is 00, BW560
        sta     $C00D                   ; 80COL on
        sta     $C05E                   ; DHIRES on, and no edge with it
        sta     $C057                   ; hi-res
        sta     $C054                   ; page 1
        sta     $C052                   ; mixed text off
        sta     $C050                   ; graphics
        rts

; void mp_main_bank(void): $2000-$3FFF on the main bank for reading and
; writing, whatever a picture seen earlier left armed.
_mp_main_bank:
        lda     #0
        sta     $C054                   ; PAGE2 off
        sta     $C000                   ; 80STORE off
        sta     $C002                   ; RAMRD main
        sta     $C004                   ; RAMWRT main
        rts

        .segment "BSS"
.ifndef MP_TEST
api:    .res 2
in:     .res 2
_mp_buf: .res 2
top:    .res 1
key:    .res 1
.endif
_mp_pos: .res 2                         ; the file position of the next byte
_mp_ck: .res 30                         ; where lines 0, 48... 672 start
lbuf:   .res 72
grp:    .res 1
sub:    .res 1
row:    .res 1
half:   .res 1
outb:   .res 1
cnt:    .res 1
at:     .res 1
have:   .res 1
savex:  .res 1
hi:     .res 1
lo:     .res 1
