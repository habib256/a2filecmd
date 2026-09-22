; format.s -- F: a fresh, bootable DOS 3.3 disk in the active panel's drive.
;
; DOS's own INIT does four things: RWTS formats every track, the DOS
; image goes onto tracks 0-2, the catalog track is cleared, and the VTOC
; is written. This does the same, but takes the DOS image sector by
; sector from the drive A2FC Mini was run from -- the boot disk -- rather
; than from memory: the boot disk carries the relocatable master image,
; which boots on any memory size, and its layout on disk is the one
; thing worth copying. So the target is the active panel's drive and the
; boot disk has to be in the other one. A one-drive machine cannot
; format here.
;
; Order, and why:
;   1. The 48 DOS sectors are read once before anything is written. An
;      unreadable boot disk, or one without a DOS 3.3 boot sector,
;      refuses the format with the target untouched: a read error is
;      never proof of anything.
;   2. Write protection. RWTS FORMAT does not sense the tab (it fails
;      otherwise, the disk untouched), but a sector write does, before
;      touching the disk: the target's VTOC sector is read and written
;      back as it is. A target that cannot be read, a blank disk, goes
;      straight to the format, which then fails if it is protected.
;   3. RWTS FORMAT (command 4, volume 254).
;   4. The DOS sectors again, two batches through the working area
;      (tracks 0-1, then track 2), each batch written then read back.
;   5. Catalog sectors 15 down to 1 as a third batch, built in the
;      working area and written the same way, then the VTOC last: a
;      disk whose VTOC reads as valid always has a valid, empty catalog
;      behind it, because the VTOC goes down only after every catalog
;      sector has been read back.
; A write that does not read back latches del_fault like every other
; write in this program: nothing writes again until the next BRUN.
;
; The engine runs from $0200-$03CF: DOS's input buffer and the free part
; of page three. It travels inside the working area of the BRUN image
; and lowstart.s moves it out before anything else runs. Nothing in DOS
; or in A2FC Mini touches those pages while the panels are up; the BRUN
; stub that uses page three is written on the way out, after this. The
; prompt and the results, format_file, stay in the resident with the
; other footers.

        .include "mini.inc"

        .export format_disk, _format_disk, fm_status, _fm_status, fm_n
        .export dos_sig

        .import read_sector, write_sector, read_into, write_into
        .import rwts_format, rwts_error, read_at, rwts_buf
        .import buffer, drive, track, sector, boot_drive
        .import del_fault, put_verified, memcmp256, scratch, fm_tick
        .import heartbeat

.ifdef SIM65
        .segment "CODE"         ; no DOS under sim65: nothing to hook
fmt_ticking:
        jmp     rwts_format
.else                           ; ca65 2.18: .ifndef does not see a -D symbol
        .export format_file
        .import foot_zone, confirm, keep_note, result_done, activate
        .import say_protected, say_uncertain, present, put, inline_text
        .import copy_done, copy_total, copy_progress, keys_bar_inline
.endif

        .segment "BSS"
fm_target:      .res 1          ; the drive being formatted: `drive` on return
fm_write:       .res 1          ; 0: dos_pass reads only; 1: the target is written
fm_first:       .res 1          ; first track of the batch: 0 (tracks 0-1), then 2
fm_n:           .res 1          ; sectors in the batch: 32, then 16
fm_lo:          .res 1          ; lowest index of the batch: 0, 1 for the catalog
fm_i:           .res 1          ; sector index within the batch
fm_status:      .res 1
_fm_status      = fm_status

.ifdef SIM65
.else
; ---------------------------------------------------------------------
; format_file -- F, resident. The footer names the drive; Y formats, N
; or Escape leaves the disk alone. The boot drive is refused before the
; question: it is where DOS comes from. Every result with a write behind
; it rereads the target's panels.
; ---------------------------------------------------------------------
; ---------------------------------------------------------------------
; A sign of life during RWTS's FORMAT. That one call formats all
; thirty-five tracks and hands nothing back for some eighteen seconds:
; no instruction of this program runs, so by itself nothing on screen
; can move. DOS's own loop runs once per track -- $BED4 to $BEFF,
; thirty-five times, measured in POM2 -- and it opens with a JSR at
; $BED6. While the format runs, and only then, that call's operand
; points at fmt_hook: the cell turns, A is kept, and DOS's own routine
; runs as it always did. The three bytes are checked first, so any
; other DOS formats exactly as before, without the heartbeat, and the
; operand goes back the instant the format returns -- DOS reclaims this
; memory for its file buffers when A2FC Mini quits.
; ---------------------------------------------------------------------
FM_JSR  = $BED6                 ; DOS 3.3: the per-track loop's first call
FM_DEST = $BE5A                 ; what it calls

        .segment "CODE"
