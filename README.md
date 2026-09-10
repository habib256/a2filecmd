<div align="center">

# A2FileCmd

**Two panels. One Apple II.**

A complete ProDOS file manager for the Apple IIe.\
Browse disks, unpack archives, read documents, view pictures and play music — in 128 KB.

[![Latest release](https://img.shields.io/github/v/release/habib256/a2filecmd?color=0075b6)](https://github.com/habib256/a2filecmd/releases/latest)
[![Build](https://github.com/habib256/a2filecmd/actions/workflows/ci.yml/badge.svg)](https://github.com/habib256/a2filecmd/actions/workflows/ci.yml)
[![License: GPL v3](https://img.shields.io/badge/license-GPL_v3-blue.svg)](LICENSE)

**[Download](https://github.com/habib256/a2filecmd/releases/latest) · [Manual](docs/MANUAL.md) · [Changelog](CHANGELOG.md) · [Plugin SDK](sdk/README.md)**

![A2FileCmd's two panels: files, ProDOS attributes and keyboard commands in 80 columns](docs/screenshots/01-panels.png)

*80 columns. Keyboard and mouse. Boots from a single 5.25" floppy.*

</div>

Inspired by [A2Command, Ammonoid and Norton Commander](#inspirations),
A2FileCmd brings the familiar source-and-destination workflow to your Apple II.
Tag a group of files and copy them across. Open a disk image like a folder. Unpack a ShrinkIt archive,
read an AppleWorks letter, or leaf through a directory of double hi-res
pictures. The tools are right there, beside your files.

## What you can do

| | |
|---|---|
| **Manage your files** | Copy, move, rename and delete files or whole directory trees. Tag batches, sort by name, size or type, change ProDOS attributes and lock files. Progress bars and overwrite prompts keep transfers clear. |
| **Explore disks and images** | Browse ProDOS and DOS 3.3 disk images as read-only folders, then extract files to the other panel. Read physical DOS 3.3 disks, create and write floppy images, copy floppies and format ProDOS disks. |
| **Unpack classic archives** | Extract ShrinkIt `.SHK` archives, including LZW/1 and LZW/2 compression, and Binary II `.BNY` archives with their ProDOS file attributes. |
| **Read, edit and compare** | Text and hex viewers, an 8 KB text editor, readable Applesoft listings and an AppleWorks word-processing viewer. Compare two files byte by byte, search files for text, or mark differences between panels. |
| **Enjoy pictures and sound** | Full-screen HGR and DHGR, raw or RLE-compressed. Use the arrow keys to browse pictures like an album. Play `.MB` music on a Mockingboard while managing files. |
| **Make it yours** | Keyboard shortcuts throughout, optional AppleMouse II support and remembered panel settings. Launch SYS, BIN and Applesoft programs, or add your own tools with the plugin SDK. |

The **!** menu also offers text and disk-image conversion, CRC-32, file
identification, Markdown reading, volume-wide search, favourite directories,
batch renaming and type repair. EXTRA and XL also provide UNDELETE recovery,
DISKCMP comparison, MKIMAGE creation, RESCUE extraction, SYNC updates and TREE totals. BLKVIEW searches and extracts blocks while preserving the source; DISKIMG reads back disk writes.
DISASM reads BIN/SYS files as 6502 or 65C02 assembly and exports text listings.
FIND continues volume searches through successive pages of 20 matches.
VERIFY handles tagged files and VOLINFO exports allocation reports and file blocks.
DATE, TAGPAT, TXTCONV, VOLNAME and
WIPE also fit the floppy edition. See the [tool reference](docs/MANUAL.md#more-tools-in-the--menu).

## See it in action

<table>
  <tr>
    <td width="50%"><img src="docs/screenshots/02-dhgr.png" alt="The DHGR viewer displaying a sixteen-colour test card"><br><strong>Double hi-res, full screen</strong><br>Browse HGR and DHGR pictures with the arrow keys.</td>
    <td width="50%"><img src="docs/screenshots/04-text.png" alt="The text viewer displaying the sample document"><br><strong>Read without leaving your files</strong><br>Page through text, Applesoft listings and AppleWorks documents.</td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/screenshots/05-hex.png" alt="The hex viewer showing bytes alongside their text representation"><br><strong>Look inside any file</strong><br>Inspect hexadecimal bytes and their text side by side.</td>
    <td width="50%"><img src="docs/screenshots/09-format.png" alt="The ProDOS formatter listing available drives and volumes"><br><strong>Keep your disks ready</strong><br>Format Disk II, SmartPort and RAM volumes.</td>
  </tr>
</table>

*Screenshots from v0.5; the current release adds archive extraction, document
readers and more disk tools. See the [changelog](CHANGELOG.md).*

## Download and boot

**Start with the [latest release](https://github.com/habib256/a2filecmd/releases/latest).**
No build required. Choose the image that fits your setup:

The table describes the current 0.7.6 source build. The latest published release
is 0.7.5; its downloads retain their own version numbers.

| Image family (0.7.6) | CPU | Contents |
|---|---|---|
| `A2FILECMD-6502-BOOT-0.7.6.dsk` | 6502 | Bootable 140 KB floppy: file manager, disk tools and formatter |
| `A2FILECMD-6502-EXTRA-0.7.6.dsk` | 6502 | 140 KB companion: 25 additional tools, menu and BASIC.SYSTEM |
| `A2FILECMD-6502-XL-0.7.6.2mg` | 6502 | Bootable 32 MB disk: all 44 overlays, BASIC.SYSTEM, `DEMO/` and `IMGHGR/` |
| `A2FILECMD-65C02-BOOT-0.7.6.dsk` | 65C02 | Bootable 140 KB floppy: file manager, disk tools and formatter |
| `A2FILECMD-65C02-EXTRA-0.7.6.dsk` | 65C02 | 140 KB companion: 25 additional tools, menu and BASIC.SYSTEM |
| `A2FILECMD-65C02-XL-0.7.6.2mg` | 65C02 | Bootable 32 MB disk: all 44 overlays, BASIC.SYSTEM, `DEMO/` and `IMGHGR/` |

The names sort by CPU, then BOOT, EXTRA, XL. Choose **6502** for an Apple II
with 128 KB and 80 columns, including the original IIe; choose **65C02** for
an enhanced IIe, //c or IIgs, with MouseText and optional mouse support.
Use the EXTRA disk for the **same CPU and release** as BOOT. Each EXTRA
keeps its own free space for future plugins. Floppies are distributed as
`.dsk`; complete XL disks use `.2mg`.

1. Boot BOOT or XL. ProDOS 8 is included. With floppies, put EXTRA in slot 6,
   drive 2. With one drive, A2FC names the required disk and drive; press
   **1** to choose drive 1, insert the disk, then press **Return**.
   `make disk` builds all six volumes; `ARCH=6502` or `ARCH=enh` selects a CPU.

2. Press **`TAB`** to switch panels, **`RETURN`** to open and **`ESC`** to go up. Press **`?`** for the full key map.
3. On the `.2mg`, explore the `DEMO/` folder already open in the right panel. On BOOT, the right panel shows the available volumes; `E`, `I` and the `!` menu load missing tools from the matching EXTRA disk.

A **Mockingboard** enables music playback; an **AppleMouse II** enables point
and click navigation. Both are optional and can be in any supported slot.

**Tested on:** a real Enhanced Apple IIe; the [Virtual II](https://www.virtualii.com/) emulator;
and, under [POM2](https://github.com/habib256/pom2), an Apple //c and an unenhanced 1983 IIe
running the 6502 build. The Apple IIgs has not been tried yet.

### Take a quick tour

The hard-disk image includes examples generated especially for A2FileCmd:

- Open `DHGR.RLE` or `HGR.RAW` to see the picture viewer; use **Left / Right** to browse.
- Read `SAMPLE`, list the `HELLO` Applesoft program with **`T`**, or open the AppleWorks `LETTER`.
- Open `TINY.PO`, `TINY.2MG` or `DOS33.DSK` as a folder; **`C`** extracts a selected file to the other panel.
- Select `SAMPLE.SHK` or `SAMPLE.BNY`, press **`!`** and choose its extractor.
- With a Mockingboard, open `WELCOME.MB` for a fanfare; **`P`** pauses or resumes it.

> **Using `/RAM`?** DHGR pictures and Mockingboard playback share its auxiliary
> memory and rebuild `/RAM` empty. Save its files elsewhere first. Single-drive
> floppy copying also uses this memory. Do not write to `/RAM` while music plays.

### Install on an existing hard disk

Copy `A2FILE.SYSTEM` and the complete `A2FILE/` folder **side by side** into
any directory. Keep the program and its overlays from the same release.
Launch `A2FILE.SYSTEM` from Bitsy Bye or with `-A2FILE.SYSTEM` from BASIC
in that directory. Settings and support files live beside the program.

<details>
<summary>Verify your download</summary>

Download `SHA256SUMS-0.7.5.txt` from the same release into the image's directory.
To verify one image on macOS:

```sh
shasum -a 256 A2FILECMD-65C02-XL-0.7.5.2mg
```

Compare the result with its line in `SHA256SUMS-0.7.5.txt`. If you downloaded all
six images and the PDF, check them together on Linux with:

```sh
sha256sum -c SHA256SUMS-0.7.5.txt
```

</details>

## The keys you'll use most

| Key | Action |
|---|---|
| `TAB` · `RETURN` · `ESC` | Switch panel · open · go up |
| Up / Down · Left / Right | Select an entry · page through a directory |
| `SPACE` | Tag a file for a batch operation |
| `C` · `V` · `R` · `D` · `K` | Copy · move · rename · delete · make directory — a full-width progress bar, panels updating file by file, `ESC` to stop |
| `T` · `H` · `I` · `E` | Read text or a document · inspect hex · view a picture · edit text |
| `W` · `F` | Disk-image tools · format a disk |
| `!` | Open the plugin menu, including archive extraction, compare and search |
| `?` · `Q` | Help · quit to ProDOS |

With a mouse, click a file to select it and click again to open it. Column
headers change the sort order; the path goes up; the bottom bar runs commands.
The [manual](docs/MANUAL.md) covers every shortcut and file format.
A [printable PDF](docs/A2FILECMD-MANUAL-EN.pdf) is also included in each release.

<details>
<summary>Limits to keep in mind</summary>

- Large directories are read in windows of 139 disk entries plus the parent entry, in disk order without sorting.
- ProDOS paths are limited to 64 characters.
- The text editor holds 8 KB; a `.MB` tune must fit in 2,304 bytes.
- Images opened as folders are read-only. Extract files before viewing or editing them; ProDOS image extraction supports files up to 128 KB, and subdirectories must be entered individually.
- Launching another program replaces A2FileCmd. The FORMAT overlay returns directly to the panels; from Applesoft, you can relaunch A2FileCmd as described in the manual.

</details>

## Build it. Extend it.

A2FileCmd is written in C and 6502 assembly, built with **cc65 2.19 or later**
and **Python 3**. The disk-image tools and demo generators are included.

```sh
make          # build the ProDOS program and its overlays
make disk     # BOOT + EXTRA (.po/.dsk) and XL (.2mg), for 6502 and 65C02
make test     # run checks that do not need an Apple II
```

`make bench` exercises the program in [POM2](https://github.com/habib256/pom2).
See the [bench guide](bench/README.md) for setup and coverage.

Want to add a tool? The **[plugin SDK](sdk/README.md)** includes a worked
example, a build script and a stable API. Plugins appear in the **`!`** menu
and work with the selected file.

| Directory | Contents |
|---|---|
| [`src/`](src/) | File manager, launcher, drivers and plugins |
| [`sdk/`](sdk/) | Plugin guide, example and build tools |
| [`tools/`](tools/) | Disk-image tools, format readers and demo generators |
| [`bench/`](bench/) | Emulator sessions and verification |
| [`data/`](data/) | Help, boot blocks, ProDOS and BASIC.SYSTEM |
| [`docs/`](docs/) | Manual, release notes and screenshots |

Found a bug or have an idea? [Open an issue](https://github.com/habib256/a2filecmd/issues).
For a bug, include the release, machine or emulator, disk format and steps to reproduce it.

## Inspirations

A2FileCmd owes a tip of the hat to these file managers. Explore the programs
that inspired it, from the classic two-panel workflow to serial virtual drives:

| Inspiration | What it brings to A2FileCmd | Disk-image download |
|---|---|---|
| **A2Command** | The Commander-style file and disk manager on Apple II. | [A2Command 1.1 — ZIP containing `a2cmd-1.1-140k.po`](https://mirrors.apple2.org.za/ftp.apple.asimov.net/utility/A2Command%20v1.1.zip), preserved by the Asimov mirror. |
| **[Ammonoid](https://github.com/colinleroy/a2tools)**, by Colin Leroy | An Apple II file manager and an inspiration for integrated serial virtual drives. | [Download `ammonoid.po`](https://github.com/colinleroy/a2tools/releases/latest/download/ammonoid.po) from the author's latest release. |
| **Norton Commander** | The classic two-panel interface and keyboard command bar. | [Norton Commander 3.0 — floppy images on WinWorld](https://winworldpc.com/download/d0ee2b62-911a-11ec-84e0-0200008a0da4) (7z archive; choose a download mirror). **For IBM PC compatibles running DOS.** |

## Credits

Created by **Arnaud VERHILLE** (`@habib256`). Free software under the
[GNU GPL v3](LICENSE), in the spirit of A2Command, Ammonoid and Norton Commander.

The disk images include **ProDOS 8 2.4.3** and **BASIC.SYSTEM**, distributed
for the Apple II community by John Brooks; these are Apple's software.
The low-level 5.25" formatter descends from **ProDOS Hyper-FORMAT** by
Jerry Hewett (1985, public domain) and Gary Desrochers (1989), as carried by ADTPro.
All the demo pictures, music, documents and archives are generated by `tools/mkdemo.py`.

A2FileCmd grew out of an Apple IIe game and became a project of its own.
Its companion emulator, [POM2](https://github.com/habib256/pom2), is by the same author.
