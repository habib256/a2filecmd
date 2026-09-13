; delete.s -- mark the catalog entry first, then free the sectors.
;
; A locked file is refused before any write. The order is the safety
; argument: once the catalog says the file is gone, a crash can leak
; sectors, which VOLINFO reports, but it cannot hand those sectors to
; another file while the name still claims them. The other order -- free
; first -- would leave a live name pointing at sectors DOS believes are
; free, and the next create would destroy the data.
;
; A physical write is not atomic. An uncertain catalog or VTOC write
; latches del_fault so this run cannot write again.

        .include "mini.inc"

        .export delete_prepare, delete_execute, delete_cancel
        .export lock_prepare, lock_execute, rename_prepare, rename_execute
        .export del_index, del_fault, lock_op, lock_ready, ren_name
        .export _delete_prepare, _delete_execute, _delete_cancel
        .export _lock_prepare, _lock_execute, _rename_prepare, _rename_execute
        .export _del_index, _del_fault, _lock_op, _lock_ready, _ren_name

        .import read_sector, write_sector, rwts_error
        .import buffer, drive, track, sector, count, sector_seen
        .import ent_track, ent_sector, ent_type, ent_seclo, ent_sechi
        .import ent_slot, ent_index, ent_ptr, sanitise
        .import seen_bit, bit_masks
        .import valid_data, read_at, vtoc_bit, memcpy256, memcmp256
        .import slot_offset
        .import vtoc, catalog_before, verify, cat_buf

        .segment "BSS"
del_index:      .res 1
del_fault:      .res 1
_del_index      = del_index
_del_fault      = del_fault

del_ready:      .res 1
lock_ready:     .res 1
ren_ready:      .res 1
lock_op:        .res 1          ; 0 toggle, 1 unlock, 2 lock
ren_name:       .res NAME_LEN
_lock_ready     = lock_ready
_lock_op        = lock_op
_ren_name       = ren_name
del_track:      .res 1          ; T/S list of the file being removed
del_sector:     .res 1
del_type:       .res 1
del_seclo:      .res 1
del_sechi:      .res 1
del_name:       .res NAME_LEN
del_cat_t:      .res 1
del_cat_s:      .res 1
del_cat_off:    .res 1
del_volume:     .res 1
pan_track:      .res 1          ; the panel's idea of the entry: the disk
pan_sector:     .res 1          ; is held to it, name alone is not an
pan_type:       .res 1          ; identity (contiguous, same order as
pan_seclo:      .res 1          ; del_track..del_sechi)
pan_sechi:      .res 1
pan_slot:       .res 1          ; catalog sector << 3 | slot the entry came from
aud_n:          .res 1          ; catalog sectors visited: 15 at most

ts_list         = cat_buf

wlk_t:          .res 1
wlk_s:          .res 1
wlk_nt:         .res 1
wlk_ns:         .res 1
wlk_ended:      .res 1
wlk_j:          .res 1
wlk_total:      .res 2
wlk_expect:     .res 2
wlk_offset:     .res 2          ; data sectors already seen, as in copy walk
aud_t:          .res 1
aud_s:          .res 1
aud_nt:         .res 1
aud_ns:         .res 1
aud_i:          .res 1
aud_off:        .res 1

.ifdef SIM65
        .segment "CODE"
.else
        .segment "LOWCODE"
.endif

; ---------------------------------------------------------------------
; memcpy256, memcmp256, read_at and vtoc_bit come from copy.s: the DEL_
; and COPY_ codes for OK and READ are the same numbers.

; put_verified -- A = track, X = sector. Write protection is reported as
; itself: RWTS refuses before touching the disk, so the caller knows
; whether anything was written before it. Anything else is uncertain.
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
        jsr     write_sector
        beq     @wrote
        lda     rwts_error
        cmp     #RWTS_PROTECTED
        bne     @uncertain
        lda     #DEL_PROTECTED
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
        lda     #DEL_OK
        rts
