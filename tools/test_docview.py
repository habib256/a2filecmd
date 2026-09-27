"""Page DOCVIEW's actual renderer over Epistole, Papyrus and HomeWord files.

The screen is modelled as rows 0-23 with an inverse flag per cell; the
renderer may write rows 1-21 only (row 22 is the status line). Every word
of a document must show up, in order, on exactly one page; commands and
codes never show; the ISO 646-FR national characters are shown as the
plain letter, or as stored with A. Real documents from the Epistole and
Papyrus disks (~/.cache/a2fc/epistole, ~/.cache/a2fc/papyrus) are paged
when present; the fixtures here are written from their observed syntax.
"""
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX, ROOT

HARNESS = PREFIX + r"""
#include "src/plugins/docview.c"
static FILE* host;
static unsigned char hx, hy, bad, hrev;
static char screen[24][81];
static char inverse[24][81];
static size_t rd_(void* p, size_t z, size_t n, FILE* f) { return fread(p, z, n, host); }
static int seek__(FILE* f, long off, int whence) { return fseek(host, off, whence); }
static void xy_(unsigned char x, unsigned char y) { hx = x; hy = y; }
static void putc__(char c)
{
    if (hy < ROW1 || hy > LASTROW || hx >= 80) bad = 1;   /* off the text area: never seen */
    if (hy < 24 && hx < 80) { screen[hy][hx] = c; inverse[hy][hx] = hrev ? '#' : ' '; }
    ++hx;
}
static unsigned char rev_(unsigned char r) { unsigned char o = hrev; hrev = r; return o; }
static void* mset(void* p, int c, size_t n) { return memset(p, c, n); }
int main(int argc, char** argv)
{
    static struct Entry sel;
    struct Start st;
    int page, r;
    host = fopen(argv[1], "rb");
    fseek(host, 0, SEEK_END); sel.size = ftell(host); rewind(host);
    a.fread = rd_; a.fseek = seek__; a.gotoxy = xy_; a.cputc = putc__; a.revers = rev_;
    a.memset = mset; a.memcpy = memcpy; a.selected = &sel;
    raw = argc > 2;
    vf = host; vbase = 0; vlen = vpos = 0;
    sniff();
    first_page();
    st = *STARTS;
    for (page = 0; page < 300; ++page) {
        memset(screen, 0, sizeof screen); memset(inverse, 0, sizeof inverse); bad = 0;
        render_page(&st);
        printf("PAGE %d %u %u %u\n", page, done, bad, hrev);
        for (r = ROW1; r <= LASTROW; ++r) {
            for (hx = 0; hx < 80; ++hx) if (!screen[r][hx]) { screen[r][hx] = ' '; inverse[r][hx] = ' '; }
            screen[r][80] = inverse[r][80] = 0;
            printf("|%s\n~%s\n", screen[r], inverse[r]);
        }
        if (done) break;
        st = next;
    }
    return 0;
}
"""
EPI = Path(os.environ.get('A2FC_EPISTOLE', Path.home() / '.cache/a2fc/epistole'))
PAP = Path(os.environ.get('A2FC_PAPYRUS', Path.home() / '.cache/a2fc/papyrus'))


