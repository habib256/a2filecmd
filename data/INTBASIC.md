# INTBASIC.SYSTEM

`INTBASIC.SYSTEM.SYS` is the unmodified 7,395-byte runtime extracted from
the official [a2stuff/intbasic v0.9 release](https://github.com/a2stuff/intbasic/releases/tag/v0.9),
asset `intbasic_system.po`, root file `INTBASIC.SYSTEM` (ProDOS type `$FF`).
It is distributed on A2FC DEVTOOLS and both XL images, alongside BASIC.SYSTEM.
The `.SYS` suffix in this repository supplies the file type during packaging;
the resulting ProDOS filename is `INTBASIC.SYSTEM`.

- Source revision: `72fdc9177eb3215e24a97f591c420e2981ea3562`.
- SHA-256: `741070ab75c701dec8b9cf1345619d8f6ccc930db72be60b8e08f46ed6e8c237`.
- [Source and usage](https://github.com/a2stuff/intbasic/tree/72fdc9177eb3215e24a97f591c420e2981ea3562).

The runtime contains Steve Wozniak's Integer BASIC, Apple copyright 1977,
adapted for ProDOS by the upstream project. Its README credits Paul R.
Santa-Maria's disassembly, Andy McFadden's SourceGen conversion and James
Davis's disassembly of Gary J. Shannon's Programmer's Aid music routines.

The standard interpreter header at `$2000` advertises a 65-byte path buffer
at `$2006`. A2FC passes the selected INT file there. The runtime relocates
its interpreter to MAIN `$A200` and uses a ProDOS I/O buffer at `$9E00`;
it does not borrow auxiliary `/RAM` storage. A running BASIC program can
perform its own disk operations. On normal completion in interpreter mode,
the runtime returns to the ProDOS selector, not directly to A2FC.
