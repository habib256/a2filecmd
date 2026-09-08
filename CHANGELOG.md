# Changelog

Changes in upcoming and published releases. See the [README](README.md) for features,
downloads and installation.

## Unreleased

- Fixed the DHGR test card in `DEMO/`: twelve of its sixteen bands showed as vertical stripes (a repeated byte is not a solid colour); the bench now checks the rendered picture, not only memory.
- Changed SPACE: tagging a file no longer moves the cursor down.
- Added Left/Right in the overlay menu, five entries at a time.
- Added a 6502 build for the unenhanced Apple IIe (`make disk ARCH=6502` with cc65 master, `A2FILECMD-6502.*`): the same program, keyboard only — no mouse driver. Releases now ship both builds, made together by the CI.
- Fixed the Binary II extractor leaving the other panel stale: the extracted files now appear in it at once.
- Added `IMGHGR/` at the root of the `.2mg`: nine HGR pictures from POM1, to leaf through with the arrows.
- Changed the panels: a directory name ends with `/`, like Ammonoid; a volume row reads `/VOL/`.
- Changed the volume list to ProDOS's own `ON_LINE` enumeration, so that every unit ProDOS knows is listed, mirrored SmartPort units included.
- Fixed VDrive on a //c picking the printer port: slot 2 (the modem port) is probed first, then 1, 3 to 7.


## [0.6.7](https://github.com/habib256/a2filecmd/releases/tag/v0.6.7) — 2026-09-08

- Added VDrive: two ProDOS volumes served over a Super Serial Card (or a //c's port 2) at 115 200 bps by ADTPro, `veserver.py` or surl-server, with the ADTPro VSDrive protocol; installed for the session, like Ammonoid.
- Added a full-width progress bar to copy, move and delete; ESC interrupts them, and the panels update file by file.
- Fixed a blank screen on unsupported machines: the launcher now requires an Enhanced IIe, //c or IIgs with 128 KB and 80 columns, and says so before returning to ProDOS.
- Fixed ShrinkIt extraction after viewing HGR/DHGR images: the LZW dictionary no longer overwrites main memory through the graphics banking switches.
- Fixed extraction progress: show each file from the start, with its archive position, progress bar and extracted byte count.

[Full changelog](https://github.com/habib256/a2filecmd/compare/v0.6.6...v0.6.7)

## [0.6.6](https://github.com/habib256/a2filecmd/releases/tag/v0.6.6) — 2026-09-08

- Added ShrinkIt (`.SHK`, stored/LZW/1/LZW/2) and Binary II (`.BNY`) extraction.
- Added readable Applesoft listings, an AppleWorks word-processing viewer, byte comparison and text search.
- Added a bootable 32 MB `.2mg` with a complete `DEMO/` collection; floppy images now carry the program without demos.
- Fixed launching and returning from a program installed in any directory; the hard-disk volume is named `/A2FILEHD`.

[Full changelog](https://github.com/habib256/a2filecmd/compare/v0.6.1...v0.6.6)

## [0.6.1](https://github.com/habib256/a2filecmd/releases/tag/v0.6.1) — 2026-09-08

- Fixed DOS 3.3 volume rows overflowing into the neighbouring panel and leaving white squares.
- Fixed file-info, attribute and launch failures reporting a stale ProDOS error.
- Added plain-language ProDOS error messages and an English manual.

[Full changelog](https://github.com/habib256/a2filecmd/compare/v0.6...v0.6.1)

## [0.6](https://github.com/habib256/a2filecmd/releases/tag/v0.6) — 2026-09-08

- Added floppy image read/write/copy tools for `.PO`, `.DSK` and `.2MG`.
- Added read-only disk-image browsing and extraction, plus DOS 3.3 catalog reading and extraction.
- Expanded the on-demand overlay system and published a third-party plugin SDK.
- Fixed relaunching A2FileCmd from Applesoft.

[Full changelog](https://github.com/habib256/a2filecmd/compare/v0.5...v0.6)

## [0.5](https://github.com/habib256/a2filecmd/releases/tag/v0.5) — 2026-09-07

- Introduced the bootable two-panel ProDOS file manager with batch operations, recursive directory copy, sorting and file attributes.
- Included text and hex viewers, an 8 KB editor, HGR/DHGR picture browsing and Mockingboard playback.
- Included mouse navigation, program launching and the ProDOS disk formatter.
- Fixed issues in the editor, launchers, large directories and shared auxiliary-memory handling.

[Source at v0.5](https://github.com/habib256/a2filecmd/tree/v0.5)