@uncertain:
        lda     #DEL_UNCERTAIN
        rts

free_in_vtoc:
        jsr     vtoc_bit
        ldx     bidx
        lda     vtoc,x
        and     bmsk
        bne     @already        ; already free: the disk is not the one we audited
        lda     bmsk
        ora     vtoc,x
        sta     vtoc,x
        lda     #DEL_OK
        rts
@already:
        lda     #DEL_CHANGED
        rts

allocated:
        jsr     vtoc_bit
        ldx     bidx
        lda     vtoc,x
        and     bmsk
        bne     @free
        lda     #DEL_OK
        rts
@free:
        lda     #DEL_INVALID
        rts

; ---------------------------------------------------------------------
delete_cancel:
_delete_cancel:
        lda     #0
        sta     del_ready
        rts

; ---------------------------------------------------------------------
; delete_prepare -- del_index selects the file. Reads only.
; ---------------------------------------------------------------------
delete_prepare:
_delete_prepare:
        lda     #0
        sta     del_ready
        lda     del_fault
        beq     @allowed
        lda     #DEL_UNCERTAIN
        rts
@allowed:
        lda     del_index
        cmp     count
        jcs     @invalid
        lda     drive
        beq     @invalid
        cmp     #3
        bcs     @invalid
        jsr     snapshot_panel
        lda     pan_type
        and     #$80
        beq     @unlocked
        lda     #DEL_LOCKED
        rts
@unlocked:
        jsr     find_and_walk
        bne     @out
        lda     #1
        sta     del_ready
        lda     #DEL_OK
@out:
        rts
@invalid:
        lda     #DEL_INVALID
        rts

; find_and_walk -- hold the disk to the panel's idea of the file
find_and_walk:
        jsr     find_entry
        bne     @out
        lda     del_type
        and     #$80
        beq     @walkit
        lda     #DEL_LOCKED
        rts
@walkit:
        ldx     #69
        lda     #0
@wipe:
        sta     sector_seen,x
        dex
        bpl     @wipe
        jsr     walk_file
@out:
        rts

; find_entry -- read the VTOC and the catalog sector the panel took the
; entry from, and hold the disk to the panel: the slot must still carry
; the T/S pointer, type, sector count and (sanitised) name it showed, or
; the disk is not the one the user was looking at (DEL_CHANGED). A name
; alone is not an identity: the panel shows unprintable characters as
; '?', and a sibling disk can reuse a name. Locked files are allowed: lock
; and rename need the slot. The T/S chain is not followed.
find_entry:
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
        sta     del_volume
        lda     pan_slot
        lsr     a
        lsr     a
        lsr     a
        jeq     @invalid
        sta     del_cat_s
        lda     #CATALOG_TRACK
        sta     del_cat_t
        lda     pan_slot
        and     #7
        cmp     #CAT_ENTRIES
        jcs     @invalid
        jsr     slot_offset
        sta     del_cat_off
        lda     del_cat_t
        ldx     del_cat_s
        jsr     read_at
        jne     @out
        SETPTR  ptr, buffer
        SETPTR  ptr2, catalog_before
        jsr     memcpy256
        ldx     del_cat_off
        lda     buffer,x
        beq     @changed        ; the slot was emptied
        cmp     #$FF
        beq     @changed
        sta     del_track
        lda     buffer+1,x
        sta     del_sector
        lda     buffer+2,x
        sta     del_type
        lda     buffer+33,x
        sta     del_seclo
        lda     buffer+34,x
        sta     del_sechi
        jsr     same_as_panel
        bcc     @changed
        ldx     del_cat_off
        inx
        inx
        inx
        ldy     #0
@char:
        lda     buffer,x
        jsr     sanitise
        cmp     del_name,y
        bne     @changed
        inx
        iny
        cpy     #NAME_LEN
        bcc     @char
        lda     #DEL_OK