fmt_hook:
        pha
        jsr     heartbeat
        pla
        jmp     FM_DEST

; The format itself, with the heartbeat hooked for its duration only.
; One call, so the engine at $0200 pays the three bytes it always paid.
fmt_ticking:
        jsr     fmt_on
        jsr     rwts_format
        pha
        jsr     fmt_off
        pla                     ; the status again, and its Z
        rts

fmt_on:
        ldx     #2
@check: lda     FM_JSR,x
        cmp     fm_sig,x
        bne     @out            ; another DOS: leave it alone
        dex
        bpl     @check
        lda     #<fmt_hook
        sta     FM_JSR+1
        lda     #>fmt_hook
        sta     FM_JSR+2
@out:   rts

fmt_off:
        lda     FM_JSR+2        ; ours? then DOS's own target again
        cmp     #>fmt_hook
        bne     @out
        lda     #<FM_DEST
        sta     FM_JSR+1
        lda     #>FM_DEST
        sta     FM_JSR+2
@out:   rts

        .segment "CODE"
format_file:
        jsr     activate        ; drive is the active panel's, as every write command
        jsr     foot_zone
        lda     drive
        cmp     boot_drive
        jeq     same_drive
        PRINT   "FORMAT D"
        lda     drive
        ora     #'0'
        jsr     put
        PRINT   " WITH DOS: ERASE ALL FILES?"
        lda     #0
        sta     inverse
        jsr     confirm
        bcs     @go
        rts
@go:
        jsr     foot_zone
        PRINT   "FORMATTING..."
        KEYBAR  22, ""          ; the bar's row, cleared like a copy's
        lda     #0              ; the bar: empty, drawn now with the message
        sta     copy_done
        sta     copy_done+1
        lda     #<FMT_TOTAL
        sta     copy_total
        lda     #>FMT_TOTAL
        sta     copy_total+1
        jsr     copy_progress
        jsr     format_disk
        jsr     foot_zone
        lda     fm_status
        bne     @notok
        PRINT   "FORMATTED WITH DOS 3.3"
        jmp     result_done
@notok:
        cmp     #FMT_PROTECTED
        bne     @notprot
        jsr     say_protected
        jmp     result_done
@notprot:
        cmp     #FMT_UNCERTAIN
        bne     @notunc
        jmp     say_uncertain
@notunc:
        cmp     #FMT_SRC_READ
        bcs     @nodos          ; FMT_SRC_READ, FMT_NO_DOS: nothing written
        ; FMT_FAILED: a protected blank disk, a bad one, or one RWTS left
        ; half formatted; FMT_SRC_LATE: formatted, then no DOS. No VTOC
        ; in any case but the first, so the reread shows what happened.
        PRINT   "FORMAT FAILED: PROTECTED, BAD OR ERASED"
        jmp     result_done
@nodos:
        PRINT   "NO DOS READ ON THE BOOT DRIVE"  ; a read error, or no DOS 3.3 boot sector
        jmp     keep_note

; same_drive -- nothing tried: no reread, marks stay
same_drive:
        PRINT   "BOOT DRIVE - FORMAT THE OTHER ONE"
        jmp     keep_note
.endif

.ifdef SIM65
        .segment "CODE"
.else
        .segment "FORMAT"       ; the engine: $0200-$03CF at run time
.endif

; ---------------------------------------------------------------------
; format_disk -- formats `drive` with the DOS of boot_drive. Returns
; A = FMT_* in fm_status, `drive` put back to the target whatever
; happened, del_fault latched on FMT_UNCERTAIN.
; ---------------------------------------------------------------------
format_disk:
_format_disk:
        lda     drive
        sta     fm_target
        cmp     boot_drive
        bne     @differs
        lda     #FMT_SAME
        bne     @done
@differs:
        lda     del_fault
        beq     @clean
        lda     #FMT_UNCERTAIN  ; latched already: @done sets it again, harmless
        bne     @done
@clean:
        sta     fm_write        ; A = del_fault = 0: dos_pass reads only
        jsr     dos_pass        ; the boot disk, read only: nothing written yet
        bne     @done
        lda     fm_target       ; dos_pass left `drive` on the boot disk
        sta     drive
        lda     #CATALOG_TRACK  ; the target's VTOC sector written back as it
        ldx     #0              ; is: RWTS senses the tab before any write
        jsr     read_at
        bne     @format         ; unreadable, a blank disk: the format will tell
        jsr     write_sector
        beq     @format
        lda     #FMT_PROTECTED
        ldx     rwts_error
        cpx     #RWTS_PROTECTED
        beq     @done           ; any other refusal: the format decides
