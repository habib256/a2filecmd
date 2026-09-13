; rwts.s -- the only door to the disk: DOS 3.3's own RWTS.
;
; The IOB layout and the two entry points are the ones in the Apple DOS
; manual, chapter 9, checked against a running DOS in POM2 rather than
; assumed. DOS keeps its own IOB and DCT: motor state, slot and the
; previous drive stay DOS's business. Only READ and WRITE are ever
; issued -- this program has no FORMAT entry point at all.
;
; Returns A = 0 and Z set on success, A = 1 and Z clear on failure. A
; failure is never an end of file: rwts_error holds DOS's return code so
; the caller can tell write protection ($10) from anything else.

        .include "mini.inc"

        .export read_sector, write_sector, rwts_error, _rwts_error

        .import buffer, drive, track, sector
        .import save_holes, restore_holes

        .segment "BSS"
rwts_error:     .res 1
_rwts_error     = rwts_error
command:        .res 1

        .segment "CODE"

read_sector:
        lda     #RWTS_READ
        bne     rwts            ; always taken

write_sector:
        lda     #RWTS_WRITE
rwts:
        sta     command
        lda     #0
        sta     rwts_error
        jsr     RWTS_LOCATE_IOB
        sty     iob
        sta     iob+1
        ldy     #IOB_DRIVE
        lda     drive
        sta     (iob),y
        iny                     ; volume 0: accept whatever is mounted
        lda     #0
        sta     (iob),y
        iny
        lda     track
        sta     (iob),y
        iny
        lda     sector
        sta     (iob),y
        ldy     #IOB_BUFFER
        lda     #<buffer
        sta     (iob),y
        iny
        lda     #>buffer
        sta     (iob),y
        iny                     ; bytes 10 and 11 are unused by READ/WRITE
        lda     #0
        sta     (iob),y
        iny
        sta     (iob),y
        iny
        lda     command
        sta     (iob),y
        jsr     restore_holes   ; clobbers ptr; IOB is already filled
        lda     iob+1
        ldy     iob
        jsr     RWTS_ENTRY
        php
        jsr     save_holes      ; clobbers ptr; flags kept in PHP
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