@out:
        rts
@invalid:
        lda     #DEL_INVALID
        rts
@changed:
        lda     #DEL_CHANGED
        rts

; same_as_panel -- carry set when the entry just copied into del_track..
; del_sechi is the one the panel showed
same_as_panel:
        ldx     #4
@byte:
        lda     del_track,x
        cmp     pan_track,x
        bne     @no
        dex
        bpl     @byte
        sec
        rts
@no:
        clc
        rts

; walk_file -- every sector the file owns must be allocated and unique
walk_file:
        lda     del_track
        sta     wlk_t
        lda     del_sector
        sta     wlk_s
        lda     #0
        sta     wlk_ended
        sta     wlk_total
        sta     wlk_total+1
        sta     wlk_offset
        sta     wlk_offset+1
        lda     del_seclo
        sta     wlk_expect
        lda     del_sechi
        sta     wlk_expect+1
@list:
        lda     wlk_t
        ldx     wlk_s
        jsr     valid_data
        jcc     @invalid
        jsr     claim_used
        jne     @out
        inc     wlk_total       ; the T/S list itself is in the catalog count
        bne     @nolist
        inc     wlk_total+1
@nolist:
        lda     wlk_t
        ldx     wlk_s
        jsr     read_at
        jne     @out
        ldx     #0
@keep:
        lda     buffer,x
        sta     ts_list,x
        inx
        bne     @keep
        lda     ts_list+1
        sta     wlk_nt
        lda     ts_list+2
        sta     wlk_ns
        lda     ts_list+5
        cmp     wlk_offset
        jne     @invalid
        lda     ts_list+6
        cmp     wlk_offset+1
        jne     @invalid
        lda     #0
        sta     wlk_j
@pair:
        lda     wlk_j
        asl     a
        tax
        lda     ts_list+12,x
        sta     wlk_t
        lda     ts_list+13,x
        sta     wlk_s
        ora     wlk_t
        bne     @live
        lda     #1
        sta     wlk_ended
        jmp     @nextpair
@live:
        lda     wlk_ended
        bne     @invalid
        lda     wlk_t
        ldx     wlk_s
        jsr     valid_data
        bcc     @invalid
        jsr     claim_used
        bne     @out
        inc     wlk_total
        bne     @off
        inc     wlk_total+1
@off:
        inc     wlk_offset
        bne     @nextpair
        inc     wlk_offset+1
@nextpair:
        inc     wlk_j
        lda     wlk_j
        cmp     #TS_PER_LIST
        bcc     @pair
        lda     wlk_nt
        beq     @check
        lda     wlk_ended
        bne     @invalid
        lda     wlk_nt
        sta     wlk_t
        lda     wlk_ns
        sta     wlk_s
        jmp     @list
@check:
        lda     wlk_total
        cmp     wlk_expect
        bne     @invalid
        lda     wlk_total+1
        cmp     wlk_expect+1
        bne     @invalid
        lda     #DEL_OK
@out:
        rts
@invalid:
        lda     #DEL_INVALID
        rts

claim_used:
        sta     s0
        stx     s1
        jsr     seen_bit
        ldx     bidx
        lda     sector_seen,x
        and     bmsk
        bne     @invalid
        lda     sector_seen,x
        ora     bmsk
        sta     sector_seen,x
        lda     s0
        ldx     s1
        jsr     allocated
        rts
@invalid:
        lda     #DEL_INVALID
        rts

; ---------------------------------------------------------------------
; delete_execute -- the only routine here that writes.
; ---------------------------------------------------------------------
delete_execute:
_delete_execute:
        lda     del_fault
        beq     @allowed
        lda     #DEL_UNCERTAIN
        rts
@allowed:
        lda     del_ready
        bne     @planned
        lda     #DEL_NOT_READY
        rts