@format:
        jsr     fmt_ticking     ; RWTS's INIT never reports the tab: a
        beq     @formatted      ; protected blank disk fails here
        lda     #FMT_FAILED
        bne     @done
@formatted:
        lda     #FMT_WEIGHT     ; RWTS's FORMAT, about half the time, done
        sta     fm_n            ; (dos_pass sets fm_n again per batch)
        jsr     fm_tick
        inc     fm_write
        jsr     dos_pass
        beq     @dos_ok
        cmp     #FMT_UNCERTAIN
        beq     @done
        lda     #FMT_SRC_LATE   ; the boot disk failed, or was swapped, after the format
        bne     @done
@dos_ok:
        jsr     write_catalog
@done:
        sta     fm_status       ; A stays the status through the restore
        ldx     fm_target
        stx     drive
        cmp     #FMT_UNCERTAIN
        bne     @out
        ldx     #1
        stx     del_fault
@out:
        rts                     ; A = fm_status

; dos_pass -- the 48 DOS sectors of boot_drive in two batches, each
; sector straight into its page of the working area. With fm_write set
; each batch then goes out through batch_out. The read loop runs from
; the batch's last sector down, like the ones there: DOS 3.3's 2:1 skew
; reads a descending chain in two turns a track, an ascending one in
; thirteen. Track 0 sector 0 must start like a DOS 3.3 boot sector, or
; the disk is not a DOS source.
dos_pass:
        lda     #0
        sta     fm_first
        sta     fm_lo           ; a DOS batch is the whole working area
@batch:
        lda     #BATCH_SECTORS  ; tracks 0 and 1 in one go
        ldx     fm_first
        beq     @size
        lsr     a               ; then track 2: half of it
@size:
        sta     fm_n
        lda     boot_drive
        sta     drive
        ldx     fm_n
@read:
        dex
        stx     fm_i
        jsr     batch_page
        jsr     read_into
        bne     @src_read
        ldx     fm_i
        bne     @read
        jsr     fm_tick         ; the bar, between two drive phases only
        lda     fm_first
        bne     @source_ok      ; only track 0 sector 0 carries the signature,
        ldx     #DOS_SIG_LEN-1  ; and index 0 is the last sector read
@sig:
        lda     scratch,x       ; index 0 of the first batch: the first page
        cmp     dos_sig,x
        bne     @no_dos
        dex
        bpl     @sig
@source_ok:
        lda     fm_write
        beq     @advance
        jsr     batch_out
        bne     @ret            ; FMT_UNCERTAIN
@advance:
        lda     fm_first
        clc
        adc     #2
        sta     fm_first
        cmp     #3
        bcc     @batch          ; 0, then 2, then done
        lda     #FMT_OK
@ret:
        rts
@src_read:
        lda     #FMT_SRC_READ
        rts
@no_dos:
        lda     #FMT_NO_DOS
        rts

; batch_out -- the batch on fm_target: indices fm_n-1 down to fm_lo
; written straight from their pages of the working area, then every one
; read back into buffer and compared with its page, odd indices first,
; then even, so that a read-back and its compare are done before the
; next sector passes under the head (four slots away instead of two).
; Nothing else runs between two RWTS calls: a 256-byte move in that gap
; is what cost a whole turn per sector. A = FMT_OK or FMT_UNCERTAIN.
batch_out:
        lda     fm_target
        sta     drive
        ldx     fm_n
@write:
        dex
        stx     fm_i
        jsr     batch_page
        jsr     write_into
        bne     @uncertain
        ldx     fm_i
        cpx     fm_lo
        bne     @write
        jsr     fm_tick
        ldx     fm_n            ; read back from the top down, odd indices
        dex                     ; first (31, 29 ... 1), then even (30 ... 0):
        stx     fm_i            ; four slots apart, still descending
@verify:
        jsr     batch_page      ; ptr2 = the page
        jsr     read_sector     ; into buffer
        bne     @uncertain
        SETPTR  ptr, buffer
        jsr     memcmp256
        bne     @uncertain
        ldx     fm_i
        dex
        dex
        stx     fm_i
        txa
        sec
        sbc     fm_lo           ; a pass ends below the batch's first index
        bpl     @verify
        cpx     #$FF            ; the odd pass ended at -1; the even one at
        bne     @done           ; fm_lo-2, which is -2 or 0, never -1
        ldx     fm_n
        dex
        dex
        stx     fm_i
        bpl     @verify         ; always: 16 or 32 sectors
