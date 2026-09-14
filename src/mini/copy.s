; copy.s -- DOS 3.3 exclusive new-file copy. No replacement, deletion,
; rename or formatting. Every write goes to copy_to; every buffer is in
; main RAM.
;
; Usable first: no whole-disk audit, no pre-read of the source, no
; re-read of both disks after each batch. The copy stays a copy: a new
; name only, VTOC reserved before data, each write read back, one catalog
; entry published last. A physical sector write is NOT atomic. A disk
; swapped after the prompt, a stale panel size, or a name hidden after
; prepare will not be caught. That is the price of staying on the
; panels and finishing before the motor spins down.

        .include "mini.inc"

        .export copy_prepare, copy_execute, copy_cancel
        .export create_prepare, create_execute
        .export copy_from, copy_to, copy_src_volume, copy_dst_volume
        .export copy_fault, cp_index, cp_dest, ram_source, data_count
        .export copy_done, copy_total
        .export cs_track, cs_sector, cs_type, cs_name, cs_seclo, cs_sechi
        .export vtoc, catalog_before, verify, cat_buf
        .export _copy_prepare, _copy_execute, _copy_cancel
        .export _create_prepare, _create_execute
        .export _copy_from, _copy_to, _copy_src_volume, _copy_dst_volume
        .export _copy_fault, _cp_index, _cp_dest, _ram_source, _data_count
        .export _cs_track, _cs_sector, _cs_type, _cs_name
        .export _cs_seclo, _cs_sechi
        .export valid_data, read_at, vtoc_bit, memcpy256, memcmp256
        .export slot_offset

        .import read_sector, write_sector, rwts_error
        .import buffer, drive, track, sector, count, sector_seen
        .import ent_track, ent_sector, ent_seclo, ent_sechi, ent_type
        .import ent_slot, ent_index, ent_ptr, sanitise
        .import seen_bit, bit_masks
        .import scratch
        .import copy_progress

        .segment "BSS"

; ---- the file being copied, taken from the panel before any disk work
cs_track:       .res 1
cs_sector:      .res 1
cs_type:        .res 1
cs_seclo:       .res 1
cs_sechi:       .res 1
cs_slot:        .res 1          ; catalog sector << 3 | slot, from ent_slot
cs_name:        .res NAME_LEN
_cs_track       = cs_track
_cs_sector      = cs_sector
_cs_type        = cs_type
_cs_seclo       = cs_seclo
_cs_sechi       = cs_sechi
_cs_name        = cs_name

copy_from:      .res 1
copy_to:        .res 1
copy_src_volume: .res 1
copy_dst_volume: .res 1
copy_fault:     .res 1          ; latched: no further writes this run
cp_index:       .res 1          ; copy_prepare arguments
cp_dest:        .res 1
ram_source:     .res 1          ; 1: the working area is the source
_copy_from      = copy_from
_copy_to        = copy_to
_copy_src_volume = copy_src_volume
_copy_dst_volume = copy_dst_volume
_copy_fault     = copy_fault
_cp_index       = cp_index
_cp_dest        = cp_dest
_ram_source     = ram_source

; ---- whole sectors kept for comparison
vtoc:           .res 256        ; the target VTOC as reserved
catalog_before: .res 256        ; the catalog sector holding the free slot
verify:         .res 256        ; what a write was supposed to leave
cat_buf:        .res 256        ; the catalog sector being walked
src_entry:      .res CAT_ENTRY_LEN

; ---- the source file's sectors, in file order
source_map_t:   .res MAX_DATA
source_map_s:   .res MAX_DATA
data_count:     .res 2
_data_count     = data_count

; ---- the target reservation
target_bits:    .res 70
target_index:   .res 2
tgt_t:          .res 1
tgt_s:          .res 1
tl_t:           .res MAX_LISTS
tl_s:           .res MAX_LISTS
list_count:     .res 1
allocated_count: .res 2
copy_done:      .res 2
copy_total:     .res 2
ready:          .res 1

; ---- where the new entry goes
out_track:      .res 1
out_sector:     .res 1
out_offset:     .res 1
src_cat_track:  .res 1
src_cat_sector: .res 1
src_cat_offset: .res 1

; ---- audit locals
aud_source:     .res 1
aud_recheck:    .res 1
aud_t:          .res 1
aud_s:          .res 1
aud_nt:         .res 1
aud_ns:         .res 1
aud_i:          .res 1
aud_off:        .res 1
aud_files:      .res 1
aud_slot:       .res 1
aud_n:          .res 1          ; catalog sectors visited: 15 at most
aud_first_t:    .res 1
aud_first_s:    .res 1
aud_size:       .res 2

; ---- walk locals
wlk_t:          .res 1
wlk_s:          .res 1
wlk_nt:         .res 1
wlk_ns:         .res 1
wlk_ended:      .res 1
wlk_collect:    .res 1
wlk_expect:     .res 2
wlk_offset:     .res 2
wlk_total:      .res 2
wlk_j:          .res 1

