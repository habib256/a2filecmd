# Changelog

Changes in upcoming and published releases. See the [README](README.md) for features,
downloads and installation.

## Unreleased

- Refuse DOS 3.3 writes when a catalog chain has an invalid end link or a file's T/S list has an incorrect logical sector offset. Apply the same audit to physical disks and image copies. Regressions preserve every malformed-image byte, assert zero physical writes, and execute valid multi-list files and both failure cases on 6502/65C02 under sim65.

- Copy and editor save now reject a destination stream error even when `fwrite` reports the full byte count. Preserve the originals and the dirty editor buffer; report failed cleanup and retain its temporary bytes. Add actual C regressions for both operations and retries against retained recovery files.

- Refuse overlay execution and caching after header/payload read errors, close failures, empty payloads or oversized files. Restore file panels after a failed large load. Clear the menu result before loading so a missing menu cannot replay an old command, including a tagged move. Add actual resident C regressions and POM2 byte/stack/AUX checks on both CPUs.

- Track DISKIMG output reservation through failed closes, check all final stream closes and report failed image cleanup by filename, including after cancellation. Preserve existing images and read-only sources; add PO/DSK byte-preservation and retry regressions. Simplified finalization saves 50/39 overlay bytes on 65C02/6502.

- A2FC Mini 0.7.0, still pure 6502: HELLO and the first screen centre `A2FILECMD`, `MINI DOS 3.3` and `V0.7.0` at the top and `GPL3 VERHILLE ARNAUD` then `LOADING .... PLEASE WAIT ....` at the bottom in 40-column text before the catalog; an IIe left in 80STORE/80-column or hi-res is forced back to 40-column text so the boot is not a black or doubled screen. Disk II screen holes are restored before RWTS; delete refuses a catalog sector count or T/S list offset that does not match the walk, and a tagged delete stops on anything but OK/LOCKED; edit refuses a text file larger than 32 data sectors; a write-protect after the VTOC is committed latches `copy_fault`. The browser uses one inverse bottom key bar (`TAB C D L R N E / ? Q`); questions stay inverse. Copy, delete, lock, rename and create return to the two panels on their own — the result stays on the footer, with no ANY KEY Back. Copy progress is a normal-video `[********----]` bar of 32 stars, not inverse cells. L locks or unlocks (cursor toggles; a tagged batch unlocks if any mark is locked, otherwise it locks) and R renames the cursor to a new exclusive name, each a verified catalog-only write that leaves file data untouched; unlock a locked file before delete or rename. The name prompt keeps X across `put`, so the second and later letters show once each instead of the row index repeating a later cell. Cancelling a copy restores the source drive so D, E, T, `/` and a later N still I/O there; `measure_text` never leaves `edit_len` at 8192 (NUL would land on the resident program); delete uses the same data-track check as copy (tracks 1–2 and 17 are not freed); a catalog count of 105 or more is full (`bcs`); `load_file` refuses a T/S list whose offset does not match the walk. 256 unused BSS bytes dropped. The Mini disk includes the raw 8 KB `TIGER` HGR page so G/Return can show a picture without a second disk. relocate the resident program to `$4000` so hi-res page one is an 8 KB working area; BRUN at `$1000` holds the editor and delete. Add tag selection (Space, Ctrl-T/N, `*`), a hi-res viewer (G, or Return on a 32–34 sector binary), exclusive TXT creation and a basic editor (N / E, save as a new name only), and delete (D) that marks the catalog entry first then frees sectors; locked files are refused. Create and copy share the write engine (VTOC first, sector readback, one catalog entry last, `copy_fault` on an uncertain write). Copy stays on the two panels: C copies every tagged file, or the cursor when nothing is marked; one confirmation, then each name exclusively; an existing name is skipped, an uncertain write stops the batch. A 32-cell bar fills per file. Whole-disk audit, source pre-read and the final cross-check are gone so the motor can finish; a swapped disk, a stale panel, or a late name collision is not caught. Host tests cover load, create collisions/faults and delete order; POM2 benches cover tags, HGR, create, delete and a two-file tagged copy on disposable images.