@done:
        lda     #FMT_OK
        rts
@uncertain:
        lda     #FMT_UNCERTAIN
        rts

; batch_page -- index fm_i: track and sector, rwts_buf and ptr2 on its
; page of the working area
batch_page:
        ldx     fm_i
        txa
        and     #15
        sta     sector
        txa
        lsr     a
        lsr     a
        lsr     a
        lsr     a
        clc
        adc     fm_first
        sta     track
        lda     #<scratch
        sta     rwts_buf
        sta     ptr2
        txa
        clc
        adc     #>scratch
        sta     rwts_buf+1
        sta     ptr2+1
        rts

; write_catalog -- catalog sectors 15 down to 1, each pointing at the
; next and 1 ending the chain with 0,0, then the VTOC: DOS 3.3 release 3, volume
; 254, 35 tracks of 16 sectors of 256 bytes, 122 pairs per T/S list,
; allocation starting after the catalog track and going up, tracks 0-2
; and 17 reserved. What INIT leaves before it saves HELLO.
;
; The 15 sectors are staged in the working area, which dos_pass has
; finished with, and go out as one batch: page i is sector i, so the
; batch is indices 1 to 15 of track 17 and batch_out writes and reads
; them back like a DOS batch. The VTOC is the one sector still written
; on its own, last of all.
write_catalog:
        lda     #<scratch
        sta     ptr2
        ldx     #15
@page:
        txa                     ; page i of the working area
        clc
        adc     #>scratch
        sta     ptr2+1
        ldy     #0
        tya
@zero:
        sta     (ptr2),y
        iny
        bne     @zero
        dex                     ; the sector this one points at
        beq     @built          ; sector 1 ends the chain with 0,0, as INIT does
        lda     #CATALOG_TRACK
        iny                     ; the fill left Y at 0
        sta     (ptr2),y
        txa
        iny
        sta     (ptr2),y
        bne     @page           ; always: X is 1 or more here
@built:
        lda     #CATALOG_TRACK
        sta     fm_first
        lda     #16
        sta     fm_n
        inx                     ; X = 0 from the last page
        stx     fm_lo           ; sector 0 is the VTOC: not in the batch
        jsr     batch_out
        bne     @out
        ; The last sector read back was sector 2, so buffer is zero
        ; everywhere but bytes 1-2, which the fields below overwrite:
        ; the VTOC is built on zeros without clearing buffer again.
        ldx     #VTOC_FIELDS-1
@field:
        ldy     vtoc_off,x
        lda     vtoc_val,x
        sta     buffer,y
        dex
        bpl     @field
        ldx     #3
@free:
        cpx     #CATALOG_TRACK
        beq     @next
        txa
        asl     a
        asl     a               ; carry clear: 34 * 4 fits
        adc     #VTOC_BITMAP
        tay
        lda     #$FF
        sta     buffer,y        ; sectors F-8
        sta     buffer+1,y      ; sectors 7-0
@next:
        inx
        cpx     #35
        bcc     @free
        lda     #CATALOG_TRACK
        ldx     #0
        jsr     put_verified
        beq     @out            ; DEL_OK is FMT_OK
        cmp     #DEL_PROTECTED  ; refused before writing, but the disk is
        bne     @unc            ; erased already: failed, not uncertain
        lda     #FMT_FAILED
        bpl     @out            ; always
@unc:
        lda     #FMT_UNCERTAIN
@out:
        rts

        .segment "RODATA"       ; read with absolute indexing: any segment
.ifdef SIM65
.else                           ; no DOS to hook under sim65, and no FM_DEST
; JSR FM_DEST, the three bytes fmt_on wants at $BED6 before it hooks.
fm_sig:
        .byte   $20, <FM_DEST, >FM_DEST
.endif

; The first bytes of a DOS 3.3 boot sector: the sector count for the
; controller ROM, then LDA $27 / CMP #$09, read from the shipped disk.
dos_sig:
        .byte   $01, $A5, $27, $C9, $09
        .assert * - dos_sig = DOS_SIG_LEN, error, "dos_sig and DOS_SIG_LEN disagree"

vtoc_off:
        .byte   $01, $02, $03, $06, $27, $30, $31, $34, $35, $37
vtoc_val:
        .byte   CATALOG_TRACK, 15, 3, DOS_VOLUME, TS_PER_LIST, CATALOG_TRACK
        .byte   1, 35, 16, 1
VTOC_FIELDS     = * - vtoc_val
