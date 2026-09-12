# A2 File Cmd -- two-panel ProDOS file manager, Apple IIe.
#
#   make            the launcher, resident and overlays, in build/ or build-6502/
#   make disk       BOOT + FILES/MEDIA/DISKTOOLS/DEVTOOLS in 6502 (.po/.dsk),
#                   plus XL .2mg for 6502 and 65C02.
#                   ARCH=6502: the floppies and XL; ARCH=enh: XL only.
#   make benchfloppy  build/A2FILECMD-full.po: a 65C02 floppy with the core
#                   overlay, for the benches only -- never shipped
#   make test       the tests outside the emulator (memory layout, volume)
#   make bench      the POM2 benches (needs the emulator, see bench/README.md)
#   make clean
#
# The program only just fits in the machine's memory: the link is checked
# every time by tools/check_layout.py, which catches the two overflows that
# ld65 lets through silently. See docs/MANUAL.md.

A2FC_VERSION = 0.8.0
VOLUME       = A2FC$(CPU)

# The .2mg hard disk: another volume name, to coexist with the floppy.
# (Comments stay on their own line: make keeps the blanks before a `#`.)
VOLUME_HD    = A2XL$(CPU)
# Universal 6502 floppies; complete XL images for 6502 and 65C02.
# ARCH=6502 uses cc65 master (apple2, 128 KB / 80 columns, no mouse).
# ARCH=enh uses cc65 2.19 (apple2enh, 65C02, MouseText and optional mouse).
# CC65_HEAD points to the separately installed cc65 master toolchain.
ifeq ($(origin ARCH),undefined)
BOTH_EDITIONS = yes
endif
ARCH ?= enh
CC65_HEAD ?= $(HOME)/opt/cc65-head
ifeq ($(ARCH),6502)
CC65BIN = CC65_HOME=$(CC65_HEAD)/share/cc65 $(CC65_HEAD)/bin/
TARGET = apple2
ASDEFS = -D A2_6502 -D CC65_MASTER
CLDEFS = --asm-define A2_6502 --asm-define CC65_MASTER -DA2FC_6502 -DA2FC_NOMOUSE -DA2FC_BIG_BINARY2
MOUSEOBJ =
# The edition and the processor, in the file name.
CPU = 6502
IMG = A2FILECMD-$(CPU)-BOOT
BUILD_SUFFIX = -6502
BIN2SIZE = 0x0D00
LAYOUT_BIG = --big BINARY2
else
CC65BIN =
TARGET = apple2enh
ASDEFS =
CLDEFS = -DA2FC_BIG_BINARY2
MOUSEOBJ = $(BUILD)/mouse.o
# The processor precedes the disk role for alphabetical grouping.
CPU = 65C02
IMG = A2FILECMD-$(CPU)-BOOT
BUILD_SUFFIX =
BIN2SIZE = 0x0D00
LAYOUT_BIG = --big BINARY2
endif
IOBUF  = $(TARGET)-iobuf-0800.o
VDRIVEOBJ = $(BUILD)/vsdrive.o
CL     = $(CC65BIN)cl65
AS     = $(CC65BIN)ca65

SRC   = src
DATA  = data
TOOLS = tools
BUILD = build$(BUILD_SUFFIX)
DIST  = dist

# -Cl: static locals. On a 6502 a stack variable costs an address
# computation at every access, a static one an absolute lda. The price: no
# function may be reentrant, and the three recursive walks in a2fc.c
# take the stack back with #pragma static-locals.
# --codesize 100: the growth the optimiser allows itself. Measured: below
# 100 the generator stops using some inline sequences and the code GROWS
# AGAIN; the minimum is a plateau from 100 to 130.
CODESIZE ?= 100
CFLAGS = -t $(TARGET) $(CLDEFS) -O -Oirs -Cl --codesize $(CODESIZE)

# __HIMEM__ = $BF00: just below the ProDOS global page. The C stack fits in
# 256 bytes -- maximum depth measured on the bench: 94 (bench/stack.py).
HIMEM      = 0xBF00
A2FC_STACK = 0x00C0
# The ProDOS I/O buffers come from $0800 upward instead of the heap:
# without this module the heap is only 270 bytes and every fopen fails.

