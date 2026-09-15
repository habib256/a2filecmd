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
; latches del_fault so this run cannot write again. del_fault is the
; copy engine's copy_fault: one latch for every write in the run.
;
; Before any write, every other file on the disk is walked too. Two
; entries claiming one sector is a cross-linked disk: freeing that sector
; would hand the other file's data to the next copy, so delete refuses.

        .include "mini.inc"

        .export delete_prepare, delete_execute, delete_cancel
        .export lock_prepare, lock_execute, rename_prepare, rename_execute
        .export del_index, lock_op, lock_ready, ren_name
        .export _delete_prepare, _delete_execute, _delete_cancel
        .export _lock_prepare, _lock_execute, _rename_prepare, _rename_execute
        .export _del_index, _lock_op, _lock_ready, _ren_name

        .import read_sector, write_sector, rwts_error
        .import buffer, drive, track, sector, count
        .import ent_track, ent_sector, ent_type, ent_seclo, ent_sechi
        .import ent_index, ent_ptr, sanitise
        .import valid_data, read_at, vtoc_bit, memcpy256, memcmp256
        .import slot_where, walk, wipe_seen, load_vtoc
        .import cat_first, cat_open, cat_step, del_fault
        .import wlk_t, wlk_s, wlk_nt, wlk_ns, wlk_j, wlk_expect, wlk_collect
        .import aud_t, aud_s, aud_off
        .import vtoc, catalog_before, verify, cat_buf

        .segment "BSS"
del_index:      .res 1
_del_index      = del_index

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
del_name:       .res NAME_STRIDE    ; the panel's name, then where it was read
del_cat_t:      .res 1
del_cat_s:      .res 1
del_cat_off:    .res 1
del_volume:     .res 1
pan_track:      .res 1          ; the panel's idea of the entry: the disk
pan_sector:     .res 1          ; is held to it, name alone is not an
pan_type:       .res 1          ; identity (contiguous, same order as
pan_seclo:      .res 1          ; del_track..del_sechi)
pan_sechi:      .res 1
pan_cat_track   = del_name + ENT_CAT_TRACK
pan_slot        = del_name + ENT_CAT_SLOT

ts_list         = cat_buf           ; free_chain only: nothing walks by then

.ifdef SIM65
        .segment "CODE"
.else
        .segment "LOWCODE"
.endif

; ---------------------------------------------------------------------
; memcpy256, memcmp256, read_at, vtoc_bit and walk come from copy.s: the
; DEL_ and COPY_ codes for OK, READ and INVALID are the same numbers.

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
        jsr     meta_gate
        bne     @out
        jsr     snapshot_panel
        lda     pan_type
        and     #$80
        beq     @unlocked
        lda     #DEL_LOCKED
        rts
@unlocked:
        jsr     find_and_walk
        bne     @out
        jsr     audit_others
        bne     @out
        lda     #1
        sta     del_ready
        lda     #DEL_OK
@out:
        rts

; find_and_walk -- hold the disk to the panel's idea of the file, then
; claim every sector it owns: allocated, on a data track, owned once
find_and_walk:
        jsr     find_entry
        bne     @out
        lda     del_type
        and     #$80
        beq     @walkit
        lda     #DEL_LOCKED
        rts
@walkit:
        jsr     wipe_seen
        lda     #0
        sta     wlk_collect
        lda     del_track
        sta     wlk_t
        lda     del_sector
        sta     wlk_s
        lda     del_seclo
        sta     wlk_expect
        lda     del_sechi
        sta     wlk_expect+1
        jmp     walk
@out:
        rts

; audit_others -- every other live entry's chain, claimed on top of the
; file's own sectors. A sector two entries share, a chain that does not
; add up, or one that cannot be read refuses the delete: freeing a
; cross-linked sector would let the next copy overwrite the other file.
; Costs one read per T/S list on the disk, before the first write.
audit_others:
        jsr     cat_first
        bne     @out