; ---- batch state
bat_n:          .res 1          ; sectors in this batch
bat_k:          .res 1
bat_t:          .res BATCH_SECTORS
bat_s:          .res BATCH_SECTORS
bat_index:      .res 2          ; first source_map index of the batch
lst_no:         .res 1          ; T/S list being built
lst_pair:       .res 1

; The batch lives in the shared working area, hi-res page one. Nothing
; else may touch it while a copy runs, and a copy must not expect it to
; hold anything on entry. See mini.inc for who else owns it and when.
; The panel name tables are not extra scratch: a tagged batch still
; walks them until the last file, and only the UI reloads after that.

        .segment "CODE"

; =====================================================================
; Small helpers
; =====================================================================

; vtoc_bit -- A = track, X = sector. Points bidx/bmsk at the sector's
; allocation bit in the VTOC. DOS stores each track as a big-endian pair,
; so sectors 0-7 live in the second byte.
vtoc_bit:
        asl     a
        asl     a
        clc
        adc     #VTOC_BITMAP
        sta     bidx
        cpx     #8
        bcs     @high
        inc     bidx
@high:
        txa
        and     #7
        tax
        lda     bit_masks,x
        sta     bmsk
        rts

; free_sector -- A = track, X = sector. Z clear when the VTOC calls it
; free. A live file sector must never be free; a target sector must be.
free_sector:
        jsr     vtoc_bit
        ldx     bidx
        lda     vtoc,x
        and     bmsk
        rts

; valid_data -- A = track, X = sector. Carry set when it may hold file
; data: tracks 1 to 34, never track 0 (the boot sector) or the catalog
; track. Tracks 1 and 2 hold DOS on a normal disk, where the VTOC marks
; all 32 of their sectors allocated; a "no DOS" disk frees them and DOS
; itself then files data there. So they are accepted only while the VTOC
; in RAM (the disk being walked) shows at least one free sector on them:
; a chain pointing into a live DOS image is still refused. A preserved.
valid_data:
        cpx     #16
        bcs     @no
        cmp     #35
        bcs     @no
        cmp     #CATALOG_TRACK
        beq     @no
        cmp     #3
        bcs     @yes
        cmp     #1
        bcc     @no
        pha                             ; A and X both go back to the caller
        lda     vtoc+VTOC_BITMAP+4      ; track 1, sectors F-8 and 7-0
        ora     vtoc+VTOC_BITMAP+5
        ora     vtoc+VTOC_BITMAP+8      ; track 2
        ora     vtoc+VTOC_BITMAP+9
        beq     @dos                    ; nothing free there: DOS lives there
        pla
@yes:
        sec
        rts
@dos:
        pla
@no:
        clc
        rts

.ifdef SIM65
        .segment "CODE"
.else
        .segment "LOWCODE"      ; prepare-time only: room below the area
.endif
; slot_offset -- A = slot 0-6 in a catalog sector, returns its offset
slot_offset:
        tax
        lda     #CAT_FIRST
@loop:
        dex
        bmi     @done
        clc
        adc     #CAT_ENTRY_LEN
        jmp     @loop
@done:
        rts
        .segment "CODE"

; claim -- A = track, X = sector. Takes ownership of one live sector in
; sector_seen. A = COPY_OK, or COPY_INVALID when the sector is outside
; the disk, already owned by another file, or marked free while in use.
claim:
        sta     s0
        stx     s1
        cmp     #35
        bcs     @invalid
        cpx     #16
        bcs     @invalid
        jsr     seen_bit
        lda     bidx
        sta     s2
        lda     bmsk
        sta     s3
        ldx     s2
        lda     sector_seen,x
        and     s3
        bne     @invalid        ; two files cannot share a sector
        lda     s0
        ldx     s1
        jsr     free_sector
        bne     @invalid
        ldx     s2
        lda     sector_seen,x
        ora     s3
        sta     sector_seen,x
        lda     #COPY_OK
        rts
@invalid:
        lda     #COPY_INVALID
        rts

; read_at -- A = track, X = sector, into buffer on the current drive.
read_at:
        sta     track
        stx     sector
        jsr     read_sector
        beq     @ok
        lda     #COPY_READ
        rts
@ok:
        lda     #COPY_OK
        rts

; memcpy256 -- ptr to ptr2
memcpy256:
        ldy     #0
@loop:
        lda     (ptr),y
        sta     (ptr2),y
        iny
        bne     @loop
        rts

; memcmp256 -- ptr against ptr2, Z set when identical
memcmp256:
        ldy     #0
@loop:
        lda     (ptr),y
        cmp     (ptr2),y
        bne     @differs
        iny
        bne     @loop
        lda     #0
        rts
@differs:
        lda     #1
        rts

; batch_ptr -- A = slot, ptr2 = scratch + slot*256. A slot offset only
; ever lands in the high byte, so no alignment is needed.
batch_ptr:
        clc
        adc     #>scratch
        sta     ptr2+1
        lda     #<scratch
        sta     ptr2
        rts

; map_ptr -- ptr/ptr2 onto source_map_t/source_map_s at a 16-bit index
; held in num. The map runs to 491 entries, past what an index register
; can reach.
map_ptr:
        lda     #<source_map_t
        clc
        adc     num
        sta     ptr
        lda     #>source_map_t
        adc     num+1
        sta     ptr+1
        lda     #<source_map_s
        clc
        adc     num
        sta     ptr2
        lda     #>source_map_s
        adc     num+1
        sta     ptr2+1
        rts

