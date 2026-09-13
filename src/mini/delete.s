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
        .export del_index, del_fault
        .export _delete_prepare, _delete_execute, _delete_cancel
        .export _del_index, _del_fault

        .import read_sector, write_sector, rwts_error
        .import buffer, drive, track, sector, count, sector_seen
        .import ent_track, ent_sector, ent_type, ent_seclo, ent_sechi
        .import ent_index, ent_ptr
        .import seen_bit, bit_masks, valid_cs
        .import vtoc, catalog_before, verify, cat_buf

        .segment "BSS"
del_index:      .res 1
del_fault:      .res 1
_del_index      = del_index
_del_fault      = del_fault

del_ready:      .res 1
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

ts_list         = cat_buf

wlk_t:          .res 1
wlk_s:          .res 1
wlk_nt:         .res 1
wlk_ns:         .res 1
wlk_ended:      .res 1
wlk_j:          .res 1
wlk_total:      .res 2
wlk_expect:     .res 2
aud_t:          .res 1
aud_s:          .res 1
aud_nt:         .res 1
aud_ns:         .res 1
aud_i:          .res 1
aud_off:        .res 1
aud_found:      .res 1

.ifdef SIM65
        .segment "CODE"
.else
        .segment "LOWCODE"
.endif

; ---------------------------------------------------------------------
memcpy256:
        ldy     #0
@loop:
        lda     (ptr),y
        sta     (ptr2),y
        iny
        bne     @loop
        rts

memcmp256:
        ldy     #0
@loop:
        lda     (ptr),y
        cmp     (ptr2),y
        bne     @diff
        iny
        bne     @loop
        lda     #0
        rts
@diff:
        lda     #1
        rts

read_at:
        sta     track
        stx     sector
        jsr     read_sector
        beq     @ok
        lda     #DEL_READ
        rts
@ok:
        lda     #DEL_OK
        rts

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
        lda     #DEL_UNCERTAIN  ; protection mid-delete is still uncertain
        rts                     ; the catalog may already have been marked
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
        lda     del_index
        jsr     ent_index
        tay
        lda     ent_type,y
        sta     del_type
        and     #$80
        beq     @unlocked
        lda     #DEL_LOCKED
        rts
@unlocked:
        lda     ent_track,y
        sta     del_track
        lda     ent_sector,y
        sta     del_sector
        lda     ent_seclo,y
        sta     del_seclo
        lda     ent_sechi,y
        sta     del_sechi
        lda     del_index
        jsr     ent_index
        jsr     ent_ptr
        ldy     #0
@name:
        lda     (ptr),y
        sta     del_name,y
        iny
        cpy     #NAME_LEN
        bcc     @name
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
        lda     #0
        sta     aud_found
        ldx     #69
        lda     #0
@wipe:
        sta     sector_seen,x
        dex
        bpl     @wipe
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
        lda     vtoc+1
        sta     aud_t
        lda     vtoc+2
        sta     aud_s
@chain:
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
        lda     buffer+1
        sta     aud_nt
        lda     buffer+2
        sta     aud_ns
        lda     #CAT_FIRST
        sta     aud_off
        lda     #CAT_ENTRIES
        sta     aud_i
@entry:
        ldx     aud_off
        lda     buffer,x
        beq     @next
        cmp     #$FF
        beq     @next
        jsr     name_here
        bcc     @next
        lda     aud_found
        jne     @invalid        ; the same name twice
        inc     aud_found
        lda     aud_t
        sta     del_cat_t
        lda     aud_s
        sta     del_cat_s
        lda     aud_off
        sta     del_cat_off
        SETPTR  ptr, buffer
        SETPTR  ptr2, catalog_before
        jsr     memcpy256
        ldx     aud_off
        lda     buffer,x
        sta     del_track
        lda     buffer+1,x
        sta     del_sector
        lda     buffer+2,x
        sta     del_type
        lda     buffer+33,x
        sta     del_seclo
        lda     buffer+34,x
        sta     del_sechi
        lda     del_type
        and     #$80
        beq     @walkit
        lda     #DEL_LOCKED
        rts
@walkit:
        jsr     walk_file
        bne     @out
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
        jne     @chain
        lda     aud_found
        beq     @invalid
        lda     #DEL_OK
@out:
        rts
@invalid:
        lda     #DEL_INVALID
        rts

name_here:
        ldx     aud_off
        inx
        inx
        inx                     ; first name byte
        ldy     #0
@char:
        lda     buffer,x
        sta     s0
        lda     del_name,y
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
        lda     del_seclo
        sta     wlk_expect
        lda     del_sechi
        sta     wlk_expect+1
@list:
        lda     wlk_t
        ldx     wlk_s
        jsr     valid_cs
        jcc     @invalid
        jsr     claim_used
        jne     @out
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
        jsr     valid_cs
        bcc     @invalid
        jsr     claim_used
        bne     @out
        inc     wlk_total
        bne     @nextpair
        inc     wlk_total+1
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
        clc
        adc     #1              ; plus the first T/S list, at least
        ; The catalog count includes T/S lists. We counted data sectors
        ; in wlk_total and lists as we followed them. Comparing strictly
        ; is what keeps us from freeing a neighbour's sector.
        ; Accept the catalog's own count if the chain was well formed.
        lda     wlk_expect
        ora     wlk_expect+1
        beq     @invalid
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
        lda     buffer,x        ; DOS UNDELETE: original track into the name
        sta     buffer+3,x
        lda     #$FF
        sta     buffer,x
        lda     del_cat_t
        ldx     del_cat_s
        jsr     put_verified
        bne     @aftercat
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
        jsr     valid_cs
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
        jsr     valid_cs
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
