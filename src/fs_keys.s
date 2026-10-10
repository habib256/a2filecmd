; Read-only panel commands. DOS viewers write MAIN screen/overlay memory
; only; write, execute and editor commands stay blocked for ALL foreign FS.
; No disk or AUX accesses here. Panel ABI: 98 bytes, fs at 94.
        .export _fs_key
        .import _active, _panels, _overlay_run, _message, _msg_roimg
        .import pushax
.export _identify_viewer
.import _input, _note
        .segment "CODE"
_fs_key:
        ldx _active
        beq :+
        ldx #98
:       ldy _panels+94,x
        beq pass
        cmp #'-'                ; Return | $20 also equals '-': keep paging
        beq pass
        ora #$20                ; zero stays outside both lists
        cpy #2                  ; FS_DOS33
        bne rejected

        ldx #3
scan:   cmp readers,x
        beq view
        dex
        bpl scan
rejected:
        jmp guard
pass:   lda #0
        tax
        rts
view:   and #$DF
        cmp #'I'
        bne :+
        lda #13                 ; DOS automatic request, distinct from ProDOS I
:
        jsr _identify_viewer
handled:lda #1
        ldx #0
        rts
_identify_viewer:
        pha
        pha                     ; preserve the key across a missing IDENT
        ldx #0
        stx _input
        stx _note
        cmp #'H'
        beq direct
        cmp #'T'
        beq direct
        lda #<ident
        ldx #>ident
        bne dispatch
direct: lda #<dosview
        ldx #>dosview
dispatch:
        jsr pushax
        pla
        jsr _overlay_run
        pla
        ldx _input
        bne resolved
        ldx _note                ; a failed identification must not be retried
        bne done
        cmp #'H'
        beq done
        cmp #'T'
        beq done
        pha
        cmp #13
        beq legacy_dos
        lda #<oldopen
        ldx #>oldopen
        bne legacy
legacy_dos:
        lda #<dosview
        ldx #>dosview
legacy: jsr pushax
        pla
        jsr _overlay_run        ; incomplete installation without IDENT stages
resolved:
        lda _input
        beq done
        lda #<_input
        ldx #>_input
        jsr pushax
        lda #13                 ; automatic reader, DOSVIEW must skip its menu
        jmp _overlay_run
done:   rts
ident:  .asciiz "IDENT"
oldopen:.asciiz "OPEN"
        .segment "LC"
guard:  ldx #11
block:  cmp blocked,x
        beq refuse
        dex
        bpl block
        jmp pass
refuse: lda #<_msg_roimg
        ldx #>_msg_roimg
        jsr _message
        jmp handled
readers:.byte "thi", $2D         ; Return | $20
dosview:.asciiz "DOSVIEW"
blocked:.byte "rkaldxewthim"