; bump_target / bump_num / bump_total -- 16-bit increments
bump_target:
        inc     target_index
        bne     @done
        inc     target_index+1
@done:
        rts

bump_num:
        inc     num
        bne     @done
        inc     num+1
@done:
        rts

bump_total:
        inc     wlk_total
        bne     @done
        inc     wlk_total+1
@done:
        rts

; next_target -- hands out the reserved sectors in disk order. A = 0 with
; tgt_t/tgt_s set, or COPY_INVALID once they run out.
next_target:
@loop:
        lda     target_index+1
        cmp     #>560
        bcc     @take
        bne     @empty
        lda     target_index
        cmp     #<560
        bcc     @take
@empty:
        lda     #COPY_INVALID
        rts
@take:
        lda     target_index+1
        sta     t1
        lda     target_index
        sta     t0
        lsr     t1
        ror     t0
        lsr     t1
        ror     t0
        lsr     t1
        ror     t0              ; t0 = index >> 3
        ldx     t0
        lda     target_index
        and     #7
        tay
        lda     target_bits,x
        and     bit_masks,y
        beq     @step
        lda     t0
        lsr     a
        sta     tgt_t           ; index >> 4
        lda     target_index
        and     #15
        sta     tgt_s
        jsr     bump_target
        lda     #COPY_OK
        rts
@step:
        jsr     bump_target
        jmp     @loop

; name_matches -- X = offset of a 30-byte name in cat_buf. Carry set when
; it is the name about to be published: the raw bytes of src_entry, which
; a disk copy took from the source catalog and a create built from the
; typed name, so catalog-art names collide exactly as DOS would see them.
name_matches:
        ldy     #0
@char:
        lda     cat_buf,x
        cmp     src_entry+3,y
        bne     @no
        inx
        iny
        cpy     #NAME_LEN
        bcc     @char
        sec
        rts
@no:
        clc
        rts

; put_verified -- A = track, X = sector. Writes buffer to the target and
; reads it back. Write protection is reported as itself; anything else is
; uncertain, because a sector may be half written.
put_verified:
        sta     s0
        stx     s1
        SETPTR  ptr, buffer
        SETPTR  ptr2, verify
        jsr     memcpy256
        lda     s0
        sta     track
        lda     s1
        sta     sector
        lda     copy_to
        sta     drive
        jsr     write_sector
        beq     @wrote
        lda     rwts_error
        cmp     #RWTS_PROTECTED
        bne     @uncertain
        lda     #COPY_PROTECTED
        rts
@wrote:
        lda     s0
        ldx     s1
        jsr     read_at
        bne     @uncertain
        SETPTR  ptr, buffer
        SETPTR  ptr2, verify
        jsr     memcmp256
        bne     @uncertain
        lda     #COPY_OK
        rts
@uncertain:
        lda     #COPY_UNCERTAIN
        rts

; =====================================================================
; walk -- follow one file's T/S chain, claiming every sector it owns.
; wlk_t/wlk_s start it, wlk_expect is the catalog's sector count, and
; wlk_collect asks for the data sectors to be recorded in source_map.
;
; Sparse and non-canonical chains are refused rather than guessed at: a
; wrong guess here would let the copy reserve a sector another file uses.
; =====================================================================
walk:
        lda     #0
        sta     wlk_ended
        sta     wlk_offset
        sta     wlk_offset+1
        sta     wlk_total
        sta     wlk_total+1
@list:
        lda     wlk_t
        ldx     wlk_s
        jsr     valid_data
        jcc     @invalid
        lda     wlk_t
        ldx     wlk_s
        jsr     claim
        jne     @return
        lda     wlk_t
        ldx     wlk_s
        jsr     read_at
        jne     @return
        lda     buffer+5        ; this list must describe the sectors
        cmp     wlk_offset      ; already seen, and no others
        jne     @invalid
        lda     buffer+6
        cmp     wlk_offset+1
        jne     @invalid
        lda     buffer+1
        sta     wlk_nt
        lda     buffer+2
        sta     wlk_ns
        lda     wlk_nt
        bne     @counted
        lda     wlk_ns          ; no track but a sector: malformed
        jne     @invalid
@counted:
        jsr     bump_total
        lda     #0
        sta     wlk_j
@pair:
        lda     wlk_j
        asl     a
        tax
        lda     buffer+12,x
        sta     wlk_t
        lda     buffer+13,x
        sta     wlk_s
        ora     wlk_t
        bne     @live
        lda     #1              ; a hole ends the file
        sta     wlk_ended
        jmp     @nextpair
@live:
        lda     wlk_ended
        jne     @invalid
        lda     wlk_t
        ldx     wlk_s
        jsr     valid_data
        jcc     @invalid
        lda     wlk_t
        ldx     wlk_s
        jsr     claim
        jne     @return
        lda     wlk_collect
        beq     @nocollect
        lda     wlk_offset+1    ; more than MAX_DATA will not fit
        cmp     #>MAX_DATA
        bcc     @room
        bne     @invalid
        lda     wlk_offset
        cmp     #<MAX_DATA
        bcs     @invalid
