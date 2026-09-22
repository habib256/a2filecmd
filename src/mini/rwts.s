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
        ; Every sector read, written or formatted turns the last cell of
        ; row 23 between / and \ (a space in every bar): a delete's audit
        ; or a batch of a copy is seconds of disk with no other change.
        ; Straight to the text page: the next present puts the image's
        ; space back. Some 20 cycles, far inside the gap between sectors.
        lda     #$AF
        cmp     $07F7
        bne     @spun
        lda     #$DC
@spun:  sta     $07F7
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
        lda     iob+1
        ldy     iob
        jsr     RWTS_ENTRY
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
