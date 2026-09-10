# Changelog

Changes in upcoming and published releases. See the [README](README.md) for features,
downloads and installation.

## Unreleased

- FIND adds optional ProDOS type and inclusive modification-date filters (TAB, then T/D; A clears). Filters combine with name/content searches and persist across result pages; invalid dates are rejected and cancelling an edit preserves the previous range.
- FIND continues with N beyond the first 20 matches, preserving traversal state and showing cumulative result ranges. A lookahead avoids empty pages at exact multiples of 20. Fixed skipped late subdirectories and the 8-bit directory-position limit in content search; unreachable/overlong paths and queue limits are reported.

- DISASM can export a text listing from the current offset to EOF, with the chosen CPU/load address, source path, offsets and raw bytes. New files are created exclusively in the other panel; errors/cancellation retain partial output and returning to the viewer preserves its position.

- Added DISASM on EXTRA and XL for both CPUs: read-only BIN/SYS disassembly, selectable 6502 or 65C02 (including Rockwell/WDC extensions), instruction-aligned pages, file-offset jumps and load-address override. Unknown or truncated instructions remain visible as data bytes; short reads are reported. Opcode tables adapted from cc65 da65 (notice retained in source).

- Extended BLKVIEW with four-byte hexadecimal search, overlapping/cross-block matches, find-next and bounded block extraction to a new binary file in the other panel. Extraction normalizes PO/DSK/2MG order, refuses existing names and writes device copies to another volume; cancellation/read/write errors retain partial output.

- Fixed TREE falsely reporting an incomplete XL root scan despite correct totals: ProDOS GET_FILE_INFO returns volume allocation for a root directory. TREE and SYNC now count its linked directory blocks, with bounded reads and error/cancellation handling.

- DISKIMG automatically reads back every block written to a device, stops at the first mismatch/read error and reports its block number. Single-drive copy prompts name the source volume and slot/drive; readback needs no additional swaps.
- VERIFY reads tagged files, skips tagged directories and reports processed files and read errors. Escape interrupts files as well as volumes, preserving the tags. Single-file results now use the same compact summary as batches.
- VOLINFO lists selected-file data/index/master/extended blocks, and exports its scan and file block list as a new text report in the other panel. Existing names are never overwritten; interrupted/error reports remain visibly partial. Lost-block counts are explicitly unconfirmed after incomplete scans.
- Added read-only BLKVIEW on EXTRA and XL: device and PO/DSK/DO/2MG/HDV image blocks, hex/ASCII, explicit directory/index interpretations, paging and four-digit hexadecimal block selection.
- The 0.7.6 source builds keep separate CPU families: 43 overlays on XL, a 42-command shared catalog, DSK floppies and versioned filenames. Updated the eight-page English manual with the current two-panel screenshot.

## [0.7.5] - 2026-09-09