@room:
        lda     wlk_offset
        sta     num
        lda     wlk_offset+1
        sta     num+1
        jsr     map_ptr
        ldy     #0
        lda     wlk_t
        sta     (ptr),y
        lda     wlk_s
        sta     (ptr2),y
@nocollect:
        inc     wlk_offset
        bne     @nooff
        inc     wlk_offset+1
@nooff:
        jsr     bump_total
@nextpair:
        inc     wlk_j
        lda     wlk_j
        cmp     #TS_PER_LIST
        jcc     @pair
        lda     wlk_nt
        beq     @chained
        lda     wlk_ended       ; a hole, and still another list
        bne     @invalid
@chained:
        lda     wlk_nt
        sta     wlk_t
        lda     wlk_ns
        sta     wlk_s
        lda     wlk_t
        beq     @ended
        jmp     @list
@ended:
        lda     wlk_total       ; the catalog's count must be the truth
        cmp     wlk_expect
        bne     @invalid
        lda     wlk_total+1
        cmp     wlk_expect+1
        bne     @invalid
        lda     wlk_collect
        beq     @ok
        lda     wlk_offset
        sta     data_count
        lda     wlk_offset+1
        sta     data_count+1
@ok:
        lda     #COPY_OK
        rts
@invalid:
        lda     #COPY_INVALID
@return:
        rts

; map_source -- follow the selected file's T/S chain only. The rest of
; the source disk is not walked.
map_source:
        lda     #CATALOG_TRACK
        ldx     #0
        jsr     read_at
        bne     @out
        SETPTR  ptr, buffer
        SETPTR  ptr2, vtoc
        jsr     memcpy256
        lda     vtoc+6
        sta     copy_src_volume
        jsr     locate_source
        bne     @out
        jsr     wipe_seen
        lda     cs_track
        sta     wlk_t
        lda     cs_sector
        sta     wlk_s
        lda     cs_seclo
        sta     wlk_expect
        lda     cs_sechi
        sta     wlk_expect+1
        lda     #1
        sta     wlk_collect
        jmp     walk
@out:
        rts

.ifdef SIM65
        .segment "CODE"
.else
        .segment "LOWCODE"      ; prepare-time only: room below the area
.endif
; locate_source -- read the catalog sector cs_slot names and hold the
; disk to the panel: the slot must still carry the T/S pointer, type,
; sector count and (sanitised) name the panel showed, or the disk is not
; the one the user pointed at (COPY_CHANGED). The raw 35-byte entry
; becomes src_entry, so the copy keeps the name byte for byte, catalog
; art included, and copy_execute can check the slot again after Y.
locate_source:
        lda     cs_slot
        lsr     a
        lsr     a
        lsr     a
        beq     @invalid
        sta     src_cat_sector
        lda     #CATALOG_TRACK
        sta     src_cat_track
        lda     cs_slot
        and     #7
        cmp     #CAT_ENTRIES
        bcs     @invalid
        jsr     slot_offset
        sta     src_cat_offset
        lda     src_cat_track
        ldx     src_cat_sector
        jsr     read_at
        bne     @out
        ldx     src_cat_offset
        lda     buffer,x
        cmp     cs_track
        bne     @changed
        lda     buffer+1,x
        cmp     cs_sector
        bne     @changed
        lda     buffer+2,x
        cmp     cs_type
        bne     @changed
        lda     buffer+33,x
        cmp     cs_seclo
        bne     @changed
        lda     buffer+34,x
        cmp     cs_sechi
        bne     @changed
        inx
        inx
        inx
        ldy     #0
@char:
        lda     buffer,x
        jsr     sanitise
        cmp     cs_name,y
        bne     @changed
        inx
        iny
        cpy     #NAME_LEN
        bcc     @char
        ldx     src_cat_offset
        ldy     #0
@take:
        lda     buffer,x
        sta     src_entry,y
        inx
        iny
        cpy     #CAT_ENTRY_LEN
        bcc     @take
        lda     #COPY_OK
@out:
        rts
@invalid:
        lda     #COPY_INVALID
        rts
@changed:
        lda     #COPY_CHANGED
        rts
        .segment "CODE"

wipe_seen:
        lda     #0
        ldx     #69
@wipe:
        sta     sector_seen,x
        dex
        bpl     @wipe
        rts

; scan_catalog -- destination VTOC and catalog names only. Finds a free
; slot and refuses a name that already exists. Other files' T/S chains
; are not followed.
scan_catalog:
        lda     #0
        sta     aud_files
        sta     aud_slot
        sta     aud_n
        sta     out_track
        lda     #CATALOG_TRACK
        ldx     #0
        jsr     read_at
        jne     @out
        SETPTR  ptr, buffer
        SETPTR  ptr2, vtoc
        jsr     memcpy256
        lda     vtoc+3
        cmp     #3
        jne     @invalid
        lda     vtoc+$34
        cmp     #35
        jne     @invalid
        lda     vtoc+$35
        cmp     #16
        jne     @invalid
        lda     vtoc+6
        sta     copy_dst_volume
        lda     vtoc+1
        sta     aud_t
        lda     vtoc+2
        sta     aud_s
