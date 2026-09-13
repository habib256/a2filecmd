; catalog.s -- read a DOS 3.3 catalog fast enough to keep the rotation.
;
; This is where the C edition lost its time, and it was not the parsing
; itself. DOS 3.3 writes a track with a 2:1 soft interleave so that a
; program has roughly 25 000 cycles to digest one sector before the next
; one arrives under the head. Miss that window and RWTS waits a whole
; revolution, about 200 000 cycles. Measured on POM2, the C edition spent
; 306 000 cycles per catalog sector -- one and a half revolutions each,
; 4.9 seconds for a sixteen-sector chain.
;
; So nothing here multiplies. Entry fields live in parallel arrays, names
; use a 32-byte stride, and the allocation bitmap index is two shifts.
;
; What it refuses is unchanged: a wrong geometry, a link outside the disk,
; a link back to the VTOC, a cycle, a file pointer outside the disk and a
; catalog larger than the panel can hold. A read error is never treated as
; the end of the chain, and never leaves a half-filled panel behind.

        .include "mini.inc"

        .export catalog, preview, load_file, load_count, blank_scratch
        .export valid_cs, seen_bit, bit_masks, ent_ptr, ent_index

        .import read_sector
        .import buffer, count, volume, track, sector, active, sector_seen
        .import ent_track, ent_sector, ent_type, ent_seclo, ent_sechi
        .import ent_name, prv_index
        .import scratch, cat_buf

        .segment "BSS"
cat_nt:         .res 1          ; link to the next catalog sector
cat_ns:         .res 1
cat_off:        .res 1          ; entry offset inside the sector
cat_i:          .res 1          ; entries left in this sector
cat_idx:        .res 1          ; where the entry lands, panel included
ldf_t:          .res 1          ; load_file: the T/S list being followed
ldf_s:          .res 1
ldf_nt:         .res 1
ldf_ns:         .res 1
ldf_j:          .res 1          ; pair within the list
ldf_got:        .res 1          ; data sectors placed so far
load_count      = ldf_got
ldf_ended:      .res 1
ldf_list        = cat_buf       ; T/S list; copy is idle while a file loads

        .segment "RODATA"
bit_masks:
        .byte   1, 2, 4, 8, 16, 32, 64, 128

        .segment "CODE"

; ---------------------------------------------------------------------
; catalog -- fills the active panel. A = 0 read, 1 read error, 2 invalid.
; ---------------------------------------------------------------------
catalog:
        lda     #0
        sta     count
        ldx     #69
@wipe:
        sta     sector_seen,x
        dex
        bpl     @wipe

        lda     #CATALOG_TRACK
        sta     track
        lda     #0
        sta     sector
        jsr     read_sector
        beq     @vtoc
        lda     #CAT_READ
        rts
@vtoc:
        lda     buffer+3        ; DOS release marker
        cmp     #3
        bne     @bad
        lda     buffer+$27      ; pairs per T/S list
        cmp     #TS_PER_LIST
        bne     @bad
        lda     buffer+$34      ; tracks
        cmp     #35
        bne     @bad
        lda     buffer+$35      ; sectors per track
        cmp     #16
        bne     @bad
        lda     buffer+$36      ; bytes per sector, low then high: 256
        bne     @bad
        lda     buffer+$37
        cmp     #1
        bne     @bad
        lda     buffer+6
        sta     volume
        lda     buffer+1
        sta     cat_nt
        lda     buffer+2
        sta     cat_ns
        lda     cat_nt
        bne     @chain
@bad:
        lda     #0              ; never hand back a partial catalog
        sta     count
        lda     #CAT_BAD
        rts

@chain:
        ldx     cat_ns
        lda     cat_nt
        jsr     valid_cs
        bcc     @bad
        lda     cat_nt          ; the VTOC is not a catalog sector
        cmp     #CATALOG_TRACK
        bne     @fresh
        lda     cat_ns
        beq     @bad
@fresh:
        lda     cat_nt          ; a chain that loops is not a chain
        ldx     cat_ns
        jsr     seen_bit
        ldx     bidx
        lda     sector_seen,x
        and     bmsk
        bne     @bad
        lda     sector_seen,x
        ora     bmsk
        sta     sector_seen,x

        lda     cat_nt
        sta     track
        lda     cat_ns
        sta     sector
        jsr     read_sector
        beq     @parse
        lda     #0
        sta     count
        lda     #CAT_READ
        rts
