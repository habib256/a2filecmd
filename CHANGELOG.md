# Changelog

Changes in upcoming and published releases. See the [README](README.md) for features,
downloads and installation.

## Unreleased

## [0.8.7] - 2026-09-15

### Data preservation
- UNSHRINK wrote ShrinkIt runs of 130 to 256 identical bytes as a single byte and still reported the file verified (the read-back decoded it the same way). Runs are decoded in full; malformed streams (codes outside the table, oversized chunks, lengths that do not add up) are refused instead of hanging or writing into I/O space; the LZW/1 stream CRC and the NuFX v3 thread CRC are checked; /RAM is recognised by its driver, not its name; a verified file is kept when only the archive tail is damaged. The real assembly core now runs under sim65 in the host tests.
- DOSGET keeps sparse random-access text files and every sector of S, R and new A/B files (no header stripped). IMGFS reads the storage type from the directory entry. DISKIMG reads non-ProDOS floppies, recognises a Disk II by its slot ROM, checks the disk at every one-drive swap and names the disk that will really be erased; W accepts real image names only.
- COMPARE and SEARCH report read and close errors instead of "Identical" or "not found"; BINARY2 skips folder records; a failed image panel read no longer mixes stale entries with volumes; the editor asks before saving converted text and leaves an unchanged file alone; tagged deletes say when directories go with their contents.
- MOVE reads and compares everything again after the confirmation (a disk swapped during the question writes nothing), bounds directory walks, never takes a read error for a free name, and allows moves at the program volume's root. BLKEDIT refuses the running volume from a subdirectory, writes into images and refuses locked ones. RESCUE really retries and uses the fresh size; UNDELETE walks a volume root and recovers empty files; VOLNAME keeps image panels consistent; TXTCONV, IMGCONV and DOSWRITE tell a refused install (nothing changed, temporary removed) from a failed one.
- PAINT816 and EXTASIE never touch /RAM for a refused picture; DISKCMP never compares a disk with itself; FIND reports unreadable files; VERIFY verifies every tagged volume; VOLINFO skips directory headers; MDVIEW and INTBASIC lose no text at a page end, and INTBASIC reads past 64 KB.

### Disks, VDrive and launch
- FORMAT identifies the target again just before the first write: a disk swapped during the prompts is left untouched. The language card is always restored after a direct driver call.
- VDrive: a send that never completes (no cable) returns an I/O error instead of freezing; STATUS no longer claims 65,535 blocks, so a blank host image is refused by FORMAT; the interrupt handler starts with CLD; both drive vectors are restored on exit.
- The launcher refuses a truncated A2FILE.CODE; the page-3 chain closes its file on every path.
- BIN launch uses the file's own load address and type, not the panel's.

### A2FileCmd Mini DOS3.3
- One write-fault latch for every command; the destination panel is reread after a failed copy; copies never allocate on tracks 1–2; `$8D` line ends in the editor; a full 8 KB text is refused rather than cut; batch results count what was done and skipped; renaming to the same name says so; delete refuses a cross-linked disk.

### A2FileCmd Mini DOS3.3 disk, replaced after the tag
- Stray characters no longer appear in column 8 during disk access (a letter missing from `COPY 5 MARKED?`, a lone letter lower on the screen). Around every RWTS call the Mini saved and restored the Disk II screen holes at `$0478+slot×16`, which are visible cells, instead of `$0478+slot`, where DOS 3.3 keeps each drive's current track.
- RETURN on a binary runs it: a 32–34 sector binary still opens as a hi-res picture, any other binary asks `BRUN NAME?` and, after Y, A2FC Mini leaves and DOS runs it from the panel's drive. B does the same on any binary. The command runs from page 3, so nothing of the Mini runs after the program, which may load over it; a name DOS could not read back (a comma, an unprintable character) is refused.

### Distribution
- The BOOT floppy and the bench floppies keep 3 free blocks, what saving A2FILE.CFG needs: messages that no test checks were shortened and duplicated code folded where fixes had pushed overlays over a block boundary.
- Benches: VOLINFO waits for its disk prompt and runs from the bench floppy; data_safety uses a real image name.