class Docview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='docview-')
        cls.p = Path(cls.tmp.name)
        (cls.p / 'test.c').write_text(HARNESS)
        cls.exe = cls.p / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(cls.p / 'test.c'), '-o', str(cls.exe)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def pages(self, data, raw=False):
        f = self.p / 'in.txt'
        f.write_bytes(data)
        out = subprocess.check_output([str(self.exe), str(f)] + (['raw'] if raw else []),
                                      text=True, timeout=10, errors='replace')
        pages = []
        for line in out.splitlines():
            if line.startswith('PAGE '):
                _, _, done, bad, rev = line.split()
                pages.append({'done': int(done), 'bad': int(bad), 'rev': int(rev), 'rows': [], 'inv': []})
            elif line.startswith('|'):
                pages[-1]['rows'].append(line[1:])
            else:
                pages[-1]['inv'].append(line[1:])
        return pages

    def words(self, pages):
        return ' '.join(r for pg in pages for r in pg['rows']).split()

    def check_clean(self, pages):
        for pg in pages:
            self.assertEqual(pg['bad'], 0, 'a row written outside rows 1-21')
            self.assertEqual(pg['rev'], 0, 'inverse video left on')
        self.assertEqual(pages[-1]['done'], 1)

    def test_epistole_commands_margins_variables_accents(self):
        doc = (b'_MG10_MD40_JD\r\r_MI20#NOM]\r_MI0\r'
               b'Ceci est une lettre type : vous d{sirez rentrer vous m{me les variables, '
               b'apr}s le dernier Return, @ la fa\\on de e^tre #NOM] et n[ 2.\r'
               b'_CE TITRE\rSUITE\r_PC\rFIN _IGgras_SG normal\r'
               b'#:X=12]#:?X+1]#*M1=]\r')
        pages = self.pages(doc)
        self.check_clean(pages)
        rows = [r for pg in pages for r in pg['rows']]
        inv = [r for pg in pages for r in pg['inv']]
        text = '\n'.join(rows)
        for command in ('_MG', '_MD', '_JD', '_MI', '_CE', '_PC', '_IG', '_SG', '#', ']'):
            self.assertNotIn(command, text)
        self.assertEqual(rows[2].index('NOM'), 30)                 # margin 10 + indent 20
        self.assertEqual(inv[2][30:33], '###')
        body = [r for r in rows if r.strip() and r.index(r.strip()[0]) == 10]
        self.assertTrue(body and all(len(r.rstrip()) <= 40 for r in body), 'the right margin')
        flat = ' '.join(text.split())
        self.assertIn('vous desirez rentrer vous meme les variables, apres le dernier Return, '
                      'a la facon de etre NOM et no 2.', flat)
        titre = next(r for r in rows if 'TITRE' in r)
        suite = next(r for r in rows if 'SUITE' in r)
        fin = next(r for r in rows if 'FIN' in r)
        self.assertGreater(titre.index('TITRE'), 10); self.assertGreater(suite.index('SUITE'), 10)
        self.assertEqual(fin.index('FIN'), 10, '_PC ends the centring')
        g = rows.index(fin)
        self.assertEqual(inv[g][fin.index('gras'):fin.index('gras') + 4], '####')
        self.assertNotIn('#', inv[g][fin.index('normal'):])
        calc = next(r for r in rows if 'X+1' in r)
        self.assertEqual(calc.split(), ['X+1M1'], 'an assignment prints nothing')
        raw = self.pages(doc, raw=True)
        self.assertIn('d{sirez', '\n'.join(r for pg in raw for r in pg['rows']))

    def test_papyrus_codes_and_accents(self):
        hi = lambda t: bytes(c | 0x80 for c in t)
        doc = (b'\xff\x0d\x07\x05\xff\xff\x06\xff' + hi(b'LE TITRE') + b'\x8d' + hi(b'Suite du texte') +
               b'\x8d' + hi(b'M') + b'\x19' + hi(b'me le pl') + b'\x1b' + hi(b't b{ton @ Paris.') + b'\x8d' +
               b'\xff\x05\xff' + hi(b'Page deux.') + b'\x8d')
        pages = self.pages(doc)
        self.check_clean(pages)
        rows = [r.rstrip() for pg in pages for r in pg['rows']]
        titre = next(r for r in rows if 'LE TITRE' in r)
        self.assertEqual(titre.index('LE TITRE'), (79 - 8) // 2, 'centred')
        self.assertEqual(next(r for r in rows if 'Suite' in r).index('Suite'), 0, 'one line only')
        self.assertIn('Meme le plot beton a Paris.', rows)
        rule = rows.index('Page deux.') - 1
        self.assertEqual(set(rows[rule]), {'-'}, 'a page break shows as a rule')

    def test_every_word_once_across_pages(self):
        words = ['mot%d' % i for i in range(1500)]
        paras, i = [], 0
        while i < len(words):
            n = (i * 7) % 90 + 1
            paras.append(' '.join(words[i:i + n])); i += n
        doc = b'_MG5_MD60\r' + b'\r'.join(p.encode() for p in paras) + b'\r'
        pages = self.pages(doc)
        self.check_clean(pages)
        self.assertEqual(self.words(pages), words)
        hi = bytes(c | 0x80 for c in b'\r'.join(p.encode() for p in paras).replace(b'\r', b'\x0d'))
        pages = self.pages(hi)
        self.check_clean(pages)
        self.assertEqual(self.words(pages), words)

    def test_arbitrary_bytes_never_leave_the_page(self):
        import random
        rng = random.Random(646)
        for n in (0, 1, 2, 7, 300, 5000):
            for mode in range(3):
                data = bytes(rng.choice(b'_#]:?*=MGDICEPSJTAx {}@\\^\r\xff\x05\x06\x19') if mode == 0
                             else rng.randrange(256) for _ in range(n))
                if mode == 2: data = bytes(b | 0x80 for b in data)
                with self.subTest(n=n, mode=mode):
                    self.check_clean(self.pages(data))

    def test_real_documents(self):
        import sys
        sys.path.insert(0, '/Users/gistair/.cache/a2fc/newsroom')
        found = 0
        for path in sorted(EPI.glob('*.dsk')) + sorted((PAP / 'docs').glob('*')):
            for name, data in self.real_files(path):
                with self.subTest(file=name):
                    pages = self.pages(data)
                    self.check_clean(pages)
                    found += 1
        if not found:
            self.skipTest('no Epistole/Papyrus documents here')

    def real_files(self, path):
        if path.suffix == '.dsk':
            sys.path.insert(0, str(ROOT / 'tools'))
            from prodos_read import Image
            from po2dsk import SECTORS
            d = path.read_bytes(); po = bytearray(len(d))
            for b in range(len(d) // 512):
                t, p = divmod(b, 8)
                for h, s in enumerate(SECTORS[p]):
                    po[b * 512 + h * 256:b * 512 + h * 256 + 256] = d[(t * 16 + s) * 256:(t * 16 + s + 1) * 256]
            im = Image(bytes(po))
            for e in im.entries(2):
                if e[0x10] == 4:
                    yield e[1:1 + (e[0] & 15)].decode(), im.read(e)
        elif path.is_file():
            yield path.name, path.read_bytes()


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == '--show':
        t = Docview(); Docview.setUpClass()
        for pg in t.pages(Path(sys.argv[2]).read_bytes(), len(sys.argv) > 3):
            print('---- page done=%d bad=%d' % (pg['done'], pg['bad']))
            for r, i in zip(pg['rows'], pg['inv']):
                print((r + ' |' + i.rstrip()).rstrip() if i.strip() else r.rstrip())
        Docview.tearDownClass()
    else:
        unittest.main()
