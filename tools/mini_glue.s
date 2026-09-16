; mini_glue.s -- test-only glue: the real 6502 modules, a simulated RWTS.
;
; The production build reaches the disk through rwts.s and DOS. Under
; sim65 there is no DOS, and two 140 KB images cannot live in a 64 KB
; address space, so read_sector and write_sector become calls into the
; harness, which asks the host process for each sector. The code under
; test is untouched: catalog.s and copy.s are the very sources the Apple
; II build assembles.
;
; Must not be named after the C file beside it: cc65 writes its own
; intermediate assembly as <name>.s and would overwrite this.

        .export read_sector, write_sector, read_into, write_into
        .export rwts_format, rwts_error, scratch
        .export _mini_catalog, _mini_preview
        .export _mini_prepare, _mini_execute, _mini_cancel
        .export _mini_load, _mini_create_prepare, _mini_create_execute
        .export _mini_delete_prepare, _mini_delete_execute
        .export _mini_measure_text
        .export _mini_lock_prepare, _mini_lock_execute
        .export _mini_rename_prepare, _mini_rename_execute
        .export _mini_copy_side, _mini_format, _mini_patch_type, _mini_patch_name

        .import _sim_read, _sim_write, _sim_format, _sim_rwts_error
        .import buffer, rwts_buf
        .import format_disk, patch_type, patch_name
        .import copy_side, side_from, side_to
        .import catalog, preview, load_file, measure_text
        .import copy_prepare, copy_execute, copy_cancel
        .import create_prepare, create_execute
        .import delete_prepare, delete_execute
        .import lock_prepare, lock_execute, rename_prepare, rename_execute
        .export copy_progress

rwts_error      = _sim_rwts_error

; Eight real kilobytes for the working area. On the Apple II+ this is
; hi-res page one at $2000; here that address is inside the harness, so
; the test owns the memory instead. The copy engine only ever addresses
; it through this symbol.
        .segment "BSS"
scratch:
        .res    $2000

        .segment "CODE"

; read_sector / write_sector move buffer, read_into / write_into the
; page rwts_buf points at, as in rwts.s.
read_sector:
        jsr     with_buffer
read_into:
        jmp     _sim_read

write_sector:
        jsr     with_buffer
write_into:
        jmp     _sim_write

with_buffer:
        lda     #<buffer
        sta     rwts_buf
        lda     #>buffer
        sta     rwts_buf+1
        rts

rwts_format:
        jmp     _sim_format

; The Apple II build draws the footer bar. The harness has no screen.
copy_progress:
        rts

; cc65 returns an unsigned char in A, which is what these already do.
_mini_catalog:
        jmp     catalog

_mini_preview:
        jmp     preview

_mini_prepare:
        jmp     copy_prepare

_mini_execute:
        jmp     copy_execute

_mini_cancel:
        jmp     copy_cancel

_mini_load:
        jmp     load_file

_mini_create_prepare:
        jmp     create_prepare

_mini_create_execute:
        jmp     create_execute

_mini_delete_prepare:
        jmp     delete_prepare

_mini_delete_execute:
        jmp     delete_execute

_mini_measure_text:             ; carry out as A: 1 when the text fills the area
        jsr     measure_text
        lda     #0
        rol     a
        rts

_mini_lock_prepare:
        jmp     lock_prepare

_mini_lock_execute:
        jmp     lock_execute

_mini_rename_prepare:
        jmp     rename_prepare

_mini_rename_execute:
        jmp     rename_execute

_mini_copy_side:
        ldx     side_from
        ldy     side_to
        jmp     copy_side

_mini_format:
        jmp     format_disk

_mini_patch_type:
        jmp     patch_type

_mini_patch_name:
        jmp     patch_name
