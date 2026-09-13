; data.s -- every byte of state A2FC Mini keeps, in one place.
;
; The C edition stored catalog entries as an array of 36-byte structs, so
; every access cost a multiply. Here the fields are parallel arrays and
; names use a 32-byte stride, so an index becomes a shift.
;
; Nothing here is initialised: start.s clears the whole BSS before use,
; exactly as the C runtime did, so an uninitialised byte reads as zero.

        .include "mini.inc"

; Names with a leading underscore are the same addresses seen from the C
; test harnesses; the assembler modules use the bare names.

        .export active, count, volume, drive, slot, track, sector
        .export selected, error, buffer, sector_seen
        .export _active, _count, _volume, _drive, _slot, _track, _sector
        .export _selected, _error, _buffer, _sector_seen
        .export ent_track, ent_sector, ent_type, ent_seclo, ent_sechi, ent_name
        .export _ent_track, _ent_sector, _ent_type, _ent_seclo, _ent_sechi
        .export _ent_name
        .export pan_drive, pan_volume, pan_count, pan_selected, pan_error
        .export pan_top
        .export _pan_drive, _pan_volume, _pan_count, _pan_selected
        .export _pan_error, _pan_top
        .export screen_image, _screen_image
        .export prv_index, _prv_index

        .segment "BSS"

; ---- panel-independent globals -------------------------------------
active:         .res 1          ; 0 or 1: which panel the keys act on
count:          .res 1          ; entries in the active panel
volume:         .res 1          ; DOS volume number last read
drive:          .res 1          ; 1 or 2, the drive RWTS will use
slot:           .res 1          ; slot A2FC was run from
track:          .res 1          ; RWTS target
sector:         .res 1
selected:       .res 1          ; cursor in the active panel
error:          .res 1          ; 0 none, 1 read error, 2 invalid catalog
_active         = active
_count          = count
_volume         = volume
_drive          = drive
_slot           = slot
_track          = track
_sector         = sector
_selected       = selected
_error          = error

prv_index:      .res 1          ; preview() argument
_prv_index      = prv_index

; ---- the one sector buffer RWTS fills ------------------------------
buffer:         .res 256
_buffer         = buffer

; ---- 560 allocation bits, reused by the catalog scan and the audit --
; Never both at once: the catalog scan finishes before a copy starts.
sector_seen:    .res 70
_sector_seen    = sector_seen

; ---- catalog entries, two panels of MINI_MAX -----------------------
ent_track:      .res 2*SIDE_STRIDE
ent_sector:     .res 2*SIDE_STRIDE
ent_type:       .res 2*SIDE_STRIDE
ent_seclo:      .res 2*SIDE_STRIDE
ent_sechi:      .res 2*SIDE_STRIDE
ent_name:       .res 2*SIDE_STRIDE*NAME_STRIDE
_ent_track      = ent_track
_ent_sector     = ent_sector
_ent_type       = ent_type
_ent_seclo      = ent_seclo
_ent_sechi      = ent_sechi
_ent_name       = ent_name

; ---- per-panel metadata --------------------------------------------
pan_drive:      .res 2
pan_volume:     .res 2
pan_count:      .res 2
pan_selected:   .res 2
pan_error:      .res 2
pan_top:        .res 2
_pan_drive      = pan_drive
_pan_volume     = pan_volume
_pan_count      = pan_count
_pan_selected   = pan_selected
_pan_error      = pan_error
_pan_top        = pan_top

; ---- the composed screen, written to $400 one changed cell at a time
screen_image:   .res SCREEN_CELLS
_screen_image   = screen_image
