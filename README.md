<div align="center">

# A2FileCmd

**Two panels. Your Apple II. Start with 48 KB.**

Select on one side. Copy to the other.\
From the essentials of DOS3.3 to a complete ProDOS workspace.

[![Latest release](https://img.shields.io/github/v/release/habib256/a2filecmd?color=0075b6)](https://github.com/habib256/a2filecmd/releases/latest)
[![Build](https://github.com/habib256/a2filecmd/actions/workflows/ci.yml/badge.svg)](https://github.com/habib256/a2filecmd/actions/workflows/ci.yml)
[![License: GPL v3](https://img.shields.io/badge/license-GPL_v3-blue.svg)](LICENSE)

**[Download](https://github.com/habib256/a2filecmd/releases/latest) · [Read the guide](docs/MANUAL.md) · [PDF guide](docs/A2FILECMD-MANUAL-EN.pdf)**

![A2 File Cmd ProDOS XL in 80 columns: the volume root on the left, the DEMO folder on the right](docs/screenshots/prodos-panels-0.9.3.png)

*ProDOS XL in 80 columns on an enhanced Apple IIe, captured in POM2 at the
screen's proportions ([how](bench/capture_panels.py), [source image](docs/screenshots/prodos-panels-0.9.3.json)).*

</div>

## A file manager in the Commander tradition

One panel is the source, the other the destination. Tag files on one side,
copy or move them across, and A2FileCmd reads back what it wrote. Browse
folders and disk images, read documents, view pictures, play music and
extract archives without leaving the panels.

It comes in two programs that share one idea:

- **ProDOS**, 80 columns and 128 KB on an Apple IIe, //c or IIgs: the complete
  workspace shown above, with its tools behind **!**.
- **DOS3.3**, 40 columns and 48 KB on an Apple II+ with two Disk II drives:
  the essentials in pure 6502 assembly ([below](#dos33-the-essentials-in-48-kb)).

| You want to… | ProDOS gives you… |
|---|---|
| **Organize a disk** | Copy and move directory trees, tags, sorting, attributes, file comparison and a text editor. |
| **Open old files** | Text, hex, BASIC listings, AppleWorks documents and sheets; extract ShrinkIt, Binary II and other classic archives. |
| **Browse a collection** | HGR/DHGR and specialist picture viewers, fonts and shapes. Arrow through an album without returning to the panels. |
| **Listen** | Mockingboard MB1/PT3 playback, including Mockingboard 4c on //c; Electric Duet also plays through the speaker. |
| **Work with disks** | Browse images as folders, extract files, create and convert images, transfer DOS files, compare, format and check volumes. |

The [guide](docs/MANUAL.md) lists the supported formats and each tool's limits.

## Choose your disk

**[0.9.3 is the published release](https://github.com/habib256/a2filecmd/releases/tag/v0.9.3).**
No build is needed to use the release downloads.

| Your setup | Download from 0.9.3 |
|---|---|
| **ProDOS · hard disk or emulator** | [XL — complete with demonstrations, 6502](https://github.com/habib256/a2filecmd/releases/download/v0.9.3/A2FILECMD-XL-0.9.3.2mg) |
| **ProDOS · 65C02 and enhanced ROM** | [XL — enhanced 65C02, optional mouse](https://github.com/habib256/a2filecmd/releases/download/v0.9.3/A2FILECMD-65C02-enhanced-mouse-XL-0.9.3.2mg) |
| **ProDOS · all tools without sample media** | [800K — complete, 6502](https://github.com/habib256/a2filecmd/releases/download/v0.9.3/A2FILECMD-800K-0.9.3.po) |
| **ProDOS · one 5¼-inch program disk** | [140K — essentials, 6502](https://github.com/habib256/a2filecmd/releases/download/v0.9.3/A2FILECMD-140K-0.9.3.dsk) |
| **Apple II+ · 48 KB · two Disk II drives** | [DOS3.3 — standalone 40-column edition](https://github.com/habib256/a2filecmd/releases/download/v0.9.3/A2FILECMD-DOS3.3-0.9.3.dsk) |

- Every ProDOS edition needs **128 KB and 80 columns**. The 6502 editions
  also run on enhanced machines.
- Choose the enhanced XL only when **both the CPU and the ROM** qualify: a
  65C02 upgrade alone is not enough. Mouse and Mockingboard are optional.
- 800K and XL carry every tool; 140K keeps the essential file operations on
  one disk. Each disk is self-contained: no category disks to juggle.
- DOS3.3 and 140K are DOS-order `.dsk`, 800K is ProDOS-order `.po`, XL is
  `.2mg`. Changing the extension does not convert a disk.
- To install ProDOS elsewhere, keep `A2FILE.SYSTEM` and its complete `A2FILE/`
  folder side by side, from the same build, and copy the root `RECOVER` guide.

<details>
<summary>Check a downloaded image</summary>

Get `SHA256SUMS-<version>.txt` from the same release. Compare the output of
`shasum -a 256 <image>` on macOS with its entry. With every release image and
the PDF together, Linux can check the whole set:

```sh
sha256sum -c SHA256SUMS-<version>.txt
```

</details>

## Your first minute

1. **Boot the matching image.** ProDOS starts with `A2FILE.SYSTEM`, also from
   a program selector; DOS3.3 can start with `BRUN A2FC`.
2. **Try the shared basics:** TAB switches panels, arrows select, Return opens,
   Space tags, **C** copies and **?** shows the edition's help.
3. **Use a spare disk for a first copy.** In ProDOS, `/` lists volumes: open
   the destination in the opposite panel. In DOS3.3, `/` selects the active
   panel's drive.
4. **On XL, explore DEMO.** Read `SAMPLE`, open an HGR/DHGR picture, browse
   `TINY.PO`, or play `CANON.ED` through the speaker. Advanced tools are in **!**.

## DOS3.3: the essentials in 48 KB

![A2 File Cmd DOS3.3 showing both catalogs and its keyboard bar](docs/screenshots/dos33-panels-0.9.2.png)

The product distilled: an Apple II+, 48 KB and two Disk II drives, 40 columns,
pure 6502 assembly, no ProDOS, 80-column card or plugins. Choose a file, tag a
few more, copy them across and let A2FileCmd verify the result. Read text,
inspect bytes, view a hi-res picture or edit a small note; rename, lock,
delete and format are a key away.

Copies refuse existing destination names, keep the source and read back what
was written. The bottom bar shows the main keys and **?** opens help. The
[developer guide](docs/MINI-DOS33.md) has its keys, write guarantees and
measurements.

## Keep the originals safe

A2FileCmd checks copies, preserves originals during supported replacements,
and names files left for recovery when an operation cannot finish. **Read the
result before retrying or removing a disk.** Verification cannot make a
physical metadata write atomic through a power cut.

Some ProDOS tools need auxiliary memory and can clear **all files in /RAM**.
They ask before using it; save those files elsewhere first. Music playback
preserves /RAM. DOS3.3 has no auxiliary-memory requirement; once a disk write
starts, its keyboard cannot interrupt it.

The guide includes a practical [incident recovery procedure](docs/MANUAL.md#recover-after-an-incident):
identify the temporary or backup, preserve a disk image, and recover from a
duplicate to a fresh destination. [Data-safety details](docs/DATA-SAFETY.md)
explain the protections and remaining limits.

## Read, build or contribute

- **Use it:** [manual](docs/MANUAL.md), [printable PDF](docs/A2FILECMD-MANUAL-EN.pdf),
  [changes](CHANGELOG.md) and [roadmap](TODO.md).
- **Explore DOS3.3:** [developer guide and measurements](docs/MINI-DOS33.md).
- **Add a ProDOS tool:** [plugin SDK](sdk/README.md), with an example and build script.
- **Test it:** [emulator benches](bench/README.md) and [real-hardware checklist](docs/HARDWARE-CHECKLIST.md).
- **Report a problem:** [open an issue](https://github.com/habib256/a2filecmd/issues)
  with version, machine/emulator, disk format, exact message and reproduction steps.

With the cc65 toolchain installed:

```sh
make mini    # standalone DOS3.3 binary
make         # ProDOS program and overlays
make disk    # all five distribution images
make test    # host checks
```

Previous versions have been tried on real //c, enhanced and unenhanced IIe
machines by the maintainer and testers, and in Virtual II and
[POM2](https://github.com/habib256/pom2). Current-release qualification is
tracked separately; emulator results are not a physical-drive guarantee.
Contributors must follow [AGENTS.md](AGENTS.md): preserving data comes first.

## Credits

Created by **Arnaud Verhille** (`@habib256`), under [GNU GPL v3](LICENSE).
Inspired by **A2Command**, **Ammonoid** by Colin Leroy and **Norton Commander**.
[Full attributions and reference links](docs/CREDITS.md) identify reused code,
formats and test material, including cc65, Hyper-FORMAT, Electric Duet,
CiderPress II and the PT3 player work.

ProDOS images include ProDOS 8 2.4.3; 800K and XL supply BASIC.SYSTEM,
Apple software distributed for the community by John Brooks, and
[INTBASIC.SYSTEM](data/INTBASIC.md) by Joshua Bell. Generated demonstrations and third-party
samples are distinguished in their source notices. The companion emulator
[POM2](https://github.com/habib256/pom2) is a separate project by the same author.
