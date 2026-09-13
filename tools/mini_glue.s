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

        .export read_sector, write_sector, rwts_error
        .export _mini_catalog, _mini_preview
        .export _mini_prepare, _mini_execute, _mini_cancel

        .import _sim_read, _sim_write, _sim_rwts_error
        .import catalog, preview, copy_prepare, copy_execute, copy_cancel

rwts_error      = _sim_rwts_error

        .segment "CODE"

read_sector:
        jmp     _sim_read

write_sector:
        jmp     _sim_write

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