@parse:
        lda     buffer+1
        sta     cat_nt
        lda     buffer+2
        sta     cat_ns
        lda     cat_nt
        bne     @entries
        lda     cat_ns          ; no track but a sector: malformed
        bne     @bad
@entries:
        lda     #CAT_FIRST
        sta     cat_off
        lda     #CAT_ENTRIES
        sta     cat_i
@entry:
        ldx     cat_off
        lda     buffer,x
        beq     @skip           ; never used
        cmp     #$FF
        beq     @skip           ; deleted
        lda     buffer+1,x
        tax
        ldy     cat_off
        lda     buffer,y
        jsr     valid_cs
        jcc     @bad
        lda     count
        cmp     #MINI_MAX
        jcs     @bad
        jsr     store_entry
        inc     count
@skip:
        lda     cat_off
        clc
        adc     #CAT_ENTRY_LEN
        sta     cat_off
        dec     cat_i
        bne     @entry
        lda     cat_nt
        jne     @chain
        lda     #CAT_OK
        rts

; ---------------------------------------------------------------------
; store_entry -- copies one catalog entry into the active panel.
; Names keep DOS's 30 characters, stripped of the high bit; anything
; unprintable becomes '?' so a crafted name cannot redirect a path.
; ---------------------------------------------------------------------
store_entry:
        lda     count
        jsr     ent_index
        sta     cat_idx
        ldx     cat_off
        tay
        lda     buffer,x
        sta     ent_track,y
        lda     buffer+1,x
        sta     ent_sector,y
        lda     buffer+2,x
        sta     ent_type,y
        lda     buffer+33,x
        sta     ent_seclo,y
        lda     buffer+34,x
        sta     ent_sechi,y
        lda     cat_idx
        jsr     ent_ptr
        lda     cat_off
        clc
        adc     #3
        tax
        ldy     #0
@char:
        lda     buffer,x
        and     #$7F
        cmp     #32
        bcc     @unprintable
        cmp     #127
        bcs     @unprintable
        bcc     @keep
@unprintable:
        lda     #'?'
@keep:
        sta     (ptr),y
        inx
        iny
        cpy     #NAME_LEN
        bcc     @char
        rts

; ---------------------------------------------------------------------
; preview -- prv_index selects the file. Reads its first T/S list, then
; the first data sector. A = 0 ready in buffer, 1 read error, 2 no
; preview. An empty or sparse file invents nothing.
; ---------------------------------------------------------------------
preview:
        lda     prv_index
        cmp     count
        bcs     @bad
        jsr     ent_index
        tay
        lda     ent_track,y
        sta     track
        lda     ent_sector,y
        sta     sector
        jsr     read_sector
        bne     @read
        lda     buffer+5        ; the first list must start at offset zero
        ora     buffer+6
        bne     @bad
        lda     buffer+12
        sta     track
        lda     buffer+13
        sta     sector
        ldx     sector
        lda     track
        jsr     valid_cs
        bcc     @bad
        jsr     read_sector
        bne     @read
        lda     #CAT_OK
        rts
@read:
        lda     #CAT_READ
        rts
@bad:
        lda     #CAT_BAD
        rts

; ---------------------------------------------------------------------
; load_file -- prv_index selects the file; its data sectors are read into
; the working area, in file order, at most SCRATCH_SIZE/256 of them.
;
; The area is blanked first, so a file shorter than a hi-res page shows
; black rather than whatever the last copy or edit left there. Reading
; stops at the area's end without complaining: a picture is the first
; 8 KB of the file, and saying so is the viewer's business.
;
; A = 0 loaded, 1 read error, 2 nothing usable. A read error is never
; treated as the end of the file.
; ---------------------------------------------------------------------
load_file:
        lda     prv_index
        cmp     count
        jcs     @bad
        jsr     ent_index
        tay
        lda     ent_track,y
        sta     ldf_t
        lda     ent_sector,y
        sta     ldf_s
        lda     #0
        sta     ldf_got
        sta     ldf_ended
        jsr     blank_scratch
@list:
        lda     ldf_t
        ldx     ldf_s
        jsr     valid_cs
        jcc     @bad
        lda     ldf_t
        sta     track
        lda     ldf_s
        sta     sector
        jsr     read_sector
        jne     @read
        ldx     #0              ; keep the list; data reads reuse buffer