- Added six service overlays on EXTRA and XL for both CPUs: UNDELETE recovers deleted ProDOS file candidates to another volume; DISKCMP compares volumes and PO/DSK/2MG images; MKIMAGE creates formatted data images; RESCUE extracts readable data with retries and a missing-block log; SYNC copies missing/newer files recursively; TREE shows cumulative directory sizes.
- Recovery leaves source volumes unchanged. UNDELETE recognizes index halves swapped by ProDOS DESTROY and refuses ambiguous or reused blocks. SYNC reads back temporary copies before replacing older files, with rollback backups. DISKCMP supports exact single-drive comparison with prompts naming the expected disk and slot/drive.
- Added VOLINFO to BOOT and XL: free space, fragmentation, a paginated bitmap, shared/lost blocks, used blocks marked free and count checks. Incomplete scans never present a lost-block verdict.
- Replaced FORMAT.SYS with FORMAT.PLG, returning directly to the panels. Kept ERASE confirmation and protection of the running program. Physical Disk II formatting preserves resident memory, including on errors, and explicitly warns that /RAM is cleared.
- Published separate 6502 and 65C02 BOOT/EXTRA 140 KB floppies and complete XL 2mg images. Each XL has all 42 overlays, BASIC.SYSTEM, DEMO and IMGHGR; BOOT and EXTRA share a 41-command catalog. The two CPU families never share an EXTRA disk. Missing-disk prompts support selecting drive 1 or 2 and returning the source disk after an overlay loads.
- Added fifteen other service overlays: TXTCONV, DATE, VERIFY, TAGPAT, VOLNAME, WIPE, FIXTYPES, GOTO, FIND, CRC, IDENT, MDVIEW, RENAME, IMGCONV and BOOTBLK. See the [manual](docs/MANUAL.md#more-tools-in-the--menu) for their controls and limits.
- Fixed floppy sorting, jump-by-letter and marking differences after other overlays run. Expanded the paginated overlay menu to 80 columns and added the program configuration path to service API version 2.
- Included a printable English PDF manual with a clickable contents page and bookmarks.
- Added CPU-specific POM2 benches and host tests covering malformed allocation, real file deletion, reversed and partially processed indices, image bitmaps, failed writes, rollback, cancellation and memory bounds. Source comments and the SDK guide are in English.

## [0.7](https://github.com/habib256/a2filecmd/releases/tag/v0.7) — 2026-09-09

- Changed the title page: each build names itself (`- 65C02`, *ENHANCED Apple IIe* / `- 6502`, *UNENHANCED Apple IIe*, no mouse) so one knows which build booted.
- Fixed the HGR viewer leaving an RGB card (Le Chat Mauve, Video-7) in a mode it never asked for: raising AN3 clocked the card's mode latch with 80COL off, so two HGR pictures in a row drifted it to BW560; it is now clocked to COL140, its power-on state.
- Fixed both DHGR viewers on machines where a directory read shares memory ProDOS does not promise to leave alone (an Apple //c, seen on POM2): a raw DHGR page was refused as `not an image` and a packed one (`.RLE`) hung the viewer, because their auxiliary plane was filled with `$2000-$3FFF` routed to the auxiliary bank; both now decode in main memory and move the plane across with `AUXMOVE`.
- Fixed a phantom mouse click at start-up: the first reading of the mouse reported the button held down at the top-left corner, which the viewer took for an Escape and, at the root, dropped to the volume list. The launcher now primes the mouse once so the false press is discarded. Most visible on an Apple //c and on any machine with an AppleMouse, where every picture and menu bounced back to the volumes.

## [0.6.8](https://github.com/habib256/a2filecmd/releases/tag/v0.6.8) — 2026-09-09

- Added a 6502 build for the unenhanced Apple IIe (`A2FILECMD-6502.*`, `make disk ARCH=6502` with cc65 master): the same program, keyboard only — no mouse driver. Both builds are made and published together.
- Added `IMGHGR/` at the root of the `.2mg`: nine HGR pictures from POM1, to leaf through with the arrows.
- Added Left/Right in the overlay menu, five entries at a time.
- Changed the panels: a directory name ends with `/`, like Ammonoid; a volume row reads `/VOL/`.
- Changed the volume list to ProDOS's own `ON_LINE` enumeration, so that every unit ProDOS knows is listed, mirrored SmartPort units included.
- Changed SPACE: tagging a file no longer moves the cursor down.
- Fixed VDrive on a //c picking the printer port: slot 2 (the modem port) is probed first, then 1, 3 to 7.
- Fixed the DHGR test card in `DEMO/`: twelve of its sixteen bands showed as vertical stripes (a repeated byte is not a solid colour); the bench now checks the rendered picture, not only memory.
- Fixed the Binary II extractor leaving the other panel stale: the extracted files now appear in it at once.

[Full changelog](https://github.com/habib256/a2filecmd/compare/v0.6.7...v0.6.8)

## [0.6.7](https://github.com/habib256/a2filecmd/releases/tag/v0.6.7) — 2026-09-08

- Added VDrive: two ProDOS volumes served over a Super Serial Card (or a //c's port 2) at 115 200 bps by ADTPro, `veserver.py` or surl-server, with the ADTPro VSDrive protocol; installed for the session, like Ammonoid. The driver (`src/vsdrive.s`) lives in the language card behind a page-3 thunk; its buffer accesses go through page 3 with bank 1 switched in, because ProDOS's `GBUF` targeted by `ON_LINE` is in bank 1 (the remote volume used to appear under the floppy's name); and it installs a ProDOS interrupt handler (`ALLOC_INTERRUPT`) so a DCD drop behind a real modem no longer ends in `RESTART SYSTEM - $01`. `bench/vdrive.py` runs it on POM2 (`pom2_playtest --ssc`, six checks).
- Added a full-width progress bar to copy, move and delete (forty cells, a counter and the byte count, redrawn only when it changes); ESC interrupts them (the partial file is removed and `Interrupted: x of y` is shown), and the panels update file by file without rereading the disk (`drop_entry`). To make room, the string literals of the EDIT, MUSIC, MENU, IMGFS, DOS33, DELETE and ATTR overlays became named arrays in their own segment, returning about 600 bytes to the resident. `bench/ops.py`, seven checks.
- Fixed a blank screen on unsupported machines: the launcher now requires an Enhanced IIe, //c or IIgs with 128 KB and 80 columns, and says so before returning to ProDOS.
- Fixed ShrinkIt extraction after viewing HGR/DHGR images: the LZW dictionary no longer overwrites main memory through the graphics banking switches.
- Fixed extraction progress: show each file from the start, with its archive position, progress bar and extracted byte count.

[Full changelog](https://github.com/habib256/a2filecmd/compare/v0.6.6...v0.6.7)

## [0.6.6](https://github.com/habib256/a2filecmd/releases/tag/v0.6.6) — 2026-09-08

- Added ShrinkIt (`.SHK`, stored/LZW/1/LZW/2) extraction (`UNSHRINK.PLG`, the LZW core in assembly running from auxiliary memory) and Binary II (`.BNY`) extraction (`BINARY2.PLG`) with the ProDOS file attributes.
- Added readable Applesoft listings (`BASLIST.PLG`), an AppleWorks word-processing viewer (`AWP.PLG`), byte comparison (`COMPARE.PLG`) and text search (`SEARCH.PLG`): six more overlays built on the SDK model, each with its own bench (`bench/shk.py`, `bny.py`, `awp.py`, `find.py`).
- Added the bare floppy and the bootable 32 MB `.2mg` (`/A2FILEHD`) with a complete `DEMO/` collection; floppy images now carry the program without demos, and `tools/mkvolume.py` writes ProDOS tree files.
- Fixed launching and returning from a program installed in any directory: the launcher keeps the prefix (or rebuilds it from the path ProDOS leaves at `$0280`), and the formatter and `RUN` start from the program's own directory (`bench/subdir.py`). A `.2MG` whose size is not a multiple of 512 bytes now opens as a directory.

[Full changelog](https://github.com/habib256/a2filecmd/compare/v0.6.1...v0.6.6)

## [0.6.1](https://github.com/habib256/a2filecmd/releases/tag/v0.6.1) — 2026-09-08

- Fixed DOS 3.3 volume rows overflowing into the neighbouring panel and leaving white squares.
- Fixed file-info, attribute and launch failures reporting a stale ProDOS error.
- Added plain-language ProDOS error messages and an English manual.

[Full changelog](https://github.com/habib256/a2filecmd/compare/v0.6...v0.6.1)

## [0.6](https://github.com/habib256/a2filecmd/releases/tag/v0.6) — 2026-09-08

- Added floppy image tools (`W`, `DISKIMG.PLG`): write a `.PO`/`.DSK`/`.DO`/`.2MG` to a floppy, read a floppy into a new image, and copy floppy to floppy on a single drive by swapping disks at each pass. Blocks go through `READ_BLOCK`/`WRITE_BLOCK` with buffers in main (`$3400`) and auxiliary (`$2000`) memory, so `/RAM` is rebuilt afterwards; typing `ERASE` guards every write.
- Added read-only disk-image browsing (`IMGFS.PLG`): RETURN on a `.PO`/`.2MG`/`.DSK`/`.DO` opens it as a directory (subdirectories, `..`, leaving it), and `C` extracts the tagged files to the ProDOS directory of the other panel. The resident block reader (`img_read_block`) handles the DOS 3.3 sector interleave of a `.DSK` and the `.2MG` header; seedling and sapling files (up to 128 KB) are extracted, the rare tree files are refused.
- Added DOS 3.3 catalog reading and extraction, from an image (`.DSK`/`.DO`/`.2MG`) or from a real disk in a drive (`dos_read_sector` reads the matching ProDOS half-block with `READ_BLOCK`). A DOS 3.3 disk without a ProDOS volume is listed under `/`, recognised by its VTOC; RETURN opens it as a flat directory and `C` extracts (`DOS33.PLG`), stripping the DOS header of Applesoft, Integer and binary files.
- Changed the resident: the editor, music, launcher, attributes, delete, menu and disk-image commands moved out into on-demand `A2FILE/*.PLG` overlays, returning close to 3.5 KB to the main window (`$4000-$ADC2` instead of `$4000-$BADF`). A big overlay (`OVERLAY_BIG` in the header) may also take `$2000-$3FFF`; the core saves the tags, calls the entry point and rereads both panels on return.
- Added the service table `struct A2fcApi` (`src/a2fc_plugin.h`): the stable ABI a third-party overlay receives at its entry point (`fopen`, `message`, `confirm`, `prompt`, `dir_open`/`dir_next`, `read_panel`, `mli`...). The `sdk/` example (`hello.c`, `build.sh`, `plugin.cfg`) is linked outside the tree, without crt0 or `A2FILE.CODE`, and `bench/plugin.py` checks it appears in the menu and runs.
- Added the overlay menu (`!`, `MENU.PLG`), listing `A2FILE/*.PLG` with the one-line description of each header, so a new command needs neither a key nor a rebuild.
- Added the digits `1`..`0` as function keys for the ten buttons of the key bar, Ctrl-T / Ctrl-N to tag or untag everything, and Ctrl-R to reread both panels.
- Fixed relaunching A2FileCmd from Applesoft (`-A2FILE.SYSTEM`) freezing on a black screen right after the switch to 80 columns. Two causes: crt0, seeing `BASIC.SYSTEM` resident, put the C stack on its `HIMEM` (about `$9600`), in the middle of the code being loaded up to `$BE40`; the stack is now always at `$BF00` (`src/crt0.s`, `src/crt0_loader.s`). And `BASIC.SYSTEM` clears the ProDOS prefix when launching a SYS; the launcher now restores it (`src/loader_mli.s`), so A2FileCmd reopens on its panels instead of the volume list.

[Full changelog](https://github.com/habib256/a2filecmd/compare/v0.5...v0.6)

## [0.5](https://github.com/habib256/a2filecmd/releases/tag/v0.5) — 2026-09-07

- Introduced the bootable two-panel ProDOS file manager with batch operations, recursive directory copy, sorting and file attributes.
- Included text and hex viewers, an 8 KB editor, HGR/DHGR picture browsing and Mockingboard playback.
- Included mouse navigation, program launching and the ProDOS disk formatter.
- Fixed issues in the editor, launchers, large directories and shared auxiliary-memory handling.

[Source at v0.5](https://github.com/habib256/a2filecmd/tree/v0.5)