### Validation
- 731 host tests in 62 suites, each new test first seen failing on 0.8.6. POM2 benches on both CPUs, the complete session 73/73.

### Earlier in this cycle
- Mini: copying a panel (`=` and the boot duplicate) now includes the catalog slot, so a mirrored view is a full identity. After a write, only panels showing that disk are reread; two views share one catalog instead of paying it twice. The copy engine still does not borrow the name tables. Host tests cover the slot, a namelist without one, and names left intact after execute.
- Every extraction now reads its output back. DOSGET, BINARY2, IMGFS (a disk image opened as a folder) and UNSHRINK reopen the closed file and compare it byte for byte with the source read a second time: the DOS sectors, the archive record, the image blocks, or the ShrinkIt thread decoded again from its start; the file must end where the data ends. A wrong byte, an unreadable output, a short read or a source lost during the second pass fails the extraction and removes the owned file. Host tests inject each fault.
- To make room, IMGFS is a big overlay (its entries come from the snapshot) and UNSHRINK keeps its state at $3E00 with its code allowed up to $3BFF; the unused `new_output` wrapper leaves the resident. 65C02 resident headroom: 429 bytes. The BOOT floppy keeps 3 blocks free.
- A tool-sequence bench (`bench/sequences.py`, both CPUs, in CI): picture, music, then a marked copy; a cancelled 300 KB copy, the same copy completed, then moved; a floppy swapped in drive 2 under an open panel, the volume list reread, a copy from each disk. Every byte is checked on the volumes after exit.
- The archive benches run on the 6502 bench floppy too (`make benchfloppy ARCH=6502`, `A2FC_BUILD=build-6502 A2FC_IMG=A2FILECMD-full`).

## [0.8.6] - 2026-09-14

### Files
- Directories can be tagged. Marked MOVE takes them: entry rewritten on the same volume; across volumes, copied and read back file by file, the source deleted only once everything arrived. MOVE on a selected directory across volumes does the same.
- The tree walks behind copy, move and delete no longer recurse: bounded frames, explicit refusals (path over 64 characters, over 213 entries along one path, unreadable directory) before any write. A 20-level tree is deleted and copied as far as ProDOS paths allow.
- The launch confirmation spells out the way back, e.g. `Run HELLO? Back: -/A2FC6502/A2FILE.SYSTEM`; the demo's HELLO points to `BYE` and the ProDOS selector.

### Distribution
- VOLNAME moves from BOOT to DISKTOOLS; BOOT has four blocks free again. The floppy launcher's title page is a line shorter.
- The DOS 3.3 catalog and disk-image directory readers live in a CATALOG overlay (BOOT and XL); a read requested while another overlay runs is deferred and settled by the main loop. 65C02 resident headroom: 299 bytes (was 23).

### Manual
- A2FileCmd Mini DOS3.3 has its own section, clearly apart from the ProDOS edition: keys, disk writes, limits and speed; the download list separates its disk from the ProDOS images.

### Validation
- 653 host tests in 72 suites. POM2 benches on both CPUs, with the test host now writing the emulated hard disk back so byte comparisons are real; the 73-check session passes, BASIC return included.

## [0.8.5] - 2026-09-13

### Two editions, one version number
- A2FC Mini now carries the release number of the ProDOS edition, from the single `A2FC_VERSION` line of the Makefile; `A2FC-MINI-DOS33-0.8.5.dsk` ships with the release files.
- Mini 0.8.5, pure 6502: 40-column boot splash, tags, hi-res viewer, exclusive TXT creation and editor, DEL, LOCK/UNLOCK and RENAME as verified catalog-only writes, one inverse key bar, results on the footer.
- Mini file-system bug hunt: every write goes back to the catalog slot the panel read, so a swapped or renamed disk is refused as `DISK CHANGED`; looping catalog chains, mismatched T/S lists and write-protected disks are refused before any write; the DOS UNDELETE mark is placed as DOS does. Disks formatted without DOS may use tracks 1–2.