CODE   = $(BUILD)/A2FILE.CODE.BIN
# The overlays, written by the same link (A2FILE/NAME.PLG, read at $1B00 on
# demand): the image decoder, the viewers, the help, deletion, music, the
# launcher, the attributes, the editor, the menu, the disk images. Each has
# two segments in its file: NAME (code) then NAMERO (strings). See
# src/a2fc_plugin.h for the header and the service table.
PLUGINS = BATCH NAV OPEN COPY FORMAT IMAGE TEXT HEX DELETE HELP EDIT RUN ATTR MENU DISKIMG IMGFS DOS33 UNSHRINK BASLIST COMPARE SEARCH BINARY2 AWP
# The floppy edition: the commands, the two viewers that cost four blocks,
# and the disk tools. The editor, the pictures, the music, the archives and
# the document readers stay on the hard disk (45 blocks, with BASIC.SYSTEM's
# 21, given back to the disk tools to come -- see TODO.md, "Les deux editions").
# COMPARE also carries the S (sort) and M (mark differences) commands.
PLUGINS_FLOPPY = BATCH NAV OPEN COPY FORMAT HELP TEXT HEX DELETE RUN ATTR MENU DISKIMG IMGFS DOS33 COMPARE
# The service-table overlays: src/plugins/NAME.c, each compiled and linked
# on its own like a third party's (sdk/plugin.cfg, no crt0, nothing of
# A2FILE.CODE), because the resident is full -- they reach the program only
# through struct A2fcApi. Lower-case source names, upper-case .PLG on disk.
# A header written `PLUGIN_MAGIC, OVERLAY_BIG,` (one line) is linked as a big
# overlay ($1B00-$3FFF); `PLUGIN_MAGIC, 0,` as a small one.
XPLUGINS = $(sort $(basename $(notdir $(wildcard $(SRC)/plugins/*.c))))
# The ones that also go on the floppy edition (TODO.md, the floppy budget).
XPLUGINS_FLOPPY = $(filter txtconv date verify tagpat volname drivespd wipe,$(XPLUGINS))
# The cc65 target library for the plugin link: the one of the machine's cc65
# for apple2enh, the one of cc65 master for apple2.
ifeq ($(ARCH),6502)
CC65LIB = $(CC65_HEAD)/share/cc65/lib/apple2.lib
CCDEFS = -DA2FC_6502 -DA2FC_NOMOUSE -DA2FC_BIG_BINARY2
else
CC65LIB = $(dir $(shell command -v cc65))../share/cc65/lib/apple2enh.lib
CCDEFS =
endif
# These overlays reserve $3000-$3FFF for scratch (FIND: $3100-$3FFF): code AND BSS must
# stop before their scratch area. ld65 enforces that boundary at link time.
XPLUGINS_SCRATCH = music bootblk find goto mdview wipe dgrview
# These decode a picture into the graphics page, so they are big (the core
# sets the tags aside and rereads the panels) but their CODE must still stop
# before $2000: they are linked with the small window, which makes ld65
# enforce that boundary instead of leaving it to luck.
XPLUGINS_HGR = extasie packfot paint816 fontview printshop lz4fh
XPLG = $(patsubst %,$(BUILD)/%.PLG,$(XPLUGINS))
XPLG_FLOPPY = $(patsubst %,$(BUILD)/%.PLG,$(XPLUGINS_FLOPPY))
SYSTEM = $(BUILD)/A2FILE.SYSTEM.SYS
FLOPPY_SYSTEM = $(BUILD)/A2FILE.FLOPPY.SYS
PO     = $(DIST)/$(IMG)-$(A2FC_VERSION).po
DSK    = $(DIST)/$(IMG)-$(A2FC_VERSION).dsk
include config/packages.mk
CATALOG = $(BUILD)/EXTRAS.CAT
PACKAGE_PO = $(foreach role,$(PACKAGE_ROLES),$(DIST)/A2FILECMD-$(CPU)-$(role)-$(A2FC_VERSION).po)
PACKAGE_DSK = $(PACKAGE_PO:.po=.dsk)

OBJS = $(BUILD)/crt0.o $(BUILD)/overlay.o $(BUILD)/unshrink.o $(VDRIVEOBJ) $(BUILD)/a2fc_mli.o $(BUILD)/chain.o \
       $(BUILD)/mb_probe.o $(BUILD)/memory_swap.o $(BUILD)/mli_safe.o $(MOUSEOBJ) $(BUILD)/format_diskii.o $(BUILD)/format_mli.o

.DELETE_ON_ERROR:

.PHONY: all disk benchfloppy xplugins test bench example clean
all: $(SYSTEM) $(CODE)

$(BUILD) $(DIST):
	@mkdir -p $@

$(BUILD)/%.o: $(SRC)/%.s | $(BUILD)
	$(AS) -t $(TARGET) $(ASDEFS) -o $@ $<

$(BUILD)/memory_swap.o: $(SRC)/memory_swap.c $(SRC)/memory_swap.h | $(BUILD)
	$(CL) $(CFLAGS) -c -o $@ $<

# Only the hardware probe is resident; both music players are overlays.
$(BUILD)/mb_probe.o: $(SRC)/mb_probe.s | $(BUILD)
	$(AS) -t $(TARGET) $(ASDEFS) -I $(SRC) -o $@ $<

# The launcher: a real SYS program, loaded at $2000 by ProDOS, which reads
# A2FILE.CODE to its three addresses (see src/loader.c).
# Separate intermediates: cl65 would otherwise overwrite src/loader.s
# when BOOT and XL are built concurrently.
$(BUILD)/launcher.o $(BUILD)/launcher_floppy.o: $(SRC)/loader.c Makefile | $(BUILD)
	$(CC65BIN)cc65 -t $(TARGET) $(CCDEFS) -O -Oirs -Cl --codesize $(CODESIZE) \
	  $(if $(filter %/launcher_floppy.o,$@),-DA2FC_FLOPPY) -D 'A2FC_VERSION="$(A2FC_VERSION)"' -o $(@:.o=.s) $<
	$(AS) -t $(TARGET) $(ASDEFS) -o $@ $(@:.o=.s)

$(SYSTEM): $(BUILD)/launcher.o
$(FLOPPY_SYSTEM): $(BUILD)/launcher_floppy.o
$(SYSTEM) $(FLOPPY_SYSTEM): $(BUILD)/crt0_loader.o $(BUILD)/loader_mli.o Makefile | $(BUILD)
	$(CL) $(CFLAGS) --start-addr 0x2000 \
	  -Wl -D,__EXEHDR__=0 -Wl -D,__HIMEM__=$(HIMEM) -Wl -D,__FILETYPE__=0xFF \
	  -o $@ $(BUILD)/crt0_loader.o $(BUILD)/loader_mli.o \
	  $(BUILD)/$(if $(filter $(FLOPPY_SYSTEM),$@),launcher_floppy,launcher).o $(IOBUF)

$(CODE): $(SRC)/media.h $(SRC)/batch.h $(SRC)/config.h $(SRC)/format.c $(SRC)/a2fc.c $(SRC)/a2fc.cfg $(SRC)/a2fc_plugin.h $(SRC)/music.h $(SRC)/memory_swap.h $(OBJS) Makefile | $(BUILD)
	$(CL) $(CFLAGS) -D 'A2FC_VERSION="$(A2FC_VERSION)"' -C $(SRC)/a2fc.cfg \
	  -Wl -D,__EXEHDR__=0 -Wl -D,__HIMEM__=$(HIMEM) -Wl -D,__STACKSIZE__=$(A2FC_STACK) -Wl -D,__BIN2SIZE__=$(BIN2SIZE) \
	  -Wl -m,$(BUILD)/a2fc.map -Wl -Ln,$(BUILD)/a2fc.lbl \
	  -o $@ $(BUILD)/crt0.o $(BUILD)/overlay.o $(BUILD)/unshrink.o $(VDRIVEOBJ) $(SRC)/a2fc.c $(SRC)/format.c $(BUILD)/format_diskii.o $(BUILD)/format_mli.o $(BUILD)/a2fc_mli.o \
	  $(BUILD)/chain.o $(BUILD)/mb_probe.o $(BUILD)/memory_swap.o $(BUILD)/mli_safe.o \
	  $(MOUSEOBJ) $(IOBUF)
	@python3 $(TOOLS)/check_layout.py --lbl $(BUILD)/a2fc.lbl --bin $@ $(LAYOUT_BIG)

# -- The service-table overlays ---------------------------------------------
$(BUILD)/%.PLG: $(SRC)/plugins/%.c $(wildcard $(SRC)/plugins/*.h) $(wildcard $(SRC)/plugins/*.s) $(wildcard $(SRC)/plugins/pt3lib/*) $(SRC)/a2fc_plugin.h sdk/plugin.cfg sdk/find.cfg sdk/pt3.cfg Makefile | $(BUILD)
	$(CC65BIN)cc65 -t $(TARGET) $(CCDEFS) -O -Oirs -Cl --codesize $(CODESIZE) -o $(BUILD)/$*.s $<
	$(CC65BIN)ca65 -t $(TARGET) -o $(BUILD)/$*.o $(BUILD)/$*.s
	@helper=; if [ -f $(SRC)/plugins/$*.s ]; then $(AS) -t $(TARGET) -o $(BUILD)/$*_svc.o $(SRC)/plugins/$*.s || exit; helper=$(BUILD)/$*_svc.o; fi; \
	  if grep -qE 'PLUGIN_MAGIC, *OVERLAY_BIG' $<; then big=1; else big=0; fi; \
	  $(CC65BIN)ld65 -C $(if $(filter find,$*),sdk/find.cfg,$(if $(filter pt3,$*),sdk/pt3.cfg,sdk/plugin.cfg)) -D __OVLSIZE__=$$( if [ $$big = 1 ]; then echo $(if $(filter $*,$(XPLUGINS_HGR)),0x0500,$(if $(filter $*,$(XPLUGINS_SCRATCH)),$(if $(filter find,$*),0x1600,0x1500),$(if $(filter volinfo blkview blkedit,$*),0x249E,0x2500))); elif [ "$*" = verify ]; then echo 0x04C2; else echo 0x0500; fi ) -m $(BUILD)/$*.map -Ln $(BUILD)/$*.lbl -o $@ $(BUILD)/$*.o $$helper $(CC65LIB) && \
	  limit=$$( [ $$big = 1 ] && echo $(if $(filter $*,$(XPLUGINS_HGR)),1280,9472) || echo 1280 ) && \
	  { test $$(wc -c < $@) -le $$limit || { echo "$@: $$(wc -c < $@) bytes, more than its $$limit-byte window"; rm -f $@; exit 1; }; } && \
	  echo "$@: $$(wc -c < $@) bytes ($$( [ $$big = 1 ] && echo big || echo small ) overlay)"
xplugins: $(XPLG)
all: xplugins

# -- Published disks --------------------------------------------------------
# BOOT has ProDOS, the launcher, file manager and disk tools; categories carry
# the remaining tools and BASIC.SYSTEM. XL contains everything plus demos.
STAGE = $(BUILD)/vol
HDV = $(BUILD)/$(IMG).hdv
TWOMG = $(DIST)/A2FILECMD-$(CPU)-XL-$(A2FC_VERSION).2mg
FULLPO = $(BUILD)/A2FILECMD-full.po
STAGE_DEPS = $(SYSTEM) $(CODE) $(DATA)/A2FILE.HELP.TXT $(DATA)/PRODOS.SYS \
       $(DATA)/prodos_boot.tmpl $(TOOLS)/mkvolume.py

ifdef BOTH_EDITIONS
disk:
	$(MAKE) ARCH=6502 disk
	$(MAKE) ARCH=enh disk
else ifeq ($(ARCH),6502)
disk: $(PO) $(DSK) $(TWOMG) $(PACKAGE_PO) $(PACKAGE_DSK)
else
disk: $(TWOMG)
endif

# The stage: the launcher, the program, the overlays named in $(1), the help,
# the formatter. Called with the plugin list.
define stage
	@rm -rf $(STAGE) && mkdir -p $(STAGE)/A2FILE
	cp $(DATA)/PRODOS.SYS $(STAGE)/
	cp $(SYSTEM) $(STAGE)/A2FILE.SYSTEM.SYS
	cp $(CODE) $(STAGE)/A2FILE/A2FILE.CODE.BIN
	for p in $(1); do cp $(CODE).$$p "$(STAGE)/A2FILE/$$p.PLG#061B00"; done
	for p in $(2); do cp $(BUILD)/$$p.PLG "$(STAGE)/A2FILE/$$(echo $$p | tr a-z A-Z).PLG#061B00"; done
	cp $(DATA)/A2FILE.HELP.TXT $(STAGE)/A2FILE/A2FILE.HELP.TXT
endef

# BOOT: the universal 6502 floppy.
ifeq ($(ARCH),6502)
$(PO): STAGE = $(BUILD)/floppy
$(PO): $(FLOPPY_SYSTEM) $(STAGE_DEPS) $(XPLG_FLOPPY) $(CATALOG) $(TOOLS)/po2dsk.py | $(DIST)
	$(call stage,$(PLUGINS_FLOPPY),$(XPLUGINS_FLOPPY))
	cp $(FLOPPY_SYSTEM) $(STAGE)/A2FILE.SYSTEM.SYS
	cp $(CATALOG) $(STAGE)/A2FILE/EXTRAS.CAT.BIN
	python3 $(TOOLS)/mkvolume.py $(STAGE) $(PO) --volume $(VOLUME) \
	  --boot $(DATA)/prodos_boot.tmpl --blocks 280
	@python3 $(TOOLS)/prodos_read.py $(PO) | head -1
	@echo "==> $(PO): the boot floppy ($(CPU))"

$(DSK): $(PO) $(TOOLS)/po2dsk.py
	python3 $(TOOLS)/po2dsk.py $< $@

endif

# The catalog uses the same link as its matching program images.
$(CATALOG): $(CODE) $(XPLG) $(TOOLS)/mkoverlay_catalog.py $(TOOLS)/disk_packages.py config/packages.mk Makefile
	python3 $(TOOLS)/mkoverlay_catalog.py $@ $(BUILD) --cpu $(CPU) --native $(PLUGINS) --plugins $(XPLUGINS)

ifeq ($(ARCH),6502)
# Each category carries MENU and the full catalog for single-drive swaps.
# Resolve native/service overlays from the same build; never copy old staging.
define package_disk
$(DIST)/A2FILECMD-$(CPU)-$(1)-$(A2FC_VERSION).po: $(CODE) $(CATALOG) $(XPLG) $(DATA)/BASIC.SYSTEM.SYS $(TOOLS)/mkvolume.py $(TOOLS)/mkpackage.py $(TOOLS)/disk_packages.py config/packages.mk Makefile | $(DIST)
	python3 $(TOOLS)/mkpackage.py $(BUILD) $$@ --role $(1) --cpu $(CPU)
$(DIST)/A2FILECMD-$(CPU)-$(1)-$(A2FC_VERSION).dsk: $(DIST)/A2FILECMD-$(CPU)-$(1)-$(A2FC_VERSION).po $(TOOLS)/po2dsk.py
	python3 $(TOOLS)/po2dsk.py $$< $$@
endef
$(foreach role,$(PACKAGE_ROLES),$(eval $(call package_disk,$(role))))
endif

# XL: the complete edition for the selected CPU.
$(TWOMG): $(STAGE_DEPS) $(XPLG) $(DATA)/BASIC.SYSTEM.SYS $(DATA)/README.TXT \
       $(TOOLS)/mkdemo.py $(TOOLS)/po22mg.py \
       $(TOOLS)/mkshk.py $(TOOLS)/mkbny.py $(TOOLS)/mkdos33.py $(wildcard $(DATA)/IMGHGR/*) | $(DIST)
	$(call stage,$(PLUGINS),$(XPLUGINS))
	cp $(DATA)/BASIC.SYSTEM.SYS $(STAGE)/
	mkdir -p $(STAGE)/DEMO
	cp $(DATA)/README.TXT $(STAGE)/DEMO/README.TXT
	python3 $(TOOLS)/mkdemo.py $(STAGE)/DEMO
	cp -R $(DATA)/IMGHGR $(STAGE)/IMGHGR
	python3 $(TOOLS)/mkvolume.py $(STAGE) $(HDV) --volume $(VOLUME_HD) \
	  --boot $(DATA)/prodos_boot.tmpl --blocks 65535
	python3 $(TOOLS)/po22mg.py $(HDV) $(TWOMG)
	@rm -rf $(STAGE)/DEMO $(STAGE)/IMGHGR   # the stage keeps the program alone (bench/plugin.py picks it up)
	@echo "==> $(TWOMG): the complete edition ($(ARCH))"

# A 65C02 floppy with the core overlays and BASIC.SYSTEM, for the benches that
# exercise the editor, the pictures and the readers from a
# floppy (bench/run.py and friends, A2FC_IMG=A2FILECMD-full). Never shipped.
benchfloppy: $(FULLPO)
$(FULLPO): STAGE = $(BUILD)/benchvol
# Archive benches build their own disposable boot fixtures (archive_support.py).
$(FULLPO): $(STAGE_DEPS) $(DATA)/BASIC.SYSTEM.SYS
	$(call stage,$(filter-out UNSHRINK BINARY2 AWP,$(PLUGINS)),)
	cp $(DATA)/BASIC.SYSTEM.SYS $(STAGE)/
	python3 $(TOOLS)/mkvolume.py $(STAGE) $(FULLPO) --volume A2FILECMD \
	  --boot $(DATA)/prodos_boot.tmpl --blocks 280
	@echo "==> $(FULLPO): the bench floppy, core overlays ($(ARCH))"

test:
	python3 $(TOOLS)/test_config.py
	python3 $(TOOLS)/test_config_native.py
	python3 $(TOOLS)/test_batch.py
	python3 $(TOOLS)/test_ui.py
	python3 $(TOOLS)/test_media.py
	python3 $(TOOLS)/test_goto_safety.py
	python3 $(TOOLS)/test_file_safety.py
	python3 $(TOOLS)/test_core_dirscan.py
	python3 $(TOOLS)/test_tree_stack.py
	python3 $(TOOLS)/test_catalog_safety.py
	python3 $(TOOLS)/test_imgconv_safety.py
	python3 $(TOOLS)/test_check_layout.py
	python3 $(TOOLS)/test_mkvolume.py
	python3 $(TOOLS)/test_prodos_read.py
	python3 $(TOOLS)/test_mkdemo.py
	python3 $(TOOLS)/test_volinfo.py
	python3 $(TOOLS)/test_diskimg_verify.py
	python3 $(TOOLS)/test_diskimg_input.py
	python3 $(TOOLS)/test_dirscan.py
	python3 $(TOOLS)/test_blkview.py
	python3 $(TOOLS)/test_blkedit.py
	python3 $(TOOLS)/test_bootblk.py
	python3 $(TOOLS)/test_disk_packages.py
	python3 $(TOOLS)/test_release_notes.py
	python3 $(TOOLS)/test_file_viewers.py
	python3 $(TOOLS)/test_move.py
	python3 $(TOOLS)/test_move_alloc.py
	python3 $(TOOLS)/test_txtconv.py
	python3 $(TOOLS)/test_imgconv.py
	python3 $(TOOLS)/test_wipe.py
	python3 $(TOOLS)/test_music.py
	python3 $(TOOLS)/test_pt3.py
	python3 $(TOOLS)/test_pt3_conv.py
	python3 $(TOOLS)/test_pt3_volume.py
	python3 $(TOOLS)/test_sample_media.py
	python3 $(TOOLS)/test_dgrview.py
	python3 $(TOOLS)/test_disasm.py
	python3 $(TOOLS)/test_packfot.py
	python3 $(TOOLS)/test_paint816.py
	python3 $(TOOLS)/test_extasie.py
	python3 $(TOOLS)/test_intbasic.py
	python3 $(TOOLS)/test_find.py
	python3 $(TOOLS)/test_six_plugins.py

bench: disk
	$(MAKE) ARCH=enh benchfloppy
	python3 bench/run.py

# The third-party example overlay (sdk/), compiled OUTSIDE the tree with only
# src/a2fc_plugin.h: the proof that the ABI holds. Produces build/HELLO.PLG,
# to be put under A2FILE/. bench/plugin.py builds it and launches it in POM2.
example: $(BUILD)/HELLO.PLG
$(BUILD)/HELLO.PLG: sdk/hello.c sdk/plugin.cfg sdk/build.sh $(SRC)/a2fc_plugin.h | $(BUILD)
	sh sdk/build.sh sdk/hello.c HELLO

clean:
	rm -rf $(BUILD) $(DIST)