@chain:
        inc     aud_n           ; the catalog track has 15 sectors: a
        lda     aud_n           ; longer chain is a loop, and the panel
        cmp     #16             ; read that refused it may be stale
        jcs     @invalid
        lda     aud_t
        cmp     #CATALOG_TRACK
        jne     @invalid
        lda     aud_s
        jeq     @invalid
        cmp     #16
        jcs     @invalid
        lda     aud_t
        ldx     aud_s
        jsr     read_at
        jne     @out
        SETPTR  ptr, buffer
        SETPTR  ptr2, cat_buf
        jsr     memcpy256
        lda     cat_buf+1
        sta     aud_nt
        lda     cat_buf+2
        sta     aud_ns
        lda     #CAT_FIRST
        sta     aud_off
        lda     #CAT_ENTRIES
        sta     aud_i
@entry:
        ldx     aud_off
        lda     cat_buf,x
        beq     @free
        cmp     #$FF
        bne     @live
@free:
        lda     aud_slot
        bne     @next
        lda     aud_t
        sta     out_track
        lda     aud_s
        sta     out_sector
        lda     aud_off
        sta     out_offset
        SETPTR  ptr, cat_buf
        SETPTR  ptr2, catalog_before
        jsr     memcpy256
        lda     #1
        sta     aud_slot
        jmp     @next
@live:
        inc     aud_files
        lda     aud_off
        clc
        adc     #3
        tax
        jsr     name_matches
        bcc     @next
        lda     #COPY_EXISTS
        rts
@next:
        lda     aud_off
        clc
        adc     #CAT_ENTRY_LEN
        sta     aud_off
        dec     aud_i
        jne     @entry
        lda     aud_nt
        sta     aud_t
        lda     aud_ns
        sta     aud_s
        lda     aud_t
        jne     @chain
        lda     aud_slot
        beq     @full
        lda     aud_files
        cmp     #MINI_MAX
        bcs     @full           ; 105 or a malformed count above it
        lda     #COPY_OK
@out:
        rts
@full:
        lda     #COPY_FULL
        rts
@invalid:
        lda     #COPY_INVALID
        rts

; =====================================================================
; copy_cancel -- a plan is only good for the confirmation it was shown
; with.
; =====================================================================
copy_cancel:
_copy_cancel:
        lda     copy_from       ; prepare left drive on the destination
        beq     @clr
        sta     drive
@clr:
        lda     #0
        sta     ready
        sta     ram_source
        sta     copy_from
        rts

; =====================================================================
; copy_prepare -- cp_index selects the file in the active panel, cp_dest
; is the drive it goes to. Reads only: nothing is written here, so the
; user can still say no.
; =====================================================================
; =====================================================================
; create_prepare -- exclusive new file from the working area.
;
; The caller has already put the bytes in scratch, and set cs_name,
; cs_type and data_count. data_count is the number of 256-byte sectors
; that will be published; it must fit in the working area, because that
; area is both the source and the write batch. An empty file still gets
; one sector, so it is a file and not a catalog ghost.
;
; Same drive is allowed: the source is RAM. The name must not exist.
; =====================================================================
create_prepare:
_create_prepare:
        lda     #0
        sta     ready
        sta     copy_from
        lda     #1
        sta     ram_source
        lda     copy_fault
        beq     @allowed
        lda     #COPY_UNCERTAIN
        rts
@allowed:
        lda     drive
        beq     @invalid
        cmp     #3
        bcs     @invalid
        sta     copy_to
        lda     data_count+1
        bne     @invalid        ; more than 255 sectors cannot be in RAM
        lda     data_count
        beq     @empty
        cmp     #BATCH_SECTORS+1
        bcs     @invalid
        jmp     @sized
@empty:
        lda     #1              ; a file with no T/S data still needs one
        sta     data_count
@sized:
        jsr     build_src_entry
        lda     copy_to
        sta     drive
        jsr     scan_catalog
        beq     @reserve
        rts
@reserve:
        jsr     count_lists
        lda     data_count
        clc
        adc     list_count
        sta     allocated_count
        lda     data_count+1
        adc     #0
        sta     allocated_count+1
        jsr     reserve
        bne     @done
        lda     #1
        sta     ready
        lda     #COPY_OK
@done:
        rts
@invalid:
        lda     #COPY_INVALID
        rts

; create_execute -- the RAM-source twin of copy_execute
create_execute:
_create_execute:
        jmp     copy_execute

; build_src_entry -- name and type only; T/S and size are filled at publish
build_src_entry:
        lda     #0
        sta     src_entry
        sta     src_entry+1
        lda     cs_type
        sta     src_entry+2
        ldx     #0
@name:
        lda     cs_name,x
        ora     #$80
        sta     src_entry+3,x
        inx
        cpx     #NAME_LEN
        bcc     @name
        lda     #0
        sta     src_entry+33
        sta     src_entry+34
        rts

