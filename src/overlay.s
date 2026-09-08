; overlay.s -- l'en-tete de chaque surcouche (a2fc_plugin.h, struct Overlay).
;
; Une surcouche est liee avec le programme : elle appelle ses fonctions a
; leurs adresses de ce lien-la, et une surcouche d'une autre construction
; partirait dans le decor. Ses deux premiers octets sont donc l'adresse de
; main dans le programme qui l'a liee, et le noyau la compare a la sienne
; avant d'y entrer (load_overlay, dans a2fc.c). Suivent un octet de drapeaux
; (bit 0 : grande surcouche, qui prend aussi la page graphique $2000-$3FFF),
; l'adresse du point d'entree que le menu des surcouches (!) appelle sur la
; selection, trois octets de reserve, et la description d'une ligne que ce
; menu affiche. Ce fichier est le premier objet du lien apres crt0 pour que
; l'en-tete soit bien en tete de chaque segment.

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

.macro  header  flags, entry, desc
        .word   _main
        .byte   flags
        .word   entry
        .res    3
        .asciiz desc
.endmacro

        .segment "IMAGE"
        header  0, _image_entry, "View the selection as an HGR or DHGR picture"
        .segment "HELP"
        header  0, _help_entry, "The help page: every key on one screen"
        .segment "TEXT"
        header  0, _text_entry, "Read the selection as text, page by page"
        .segment "BASLIST"
        header  0, _baslist_entry, "List an Applesoft BAS program (T on a BAS)"
        .segment "COMPARE"
        header  0, _compare_entry, "Compare the selection with the other panel, byte by byte"
        .segment "SEARCH"
        header  0, _search_entry, "Search the panel files for text, tag those that match"
        .segment "BINARY2"
        header  0, _binary2_entry, "Extract a Binary II (.BNY) archive to the other panel"

        .segment "AWP"
        header  0, _awp_entry, "Read an AppleWorks word-processor document"
        .segment "HEX"
        header  0, _hex_entry, "Show the selection in hexadecimal"
        .segment "DELETE"
        header  0, _delete_entry, "Delete the tagged files, or the selection"
        .segment "EDIT"
        header  BIG, _edit_entry, "Edit the selection as text (6 KB), or a new file"
        .segment "MUSIC"
        header  0, _music_entry, "Play the selected .MB tune on a Mockingboard"
        .segment "RUN"
        header  0, _run_entry, "Run the selected SYS, BIN or BAS program"
        .segment "ATTR"
        header  0, _attr_entry, "Change the type and auxtype of the selection"
        .segment "DISKIMG"
        header  BIG, _diskimg_entry, "Disk images: write to a disk, read a disk, copy disks"
        .segment "IMGFS"
        header  0, _imgfs_entry, "Extract the tagged files from an image (C)"
        .segment "DOS33"
        header  0, _dos33_entry, "DOS 3.3 catalog: extract files, mark differences"
        .segment "UNSHRINK"
        header  BIG, _unshrink_entry, "Extract a ShrinkIt .SHK archive to the other panel"
        .segment "MENU"
        header  BIG, _menu_entry, "This menu"