- Copy selected ProDOS TXT/BIN/BAS/INT files to real DOS 3.3 disks with C and DOSWRITE (FILES/XL). Detect the selected Disk II slot instead of requiring slot 6, fixing copies to slot 5 (including TIGER BIN $2000). Audit allocations before writing, preserve neighbouring half-blocks, verify written data and source closes, publish the catalog entry last, and keep the source. Refuse existing names and protected disks; report retained allocation after failures.
- Support C into DOS-order DSK/DO/2MG images through DOSIMAGE/DOSPUT (FILES/XL). Reserve a sibling exclusively, copy and compare the whole image, audit DOS allocations, verify the closed result, and install with recoverable renames. Preserve the source and original image on errors; refuse existing DOS names and protected containers. Add byte-preservation fault tests and POM2 disk/image tests on both CPUs. Populate the demo DOS image's free-sector bitmap so it can accept files.
- Refuse DOS image installation if a successful write corrupts bytes outside the intended sectors, or if the validated 2MG header changes during confirmation. Regressions check existing files, boot bytes, free space, container trailers and preservation-scan read failures.
- Reset image/DOS mode when returning to the volume list, so physical DOS 3.3 catalogs are not displayed as ProDOS volumes and can be reopened repeatedly.

- Reject truncated Binary II headers, data and padding, and report archive close failures. Track exclusive output ownership through reservation failures, report failed cleanup with the retained filename, and preserve earlier extracts and colliding files. Add native C fault-injection and retry tests.

- Publish editor saves through the shared installation/rollback transaction. Keep verified temporary files after any installation failure and explicitly report failed restoration. Test late target/backup collisions, failed renames, retained backups and retries, checking original bytes throughout writing and verification.

- Report failed editor temporary cleanup after reservation, I/O or publication refusal. Never reopen after a failed reservation close; preserve the original, recovery file and unsaved edit buffer, including on retries. Add byte-preservation regressions for combined failures and late creation collisions.

- Place private editor, menu and archive messages in their owning overlays. Recover 127 resident bytes on both CPUs, restoring MAIN headroom to 276/786 bytes without changing file operations, BSS, stack size or memory ceilings.

- Rewrite the standalone Apple II+ DOS 3.3 edition (A2FC Mini 0.6.0) in pure 6502 assembly and retire its C sources. Same screens, keys, messages and copy semantics; the binary drops from 12,065 to 7,750 bytes and the program ends at `$7BB8`, 1,096 bytes clear of DOS, with a layout check on every link. Measured on POM2's NMOS core with Disk II timing: a 16-sector catalog read falls from 4,898,568 to 1,703,592 cycles, and copying the 48-sector `A2FC.MINI` from 280 to 64 seconds at 1 MHz. Parsing a catalog sector now fits inside DOS 3.3's 2:1 interleave window instead of waiting out a revolution per sector, and the copy engine moves a batch of sixteen sectors per change of drive instead of alternating drives for every sector. The checks are unchanged: VTOC reserved before any data, every write read back, both disks compared afresh, one catalog entry published last, and copy_fault latched on an uncertain write. `make test-mini` runs the shipped 6502 modules under sim65 with the disk images held by the test process, so a chosen read or write can still be made to fail, tear in half or silently corrupt a byte; 33 host tests, and both POM2 benches pass unchanged. See [the guide](docs/MINI-DOS33.md).

- Write COPY results to an exclusively created A2FC.COPY and read them back before moving the old destination aside. Publish through the shared installation/rollback transaction; preserve verified temporary files on installation failure and refuse recovery-name collisions. Test old destination bytes throughout transfer and verification, plus late collisions, rollback faults and path limits on both CPU builds.

- Keep COPY reservation ownership through failed closes, report failed cleanup even after cancellation, and skip rollback when output deletion failed. Move finalization into resident code to increase COPY headroom from 33/25 to 116/111 bytes on 65C02/6502, with unchanged BSS. Verify preserved source, output and backup bytes under combined failures.

- Share resident exclusive reservation with BATCH, distinguishing failed creation from an owned file whose reservation close failed. Preserve manifest ownership on cleanup failure and forbid reopening after a failed close. Add native reservation-state tests and COPY/BATCH byte-preservation regressions, including retry collisions.

- Move GOTO preference saves onto the shared installation transaction. Check configuration metadata, storage and protections before creating output, and retain the verified temporary after failed installation. Add byte-preservation tests for late name collisions, combined cleanup failures and retries.

- Share the temporary-file installation and rollback sequence across SYNC, TXTCONV and IMGCONV. SYNC retains its verified temporary after failed installation and stops before the next file when recovery is needed, preserving the diagnostic. Compact API calls save 730/728 bytes in SYNC on 65C02/6502; add native transaction tests and full SYNC traversal failure tests.