; =====================================================================
; copy_prepare -- cp_index selects the file in the active panel, cp_dest
; is the drive it goes to. Reads only: nothing is written here, so the
; user can still say no.
; =====================================================================
copy_prepare:
_copy_prepare:
        lda     #0
        sta     ready
        sta     ram_source
        lda     copy_fault
        beq     @allowed
        lda     #COPY_UNCERTAIN
        rts
@allowed:
        lda     cp_index
        cmp     count
        jcs     @invalid
        lda     drive
        jeq     @invalid
        cmp     #3
        jcs     @invalid
        lda     cp_dest
        jeq     @invalid
        cmp     #3
        jcs     @invalid
        lda     drive
        cmp     cp_dest
        bne     @twodrives
        lda     #COPY_SAME
        rts
@twodrives:
        lda     cp_index        ; take the panel's idea of the file, then
        jsr     ent_index       ; walk that file only
        tay
        lda     ent_track,y
        sta     cs_track
        lda     ent_sector,y
        sta     cs_sector
        lda     ent_type,y
        sta     cs_type
        lda     ent_seclo,y
        sta     cs_seclo
        lda     ent_sechi,y
        sta     cs_sechi
        lda     ent_slot,y
        sta     cs_slot
        lda     cp_index
        jsr     ent_index
        jsr     ent_ptr
        ldy     #0
@name:
        lda     (ptr),y
        sta     cs_name,y
        iny
        cpy     #NAME_LEN
        bcc     @name
        lda     drive
        sta     copy_from
        lda     cp_dest
        sta     copy_to
        jsr     map_source
        bne     @out
        lda     copy_to
        sta     drive
        jsr     scan_catalog
        beq     @reserve
@out:
        rts
@reserve:
        jsr     count_lists
        lda     data_count
        clc
        adc     list_count
        sta     allocated_count
        lda     data_count+1
        adc     #0
        sta     allocated_count+1
        jsr     reserve
        bne     @done
        lda     #1
        sta     ready
        lda     #COPY_OK
@done:
        rts
@invalid:
        lda     #COPY_INVALID
        rts

.ifdef SIM65
        .segment "CODE"
.else
        .segment "LOWCODE"      ; prepare-time only: room below the area
.endif
; count_lists -- ceil(data_count / 122), never fewer than one, so an
; empty file still gets the T/S list that makes it a file.
count_lists:
        lda     data_count
        sta     num
        lda     data_count+1
        sta     num+1
        lda     #0
        sta     list_count
@loop:
        lda     num
        ora     num+1
        beq     @done
        inc     list_count
        lda     num
        sec
        sbc     #TS_PER_LIST
        sta     num
        lda     num+1
        sbc     #0
        sta     num+1
        bcs     @loop
        lda     #0              ; the subtraction went below zero
        sta     num
        sta     num+1
        jmp     @loop
@done:
        lda     list_count
        bne     @have
        inc     list_count
@have:
        rts
        .segment "CODE"

; reserve -- choose allocated_count free sectors in disk order. The last
; list_count of them become the T/S lists. Nothing is written: the VTOC
; on the disk keeps its own bits until the user confirms.
reserve:
        lda     #0
        ldx     #69
@wipe:
        sta     target_bits,x
        dex
        bpl     @wipe
        lda     #0
        sta     num             ; sectors chosen so far
        sta     num+1
        lda     #1              ; track 0 is the boot track; 1 and 2 are
        sta     s4              ; free only on a disk without DOS, where
@track:                         ; DOS itself files data on them
        lda     num
        cmp     allocated_count
        bne     @room
        lda     num+1
        cmp     allocated_count+1
        beq     @done
@room:
        lda     s4
        cmp     #35
        bcs     @done
        cmp     #CATALOG_TRACK
        beq     @nexttrack
        lda     #0
        sta     w2
@sector:
        lda     num
        cmp     allocated_count
        bne     @space
        lda     num+1
        cmp     allocated_count+1
        beq     @done
@space:
        lda     w2
        cmp     #16
        bcs     @nexttrack
        lda     s4
        ldx     w2
        jsr     free_sector
        beq     @nextsector
        lda     s4              ; mark it in our own reservation
        ldx     w2
        jsr     seen_bit
        ldx     bidx
        lda     target_bits,x
        ora     bmsk
        sta     target_bits,x
        lda     num+1           ; the tail of the reservation is the lists
        cmp     data_count+1
        bcc     @isdata
        bne     @islist
        lda     num
        cmp     data_count
        bcc     @isdata
@islist:
        lda     num
        sec
        sbc     data_count
        tax
        lda     s4
        sta     tl_t,x
        lda     w2
        sta     tl_s,x
@isdata:
        jsr     bump_num
@nextsector:
        inc     w2
        jmp     @sector
@nexttrack:
        inc     s4
        jmp     @track
@done:
        lda     num             ; enough of them?
        cmp     allocated_count
        bne     @short
        lda     num+1
        cmp     allocated_count+1
        bne     @short
        lda     #COPY_OK
        rts
@short:
        lda     #COPY_FULL
        rts