@planned:
        lda     #0
        sta     del_ready
        lda     #CATALOG_TRACK
        ldx     #0
        jsr     read_at
        jne     @fail
        SETPTR  ptr, buffer
        SETPTR  ptr2, vtoc
        jsr     memcmp256
        bne     @changed
        lda     del_cat_t
        ldx     del_cat_s
        jsr     read_at
        jne     @fail
        SETPTR  ptr, buffer
        SETPTR  ptr2, catalog_before
        jsr     memcmp256
        bne     @changed
        ldx     del_cat_off
        lda     buffer,x        ; DOS UNDELETE convention: the T/S list
        sta     buffer+32,x     ; track goes into the LAST name byte
        lda     #$FF            ; (entry+$20), then the track byte is $FF
        sta     buffer,x
        lda     del_cat_t
        ldx     del_cat_s
        jsr     put_verified
        beq     @marked
        cmp     #DEL_PROTECTED  ; refused before the first write: nothing
        bne     @aftercat       ; on the disk moved, nothing to latch
        rts
@marked:
        jsr     free_chain
        bne     @aftercat
        SETPTR  ptr, vtoc
        SETPTR  ptr2, buffer
        jsr     memcpy256
        lda     #CATALOG_TRACK
        ldx     #0
        jsr     put_verified
        bne     @aftercat
        lda     #DEL_OK
        rts
@changed:
        lda     #DEL_CHANGED
        rts
@aftercat:
        ; the catalog is already marked, or the write is uncertain
        cmp     #DEL_UNCERTAIN
        beq     @latch
        ; a changed/invalid VTOC after a published delete is uncertain
        lda     #DEL_UNCERTAIN
@latch:
        sta     s0
        lda     #1
        sta     del_fault
        lda     s0
        rts
@fail:
        lda     #DEL_READ
        rts

; free_chain -- walk the saved T/S pointer and mark those sectors free
; in the VTOC image. The catalog already says the file is gone.
free_chain:
        lda     del_track
        sta     wlk_t
        lda     del_sector
        sta     wlk_s
@list:
        lda     wlk_t
        ldx     wlk_s
        jsr     valid_data
        bcc     @bad
        jsr     free_in_vtoc
        bne     @out
        lda     wlk_t
        ldx     wlk_s
        jsr     read_at
        bne     @out
        ldx     #0
@keep:
        lda     buffer,x
        sta     ts_list,x
        inx
        bne     @keep
        lda     ts_list+1
        sta     wlk_nt
        lda     ts_list+2
        sta     wlk_ns
        lda     #0
        sta     wlk_j
@pair:
        lda     wlk_j
        asl     a
        tax
        lda     ts_list+12,x
        sta     wlk_t
        lda     ts_list+13,x
        sta     wlk_s
        ora     wlk_t
        beq     @next
        lda     wlk_t
        ldx     wlk_s
        jsr     valid_data
        bcc     @bad
        jsr     free_in_vtoc
        bne     @out
@next:
        inc     wlk_j
        lda     wlk_j
        cmp     #TS_PER_LIST
        bcc     @pair
        lda     wlk_nt
        beq     @ok
        sta     wlk_t
        lda     wlk_ns
        sta     wlk_s
        jmp     @list
@ok:
        lda     #DEL_OK
@out:
        rts
@bad:
        lda     #DEL_UNCERTAIN
        rts

; ---------------------------------------------------------------------
; lock_prepare -- del_index + lock_op. Reads only.
; lock_op: 0 toggle, 1 unlock, 2 lock. Already-desired state is
; DEL_LOCKED so a batch can skip it without writing.
; ---------------------------------------------------------------------
lock_prepare:
_lock_prepare:
        lda     #0
        sta     lock_ready
        jsr     meta_gate
        bne     @out
        jsr     snapshot_panel
        jsr     find_entry
        bne     @out
        lda     lock_op
        beq     @ready
        cmp     #1
        beq     @want_off
        lda     del_type
        and     #$80
        bne     @same
        jmp     @ready
