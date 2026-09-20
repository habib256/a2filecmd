#!/usr/bin/env python3
"""Check the five published images against their matching builds."""
from pathlib import Path
import re

from po2dsk import to_dsk
from prodos_read import Image

ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = (ROOT / 'Makefile').read_text()
VERSION = re.search(r'^A2FC_VERSION\s*=\s*(\S+)', MAKEFILE, re.M)[1]
from distribution import RUNTIMES, inventories, image_name


def entries(image, block):
    return {e[1:1 + (e[0] & 15)].decode('ascii'): e for e in image.entries(block)}


def directory_blocks(image, block):
    count = 0
    while block:
        count += 1
        block = int.from_bytes(image.block(block)[2:4], 'little')
    return count


def check_config_room(image, directory, key, path):
    """Saving preferences on a bootable volume adds A2FILE.CFG, then
    A2FILE.TMP next to it (one block each); when A2FILE/ is full, ProDOS
    also extends the directory by a block, which it never gives back. A
    volume short of that saves once and then refuses every later save."""
    capacity = directory_blocks(image, key) * 13 - 1
    entries_needed = len(directory) + 2 - ('A2FILE.CFG' in directory)
    needed = 2 + (entries_needed > capacity)
    assert image.free_blocks() >= needed, (path, 'no room to save A2FILE.CFG twice',
                                           image.free_blocks(), needed)


def check_launch_version(program):
    marker = ('A2 FILE CMD ' + VERSION + ' - ').encode('ascii')
    assert marker in program, 'launcher version differs from release version ' + VERSION


def check_cpu(cpu):
    build = ROOT / ('build-6502' if cpu == '6502' else 'build')
    native = re.search(r'^PLUGINS = (.+)$', MAKEFILE, re.M)[1].split()
    expected = {name + '.PLG': (build / ('A2FILE.CODE.BIN.' + name)).read_bytes()
                for name in native}
    expected.update({p.stem.upper() + '.PLG': (build / (p.stem + '.PLG')).read_bytes()
                     for p in (ROOT / 'src/plugins').glob('*.c')})
    essential, complete = inventories()
    for role in (('140K', '800K', 'XL') if cpu == '6502' else ('65C02-enhanced-mouse-XL',)):
        path = ROOT / 'dist' / image_name(role)
        raw = path.read_bytes()
        xl = role.endswith('XL')
        blocks = 65535 if xl else 1600 if role == '800K' else 280
        if xl:
            assert len(raw) == 64 + blocks * 512 and raw[:4] == b'2IMG', path
            assert int.from_bytes(raw[24:28], 'little') == 64, path
            data = raw[64:]
        elif role == '140K':
            data = path.with_suffix('.po').read_bytes()
            assert raw == to_dsk(data), path
        else:
            data = raw
        assert len(data) == blocks * 512, path
        image = Image(data)
        volume = ('A2XL' + cpu) if xl else 'A28006502' if role == '800K' else 'A2FC6502'
        assert image.header()['name'] == volume, path
        root = entries(image, 2)
        key = int.from_bytes(root['A2FILE'][17:19], 'little')
        directory = entries(image, key)
        check_config_room(image, directory, key, path)
        plugins = {name for name in directory if name.endswith('.PLG')}
        required = essential if role == '140K' else complete
        assert plugins == {name + '.PLG' for name in required}, (path, plugins ^ {n + '.PLG' for n in required})
        assert 'EXTRAS.CAT' not in directory, (path, 'obsolete companion catalog')
        assert 'FORMAT.SYS' not in directory, path
        for name in plugins:
            entry = directory[name]
            assert entry[16] == 6 and int.from_bytes(entry[31:33], 'little') == 0x1B00, (path, name)
            assert image.read(entry) == expected[name], (path, name, 'wrong CPU or stale overlay')
        launcher = 'A2FILE.FLOPPY.SYS' if role == '140K' else 'A2FILE.SYSTEM.SYS'
        program = image.read(root['A2FILE.SYSTEM'])
        check_launch_version(program)
        assert program == (build / launcher).read_bytes(), path
        title = cpu + (' FLOPPY EDITION' if role == '140K' else ' COMPLETE EDITION')
        assert title.encode('ascii') in program, (path, 'wrong launch screen')
        assert image.read(directory['A2FILE.CODE']) == (build / 'A2FILE.CODE.BIN').read_bytes(), path
        assert image.read(root['PRODOS']) == (ROOT / 'data/PRODOS.SYS').read_bytes(), path
        for runtime in RUNTIMES:
            assert (runtime in root) == (role != '140K'), (path, runtime)
            if runtime in root:
                assert root[runtime][16] == 0xFF, (path, runtime)
                assert image.read(root[runtime]) == (ROOT / ('data/' + runtime + '.SYS')).read_bytes(), (path, runtime)
        assert ('DEMO' in root) == xl and ('IMGHGR' in root) == xl, path
        print('PASS %s: %d overlays, %d free blocks, matching build and disk layout' %
              (path.name, len(plugins), image.free_blocks()))


def check_mini():
    from build_mini_disk import from_template
    from mkmini33 import build
    path = ROOT / 'dist' / image_name('DOS3.3')
    expected = build(from_template((ROOT / 'data/dos33_boot.tmpl').read_bytes()),
                     (ROOT / 'build-mini/A2FC.MINI').read_bytes())
    assert path.read_bytes() == expected, (path, 'stale or malformed Mini')
    print('PASS %s: boot tracks and all files match this build' % path.name)


if __name__ == '__main__':
    for cpu in ('6502', '65C02'):
        check_cpu(cpu)
    check_mini()