; =====================================================================
; copy_execute -- the only routine here that writes.
; =====================================================================
copy_execute:
_copy_execute:
        lda     copy_fault
        beq     @allowed
        lda     #COPY_UNCERTAIN
        rts
@allowed:
        lda     ready
        bne     @planned
        lda     #COPY_NOT_READY
        rts
@planned:
        lda     #0
        sta     ready           ; one confirmation, one copy
        sta     copy_done
        sta     copy_done+1
        lda     allocated_count
        clc
        adc     #2              ; VTOC write and the catalog entry
        sta     copy_total
        lda     allocated_count+1
        adc     #0
        sta     copy_total+1
        lda     ram_source      ; a disk source: its catalog slot must
        bne     @srcok          ; still be the entry that was mapped, or
        lda     copy_from       ; a source swapped at the prompt would be
        sta     drive           ; read sector by sector as if it were it
        lda     src_cat_track
        ldx     src_cat_sector
        jsr     read_at
        jne     @unread
        ldx     src_cat_offset
        ldy     #0
@srccmp:
        lda     buffer,x
        cmp     src_entry,y
        jne     @changed
        inx
        iny
        cpy     #CAT_ENTRY_LEN
        bcc     @srccmp
@srcok:
        lda     copy_to         ; the VTOC is about to be replaced from
        sta     drive           ; the reservation image: it must still be
        lda     #CATALOG_TRACK  ; the one that image was planned on, or
        ldx     #0              ; a disk swapped at the prompt would get
        jsr     read_at         ; another disk's allocation map
        jne     @unread
        SETPTR  ptr, buffer
        SETPTR  ptr2, vtoc
        jsr     memcmp256
        jne     @changed
        jsr     copy_progress

; Take the reserved sectors out of the VTOC image. Still in RAM.
@clearbits:
        lda     #0
        sta     target_index
        sta     target_index+1
        sta     num
        sta     num+1
@onebit:
        lda     num
        cmp     allocated_count
        bne     @clearone
        lda     num+1
        cmp     allocated_count+1
        beq     @writevtoc
@clearone:
        jsr     next_target
        bne     @changed
        lda     tgt_t
        ldx     tgt_s
        jsr     free_sector
        beq     @changed        ; somebody took it while we were asking
        lda     tgt_t
        ldx     tgt_s
        jsr     vtoc_bit
        ldx     bidx
        lda     bmsk
        eor     #$FF
        and     vtoc,x
        sta     vtoc,x
        jsr     bump_num
        jmp     @onebit
@changed:
        lda     #COPY_CHANGED
        rts
@unread:
        lda     #COPY_READ      ; nothing written yet: a plain refusal
        rts

; The reservation reaches the disk before any data. Interrupted here the
; sectors are merely lost, which VOLINFO reports; the other order would
; leave a file pointing at sectors DOS believes are free.
@writevtoc:
        SETPTR  ptr, vtoc
        SETPTR  ptr2, buffer
        jsr     memcpy256
        lda     #CATALOG_TRACK
        ldx     #0
        jsr     put_verified
        bne     @vtocfail
        jsr     tick_progress
        jmp     @data
@vtocfail:
        cmp     #COPY_PROTECTED
        beq     @protected
        jmp     @uncertain
@protected:
        rts

; ---- the data, one batch per change of drive ----
@data:
        lda     #0
        sta     target_index
        sta     target_index+1
        sta     bat_index
        sta     bat_index+1
@batch:
        lda     bat_index
        cmp     data_count
        bne     @batchwork
        lda     bat_index+1
        cmp     data_count+1
        beq     @lists
@batchwork:
        jsr     batch_plan
        jne     @uncertain
        jsr     batch_read
        jne     @uncertain
        jsr     batch_write
        bne     @writefail
        lda     bat_index
        clc
        adc     bat_n
        sta     bat_index
        bcc     @batch
        inc     bat_index+1
        jmp     @batch
@writefail:
        cmp     #COPY_PROTECTED
        jeq     @prot_after
        jmp     @uncertain

; ---- the T/S lists, once every data sector is down and checked ----
@lists:
        lda     #0
        sta     target_index
        sta     target_index+1
        sta     lst_no
@onelist:
        lda     lst_no
        cmp     list_count
        jcs     @publish
        lda     #0
        tax
@blank:
        sta     buffer,x
        inx
        bne     @blank
        lda     lst_no          ; link to the next list, if there is one
        clc
        adc     #1
        cmp     list_count
        bcs     @nolink
        tax
        lda     tl_t,x
        sta     buffer+1
        lda     tl_s,x
        sta     buffer+2
@nolink:
        lda     #0              ; offset = lst_no * 122
        sta     num
        sta     num+1
        ldx     lst_no
        beq     @haveoffset
@mul:
        lda     num
        clc
        adc     #TS_PER_LIST
        sta     num
        lda     num+1
        adc     #0
        sta     num+1
        dex
        bne     @mul
@haveoffset:
        lda     num
        sta     buffer+5
        lda     num+1
        sta     buffer+6
        lda     #0
        sta     lst_pair
@pairloop:
        lda     lst_pair
        cmp     #TS_PER_LIST
        bcs     @writelist
        lda     num
        cmp     data_count
        bne     @pairroom
        lda     num+1
        cmp     data_count+1
        beq     @writelist