@want_off:
        lda     del_type
        and     #$80
        beq     @same
@ready:
        lda     #1
        sta     lock_ready
        lda     #DEL_OK
@out:
        rts
@same:
        lda     #DEL_LOCKED
        rts

lock_execute:
_lock_execute:
        lda     del_fault
        beq     @nofault
        lda     #DEL_UNCERTAIN
        rts
@nofault:
        lda     lock_ready
        bne     @planned
        lda     #DEL_NOT_READY
        rts
@planned:
        lda     #0
        sta     lock_ready
        jsr     recat_same
        bne     @out
        ldx     del_cat_off
        lda     lock_op
        beq     @tog
        cmp     #1
        beq     @unl
        lda     buffer+2,x
        ora     #$80
        jmp     @store
@unl:
        lda     buffer+2,x
        and     #$7F
        jmp     @store
@tog:
        lda     buffer+2,x
        eor     #$80
@store:
        sta     buffer+2,x
        lda     del_cat_t
        ldx     del_cat_s
        jsr     put_verified
        beq     @ok
        cmp     #DEL_PROTECTED  ; the only write, refused: nothing to latch
        beq     @ok
        jsr     latch_fault
@ok:
@out:
        rts

; ---------------------------------------------------------------------
; rename_prepare -- del_index is the old name, ren_name the new one.
; Locked files are refused. A live collision is refused. The same name
; is a no-op (DEL_LOCKED to the batch, no write).
; ---------------------------------------------------------------------
rename_prepare:
_rename_prepare:
        lda     #0
        sta     ren_ready
        jsr     meta_gate
        bne     @out
        jsr     snapshot_panel
        jsr     names_same
        bcs     @same
        jsr     find_entry
        bne     @out
        lda     del_type
        and     #$80
        bne     @locked
        jsr     ren_collision
        bcs     @out            ; A says why: REN_EXISTS, INVALID or READ
        lda     #1
        sta     ren_ready
        lda     #DEL_OK
@out:
        rts
@same:
        lda     #DEL_LOCKED
        rts
@locked:
        lda     #DEL_LOCKED
        rts

rename_execute:
_rename_execute:
        lda     del_fault
        beq     @nofault
        lda     #DEL_UNCERTAIN
        rts
@nofault:
        lda     ren_ready
        bne     @planned
        lda     #DEL_NOT_READY
        rts
@planned:
        lda     #0
        sta     ren_ready
        jsr     recat_same
        bne     @out
        jsr     ren_collision
        bcs     @out            ; A says why: REN_EXISTS, INVALID or READ
        SETPTR  ptr, catalog_before
        SETPTR  ptr2, buffer
        jsr     memcpy256
        ldx     del_cat_off
        inx
        inx
        inx
        ldy     #0
@copy:
        lda     ren_name,y
        ora     #$80
        sta     buffer,x
        inx
        iny
        cpy     #NAME_LEN
        bcc     @copy
        lda     del_cat_t
        ldx     del_cat_s
        jsr     put_verified
        beq     @ok
        cmp     #DEL_PROTECTED  ; the only write, refused: nothing to latch
        beq     @ok
        jsr     latch_fault
@ok:
@out:
        rts

meta_gate:
        lda     del_fault
        beq     @ok
        lda     #DEL_UNCERTAIN
        rts
@ok:
        lda     del_index
        cmp     count
        bcs     @inv
        lda     drive
        beq     @inv
        cmp     #3
        bcs     @inv
        lda     #0
        rts
@inv:
        lda     #DEL_INVALID
        rts