### Music and pictures
- New DUET overlay (MEDIA/XL) plays Electric Duet songs (`$D5`/`$D0E7` type or `.ED` name, legacy `M.*` BIN files): speaker player transcribed cycle for cycle, Mockingboard when present, 1/2 switch outputs, D pulse width, P pause, Left/Right browse. The demo disk gains `CANON.ED`.
- Browsing lo-res and double lo-res pictures with Left/Right keeps the current picture on the air until the next one is drawn; no text-page flash or panel redraw between neighbours.

### Files and DOS 3.3 from ProDOS
- Copy ProDOS TXT/BIN/BAS/INT files to real DOS 3.3 disks (DOSWRITE) and into DOS-order DSK/DO/2MG images (DOSIMAGE/DOSPUT): allocations audited, VTOC reserved first, data read back, catalog entry published last, source kept; existing names and protected disks refused. The real Disk II slot is used, slot 5 included.
- DOSGET (FILES/XL) extracts DOS files with exact metadata: BIN keeps its load address, BIN/BAS/INT drop sector padding; cycles, bounds, I/O and cleanup are checked and Escape cancels.
- IDENT recognises DUET, PT3, font and specialised picture families and reports read errors; FIXTYPES validates DUET candidates, proposes `$D5/$D0E7` without renaming, and confirms every attribute change with metadata reread first.
- The `!` menu's category page shows how many overlays each category holds and what they are for.

### Data preservation
- UNSHRINK, BINARY2, DISKIMG, COPY, EDIT, BATCH, GOTO, SYNC, TXTCONV and IMGCONV own their output reservations through failed closes, report a failed cleanup by naming the retained file, and keep originals, recovery files and unsaved buffers on every failure and retry.
- COPY and editor saves publish through the shared verified-temporary installation with recoverable renames; a destination stream error is refused even when the write count is complete.
- UNSHRINK reads skipped threads and padding exactly, refuses truncated or inconsistent headers, stops on stream or close errors and cancels between blocks. Binary II refuses truncated headers, data and padding.
- Overlay loading refuses read errors, empty or oversized payloads, restores the panels after a failed large load, and clears the menu result so a missing menu cannot replay an old command.
- DOS image installs are refused when a write changed bytes outside the intended sectors or the validated 2MG header changed during confirmation; returning to the volume list resets image/DOS mode.

### Memory and validation
- Private editor, menu and archive messages live in their overlays (127 resident bytes back); DISKIMG, SYNC and COPY finalisation trimmed. Ceilings and the 192-byte C stack are unchanged; API v5 adds the active-entry snapshot without moving service offsets.
- 650 host tests in 70 suites, including 66 sim65 runs of the Mini modules with injected faults and the real 6502 under sim65 for the ProDOS services; POM2 benches on both CPUs for DUET, DOS writes, DOS images, overlay faults and the Mini disk. Seven release images verified; a page-aligned indexing bug in cc65 2.19 was found and worked around.

## [0.8.0] - 2026-09-12

### Navigation and interface
- Overlay menu organized by category; prompts displayed in inverse video.
- Return or I automatically selects the appropriate image viewer.
- Left/Right browses pictures and music of the same type within a directory.
- Leaving a folder restores its selection, including in large directories.

### Pictures and music
- New foreground Mockingboard PT3 player with pause, title, artist and player credits (4,608-byte modules).
- MB1 playback moves into a foreground overlay; both music players preserve /RAM.
- New viewers for MGTK fonts, Print Shop clip art and LZ4FH images.
- Improved Extasie, 816/Paint and DGR handling; direct opening of Integer BASIC listings.

### Data preservation
- Safer copy, move, save, conversion and extraction, with verified writes and recoverable originals.
- Explicit confirmation before destructive use of /RAM; safer preference saving and batch moves.
- Fixed malformed-file handling, incomplete directory reads, catalog loops and recursive stack overflow.

### Distribution and validation
- Five universal 6502 floppies: BOOT, FILES, MEDIA, DISKTOOLS and DEVTOOLS.
- Complete XL images for 6502 and 65C02, with 59 overlays; updated English PDF manual.
- 396 host tests, 7,140 mutation cases and 219 POM2 checks passed; seven release images verified.

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
