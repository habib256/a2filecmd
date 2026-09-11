"""Run MOVE's actual entry point against a real ProDOS volume.

The volume is built by the project's own writer (mkvolume.py) and read back
by its own reader (prodos_read.py), so the oracle is not a second copy of
the code under test: after a move the file must be reachable at its new
path, gone from the old one, and every block of data must be untouched.
"""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX, ROOT
from prodos_read import Image

HARNESS = PREFIX + r'''
#include "src/plugins/move.c"

static FILE* disk;
static char volname[16];
static unsigned char vollen;
static unsigned char answer = 1;                 /* what confirm() replies */

struct Blk { unsigned char n, unit; unsigned char* buffer; unsigned int block; };
struct Onl { unsigned char n, unit; unsigned char* buffer; };

static unsigned char mock_mli(unsigned char cmd, void* p)
{
    struct Blk* b = p;
    struct Onl* o = p;
    if (cmd == 0x80 || cmd == 0x81) {
        if (fseek(disk, (long)b->block * 512, SEEK_SET)) return 0x27;
        if (cmd == 0x80) return fread(b->buffer, 1, 512, disk) == 512 ? 0 : 0x27;
        if (fwrite(b->buffer, 1, 512, disk) != 512) return 0x27;
        fflush(disk);
        return 0;
    }
    if (cmd == 0xC5) {                           /* ON_LINE: one drive, our volume */
        memset(o->buffer, 0, 256);
        o->buffer[0] = 0x60 | vollen;
        memcpy(o->buffer + 1, volname, vollen);
        return 0;
    }
    return 0x01;
}

static unsigned char mock_confirm(const char* q) { (void)q; return answer; }
static void mock_bar(const char* n, unsigned long d, unsigned long t)
{ (void)n; (void)d; (void)t; }

/* A copy that comes up short or wrong: the verify pass must catch it and
 * the original must survive. */
static long corrupt_at = -1;
static size_t mock_fwrite(const void* p, size_t sz, size_t n, FILE* f)
{
    static unsigned char tmp[512];
    if (corrupt_at >= 0 && ftell(f) >= corrupt_at) {
        memcpy(tmp, p, n);
        tmp[0] ^= 0xFF;
        return fwrite(tmp, sz, n, f);
    }
    return fwrite(p, sz, n, f);
}

static unsigned char host_type;
static unsigned int host_aux;

static struct Panel host_panels[2];
static unsigned char host_active;
static struct Entry host_sel;
static char host_full[81], host_note[80], host_reselect[17];
static unsigned char host_buf[512];

int main(int argc, char** argv)
{
    static struct A2fcApi api;
    /* argv: image volume src dst name [confirm] */
    disk = fopen(argv[1], "r+b");
    vollen = strlen(argv[2]);
    memcpy(volname, argv[2], vollen);
    strcpy(host_panels[0].path, argv[3]);
    strcpy(host_panels[1].path, argv[4]);
    strcpy(host_sel.name, argv[5]);
    host_sel.type = 0;
    sprintf(host_full, "%s/%s", argv[3], argv[5]);
    if (argc > 6) answer = atoi(argv[6]);
    if (argc > 7) host_sel.type = atoi(argv[7]);
    if (argc > 8) host_sel.size = atol(argv[8]);
    if (argc > 9) corrupt_at = atol(argv[9]);
    host_note[0] = 0;
    host_active = 0;

    api.panels = host_panels; api.active = &host_active;
    api.selected = &host_sel; api.full = host_full;
    api.note = host_note; api.reselect = host_reselect;
    api.copy_buf = host_buf;
    api.cfg_path = "/NOWHERE/A2FILE/A2FILE.CFG";
    api.mli = mock_mli; api.confirm = mock_confirm;
    api.progress_bar = mock_bar;
    api.fopen = fopen; api.fread = fread; api.fwrite = mock_fwrite;
    api.fclose = fclose; api.remove = remove;
    api.filetype = &host_type; api.auxtype = &host_aux;
    api.memcpy = memcpy; api.memset = memset;
    api.strcpy = strcpy; api.strcmp = strcmp; api.strlen = strlen;
    api.sprintf = sprintf;

    plugin_entry(&api);
    printf("%s\n", host_note);
    fclose(disk);
    return 0;
}
'''


