# A2 File Cmd -- two-panel ProDOS file manager, Apple IIe.
#
#   make            the launcher, resident and overlays, in build/ or build-6502/
#   make disk       140K essentials, 800K complete, Mini, XL 6502 and
#                   XL 65C02-enhanced. ARCH=enh builds only its XL.
#   make benchfloppy  build/A2FILECMD-full.po: a 65C02 floppy with the core
#                   overlay, for the benches only -- never shipped
#   make test       the tests outside the emulator (memory layout, volume)
#   make bench      one POM2 session (needs the emulator, see bench/README.md)
#   make qualify    every bench of bench/all.py, the release replay
#   make clean
#
# The program only just fits in the machine's memory: the link is checked
# every time by tools/check_layout.py, which catches the two overflows that
# ld65 lets through silently. See docs/MANUAL.md.

A2FC_VERSION = 0.9.3
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
IMG = A2FILECMD-PRODOS-140K
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
IMG = A2FILECMD-PRODOS-140K
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
# Benches at once in `make qualify`. One by default: several emulators at
# 200 000 cycles a second starve each other on one machine, and the benches
# that count wall-clock time (a nibble copy, an interrupted copy) then time
# out although nothing is wrong. BENCH_JOBS=3 is for iterating, not for
# qualifying a version.
BENCH_JOBS ?= 1
CFLAGS = -t $(TARGET) $(CLDEFS) -O -Oirs -Cl --codesize $(CODESIZE)