; snapshot_panel -- what the panel shows for del_index: T/S pointer,
; type, sector count, slot and name. find_entry holds the disk to these.
snapshot_panel:
        lda     del_index
        jsr     ent_index
        tay
        lda     ent_track,y
        sta     pan_track
        lda     ent_sector,y
        sta     pan_sector
        lda     ent_type,y
        sta     pan_type
        lda     ent_seclo,y
        sta     pan_seclo
        lda     ent_sechi,y
        sta     pan_sechi
        lda     ent_slot,y
        sta     pan_slot
        lda     del_index
        jsr     ent_index
        jsr     ent_ptr
        ldy     #0
@n:
        lda     (ptr),y
        sta     del_name,y
        iny
        cpy     #NAME_LEN
        bcc     @n
        rts

names_same:
        ldy     #0
@n:
        lda     del_name,y
        cmp     ren_name,y
        bne     @no
        iny
        cpy     #NAME_LEN
        bcc     @n
        sec
        rts
@no:
        clc
        rts

; recat_same -- VTOC and the saved catalog sector are still the ones
; we planned against. A is 0, or DEL_CHANGED / DEL_READ.
recat_same:
        lda     #CATALOG_TRACK
        ldx     #0
        jsr     read_at
        bne     @fail
        SETPTR  ptr, buffer
        SETPTR  ptr2, vtoc
        jsr     memcmp256
        bne     @chg
        lda     del_cat_t
        ldx     del_cat_s
        jsr     read_at
        bne     @fail
        SETPTR  ptr, buffer
        SETPTR  ptr2, catalog_before
        jsr     memcmp256
        bne     @chg
        lda     #DEL_OK
        rts
@chg:
        lda     #DEL_CHANGED
        rts
@fail:
        lda     #DEL_READ
        rts

latch_fault:
        sta     s0
        lda     #1
        sta     del_fault
        lda     s0
        rts

; ren_collision -- carry set when the rename must be refused, with A
; saying why: REN_EXISTS when ren_name is already a live file that is not
; the slot we are renaming, DEL_INVALID for a malformed or looping chain,
; DEL_READ when a catalog sector could not be read. Destroys buffer;
; catalog_before still holds our sector.
ren_collision:
        lda     #0
        sta     aud_n
        lda     vtoc+1
        sta     aud_t
        lda     vtoc+2
        sta     aud_s
@chain:
        inc     aud_n           ; a chain longer than the track is a loop
        lda     aud_n
        cmp     #16
        bcs     @inv
        lda     aud_t
        cmp     #CATALOG_TRACK
        bne     @inv
        lda     aud_s
        beq     @inv
        cmp     #16
        bcs     @inv
        lda     aud_t
        ldx     aud_s
        jsr     read_at
        bne     @rd
        lda     buffer+1
        sta     aud_nt
        lda     buffer+2
        sta     aud_ns
        lda     #CAT_FIRST
        sta     aud_off
        lda     #CAT_ENTRIES
        sta     aud_i
@entry:
        jsr     our_slot
        bcs     @next
        ldx     aud_off
        lda     buffer,x
        beq     @next
        cmp     #$FF
        beq     @next
        jsr     name_ren
        bcs     @yes
@next:
        lda     aud_off
        clc
        adc     #CAT_ENTRY_LEN
        sta     aud_off
        dec     aud_i
        bne     @entry
        lda     aud_nt
        sta     aud_t
        lda     aud_ns
        sta     aud_s
        lda     aud_t
        bne     @chain
        clc
        rts
@yes:
        lda     #REN_EXISTS
        sec
        rts
@inv:
        lda     #DEL_INVALID
@rd:                            ; A is already DEL_READ from read_at
        sec
        rts

our_slot:
        lda     aud_t
        cmp     del_cat_t
        bne     @no
        lda     aud_s
        cmp     del_cat_s
        bne     @no
        lda     aud_off
        cmp     del_cat_off
        bne     @no
        sec
        rts
@no:
        clc
        rts

name_ren:
        ldx     aud_off
        inx
        inx
        inx
        ldy     #0
@char:
        lda     buffer,x
        sta     s0
        lda     ren_name,y
        ora     #$80
        cmp     s0
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
