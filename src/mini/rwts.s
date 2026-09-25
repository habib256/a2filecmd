; rwts.s -- the only door to the disk: DOS 3.3's own RWTS.
;
; The IOB layout and the two entry points are the ones in the Apple DOS
; manual, chapter 9, checked against a running DOS in POM2 rather than
; assumed. DOS keeps its own IOB and DCT: motor state, slot and the
; previous drive stay DOS's business. READ and WRITE are issued from
; everywhere; FORMAT, every track gone, only from format.s after its
; prompt.
;
; Returns A = 0 and Z set on success, A = 1 and Z clear on failure. A
; failure is never an end of file: rwts_error holds DOS's return code so
; the caller can tell write protection ($10) from anything else.

        .include "mini.inc"

        .export read_sector, write_sector, read_into, write_into
        .export rwts_format, rwts_error, _rwts_error

        .import buffer, rwts_buf, drive, track, sector

        .segment "BSS"
rwts_error:     .res 1
_rwts_error     = rwts_error
command:        .res 1

        .segment "CODE"

; read_sector / write_sector move buffer; read_into / write_into move
; the page rwts_buf points at, set by the caller. The 2:1 skew leaves
; about a sector slot between two consecutive sectors of a chain, and
; a 256-byte copy in that gap is what turns it into a lost turn.
; The sign of life, the last cell of row 23: a space in every bar, so
; the next present puts it back on its own. Every sector read, written
; or formatted turns it between / and \ -- a delete's audit or a batch
; of a copy is seconds of disk with no other change on screen. Straight
; to the text page, some 20 cycles, far inside the gap between sectors.
; lend_hook below also runs it from inside DOS during READ and FORMAT.
        .export heartbeat
heartbeat:
        lda     #$AF
        cmp     $07F7
        bne     @spun
        lda     #$DC
@spun:  sta     $07F7
        rts

read_into:
        lda     #RWTS_READ
        bne     rwts            ; always taken

write_into:
        lda     #RWTS_WRITE
        bne     rwts

rwts_format:
        lda     #RWTS_FORMAT
        bne     with_buffer     ; FORMAT ignores the buffer; keep it defined

read_sector:
        lda     #RWTS_READ
        bne     with_buffer

write_sector:
        lda     #RWTS_WRITE
with_buffer:
        ldx     #<buffer
        stx     rwts_buf
        ldx     #>buffer
        stx     rwts_buf+1
rwts:
        sta     command
        jsr     heartbeat
        lda     #0
        sta     rwts_error
        jsr     RWTS_LOCATE_IOB
        sty     iob
        sta     iob+1
        ldy     #IOB_DRIVE
        lda     drive
        sta     (iob),y
        iny                     ; volume 0: accept whatever is mounted;
        lda     #0              ; FORMAT stamps DOS's default instead
        ldx     command
        cpx     #RWTS_FORMAT
        bne     @volume
        lda     #DOS_VOLUME
@volume:
        sta     (iob),y
        iny
        lda     track
        sta     (iob),y
        iny
        lda     sector
        sta     (iob),y
        ldy     #IOB_BUFFER
        lda     rwts_buf
        sta     (iob),y
        iny
        lda     rwts_buf+1
        sta     (iob),y
        iny                     ; bytes 10 and 11 are unused by READ/WRITE
        lda     #0
        sta     (iob),y
        iny
        sta     (iob),y
        iny
        lda     command
        sta     (iob),y
; A READ or FORMAT lends one of DOS's own JSRs to lend_hook for this
; call only (see lend_site below). The three bytes are checked first:
; any other DOS runs exactly as before, and so does every WRITE. iob
; now points at the site, or at lend_call itself when nothing is lent,
; so the restore after the call is one unconditional loop: on a site it
; puts DOS's operand back, on lend_call it rewrites two bytes with
; themselves. RWTS keeps out of $80-$9F, so iob survives the call.
        ldx     command
        dex                     ; READ 0, WRITE 1, FORMAT 3
        cpx     #RWTS_WRITE-1
        beq     @alone          ; a write runs without a hook
        lda     lend_site,x
        sta     iob
        lda     lend_site+1,x
        sta     iob+1
        ldy     #0
@check: lda     (iob),y
        cmp     lend_sig,x
        bne     @alone          ; another DOS: leave it alone
        sta     lend_call,y     ; JSR and DOS's destination, for the hook
        inx
        iny
        cpy     #3
        bne     @check
        dey
        dey
        lda     #<lend_hook
        sta     (iob),y
        iny
        lda     #>lend_hook     ; never 0: the resident is above $4000
        sta     (iob),y
        bne     @call           ; always taken
@alone: lda     #<lend_call
        sta     iob
        lda     #>lend_call
        sta     iob+1
@call:  jsr     RWTS_LOCATE_IOB ; the IOB address again, for RWTS
        jsr     RWTS_ENTRY
        php                     ; RWTS's carry, through the restore
        ldy     #2
@back:  lda     lend_call,y     ; DOS's operand back the instant RWTS
        sta     (iob),y         ; returns: DOS takes this memory for
        dey                     ; its file buffers when A2FC Mini quits
        bne     @back
        plp
        bcc     @ok
        jsr     RWTS_LOCATE_IOB ; carry set: read DOS's reason for it
        sty     iob
        sta     iob+1
        ldy     #IOB_RETURN
        lda     (iob),y
        sta     rwts_error
        lda     #1
        rts
@ok:
        lda     #0
        rts

; ---------------------------------------------------------------------
; A sign of life inside one RWTS call. RWTS gives nothing back until it
; is done: an 18-second FORMAT, or a READ of a disk it cannot read,
; which tries 48 address fields, recalibrates, and tries 48 more before
; it reports the error, some five seconds. Two JSRs of DOS 3.3's RWTS,
; measured in POM2 with a per-instruction trace:
;   $BDC4 JSR $B944  the READ/WRITE retry loop's call to RDADR16, once
;                    per address field tried: about every 25 ms on a
;                    blank surface, before each one on a good disk
;   $BED6 JSR $BE5A  the FORMAT per-track loop's seek, 35 times
; For a READ (the first) or a FORMAT (the second), and only for the
; duration of that call, the operand points here: the cell turns, A, X
; and Y are kept (heartbeat moves the carry, which neither routine reads
; before setting it: RDADR16 opens with LDY, the seek with ROR), and
; DOS's own routine runs as it always did, its carry and registers
; handed back untouched. Before RDADR16 the hook costs some
; 45 cycles of a wait for the next address field, and 6 after it
; returns, far inside the gap before the data field; before the seek
; it costs nothing that matters. A WRITE never runs with it.
; ---------------------------------------------------------------------
lend_hook:
        pha
        jsr     heartbeat
        pla
lend_call:
        jsr     $0000           ; DOS's destination, copied from the site
        rts

        .segment "RODATA"
; Where the two JSRs are, indexed by command-1 (READ 0, FORMAT 3), and
; the three bytes each must hold before it is lent.
lend_site:
        .word   $BDC4           ; READ: JSR RDADR16
        .byte   0               ; (WRITE: never looked up)
        .word   $BED6           ; FORMAT: JSR SEEK
lend_sig:
        .byte   $20, $44, $B9   ; JSR $B944
        .byte   $20, $5A, $BE   ; JSR $BE5A