@entry:
        jsr     our_slot
        bcs     @next
        ldx     aud_off
        lda     cat_buf,x
        beq     @next           ; never used
        cmp     #$FF
        beq     @next           ; deleted: its sectors are free
        sta     wlk_t
        lda     cat_buf+1,x
        sta     wlk_s
        lda     cat_buf+33,x
        sta     wlk_expect
        lda     cat_buf+34,x
        sta     wlk_expect+1
        jsr     walk            ; reads into buffer; cat_buf is kept
        bne     @out
@next:
        jsr     cat_step
        bcc     @entry
        beq     @out            ; the end of the chain, A = 0
        jsr     cat_open
        beq     @entry
@out:
        rts

; find_entry -- read the VTOC and the catalog sector the panel took the
; entry from, and hold the disk to the panel: the slot must still carry
; the T/S pointer, type, sector count and (sanitised) name it showed, or
; the disk is not the one the user was looking at (DEL_CHANGED). A name
; alone is not an identity: the panel shows unprintable characters as
; '?', and a sibling disk can reuse a name. Locked files are allowed: lock
; and rename need the slot. The T/S chain is not followed.
;
; Only a slot on track 17 is written. catalog() follows a chain onto any
; track, but a write there could land on a sector a file uses, and a
; slot read elsewhere must never be taken for the track-17 one.
find_entry:
        jsr     load_vtoc
        jne     @out
        lda     vtoc+6
        sta     del_volume
        lda     pan_cat_track
        cmp     #CATALOG_TRACK
        bne     @invalid
        sta     del_cat_t
        ldx     pan_slot
        jsr     slot_where
        bcc     @invalid
        sta     del_cat_off
        stx     del_cat_s
        lda     del_cat_t
        jsr     read_at
        bne     @out
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
; Locked files are refused. A live collision is refused. A name the slot
; already holds, byte for byte, is REN_SAME and writes nothing; the
; panel's sanitised text is not that name, so a FLASH or control name
; can still be normalised by typing what the panel shows.
; ---------------------------------------------------------------------
rename_prepare:
_rename_prepare:
        lda     #0
        sta     ren_ready
        jsr     meta_gate
        bne     @out
        jsr     snapshot_panel
        jsr     find_entry
        bne     @out
        lda     del_type
        and     #$80
        bne     @locked
        SETPTR  ptr, catalog_before
        SETPTR  ptr2, cat_buf
        jsr     memcpy256
        lda     del_cat_off
        sta     aud_off
        jsr     name_ren
        bcs     @same
        jsr     ren_collision
        bne     @out            ; REN_EXISTS, INVALID or READ
        lda     #1
        sta     ren_ready
        lda     #DEL_OK
@out:
        rts
@same:
        lda     #REN_SAME
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
        bne     @out            ; REN_EXISTS, INVALID or READ
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
        lda     del_index
        jsr     ent_index
        jsr     ent_ptr
        ldy     #0
@n:
        lda     (ptr),y         ; the name, then where it was read
        sta     del_name,y
        iny
        cpy     #NAME_STRIDE
        bcc     @n
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

; ren_collision -- A = 0 when ren_name is free, REN_EXISTS when it is
; already a live file that is not the slot being renamed, DEL_INVALID
; for a malformed or looping chain, DEL_READ when a catalog sector could
; not be read. Destroys buffer and cat_buf; catalog_before still holds
; our sector.
ren_collision:
        jsr     cat_first
        bne     @out
@entry:
        jsr     our_slot
        bcs     @next
        ldx     aud_off
        lda     cat_buf,x
        beq     @next
        cmp     #$FF
        beq     @next
        jsr     name_ren
        bcs     @yes
@next:
        jsr     cat_step
        bcc     @entry
        beq     @out            ; the end of the chain, A = 0
        jsr     cat_open
        beq     @entry
@out:
        rts
@yes:
        lda     #REN_EXISTS
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

; name_ren -- carry set when the entry at aud_off in cat_buf holds
; ren_name exactly, high bits included
name_ren:
        ldx     aud_off
        inx
        inx
        inx
        ldy     #0
@char:
        lda     cat_buf,x
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