- Report failed output cleanup in TXTCONV and IMGCONV, including cancellation; do not claim an image was removed when deletion failed. Distinguish failed backup restoration from other installation failures. Preserve recovery files and late-arriving destination files, with combined-failure and retry regressions.

- Share exclusive ProDOS CREATE between TXTCONV and the utility plugins, including SYNC. Preserve all MLI errors and creation ownership; exercise dirty-state file/directory sequences on both CPUs and source/recovery-file preservation on failed creation. No plugin ABI or AUX-memory change.

- Extract the core exclusive-output and verified-copy services into internal modules with explicit buffer/overlay contracts and a compile-time copy-state capacity check. Preserve identical binaries on both CPUs; add cancellation/retry and failed-overlay-after-success sequences to the native C host tests. Shared plugin replacement and COPY memory headroom remain open.

- Add NIBCOPY to DISKTOOLS and XL: resident Disk II transport for one- or two-drive copies of 35 standard 16-sector tracks. Preserve encoded fields/order, rebuild sync gaps, compare two source reads and verify target fields. Require AUX-loss consent, a physically write-protected source and explicit target destruction confirmation at each single-drive exchange. Stop with a partial-track count on failure; protected/nonstandard disk formats and power-failure recovery are not supported.

- Prepare the next media filename before image/music cleanup can reveal text, then restore the panels directly on that target. Left/Right no longer redraws the previous selection while the next file loads. Refuse a vanished target or failed directory reread; retain AUX consent and marks.

- Prioritize reused PT3 samples and ornaments in the main-RAM cache. The sparse TurboSound benchmark drops from 156 to 105 disk misses and from 9.15 to 8.20 seconds on the enhanced IIe at 1 MHz; compact pairs retain 50 Hz. Preserve source/AUX, exact-read failure handling and both CPU memory limits.

- Consolidate media routing around one resident viewer-name table and byte IDs; preserve probe errors, decoder precedence, AUX consent and navigation. Free OPEN space rises from 4/42 to 185/215 bytes, and MAIN from 145/682 to 259/779 bytes (65C02/6502), with unchanged memory ceilings.

- Play standard TurboSound `02TS` pairs on both Mockingboard AY chips, with independent frequency/volume tables and endings, shared transport and preserved AUX. Cache-resident pairs keep 50 Hz at 1 MHz; sparse pairs can slow down on cache misses.
- Add PURPLE to MEDIA and XL (60 overlays): open original Purplesoft `.FOTO1`/`.FOTO2` pairs, restore their EVE graphics mode, browse distinct pictures with one AUX consent, and return with Escape. Validate exact planes and failed reads/closes; rebuild `/RAM` on any exit after AUX writes.

- Support all historical PT3 frequency tables and verify their 96 tones on both CPUs.
- Keep AUX consent while browsing images; clear it when returning to the panels.
- Recognize Escape and media arrows even when cc65 adds the Open-Apple/PB0 flag; regress TWOSTEVESTITLE playback and return.

- Extend PT3 playback from 4,608 to 65,535 bytes with a main-RAM page cache, read-only source access and preserved `/RAM`; cover I/O failures, pause/navigation, natural completion and stack bounds on both CPUs.

- Consolidate resident display/input helpers with unchanged panel text and plugin ABI: free MAIN reaches 290/835 bytes and language-card space 172/169 bytes on 65C02/6502, meeting the first reserve targets without raising memory limits.
- Return/X launches Integer BASIC programs through INTBASIC.SYSTEM v0.9, included with Applesoft's runtime on DEVTOOLS and XL; T keeps listing BASIC source.
- Keep program/runtime paths separate during launch, check interpreter headers and actual load sizes, and reject loader close failures.
- Relaunch A2FC from BASIC using its own system path even when the previous program's prefix remains set.
- Verify automatic return to both panels, silenced hardware and preserved AUX after MB1/PT3 finish, on both CPU builds.
- Build checks now report free bytes in resident memory and core overlays to guide consolidation.
- Compact resident ProDOS diagnostics and relocate launch-only text, freeing 22 bytes in MAIN and 71/70 bytes in the 65C02/6502 language card with unchanged error messages.
- Add an opt-in Mockingboard 4c to the POM2 test host and cover automatic detection and MB1/PT3 playback on Apple //c; document the existing `$C400` probe support.

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
