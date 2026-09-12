; Bounded second-chance replacement. Instrument reads mark bit 6;
; streaming pattern reads preserve it but do not promote cold pages.
; all native cache/header pages are below $4000, so this is not an address bit.
; Only a mapping still owned by this slot may be cleared or invalidated.
; Unused slots can contain stale tags: never clear another slot or a header.
.export _pt_victim, _pt_slots, _pt_next
.segment "BSS"
_pt_slots: .res 8
_pt_next: .res 1
.segment "CODE"
_pt_victim:
 ldx _pt_next
@scan:
 ldy _pt_slots,x
 lda _pt_pages,y
 and #$BF
 cmp _pt_cache_pages,x
 bne @found
 lda _pt_pages,y
 and #$40
 beq @evict
 lda _pt_cache_pages,x
 sta _pt_pages,y
 jsr cache_advance
 jmp @scan
@evict:
 lda #0
 sta _pt_pages,y
@found:
 txa
 pha
 jsr cache_advance
 stx _pt_next
 pla
 ldx #0
 rts
cache_advance:
 inx
 cpx _pt_running
 bcc :+
 ldx #0
: rts