# __HIMEM__ = $BF00: just below the ProDOS global page. The C stack fits in
# 192 bytes -- the deepest point measured is 145 bytes, a tree copy
# (bench/memory.py); walk_tree stops descending 80 bytes above the floor.
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
PLUGINS = BATCH NAV CATALOG OPEN COPY FORMAT IMAGE TEXT HEX DELETE HELP EDIT RUN ATTR MENU DISKIMG IMGFS DOSGET UNSHRINK BASLIST COMPARE SEARCH BINARY2 AWP
# Essential 140K: file operations, editor, readers, format and verify.
# No catalog advertises missing tools; IMGFS also extracts mounted images.
# COMPARE provides sorting and panel comparison; MOVE handles marked moves.
PLUGINS_FLOPPY = BATCH NAV CATALOG OPEN COPY FORMAT HELP TEXT HEX DELETE RUN ATTR MENU IMGFS COMPARE EDIT
# The service-table overlays: src/plugins/NAME.c, each compiled and linked
# on its own like a third party's (sdk/plugin.cfg, no crt0, nothing of
# A2FILE.CODE), because the resident is full -- they reach the program only
# through struct A2fcApi. Lower-case source names, upper-case .PLG on disk.
# A header written `PLUGIN_MAGIC, OVERLAY_BIG,` (one line) is linked as a big
# overlay ($1B00-$3FFF); `PLUGIN_MAGIC, 0,` as a small one.
XPLUGINS = $(sort $(basename $(notdir $(wildcard $(SRC)/plugins/*.c))))
# The ones that also go on the floppy edition (tools/check_images.py keeps BOOT's free blocks).
XPLUGINS_FLOPPY = $(filter move verify,$(XPLUGINS))
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
XPLUGINS_SCRATCH = music bootblk find goto mdview wipe dgrview fixtypes
# These decode a picture into the graphics page, so they are big (the core
# sets the tags aside and rereads the panels) but their CODE must still stop
# before $2000: they are linked with the small window, which makes ld65
# enforce that boundary instead of leaving it to luck.
XPLUGINS_HGR = purple extasie arlequin macpaint shapes packfot paint816 fontview printshop lz4fh
# DUET stages its song at $2400 (7 KB, the largest known Electric Duet
# files are 5.5 KB): code and BSS are linked into $1B00-$23FF.
XPLG = $(patsubst %,$(BUILD)/%.PLG,$(XPLUGINS))
XPLG_FLOPPY = $(patsubst %,$(BUILD)/%.PLG,$(XPLUGINS_FLOPPY))
SYSTEM = $(BUILD)/A2FILE.SYSTEM.SYS
FLOPPY_SYSTEM = $(BUILD)/A2FILE.FLOPPY.SYS
PO     = $(DIST)/$(IMG)-$(A2FC_VERSION).po
DSK    = $(DIST)/$(IMG)-$(A2FC_VERSION).dsk
include config/packages.mk
CATALOG = $(BUILD)/EXTRAS.CAT

OBJS = $(BUILD)/crt0.o $(BUILD)/overlay.o $(BUILD)/unshrink.o $(VDRIVEOBJ) $(BUILD)/a2fc_mli.o $(BUILD)/chain.o \
       $(BUILD)/mb_probe.o $(BUILD)/memory_swap.o $(BUILD)/mli_safe.o $(MOUSEOBJ) $(BUILD)/format_diskii.o $(BUILD)/format_mli.o

.DELETE_ON_ERROR:

.PHONY: all disk benchpackages benchfloppy xplugins test bench qualify example clean pom2host
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

$(BUILD)/crt0_loader.o: $(SRC)/machine_check.inc

$(SYSTEM): $(BUILD)/launcher.o
$(FLOPPY_SYSTEM): $(BUILD)/launcher_floppy.o
$(SYSTEM) $(FLOPPY_SYSTEM): $(BUILD)/crt0_loader.o $(BUILD)/loader_mli.o Makefile | $(BUILD)
	$(CL) $(CFLAGS) --start-addr 0x2000 \
	  -Wl -D,__EXEHDR__=0 -Wl -D,__HIMEM__=$(HIMEM) -Wl -D,__FILETYPE__=0xFF \
	  -o $@ $(BUILD)/crt0_loader.o $(BUILD)/loader_mli.o \
	  $(BUILD)/$(if $(filter $(FLOPPY_SYSTEM),$@),launcher_floppy,launcher).o $(IOBUF)

$(CODE): $(SRC)/plugins/file_install.h $(SRC)/file_output.h $(SRC)/file_copy.h $(SRC)/tree_walk.h $(SRC)/display_types.h $(SRC)/launch.h $(SRC)/errors.h $(SRC)/media.h $(SRC)/viewer_ids.h $(SRC)/duet_probe.h $(SRC)/batch.h $(SRC)/config.h $(SRC)/format.c $(SRC)/a2fc.c $(SRC)/a2fc.cfg $(SRC)/a2fc_plugin.h $(SRC)/music.h $(SRC)/memory_swap.h $(BUILD)/display.o $(OBJS) Makefile | $(BUILD)
	$(CL) $(CFLAGS) -D 'A2FC_VERSION="$(A2FC_VERSION)"' -C $(SRC)/a2fc.cfg \
	  -Wl -D,__EXEHDR__=0 -Wl -D,__HIMEM__=$(HIMEM) -Wl -D,__STACKSIZE__=$(A2FC_STACK) -Wl -D,__BIN2SIZE__=$(BIN2SIZE) \
	  -Wl -m,$(BUILD)/a2fc.map -Wl -Ln,$(BUILD)/a2fc.lbl \
	  -o $@ $(BUILD)/crt0.o $(BUILD)/overlay.o $(BUILD)/unshrink.o $(VDRIVEOBJ) $(SRC)/a2fc.c $(SRC)/format.c $(BUILD)/format_diskii.o $(BUILD)/format_mli.o $(BUILD)/a2fc_mli.o \
	  $(BUILD)/display.o $(BUILD)/chain.o $(BUILD)/mb_probe.o $(BUILD)/memory_swap.o $(BUILD)/mli_safe.o \
	  $(MOUSEOBJ) $(IOBUF)
	@python3 $(TOOLS)/check_layout.py --lbl $(BUILD)/a2fc.lbl --bin $@ $(LAYOUT_BIG)

# -- The service-table overlays ---------------------------------------------
$(BUILD)/dosput.PLG: $(SRC)/plugins/doswrite.c

$(BUILD)/%.PLG: $(SRC)/plugins/%.c $(wildcard $(SRC)/plugins/*.h) $(wildcard $(SRC)/plugins/*.s) $(wildcard $(SRC)/plugins/*.inc) $(wildcard $(SRC)/plugins/pt3lib/*) $(SRC)/a2fc_plugin.h sdk/plugin.cfg sdk/find.cfg sdk/pt3.cfg sdk/nibcopy.cfg Makefile | $(BUILD)
	$(CC65BIN)cc65 -t $(TARGET) $(CCDEFS) -O -Oirs -Cl --codesize $(CODESIZE) -o $(BUILD)/$*.s $<
	$(CC65BIN)ca65 -t $(TARGET) -o $(BUILD)/$*.o $(BUILD)/$*.s
	@helper=; if [ -f $(SRC)/plugins/$*.s ]; then $(AS) -t $(TARGET) -o $(BUILD)/$*_svc.o $(SRC)/plugins/$*.s || exit; helper=$(BUILD)/$*_svc.o; fi; \
	  if grep -qE 'PLUGIN_MAGIC, *OVERLAY_BIG' $<; then big=1; else big=0; fi; \
	  $(CC65BIN)ld65 -C $(if $(filter find,$*),sdk/find.cfg,$(if $(filter pt3,$*),sdk/pt3.cfg,$(if $(filter nibcopy,$*),sdk/nibcopy.cfg,sdk/plugin.cfg))) -D __OVLSIZE__=$$( if [ $$big = 1 ]; then echo $(if $(filter $*,$(XPLUGINS_HGR)),0x0500,$(if $(filter $*,$(XPLUGINS_SCRATCH)),$(if $(filter find,$*),0x1600,0x1500),$(if $(filter volinfo blkview blkedit fixit repair,$*),0x249E,$(if $(filter duet,$*),0x0900,0x2500)))); elif [ "$*" = verify ]; then echo 0x04C2; else echo 0x0500; fi ) -m $(BUILD)/$*.map -Ln $(BUILD)/$*.lbl -o $@ $(BUILD)/$*.o $$helper $(CC65LIB) && \
	  limit=$$( [ $$big = 1 ] && echo $(if $(filter $*,$(XPLUGINS_HGR)),1280,$(if $(filter duet,$*),2304,9472)) || echo 1280 ) && \
	  { test $$(wc -c < $@) -le $$limit || { echo "$@: $$(wc -c < $@) bytes, more than its $$limit-byte window"; rm -f $@; exit 1; }; } && \
	  echo "$@: $$(wc -c < $@) bytes ($$( [ $$big = 1 ] && echo big || echo small ) overlay)"
xplugins: $(XPLG)
all: xplugins

# -- Published disks --------------------------------------------------------
# 140K is self-contained with essential tools; 800K has all tools.
# XL contains the same complete toolset plus the demo corpus.
STAGE = $(BUILD)/vol
HDV = $(BUILD)/A2FILECMD-XL.hdv
TWOMG = $(DIST)/A2FILECMD-PRODOS-XL-$(if $(filter 65C02,$(CPU)),65C02-enhanced-,)$(A2FC_VERSION).2mg
PO800 = $(DIST)/A2FILECMD-PRODOS-800K-$(A2FC_VERSION).po
FULLPO = $(BUILD)/A2FILECMD-full.po
STAGE_DEPS = $(SYSTEM) $(CODE) $(DATA)/A2FILE.HELP.TXT $(DATA)/RECOVER.TXT $(DATA)/PRODOS.SYS \
       $(DATA)/prodos_boot.tmpl $(TOOLS)/mkvolume.py

ifdef BOTH_EDITIONS
disk:
	$(MAKE) ARCH=6502 disk
	$(MAKE) ARCH=enh disk
else ifeq ($(ARCH),6502)
disk: $(PO) $(DSK) $(PO800) $(TWOMG) mini-disk
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
$(PO): $(FLOPPY_SYSTEM) $(STAGE_DEPS) $(XPLG_FLOPPY) $(TOOLS)/po2dsk.py | $(DIST)
	$(call stage,$(PLUGINS_FLOPPY),$(XPLUGINS_FLOPPY))
	cp $(FLOPPY_SYSTEM) $(STAGE)/A2FILE.SYSTEM.SYS
	cp $(DATA)/RECOVER.TXT $(STAGE)/
	python3 $(TOOLS)/mkvolume.py $(STAGE) $(PO) --volume $(VOLUME) \
	  --a2fc-layout --boot $(DATA)/prodos_boot.tmpl --blocks 280
	@python3 $(TOOLS)/prodos_read.py $(PO) | head -1
	@echo "==> $(PO): the boot floppy ($(CPU))"

$(DSK): $(PO) $(TOOLS)/po2dsk.py
	python3 $(TOOLS)/po2dsk.py $< $@

endif

# The catalog uses the same link as its matching program images.
$(CATALOG): $(CODE) $(XPLG) $(TOOLS)/mkoverlay_catalog.py $(TOOLS)/disk_packages.py config/packages.mk Makefile
	python3 $(TOOLS)/mkoverlay_catalog.py $@ $(BUILD) --cpu $(CPU) --native $(PLUGINS) --plugins $(XPLUGINS)

ifeq ($(ARCH),6502)
# Historical category fixtures, used only by the disk-swap regression benches.
benchpackages: $(CATALOG) $(XPLG)
	@mkdir -p $(BUILD)/legacy
	@for role in $(PACKAGE_ROLES); do python3 $(TOOLS)/mkpackage.py $(BUILD) $(BUILD)/legacy/$$role.po --role $$role --cpu $(CPU) || exit; done

$(PO800): STAGE = $(BUILD)/vol800
$(PO800): $(STAGE_DEPS) $(XPLG) $(DATA)/BASIC.SYSTEM.SYS $(DATA)/INTBASIC.SYSTEM.SYS | $(DIST)
	$(call stage,$(PLUGINS),$(XPLUGINS))
	cp $(DATA)/BASIC.SYSTEM.SYS $(DATA)/INTBASIC.SYSTEM.SYS $(STAGE)/
	cp $(DATA)/RECOVER.TXT $(STAGE)/
	python3 $(TOOLS)/mkvolume.py $(STAGE) $@ --volume A28006502 --a2fc-layout --boot $(DATA)/prodos_boot.tmpl --blocks 1600
endif

# XL: the complete edition for the selected CPU.
$(TWOMG): $(STAGE_DEPS) $(XPLG) $(DATA)/BASIC.SYSTEM.SYS $(DATA)/INTBASIC.SYSTEM.SYS $(DATA)/README.TXT \
       $(TOOLS)/mkdemo.py $(TOOLS)/po22mg.py \
       $(TOOLS)/mkshk.py $(TOOLS)/mkbny.py $(TOOLS)/mkdos33.py $(wildcard $(DATA)/IMGHGR/*) \
       $(shell find $(DATA)/CP2 -type f) | $(DIST)
	$(call stage,$(PLUGINS),$(XPLUGINS))
	cp $(DATA)/BASIC.SYSTEM.SYS $(DATA)/INTBASIC.SYSTEM.SYS $(STAGE)/
	mkdir -p $(STAGE)/DEMO
	cp $(DATA)/README.TXT $(STAGE)/DEMO/README.TXT
	python3 $(TOOLS)/mkdemo.py $(STAGE)/DEMO
	cp -R $(DATA)/CP2 $(STAGE)/DEMO/CIDERPRESS
	cp -R $(DATA)/IMGHGR $(STAGE)/IMGHGR
	cp $(DATA)/RECOVER.TXT $(STAGE)/
	python3 $(TOOLS)/mkvolume.py $(STAGE) $(HDV) --volume $(VOLUME_HD) \
	  --a2fc-layout --boot $(DATA)/prodos_boot.tmpl --blocks 65535
	python3 $(TOOLS)/po22mg.py $(HDV) $(TWOMG)
	@rm -rf $(STAGE)/DEMO $(STAGE)/IMGHGR   # the stage keeps the program alone (bench/plugin.py picks it up)
	@echo "==> $(TWOMG): the complete edition ($(ARCH))"

# A 65C02 floppy with the core overlays and BASIC.SYSTEM, for the benches that
# exercise the editor, the pictures and the readers from a
# floppy (bench/run.py and friends, A2FC_IMG=A2FILECMD-full). Never shipped.
benchfloppy: $(FULLPO)
$(FULLPO): STAGE = $(BUILD)/benchvol
# Archive benches build their own disposable boot fixtures (archive_support.py).
# Both fixtures use the compact launcher and omit SEARCH to fit 140K.
# Its UI bench adds SEARCH to a disposable fixture; both XLs keep it.
$(FULLPO): $(STAGE_DEPS) $(FLOPPY_SYSTEM) $(DATA)/BASIC.SYSTEM.SYS
	$(call stage,$(filter-out UNSHRINK BINARY2 AWP SEARCH,$(PLUGINS)),)
	cp $(FLOPPY_SYSTEM) $(STAGE)/A2FILE.SYSTEM.SYS
	cp $(DATA)/BASIC.SYSTEM.SYS $(STAGE)/
	python3 $(TOOLS)/mkvolume.py $(STAGE) $(FULLPO) --volume A2FILECMD \
	  --a2fc-layout --boot $(DATA)/prodos_boot.tmpl --blocks 280
	@echo "==> $(FULLPO): the bench floppy, core overlays ($(ARCH))"

test: test-mini
	python3 $(TOOLS)/test_loader_prefix.py
	python3 $(TOOLS)/test_machine_check.py
	python3 $(TOOLS)/test_chain.py
	python3 $(TOOLS)/test_vsdrive.py
	python3 $(TOOLS)/test_launch.py
	python3 $(TOOLS)/test_errors.py
	python3 $(TOOLS)/test_display.py
	python3 $(TOOLS)/test_config.py
	python3 $(TOOLS)/test_config_native.py
	python3 $(TOOLS)/test_abi_freeze.py
	python3 $(TOOLS)/test_batch.py
	python3 $(TOOLS)/test_ui.py
	python3 $(TOOLS)/test_media.py
	python3 $(TOOLS)/test_media_transition.py
	python3 $(TOOLS)/test_raw_transition.py
	python3 $(TOOLS)/test_overlay_load.py
	python3 $(TOOLS)/test_catalog_overlay.py
	python3 $(TOOLS)/test_tree_walk.py
	python3 $(TOOLS)/test_goto_safety.py
	python3 $(TOOLS)/test_file_safety.py
	python3 $(TOOLS)/test_binary2_safety.py
	python3 $(TOOLS)/test_compare_search.py
	python3 $(TOOLS)/test_panel_sort.py
	python3 $(TOOLS)/test_unshrink_safety.py
	python3 $(TOOLS)/test_unshrink_core.py
	python3 $(TOOLS)/lzc_ref.py --selftest
	python3 $(TOOLS)/test_imgfs_safety.py
	python3 $(TOOLS)/test_dos_extract.py
	python3 $(TOOLS)/test_format_repair.py
	python3 $(TOOLS)/test_doswrite.py
	python3 $(TOOLS)/test_dos33w.py
	python3 $(TOOLS)/test_dosrepl.py
	python3 $(TOOLS)/test_imgput.py
	python3 $(TOOLS)/pascal_ref.py --selftest
	python3 $(TOOLS)/test_pascal.py
	python3 $(TOOLS)/test_pascalw.py
	python3 $(TOOLS)/cpm_ref.py --selftest
	python3 $(TOOLS)/test_cpm.py
	python3 $(TOOLS)/test_cpmw.py
	python3 $(TOOLS)/test_dosimage.py
	python3 $(TOOLS)/test_file_create.py
	python3 $(TOOLS)/test_file_output.py
	python3 $(TOOLS)/test_file_install.py
	python3 $(TOOLS)/test_core_dirscan.py
	python3 $(TOOLS)/test_tree_stack.py
	python3 $(TOOLS)/test_catalog_safety.py
	python3 $(TOOLS)/test_imgconv_safety.py
	python3 $(TOOLS)/test_check_layout.py
	python3 $(TOOLS)/test_bench_inventory.py
	python3 $(TOOLS)/test_mkvolume.py
	python3 $(TOOLS)/test_prodos_read.py
	python3 $(TOOLS)/test_mkdemo.py
	python3 $(TOOLS)/test_volinfo.py
	python3 $(TOOLS)/test_prodos_check.py
	python3 $(TOOLS)/test_fixit.py
	python3 $(TOOLS)/test_repair.py
	python3 $(TOOLS)/test_fixit_bits.py
	python3 $(TOOLS)/test_strobe.py
	python3 $(TOOLS)/test_flag_reuse.py
	python3 $(TOOLS)/test_cc65_traps.py
	python3 $(TOOLS)/check_warnings.py
	python3 $(TOOLS)/test_hw_media.py
	python3 $(TOOLS)/fuzz_prodos.py --count 150 --seed 1
	python3 $(TOOLS)/test_fuzz_prodos.py
	python3 $(TOOLS)/fuzz_archives.py --count 60 --seed 1
	python3 $(TOOLS)/test_fuzz_archives.py
	python3 $(TOOLS)/test_diskimg_verify.py
	python3 $(TOOLS)/test_diskimg_input.py
	python3 $(TOOLS)/test_diskimg_output.py
	python3 $(TOOLS)/test_diskimg_scan.py
	python3 $(TOOLS)/test_delete_confirm.py
	python3 $(TOOLS)/test_dirscan.py
	python3 $(TOOLS)/test_blkview.py
	python3 $(TOOLS)/test_blkedit.py
	python3 $(TOOLS)/test_bootblk.py
	python3 $(TOOLS)/test_nibcopy.py
	python3 $(TOOLS)/test_disk_packages.py
	python3 $(TOOLS)/test_distribution.py
	python3 $(TOOLS)/test_release_notes.py
	python3 $(TOOLS)/test_file_viewers.py
	python3 $(TOOLS)/test_move.py
	python3 $(TOOLS)/test_move_alloc.py
	python3 $(TOOLS)/test_txtconv.py
	python3 $(TOOLS)/test_imgconv.py
	python3 $(TOOLS)/test_wipe.py
	python3 $(TOOLS)/test_music.py
	python3 $(TOOLS)/test_duet.py
	python3 $(TOOLS)/test_pt3.py
	python3 $(TOOLS)/test_pt3_frequency.py
	python3 $(TOOLS)/test_pt3_dual.py
	python3 $(TOOLS)/test_pt3_cache.py
	python3 $(TOOLS)/test_pt3_clock.py
	python3 $(TOOLS)/test_pt3_conv.py
	python3 $(TOOLS)/test_pt3_volume.py
	python3 $(TOOLS)/test_sample_media.py
	python3 $(TOOLS)/test_dgrview.py
	python3 $(TOOLS)/test_disasm.py
	python3 $(TOOLS)/test_packfot.py
	python3 $(TOOLS)/test_purple.py
	python3 $(TOOLS)/test_paint816.py
	python3 $(TOOLS)/test_extasie.py
	python3 $(TOOLS)/arlequin_ref.py --selftest
	python3 $(TOOLS)/test_arlequin.py
	python3 $(TOOLS)/macpaint_ref.py --selftest
	python3 $(TOOLS)/test_macpaint.py
	python3 $(TOOLS)/awdata_ref.py --selftest
	python3 $(TOOLS)/test_awdata.py
	python3 $(TOOLS)/dc42.py --selftest
	python3 $(TOOLS)/test_dc42.py
	python3 $(TOOLS)/unwrap_ref.py --selftest
	python3 $(TOOLS)/test_unwrap.py
	python3 $(TOOLS)/binscii_ref.py --selftest
	python3 $(TOOLS)/test_sciibin.py
	python3 $(TOOLS)/shapes_ref.py --selftest
	python3 $(TOOLS)/test_shapes.py
	python3 $(TOOLS)/test_fontview.py
	python3 $(TOOLS)/busbasic_ref.py --selftest
	python3 $(TOOLS)/squeeze_ref.py --selftest
	python3 $(TOOLS)/test_unsq.py
	python3 $(TOOLS)/test_intbasic.py
	python3 $(TOOLS)/test_find.py
	python3 $(TOOLS)/test_mdview.py
	python3 $(TOOLS)/test_diskcmp.py
	python3 $(TOOLS)/test_six_plugins.py

# The headless POM2 test host the benches drive, built from its source kept
# here (bench/pom2_playtest/) against the POM2 emulator library (POM2_ROOT,
# default ~/src/pom2). No other repository is involved.
pom2host:
	sh bench/pom2_playtest/build.sh

bench: disk
	$(MAKE) ARCH=enh benchfloppy
	$(MAKE) ARCH=6502 benchpackages
	A2FC_IMG=A2FILECMD-full python3 bench/run.py

# The whole bench table (bench/all.py), which is what qualifies a release:
# every bench with the machine and the image it needs, one log per step, and
# a missing fixture counted as a failure instead of a silent gap.
qualify: disk
	$(MAKE) ARCH=enh benchfloppy
	$(MAKE) ARCH=6502 benchfloppy
	$(MAKE) ARCH=6502 xplugins benchpackages
	python3 bench/all.py --setup --strict --jobs $(BENCH_JOBS) --out $(BUILD)/bench

# The third-party example overlay (sdk/), compiled OUTSIDE the tree with only
# src/a2fc_plugin.h: the proof that the ABI holds. Produces build/HELLO.PLG,
# to be put under A2FILE/. bench/plugin.py builds it and launches it in POM2.
example: $(BUILD)/HELLO.PLG
$(BUILD)/HELLO.PLG: sdk/hello.c sdk/plugin.cfg sdk/build.sh $(SRC)/a2fc_plugin.h | $(BUILD)
	sh sdk/build.sh sdk/hello.c HELLO

clean:
	rm -rf $(BUILD) $(DIST)

# Standalone Apple II+ / 48K / DOS 3.3 edition, pure 6502 assembly.
# No ProDOS, no cc65 runtime, no software stack: see src/mini/mini-asm.cfg.
MINI_BUILD = build-mini
MINI_AS ?= ca65
MINI_LD ?= ld65
MINI_MASTER ?=
MINI_DISK ?= $(DIST)/A2FILECMD-DOS3.3-$(A2FC_VERSION).dsk
# start.s must come first: its STARTUP segment lands on the load address.
MINI_MODULES = lowstart start rwts screen catalog copy keyboard ui data scratch delete edit fileops format
MINI_OBJS = $(addprefix $(MINI_BUILD)/,$(addsuffix .o,$(MINI_MODULES)))
.PHONY: mini mini-disk test-mini
mini: $(MINI_BUILD)/A2FC.MINI
$(MINI_BUILD):
	mkdir -p $@
# The Mini splash prints the release number from one place: version.inc is
# rewritten only when A2FC_VERSION changes, so an unchanged build stays
# byte-identical and does not reassemble every module.
$(MINI_BUILD)/version.inc: Makefile | $(MINI_BUILD)
	@printf '        .define VERSION_STR "V$(A2FC_VERSION)"\n' > $@.tmp; \
	  cmp -s $@.tmp $@ && rm -f $@.tmp || mv $@.tmp $@
$(MINI_BUILD)/%.o: $(SRC)/mini/%.s $(SRC)/mini/mini.inc $(MINI_BUILD)/version.inc | $(MINI_BUILD)
	$(MINI_AS) --cpu 6502 -I $(SRC)/mini -I $(MINI_BUILD) -o $@ $<
$(MINI_BUILD)/A2FC.MINI: $(MINI_OBJS) $(SRC)/mini/mini-asm.cfg
	$(MINI_LD) -C $(SRC)/mini/mini-asm.cfg -m $(MINI_BUILD)/mini.map \
		-Ln $(MINI_BUILD)/mini.lbl -o $@ $(MINI_OBJS)
	python3 $(TOOLS)/check_mini_layout.py $(MINI_BUILD)/mini.map
mini-disk: $(MINI_DISK)
$(MINI_DISK): $(MINI_BUILD)/A2FC.MINI $(DATA)/dos33_boot.tmpl $(TOOLS)/mkmini33.py $(TOOLS)/build_mini_disk.py $(DATA)/IMGHGR/TIGER\#062000 | $(DIST)
	python3 $(TOOLS)/build_mini_disk.py $(if $(MINI_MASTER),--master "$(MINI_MASTER)",--boot-template $(DATA)/dos33_boot.tmpl) --binary $(MINI_BUILD)/A2FC.MINI --output "$@"
test-mini: mini
	python3 $(TOOLS)/test_mini33.py
	python3 $(TOOLS)/test_mini33_write.py
	python3 $(TOOLS)/test_mini33_format.py
