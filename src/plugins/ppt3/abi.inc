; abi.inc -- the contract between the GROUiK engine image (AUX, engine.s)
; and its main-memory half (hook.s, driver.s): both include this file.
;
; Why $2000: AUX $0800-$1FFF is where ProDOS's /RAM keeps its volume
; bitmap ($0C00) and directory ($0E00); with the engine there, rebuilding
; /RAM afterwards (api->ram_format) sent POM2's enhanced IIe into the
; monitor (2026-10-03). $2000-$BFFF is what DHGR pictures and UNSHRINK
; already borrow before the same rebuild. $0800-$1FFF is never written.
PPT3_ABI     = 1
PPT3_BASE    = $2000            ; AUX: the engine image (code + tables)
PPT3_ENTRY   = PPT3_BASE+5      ; JMP: A = 0 INIT, 1 PLAY; returns A = 0/1/2
PPT3_OUT     = PPT3_BASE+8      ; 14 AY registers, after the original ROUT conversion
PPT3_MODHI   = PPT3_BASE+22     ; word: first address past the module (host writes it)
PPT3_LEN     = PPT3_BASE+24     ; word: size of the image file part, header included
PPT3_LIMIT   = $3B00            ; image, variables and tables end below this
PPT3_MODULE  = $4000            ; AUX: the module, whole
PPT3_MODMAX  = $8000            ; ... up to $BFFF
PPT3_EMPTY   = 6                ; readable bytes of the built-in empty sample/ornament
PPT3_PUSHMAX = 4                ; deferred special commands per channel and row