@pairroom:
        jsr     next_target
        jne     @uncertain
        lda     lst_pair
        asl     a
        tax
        lda     tgt_t
        sta     buffer+12,x
        lda     tgt_s
        sta     buffer+13,x
        jsr     bump_num
        inc     lst_pair
        jmp     @pairloop
@writelist:
        ldx     lst_no
        lda     tl_s,x
        sta     s3
        lda     tl_t,x
        ldx     s3
        jsr     put_verified
        bne     @listfail
        jsr     tick_progress
        jmp     @nextlist
@listfail:
        cmp     #COPY_PROTECTED
        jeq     @prot_after
        jmp     @uncertain
@nextlist:
        inc     lst_no
        jmp     @onelist

; ---- nothing is visible until here ----
@publish:
        lda     copy_to
        sta     drive
        lda     out_track
        ldx     out_sector
        jsr     read_at
        jne     @uncertain
        ldx     out_offset
        lda     buffer,x
        beq     @slot
        cmp     #$FF
        jne     @uncertain
@slot:
        ldx     out_offset
        ldy     #0
@entry:
        lda     src_entry,y
        sta     buffer,x
        inx
        iny
        cpy     #CAT_ENTRY_LEN
        bcc     @entry
        ldx     out_offset
        lda     tl_t
        sta     buffer,x
        lda     tl_s
        sta     buffer+1,x
        lda     allocated_count
        sta     buffer+33,x
        lda     allocated_count+1
        sta     buffer+34,x
        lda     out_track
        ldx     out_sector
        jsr     put_verified
        bne     @pubfail
        jsr     tick_progress
        lda     #COPY_OK
        rts
@pubfail:
        cmp     #COPY_PROTECTED
        jeq     @prot_after
        jmp     @uncertain
@prot_after:
        lda     #1
        sta     copy_fault
        lda     #COPY_PROTECTED
        rts
@uncertain:
        lda     #1
        sta     copy_fault
        lda     #COPY_UNCERTAIN
        rts

; =====================================================================
; One batch: plan it, read it from the source, write and read back each
; sector on the target. The two disks are not compared again.
; =====================================================================

; batch_plan -- how many sectors, and which target sectors they go to
batch_plan:
        lda     data_count      ; left = data_count - bat_index
        sec
        sbc     bat_index
        sta     s0
        lda     data_count+1
        sbc     bat_index+1
        bne     @full           ; more than 255 still to go
        lda     s0
        cmp     #BATCH_SECTORS
        bcc     @part
@full:
        lda     #BATCH_SECTORS
        jmp     @have
@part:
        lda     s0
@have:
        sta     bat_n
        lda     #0
        sta     bat_k
@target:
        lda     bat_k
        cmp     bat_n
        bcs     @done
        jsr     next_target
        bne     @fail
        ldx     bat_k
        lda     tgt_t
        sta     bat_t,x
        lda     tgt_s
        sta     bat_s,x
        inc     bat_k
        jmp     @target
@done:
        lda     #COPY_OK
        rts
@fail:
        lda     #COPY_UNCERTAIN
        rts

; batch_source_index -- num = bat_index + bat_k
batch_source_index:
        lda     bat_index
        clc
        adc     bat_k
        sta     num
        lda     bat_index+1
        adc     #0
        sta     num+1
        rts

; batch_read -- the source drive, once, into the working area.
; A RAM source already lives there; reading it again would overwrite it.
batch_read:
        lda     ram_source
        bne     @ram
        lda     copy_from
        sta     drive
        lda     #0
        sta     bat_k
@loop:
        lda     bat_k
        cmp     bat_n
        bcs     @done
        jsr     batch_source_index
        jsr     map_ptr
        ldy     #0
        lda     (ptr2),y
        tax
        lda     (ptr),y
        jsr     read_at
        bne     @fail
        SETPTR  ptr, buffer
        lda     bat_k
        jsr     batch_ptr
        jsr     memcpy256
        inc     bat_k
        jmp     @loop
@ram:
@done:
        lda     #COPY_OK
        rts
@fail:
        lda     #COPY_UNCERTAIN ; past the first write, a read failure is
        rts                     ; uncertain, not a plain read error

; batch_write -- the target drive, once: write each sector and read it
; back, exactly as the C edition's put_verified did
batch_write:
        lda     #0
        sta     bat_k
@loop:
        lda     bat_k
        cmp     bat_n
        bcs     @done
        lda     bat_k
        jsr     batch_ptr
        lda     ptr2
        sta     ptr
        lda     ptr2+1
        sta     ptr+1
        SETPTR  ptr2, buffer
        jsr     memcpy256
        ldx     bat_k
        lda     bat_s,x
        sta     s3
        lda     bat_t,x
        ldx     s3
        jsr     put_verified
        bne     @fail
        jsr     tick_progress
        inc     bat_k
        jmp     @loop
@done:
        lda     #COPY_OK
@fail:
        rts

tick_progress:
        inc     copy_done
        bne     @go
        inc     copy_done+1
@go:
        jmp     copy_progress

