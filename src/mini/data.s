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
        .export boot_drive, _boot_drive
        .export selected, error, buffer, sector_seen, rwts_buf
        .export _active, _count, _volume, _drive, _slot, _track, _sector
        .export _selected, _error, _buffer, _sector_seen, _rwts_buf
        .export ent_track, ent_sector, ent_type, ent_seclo, ent_sechi, ent_name
        .export _ent_track, _ent_sector, _ent_type, _ent_seclo, _ent_sechi
        .export _ent_name
        .export pan_drive, pan_volume, pan_count, pan_selected, pan_error
        .export pan_top
        .export _pan_drive, _pan_volume, _pan_count, _pan_selected
        .export _pan_error, _pan_top
        .export screen_image, _screen_image
        .export prv_index, _prv_index
        .export tags, _tags
        .export edit_len, _edit_len
        .export name_buf, _name_buf

        .segment "BSS"

; ---- panel-independent globals -------------------------------------
active:         .res 1          ; 0 or 1: which panel the keys act on
slot:           .res 1          ; slot A2FC was run from
boot_drive:     .res 1          ; drive A2FC was run from: format's DOS source
_boot_drive     = boot_drive
track:          .res 1          ; RWTS target
sector:         .res 1

; The five values a panel owns, in the order of the pan_* block below
; and nowhere else: remember and activate walk the two blocks side by
; side, one index each, instead of naming ten addresses twice. The
; asserts keep that promise even if someone inserts a byte here.
live_panel:
drive:          .res 1          ; 1 or 2, the drive RWTS will use
volume:         .res 1          ; DOS volume number last read
count:          .res 1          ; entries in the active panel
selected:       .res 1          ; cursor in the active panel
error:          .res 1          ; 0 none, 1 read error, 2 invalid catalog
        .export live_panel
        .assert * - live_panel = PANEL_FIELDS, error, "live block and PANEL_FIELDS disagree"
        .assert volume = drive + 1, error, "remember/activate walk drive..error"
        .assert count = drive + 2, error, "remember/activate walk drive..error"
        .assert selected = drive + 3, error, "remember/activate walk drive..error"
        .assert error = drive + 4, error, "remember/activate walk drive..error"
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

; One past the last non-zero text byte; never $2000, or poke_nul
; would write the first byte of the resident program.
edit_len:       .res 2
_edit_len       = edit_len

; ---- the name ask_name collects: N's new file, R's new name (ren_name)
name_buf:       .res NAME_LEN
_name_buf       = name_buf

; ---- the one sector buffer RWTS fills ------------------------------
buffer:         .res 256
_buffer         = buffer
; where read_into / write_into move a sector: a page of the working
; area, so a batch is not copied sector by sector between two RWTS
; calls. read_sector / write_sector point it at buffer themselves.
rwts_buf:       .res 2
_rwts_buf       = rwts_buf

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
; Each name stride is 30 characters, then where the entry was read:
; ENT_CAT_TRACK, the catalog track, and ENT_CAT_SLOT, catalog sector << 3
; | slot 0-6. A write finds that very slot again, not a same name. Both
; are zero for an entry no catalog filled, which no write accepts.
ent_name:       .res 2*SIDE_STRIDE*NAME_STRIDE
_ent_track      = ent_track
_ent_sector     = ent_sector
_ent_type       = ent_type
_ent_seclo      = ent_seclo
_ent_sechi      = ent_sechi
_ent_name       = ent_name

; ---- per-panel metadata --------------------------------------------
; One block of six two-byte fields, left side first. The order of the
; first five matches the live globals above, and pan_top follows them,
; so remember, activate and mirror_panel index the block instead of
; naming every field twice. The asserts hold the layout in place.
pan_drive:      .res 2
pan_volume:     .res 2
pan_count:      .res 2
pan_selected:   .res 2
pan_error:      .res 2
pan_top:        .res 2
        .assert * - pan_drive = PAN_BYTES, error, "pan_* block and PAN_BYTES disagree"
        .assert pan_volume = pan_drive + 2, error, "pan_* must stay one block"
        .assert pan_count = pan_drive + 4, error, "pan_* must stay one block"
        .assert pan_selected = pan_drive + 6, error, "pan_* must stay one block"
        .assert pan_error = pan_drive + 8, error, "pan_* must stay one block"
        .assert pan_top = pan_drive + 10, error, "pan_* must stay one block"
_pan_drive      = pan_drive
_pan_volume     = pan_volume
_pan_count      = pan_count
_pan_selected   = pan_selected
_pan_error      = pan_error
_pan_top        = pan_top

; ---- marks, one bit per entry, per panel.
;
; A mark belongs to the catalog snapshot it was made on, so every reread
; clears them. Keeping them across a reread would mean a mark could end
; up on a different file than the one the user pointed at, and marks
; decide what DELETE and COPY act on.
tags:           .res 2*TAG_BYTES
_tags           = tags

; ---- the composed screen, written to $400 one changed cell at a time
screen_image:   .res SCREEN_CELLS
_screen_image   = screen_image
