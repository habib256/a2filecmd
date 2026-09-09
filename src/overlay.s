; overlay.s -- the header of each overlay (a2fc_plugin.h, struct Overlay).
;
; An overlay is linked with the program: it calls its functions at their
; addresses from that particular link, and an overlay from another build
; would go off the rails. So its first two bytes are the address of main
; in the program that linked it, and the core compares it with its own
; before entering it (load_overlay, in a2fc.c). Then come a flags byte
; (bit 0: big overlay, which also takes the graphics page $2000-$3FFF),
; the address of the entry point that the overlay menu (!) calls on
; selection, three reserved bytes, and the one-line description that this
; menu displays. This file is the first object of the link after crt0 so
; that the header sits right at the head of each segment.

        .import _main
        .import _image_entry, _help_entry, _text_entry, _hex_entry, _delete_entry
        .import _edit_entry, _music_entry, _run_entry, _attr_entry, _menu_entry
        .import _diskimg_entry
        .import _imgfs_entry
        .import _dos33_entry
        .import _unshrink_entry
        .import _baslist_entry
        .import _compare_entry, _search_entry
        .import _binary2_entry
        .import _awp_entry

BIG = 1

; The link's identity, readable from C: the address of main, which cc65
; master no longer lets us take in C (&main) but which the assembler gives.
        .export _a2fc_link_id
        .segment "RODATA"
_a2fc_link_id:
        .word   _main

.macro  header  flags, entry, desc
        .word   _main
        .byte   flags
        .word   entry
        .res    3
        .asciiz desc
.endmacro

        .segment "IMAGE"
        header  0, _image_entry, "View the selection full screen as an HGR or DHGR picture (I)"
        .segment "HELP"
        header  0, _help_entry, "The help page: every key of A2 File Cmd on one screen (?)"
        .segment "TEXT"
        header  0, _text_entry, "Read the selection as text, page by page (T)"
        .segment "BASLIST"
        header  1, _baslist_entry, "List an Applesoft program, readably, page by page (T on a BAS)"
        .segment "COMPARE"
        header  0, _compare_entry, "Compare the selection with the other panel, byte by byte"
        .segment "SEARCH"
        header  0, _search_entry, "Search every file of the panel for a text, and tag those found"
        .segment "BINARY2"
.ifdef A2_6502
        header  1, _binary2_entry, "Extract a Binary II (.BNY) archive into the other panel"
.else
        header  0, _binary2_entry, "Extract a Binary II (.BNY) archive into the other panel"
.endif

        .segment "AWP"
        header  0, _awp_entry, "Read an AppleWorks word-processor document, page by page"
        .segment "HEX"
        header  0, _hex_entry, "Show the selection in hexadecimal, side by side with its text (H)"
        .segment "DELETE"
        header  0, _delete_entry, "Delete the tagged files, or the selection, after confirmation (D)"
        .segment "EDIT"
        header  BIG, _edit_entry, "Edit the selection as text, up to 6 KB, or write a new file (E)"
        .segment "MUSIC"
        header  0, _music_entry, "Play the selected .MB tune on a Mockingboard, P pauses it"
        .segment "RUN"
        header  0, _run_entry, "Run the selected SYS, BIN or Applesoft program, and leave A2FC"
        .segment "ATTR"
        header  0, _attr_entry, "Change the ProDOS type and auxtype of the selection (A)"
        .segment "DISKIMG"
        header  BIG, _diskimg_entry, "Disk images: write one to a floppy, read a floppy, copy a floppy"
        .segment "IMGFS"
        header  0, _imgfs_entry, "Extract the tagged files of a disk image into the other panel (C)"
        .segment "DOS33"
        header  0, _dos33_entry, "A DOS 3.3 disk or image: extract its tagged files (C)"
        .segment "UNSHRINK"
        header  BIG, _unshrink_entry, "Extract a ShrinkIt (.SHK) archive into the other panel"
        .segment "MENU"
        header  BIG, _menu_entry, "This menu"