@keep:
        lda     buffer,x
        sta     ldf_list,x
        inx
        bne     @keep
        lda     ldf_list+1
        sta     ldf_nt
        lda     ldf_list+2
        sta     ldf_ns
        lda     ldf_nt
        bne     @pairs
        lda     ldf_ns          ; no track but a sector: malformed
        bne     @bad
@pairs:
        lda     #0
        sta     ldf_j
@pair:
        lda     ldf_got         ; the area is full: show what we have
        cmp     #SCRATCH_SIZE/256
        bcs     @done
        lda     ldf_j
        asl     a
        tax
        lda     ldf_list+12,x
        sta     ldf_t
        lda     ldf_list+13,x
        sta     ldf_s
        ora     ldf_t
        bne     @live
        lda     #1              ; a hole ends the file
        sta     ldf_ended
        jmp     @nextpair
@live:
        lda     ldf_ended
        bne     @bad            ; data after the hole
        lda     ldf_t
        ldx     ldf_s
        jsr     valid_cs
        bcc     @bad
        lda     ldf_t
        sta     track
        lda     ldf_s
        sta     sector
        jsr     read_sector
        bne     @read
        jsr     place_sector
        inc     ldf_got
@nextpair:
        inc     ldf_j
        lda     ldf_j
        cmp     #TS_PER_LIST
        bcc     @pair
        lda     ldf_nt
        beq     @done
        lda     ldf_ended       ; a hole, and still another list
        bne     @bad
        lda     ldf_nt
        sta     ldf_t
        lda     ldf_ns
        sta     ldf_s
        jmp     @list
@done:
        lda     #CAT_OK         ; zero sectors is an empty file, still loaded
        rts
@read:
        lda     #CAT_READ
        rts
@bad:
        lda     #CAT_BAD
        rts

; place_sector -- buffer into the working area at slot ldf_got. A slot
; offset only lands in the high byte, so no alignment is needed.
place_sector:
        lda     #<scratch
        sta     ptr
        lda     ldf_got
        clc
        adc     #>scratch
        sta     ptr+1
        ldy     #0
@byte:
        lda     buffer,y
        sta     (ptr),y
        iny
        bne     @byte
        rts

; blank_scratch -- the whole working area to zero: black on a hi-res page
blank_scratch:
        lda     #<scratch
        sta     ptr
        lda     #>scratch
        sta     ptr+1
        ldx     #>SCRATCH_SIZE
        lda     #0
        ldy     #0
@page:
        sta     (ptr),y
        iny
        bne     @page
        inc     ptr+1
        dex
        bne     @page
        rts

; ---------------------------------------------------------------------
; ent_index -- A = index within the panel, returns the index within the
; shared arrays for whichever panel is active.
; ---------------------------------------------------------------------
ent_index:
        ldy     active
        beq     @done
        clc
        adc     #SIDE_STRIDE
@done:
        rts

; ---------------------------------------------------------------------
; ent_ptr -- A = array index, leaves ptr on that entry's 30-byte name.
; The 32-byte stride turns the multiply into three shifts.
; ---------------------------------------------------------------------
ent_ptr:
        pha
        lsr     a
        lsr     a
        lsr     a
        sta     t0
        pla
        and     #7
        asl     a
        asl     a
        asl     a
        asl     a
        asl     a
        clc
        adc     #<ent_name
        sta     ptr
        lda     t0
        adc     #>ent_name
        sta     ptr+1
        rts

; ---------------------------------------------------------------------
; valid_cs -- A = track, X = sector. Carry set when a catalog link or a
; file pointer may be followed: track 1 to 34, sector 0 to 15. Track 0
; belongs to DOS and is never a file.
; ---------------------------------------------------------------------
valid_cs:
        cpx     #16
        bcs     @no
        cmp     #35
        bcs     @no
        cmp     #1
        bcc     @no
        sec
        rts
@no:
        clc
        rts

; ---------------------------------------------------------------------
; seen_bit -- A = track, X = sector. Points bidx/bmsk at that sector's
; bit in sector_seen. Because a sector number is 16 per track, the byte
; index is just 2*track plus the top bit of the sector.
; ---------------------------------------------------------------------
seen_bit:
        asl     a
        sta     bidx
        cpx     #8
        bcc     @low
        inc     bidx
@low:
        txa
        and     #7
        tax
        lda     bit_masks,x
        sta     bmsk
        rts
