#!/usr/bin/env python3
"""The 1.0 freeze: what an overlay built once, or a saved A2FILE.CFG, relies on.

A third-party .PLG knows the program only through src/a2fc_plugin.h. From 1.0
on, the structures it shares with the core do not change, the service table
only grows at its end, and the constants that place an overlay in memory stay
put. The settings file keeps its text layout. A change here breaks every
overlay compiled against an earlier header, or loses a user's settings: it
must be a deliberate new format, not a side effect.

Sizes use cc65's 6502 model: char 1, int and pointers 2, long 4, no padding.
"""

import re, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = (ROOT / 'src/a2fc_plugin.h').read_text()

FROZEN = {
    'Entry': ['char name[NAME_LEN]', 'unsigned char type', 'unsigned char access',
              'unsigned int aux', 'unsigned int blocks', 'unsigned long size',
              'unsigned int mdate'],
    'Panel': ['char path[PATH_LEN]', 'unsigned char count', 'unsigned char cursor',
              'unsigned char top', 'unsigned char more', 'unsigned int first',
              'unsigned int free_blocks', 'unsigned int total_blocks', 'struct Entry* e',
              'unsigned char tags[(MAX_ENTRIES + 7) / 8]', 'unsigned char fs',
              'unsigned char img_len', 'unsigned int dir_key'],
    'DirEntry': ['char name[NAME_LEN]', 'unsigned char type', 'unsigned char access',
                 'unsigned int aux', 'unsigned int blocks', 'unsigned int mdate',
                 'unsigned long size', 'unsigned int key'],
    'Overlay': ['unsigned int signature', 'unsigned char flags', 'fn entry',
                'unsigned char reserved[3]', 'char desc[1]'],
}

# The service table of API v5, in order. New services go after the last one.
API_V5 = ['version', 'arg', 'panels', 'active', 'full', 'other_full', 'input', 'copy_buf',
          'dir_entry', 'message', 'confirm', 'prompt', 'progress_bar', 'keys_bar',
          'bar_begin', 'draw_all', 'read_panel', 'report_error', 'wait_key', 'build_full',
          'dir_open', 'dir_next', 'dir_close', 'mli', 'fopen', 'fread', 'fwrite', 'fclose',
          'fseek', 'remove', 'cprintf', 'sprintf', 'cputs', 'cputc', 'gotoxy', 'revers',
          'cclearxy', 'clrscr', 'cgetc', 'memcpy', 'memset', 'strcpy', 'strcmp', 'strlen',
          'filetype', 'auxtype', 'reselect', 'note', 'selected', 'cfg_path', 'ram_format',
          'media_key', 'media_wait', 'music_info']

CONSTANTS = {
    'MEDIA_PLUGIN_MAGIC': 0xA2FD, 'PLUGIN_MAGIC': 0xA2FC, 'OVERLAY_AUDIO': 0x04,
    'OVERLAY_AUX': 0x02, 'OVERLAY_BIG': 0x01, 'OVERLAY_SMALL': 0x0500,
    'OVERLAY_LARGE': 0x2500, 'MAX_ENTRIES': 140, 'PATH_LEN': 64, 'NAME_LEN': 17,
    'ROWS': 18, 'FS_PRODOS': 0, 'FS_IMG': 1, 'FS_DOS33': 2,
}


def body(name):
    m = re.search(r'struct %s \{(.*?)\n\};' % name, HEADER, re.S)
    assert m, name
    text = re.sub(r'/\*.*?\*/', '', m.group(1), flags=re.S)
    return [' '.join(d.split()) for d in text.split(';') if d.strip()]


def fields(name):
    out = []
    for decl in body(name):
        if '(*' in decl:                     # a function pointer
            out.append('fn ' + re.search(r'\(\*\s*(\w+)\)', decl).group(1))
            continue
        if ',' in decl:                      # "unsigned char count, cursor, top, more"
            first = decl.split(',')[0]
            kind = first.rsplit(' ', 1)[0]
            out.append(first)
            out += ['%s %s' % (kind, n.strip()) for n in decl.split(',')[1:]]
        else:
            out.append(decl)
    return out


def size(decl, n=None):
    consts = dict(CONSTANTS)
    kind = decl.split('[')[0]
    count = 1
    for dim in re.findall(r'\[([^\]]+)\]', decl):
        count *= eval(dim.replace('/', '//'), {}, consts)
    if kind.startswith('fn') or '*' in kind: unit = 2
    elif kind.startswith('unsigned long'): unit = 4
    elif kind.startswith('unsigned int'): unit = 2
    elif kind.startswith('struct'): raise AssertionError(decl)
    else: unit = 1
    return unit * count


class AbiFreeze(unittest.TestCase):
    def test_shared_structures_are_frozen(self):
        for name, frozen in FROZEN.items():
            self.assertEqual(fields(name), frozen, name)

    def test_layouts_match_the_asm_and_the_comments(self):
        self.assertEqual(sum(size(f) for f in FROZEN['Entry']), 29)
        offset, at = 0, {}
        for f in FROZEN['Panel']:
            at[re.split(r'[ *]', f.split('[')[0])[-1]] = offset
            offset += size(f)
        # panel_hash (a2fc_mli.s) and the header comments rely on these
        self.assertEqual((at['path'], at['count'], at['cursor'], at['top'], at['more'],
                          at['first'], at['e']), (0, 64, 65, 66, 67, 68, 74))
        self.assertEqual(sum(size(f) for f in FROZEN['DirEntry']), 31)
        self.assertEqual(sum(size(f) for f in FROZEN['Overlay']), 9)   # desc starts at +8

    def test_service_table_only_grows_at_its_end(self):
        names = []
        for f in fields('A2fcApi'):
            names.append(f[3:] if f.startswith('fn ') else re.split(r'[ *]', f)[-1])
        self.assertEqual(names[:len(API_V5)], API_V5)
        version = int(re.search(r'#define A2FC_API_VERSION (\d+)', HEADER).group(1))
        self.assertGreaterEqual(version, 5)
        if len(names) > len(API_V5):
            self.assertGreater(version, 5, 'new services need a new api->version')

    def test_constants_are_frozen(self):
        for name, value in CONSTANTS.items():
            if name.startswith('FS_'):
                continue
            m = re.search(r'#define %s\s+(\S+)' % name, HEADER)
            self.assertIsNotNone(m, name)
            self.assertEqual(int(m.group(1), 0), value, name)
        self.assertIn('enum { FS_PRODOS, FS_IMG, FS_DOS33 };', HEADER)
        self.assertIn('#define OVERLAY_WINDOW ((unsigned char*)0x1B00)', HEADER)
        self.assertIn('#define ENTRY_SNAPSHOT ((struct Entry*)0x3000)', HEADER)

    def test_settings_file_layout_is_frozen(self):
        config = (ROOT / 'src/config.h').read_text()
        self.assertIn(r'static const char cfg_format[] = "%s\r%s\rS%uA%u\r";', config)
        for name in ('A2FILE.CFG', 'A2FILE.TMP', 'A2FILE.BAK'):
            self.assertIn('"%s"' % name, config)


if __name__ == '__main__':
    unittest.main()