def entries(img, key):
    """Live entries of the directory whose key block is `key`, in disk order."""
    out, b, first = [], key, True
    while b:
        blk = img.block(b)
        for k in range(13):
            e = blk[4 + 39 * k:4 + 39 * (k + 1)]
            if first and k == 0:
                continue
            if e[0] >> 4:
                out.append((b, k, e))
        first = False
        b = int.from_bytes(blk[2:4], 'little')
    return out


def child_key(img, key, name):
    for _, _, e in entries(img, key):
        if e[1:1 + (e[0] & 15)].decode('ascii', 'replace') == name:
            return int.from_bytes(e[0x11:0x13], 'little')
    return None


def find(img, key, name):
    for b, k, e in entries(img, key):
        if e[1:1 + (e[0] & 15)].decode('ascii', 'replace') == name:
            return b, k, e
    return None, None, None


def bitmap_free(img, n):
    """Is block n free? One bit a block, set meaning free."""
    hdr = img.block(2)[4:4 + 39]
    bitmap = int.from_bytes(hdr[0x23:0x25], 'little')
    blk = img.block(bitmap + n // 4096)
    return bool((blk[(n % 4096) // 8] >> (7 - (n & 7))) & 1)


def chain(img, key):
    """The blocks of a directory, in order."""
    out, b = [], key
    while b:
        out.append(b)
        b = int.from_bytes(img.block(b)[2:4], 'little')
    return out


def header_count(img, key):
    return int.from_bytes(img.block(key)[4 + 0x21:4 + 0x23], 'little')


class Move(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='move-')
        cls.p = Path(cls.tmp.name)
        (cls.p / 'test.c').write_text(HARNESS)
        cls.exe = cls.p / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(cls.p / 'test.c'), '-o', str(cls.exe)],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def volume(self):
        """A fresh /MOVE volume: SRC with a file and a subdirectory, DST empty."""
        stage = self.p / 'stage'
        subprocess.run(['rm', '-rf', str(stage)], check=True)
        (stage / 'SRC' / 'SUB').mkdir(parents=True)
        (stage / 'DST').mkdir(parents=True)
        (stage / 'SRC' / 'HELLO#040000').write_bytes(bytes(range(256)) * 6)
        (stage / 'SRC' / 'SUB' / 'INSIDE#040000').write_bytes(b'inside' * 100)
        (stage / 'DST' / 'KEEP#040000').write_bytes(b'keep' * 64)
        img = self.p / 'vol.po'
        subprocess.run(['python3', str(ROOT / 'tools' / 'mkvolume.py'), str(stage),
                        str(img), '--volume', 'MOVE', '--blocks', '280'],
                       check=True, capture_output=True)
        return img

    def wide_volume(self):
        """DST full to the brim: twelve entries fill its first block, so the
        next one lands in a SECOND block and dblk is no longer dstkey."""
        stage = self.p / 'wide'
        subprocess.run(['rm', '-rf', str(stage)], check=True)
        (stage / 'SRC' / 'SUB').mkdir(parents=True)
        (stage / 'DST').mkdir(parents=True)
        (stage / 'SRC' / 'SUB' / 'INSIDE#040000').write_bytes(b'inside' * 100)
        for i in range(13):
            (stage / 'DST' / ('F%02d#040000' % i)).write_bytes(b'x' * 16)
        img = self.p / 'wide.po'
        subprocess.run(['python3', str(ROOT / 'tools' / 'mkvolume.py'), str(stage),
                        str(img), '--volume', 'MOVE', '--blocks', '280'],
                       check=True, capture_output=True)
        return img

    def full_volume(self, files=12, root_extra=0):
        """DST filled to the last slot of its only block: twelve entries, the
        header taking slot 0. Anything more has to grow it."""
        stage = self.p / 'full'
        subprocess.run(['rm', '-rf', str(stage)], check=True)
        (stage / 'SRC' / 'SUB').mkdir(parents=True)
        (stage / 'DST').mkdir(parents=True)
        (stage / 'SRC' / 'SUB' / 'INSIDE#040000').write_bytes(b'inside' * 100)
        (stage / 'SRC' / 'HELLO#040000').write_bytes(b'hello' * 20)
        for i in range(files):
            (stage / 'DST' / ('F%02d#040000' % i)).write_bytes(b'x' * 16)
        for i in range(root_extra):
            (stage / ('R%02d#040000' % i)).write_bytes(b'r' * 16)
        img = self.p / 'full.po'
        subprocess.run(['python3', str(ROOT / 'tools' / 'mkvolume.py'), str(stage),
                        str(img), '--volume', 'MOVE', '--blocks', '280'],
                       check=True, capture_output=True)
        return img

    def test_a_full_target_directory_grows_by_one_block(self):
        """The refusal this replaces: MOVE used to stop at a target with no
        free entry. It now allocates a block, links it on and tells the
        directory's own entry that it is longer."""
        img = self.full_volume()
        before = Image(img.read_bytes())
        dstkey = child_key(before, 2, 'DST')
        srckey = child_key(before, 2, 'SRC')
        self.assertEqual(chain(before, dstkey), [dstkey], 'the fixture is not one block')
        self.assertIsNone(find(before, dstkey, 'HELLO')[1])
        _, _, dst_entry = find(before, 2, 'DST')
        blocks_before = int.from_bytes(dst_entry[0x13:0x15], 'little')
        eof_before = int.from_bytes(dst_entry[0x15:0x18], 'little')

        note = self.run_move(img, '/MOVE/SRC', '/MOVE/DST', 'HELLO')
        self.assertIn('moved', note)

        after = Image(img.read_bytes())
        blocks = chain(after, dstkey)
        self.assertEqual(len(blocks), 2, 'the directory did not grow')
        new = blocks[1]
        self.assertFalse(bitmap_free(after, new), 'the new block is still marked free')
        self.assertEqual(int.from_bytes(after.block(new)[0:2], 'little'), dstkey,
                         'the new block does not point back')
        blk, slot, moved = find(after, dstkey, 'HELLO')
        self.assertEqual(blk, new)
        self.assertEqual(int.from_bytes(moved[0x25:0x27], 'little'), dstkey)
        self.assertEqual(header_count(after, dstkey), 13)
        self.assertEqual(header_count(after, srckey), 1)
        _, _, dst_after = find(after, 2, 'DST')
        self.assertEqual(int.from_bytes(dst_after[0x13:0x15], 'little'), blocks_before + 1)
        self.assertEqual(int.from_bytes(dst_after[0x15:0x18], 'little'), eof_before + 512)
        self.assertEqual(after.read(moved), b'hello' * 20)

    def test_growing_asks_first_and_declining_changes_nothing(self):
        img = self.full_volume()
        before = img.read_bytes()
        note = self.run_move(img, '/MOVE/SRC', '/MOVE/DST', 'HELLO', confirm=0)
        self.assertEqual(note, '')
        self.assertEqual(img.read_bytes(), before, 'saying no still touched the volume')

    def test_a_full_volume_directory_is_refused(self):
        """Its four blocks are fixed and it has no entry of its own to
        rewrite, so it is the one directory that cannot be made longer."""
        img = self.full_volume(files=1, root_extra=49)     # SRC + DST + 49 = 51
        before = img.read_bytes()
        self.assertEqual(len(entries(Image(before), 2)), 51, 'the root is not full')
        note = self.run_move(img, '/MOVE/SRC', '/MOVE', 'HELLO')
        self.assertIn('cannot grow', note)
        self.assertEqual(img.read_bytes(), before, 'a refused move touched the volume')

    def test_a_second_directory_block_is_used_and_pointed_at(self):
        """parent_pointer is the BLOCK holding the entry, not the directory's
        key block -- the two differ only once a directory spans two blocks."""
        img = self.wide_volume()
        before = Image(img.read_bytes())
        dstkey = child_key(before, 2, 'DST')
        subkey = child_key(before, child_key(before, 2, 'SRC'), 'SUB')

        note = self.run_move(img, '/MOVE/SRC', '/MOVE/DST', 'SUB')
        self.assertIn('moved', note)

        after = Image(img.read_bytes())
        blk, slot, moved = find(after, dstkey, 'SUB')
        self.assertIsNotNone(slot)
        self.assertNotEqual(blk, dstkey, 'the fixture did not spill into a second block')
        hdr = after.block(subkey)[4:4 + 39]
        self.assertEqual(int.from_bytes(hdr[0x23:0x25], 'little'), blk)
        self.assertEqual(hdr[0x25], slot + 1)
        # the entry still names the directory by its KEY block, not by blk
        self.assertEqual(int.from_bytes(moved[0x25:0x27], 'little'), dstkey)
        _, _, inside = find(after, subkey, 'INSIDE')
        self.assertEqual(after.read(inside), b'inside' * 100)

    def run_move(self, img, src, dst, name, confirm=1):
        return subprocess.check_output(
            [str(self.exe), str(img), 'MOVE', src, dst, name, str(confirm)],
            text=True).strip()

    def run_copy(self, src, dst, name, confirm=1, ftype=4, size=None, corrupt=-1):
        """The fallback: host directories, so unit_of finds no volume and MOVE
        has to copy. The image argument is unused but still opened."""
        if size is None:
            size = (Path(src) / name).stat().st_size if (Path(src) / name).exists() else 0
        return subprocess.check_output(
            [str(self.exe), str(self.p / 'vol.po'), 'MOVE', src, dst, name,
             str(confirm), str(ftype), str(size), str(corrupt)], text=True).strip()

    def test_a_file_changes_directory_without_moving_a_block(self):
        img = self.volume()
        before = Image(img.read_bytes())
        srckey = child_key(before, 2, 'SRC')
        dstkey = child_key(before, 2, 'DST')
        _, _, e = find(before, srckey, 'HELLO')
        key, data = int.from_bytes(e[0x11:0x13], 'little'), before.read(e)
        n_src, n_dst = header_count(before, srckey), header_count(before, dstkey)

        note = self.run_move(img, '/MOVE/SRC', '/MOVE/DST', 'HELLO')
        self.assertIn('moved', note)

        after = Image(img.read_bytes())
        self.assertEqual(find(after, srckey, 'HELLO'), (None, None, None))
        _, slot, moved = find(after, dstkey, 'HELLO')
        self.assertIsNotNone(slot)
        # the same file: same key block, same bytes, not one block recopied
        self.assertEqual(int.from_bytes(moved[0x11:0x13], 'little'), key)
        self.assertEqual(after.read(moved), data)
        # the entry now names its new directory
        self.assertEqual(int.from_bytes(moved[0x25:0x27], 'little'), dstkey)
        self.assertEqual(header_count(after, srckey), n_src - 1)
        self.assertEqual(header_count(after, dstkey), n_dst + 1)

    def test_a_subdirectory_takes_its_parent_pointers_with_it(self):
        img = self.volume()
        before = Image(img.read_bytes())
        srckey = child_key(before, 2, 'SRC')
        dstkey = child_key(before, 2, 'DST')
        subkey = child_key(before, srckey, 'SUB')

        note = self.run_move(img, '/MOVE/SRC', '/MOVE/DST', 'SUB')
        self.assertIn('moved', note)

        after = Image(img.read_bytes())
        blk, slot, moved = find(after, dstkey, 'SUB')
        self.assertIsNotNone(slot)
        self.assertEqual(int.from_bytes(moved[0x11:0x13], 'little'), subkey)
        self.assertEqual(int.from_bytes(moved[0x25:0x27], 'little'), dstkey)
        # its own header must point back at the block and slot it now sits in
        hdr = after.block(subkey)[4:4 + 39]
        self.assertEqual(int.from_bytes(hdr[0x23:0x25], 'little'), blk)
        self.assertEqual(hdr[0x25], slot + 1)        # counted from one
        self.assertEqual(hdr[0x26], 39)
        # and what is inside it is still reachable and unchanged
        _, _, inside = find(after, subkey, 'INSIDE')
        self.assertEqual(after.read(inside), b'inside' * 100)

    def test_no_block_outside_the_directories_is_touched(self):
        img = self.volume()
        before = img.read_bytes()
        b = Image(before)
        dirs = {2, child_key(b, 2, 'SRC'), child_key(b, 2, 'DST'),
                child_key(b, child_key(b, 2, 'SRC'), 'SUB')}
        self.run_move(img, '/MOVE/SRC', '/MOVE/DST', 'SUB')
        after = img.read_bytes()
        changed = {i // 512 for i in range(0, len(before), 512)
                   if before[i:i + 512] != after[i:i + 512]}
        self.assertTrue(changed <= dirs, 'touched %s, allowed %s' % (changed - dirs, dirs))

    def test_a_name_already_there_is_refused(self):
        img = self.volume()
        before = img.read_bytes()
        # put a KEEP in SRC too, then try to move it onto DST/KEEP
        note = self.run_move(img, '/MOVE/DST', '/MOVE/SRC', 'KEEP')
        self.assertIn('moved', note)                 # this one is fine
        img2 = self.volume()
        before2 = img2.read_bytes()
        note = self.run_move(img2, '/MOVE/SRC', '/MOVE/DST', 'NOSUCH')
        self.assertIn('no longer', note)
        self.assertEqual(img2.read_bytes(), before2)

    def test_the_same_directory_is_refused(self):
        img = self.volume()
        before = img.read_bytes()
        note = self.run_move(img, '/MOVE/SRC', '/MOVE/SRC', 'HELLO')
        self.assertIn('same directory', note)
        self.assertEqual(img.read_bytes(), before)

    def test_a_directory_cannot_move_inside_itself(self):
        img = self.volume()
        before = img.read_bytes()
        note = self.run_move(img, '/MOVE/SRC', '/MOVE/SRC/SUB', 'SUB')
        self.assertIn('inside itself', note)
        self.assertEqual(img.read_bytes(), before)

    def test_declining_the_question_writes_nothing(self):
        img = self.volume()
        before = img.read_bytes()
        self.run_move(img, '/MOVE/SRC', '/MOVE/DST', 'HELLO', confirm=0)
        self.assertEqual(img.read_bytes(), before)

    def test_to_and_from_the_volume_directory(self):
        """The volume directory is block 2 and counts its entries in the same
        place, but it can never grow: it is worth its own round trip."""
        img = self.volume()
        before = Image(img.read_bytes())
        srckey = child_key(before, 2, 'SRC')
        root_n = header_count(before, 2)

        self.assertIn('moved', self.run_move(img, '/MOVE/SRC', '/MOVE', 'HELLO'))
        mid = Image(img.read_bytes())
        _, _, e = find(mid, 2, 'HELLO')
        self.assertIsNotNone(e)
        self.assertEqual(int.from_bytes(e[0x25:0x27], 'little'), 2)
        self.assertEqual(header_count(mid, 2), root_n + 1)

        self.assertIn('moved', self.run_move(img, '/MOVE', '/MOVE/SRC', 'HELLO'))
        after = Image(img.read_bytes())
        self.assertEqual(find(after, 2, 'HELLO'), (None, None, None))
        _, _, back = find(after, srckey, 'HELLO')
        self.assertEqual(int.from_bytes(back[0x25:0x27], 'little'), srckey)
        self.assertEqual(header_count(after, 2), root_n)

    def test_the_move_is_reversible(self):
        """There and back again must give the volume its entries back."""
        img = self.volume()
        b = Image(img.read_bytes())
        srckey, dstkey = child_key(b, 2, 'SRC'), child_key(b, 2, 'DST')
        self.run_move(img, '/MOVE/SRC', '/MOVE/DST', 'HELLO')
        self.run_move(img, '/MOVE/DST', '/MOVE/SRC', 'HELLO')
        after = Image(img.read_bytes())
        _, _, e = find(after, srckey, 'HELLO')
        self.assertIsNotNone(e)
        self.assertEqual(int.from_bytes(e[0x25:0x27], 'little'), srckey)
        self.assertEqual(find(after, dstkey, 'HELLO'), (None, None, None))
        self.assertEqual(header_count(after, srckey), 2)
        self.assertEqual(header_count(after, dstkey), 1)


class CopyAcrossVolumes(unittest.TestCase):
    """Two volumes have no entry that can point across, so MOVE copies the
    file and removes the original -- and never removes it before the copy
    has been read back and compared."""

    @classmethod
    def setUpClass(cls):
        Move.setUpClass.__func__(cls)
        cls.volume = Move.volume.__get__(cls)          # the image is still opened
        cls.volume()

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()
        subprocess.run(['rm', '-rf', '/tmp/mv'], check=False)

    run_copy = Move.run_copy
    run_move = Move.run_move

    def fixture(self, payload=b'the file that has to survive' * 40):
        subprocess.run(['rm', '-rf', '/tmp/mv'], check=True)
        Path('/tmp/mv/s').mkdir(parents=True)
        Path('/tmp/mv/d').mkdir(parents=True)
        (Path('/tmp/mv/s') / 'HELLO').write_bytes(payload)
        return payload

    def test_a_file_is_copied_across_and_the_original_removed(self):
        payload = self.fixture()
        note = self.run_copy('/tmp/mv/s', '/tmp/mv/d', 'HELLO')
        self.assertIn('copied to the other volume and removed', note)
        self.assertEqual(Path('/tmp/mv/d/HELLO').read_bytes(), payload)
        self.assertFalse(Path('/tmp/mv/s/HELLO').exists())

    def test_a_bad_copy_never_costs_the_original(self):
        payload = self.fixture()
        note = self.run_copy('/tmp/mv/s', '/tmp/mv/d', 'HELLO', corrupt=512)
        self.assertIn('NOT removed', note)
        self.assertTrue(Path('/tmp/mv/s/HELLO').exists())
        self.assertEqual(Path('/tmp/mv/s/HELLO').read_bytes(), payload)
        self.assertFalse(Path('/tmp/mv/d/HELLO').exists())    # and no half copy left

    def test_a_name_already_there_is_refused(self):
        self.fixture()
        (Path('/tmp/mv/d') / 'HELLO').write_bytes(b'mine')
        note = self.run_copy('/tmp/mv/s', '/tmp/mv/d', 'HELLO')
        self.assertIn('already in the other panel', note)
        self.assertEqual(Path('/tmp/mv/d/HELLO').read_bytes(), b'mine')
        self.assertTrue(Path('/tmp/mv/s/HELLO').exists())

    def test_a_directory_across_volumes_says_to_use_V(self):
        self.fixture()
        note = self.run_copy('/tmp/mv/s', '/tmp/mv/d', 'HELLO', ftype=0x0F)
        self.assertIn('V copies it', note)
        self.assertTrue(Path('/tmp/mv/s/HELLO').exists())

    def test_declining_copies_nothing(self):
        self.fixture()
        self.run_copy('/tmp/mv/s', '/tmp/mv/d', 'HELLO', confirm=0)
        self.assertTrue(Path('/tmp/mv/s/HELLO').exists())
        self.assertFalse(Path('/tmp/mv/d/HELLO').exists())


if __name__ == '__main__':
    unittest.main()
