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
#include <errno.h>
static int mock_ferror(FILE*);
#define ferror mock_ferror
#include "src/plugins/move.c"
#undef ferror

static FILE* disk;
static char volname[16];
static unsigned char vollen;
static unsigned char answer = 1;                 /* what confirm() replies */
static unsigned char io_fault;
static unsigned char probed;
static unsigned int open_number, close_number;
static FILE *verify_source, *verify_target, *read_error;
static int mock_ferror(FILE* f) { return f == read_error || ferror(f); }
static size_t mock_fread(void* p, size_t z, size_t n, FILE* f) {
    if (n == 1 && ((io_fault == 3 && f == verify_source) ||
                   (io_fault == 4 && f == verify_target))) {
        read_error = f; errno = EIO; return 0;
    }
    if (io_fault == 11 && n > 1) return fread(p, z, n / 2, f);
    return fread(p, z, n, f);
}
static int mock_fclose(FILE* f) {
    int result = fclose(f);
    ++close_number;
    if (io_fault >= 5 && io_fault <= 8 && close_number == io_fault - 4)
        return EOF;
    return result;
}
static unsigned int write_number, fail_write;
static unsigned char fail_after;

struct Blk { unsigned char n, unit; unsigned char* buffer; unsigned int block; };
struct Onl { unsigned char n, unit; unsigned char* buffer; };
struct New { unsigned char n; unsigned char* path; };

static unsigned char mock_mli(unsigned char cmd, void* p)
{
    struct Blk* b = p;
    struct Onl* o = p;
    if (cmd == 0xC0) {                          /* exclusive CREATE */
        struct New* c = p;
        char path[81];
        FILE* f;
        if (io_fault == 2) return 0x27;
        memcpy(path, c->path + 1, c->path[0]);
        path[c->path[0]] = 0;
        f = fopen(path, "wx");
        if (!f) return errno == EEXIST ? 0x47 : 0x27;
        return fclose(f) ? 0x27 : 0;
    }
    if (cmd == 0x80 || cmd == 0x81) {
        if (fseek(disk, (long)b->block * 512, SEEK_SET)) return 0x27;
        if (cmd == 0x80) return fread(b->buffer, 1, 512, disk) == 512 ? 0 : 0x27;
        ++write_number;
        if(write_number==fail_write && !fail_after)return 0x27;
        if (fwrite(b->buffer, 1, 512, disk) != 512) return 0x27;
        fflush(disk);
        return write_number==fail_write?0x27:0;
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
static FILE* mock_fopen(const char* path, const char* mode)
{
    /* Fail only the initial destination existence probe, as a transient
     * read error would. The old implementation then overwrites the file. */
    if (io_fault == 1 && !probed && !strcmp(mode, "rb")) {
        probed = 1;
        return NULL;
    }
    {
        FILE* f = fopen(path, mode);
        ++open_number;
        if (open_number == 3) verify_source = f;
        if (open_number == 4) verify_target = f;
        return f;
    }
}
static void mock_bar(const char* n, unsigned long d, unsigned long t)
{ (void)n; (void)d; (void)t; if (io_fault == 9) cancelled = 1; }

/* A copy that comes up short or wrong: the verify pass must catch it and
 * the original must survive. */
static long corrupt_at = -1;
static size_t mock_fwrite(const void* p, size_t sz, size_t n, FILE* f)
{
    static unsigned char tmp[512];
    if (io_fault == 10) return fwrite(p, sz, n / 2, f);
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
static char host_full[81], host_target[81], host_note[80], host_reselect[17];
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
    if (argc > 10) io_fault = atoi(argv[10]);
    if (argc > 11) fail_write = atoi(argv[11]);
    if (argc > 12) fail_after = atoi(argv[12]);
    host_note[0] = 0;
    host_active = 0;

    api.panels = host_panels; api.active = &host_active;
    api.selected = &host_sel; api.full = host_full;
    api.other_full = host_target;
    api.note = host_note; api.reselect = host_reselect;
    api.copy_buf = host_buf;
    api.cfg_path = "/NOWHERE/A2FILE/A2FILE.CFG";
    api.mli = mock_mli; api.confirm = mock_confirm;
    api.progress_bar = mock_bar;
    api.fopen = mock_fopen; api.fread = mock_fread; api.fwrite = mock_fwrite;
    api.fclose = mock_fclose; api.remove = remove;
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

    def test_growth_refuses_a_broken_parent_reference_before_writing(self):
        for damage in ('wrong_directory', 'file', 'slot14', 'slot255',
                       'entry_length', 'unreadable_parent'):
            with self.subTest(damage=damage):
                img = self.full_volume()
                data = bytearray(img.read_bytes())
                volume = Image(data)
                dstkey = child_key(volume, 2, 'DST')
                srckey = child_key(volume, 2, 'SRC')
                hdr = dstkey * 512 + 4
                if damage in ('wrong_directory', 'file'):
                    block, slot, _ = (find(volume, 2, 'SRC') if damage == 'wrong_directory'
                                      else find(volume, srckey, 'HELLO'))
                    data[hdr + 0x23:hdr + 0x25] = block.to_bytes(2, 'little')
                    data[hdr + 0x25] = slot + 1
                elif damage.startswith('slot'):
                    data[hdr + 0x25] = int(damage[4:])
                elif damage == 'entry_length':
                    data[hdr + 0x26] = 40
                else:
                    data[hdr + 0x23:hdr + 0x25] = (280).to_bytes(2, 'little')
                img.write_bytes(data)
                note = self.run_move(img, '/MOVE/SRC', '/MOVE/DST', 'HELLO')
                self.assertIn('could not be made longer', note)
                self.assertEqual(img.read_bytes(), data,
                                 'invalid parent reference still changed the volume')

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

    def test_failed_raw_writes_restore_source_and_remove_duplicate(self):
        for name,count in (('HELLO',4),('SUB',5)):
            for fail_at in range(1,count+1):
                for after_write in (0,1):
                    with self.subTest(name=name,fail_at=fail_at,after_write=after_write):
                        path=self.volume();before=Image(path.read_bytes())
                        src=child_key(before,2,'SRC');dst=child_key(before,2,'DST')
                        _,_,original=find(before,src,name)
                        note=subprocess.check_output([self.exe,path,'MOVE','/MOVE/SRC','/MOVE/DST',name,
                            '1','0','0','-1','0',str(fail_at),str(after_write)],text=True)
                        self.assertIn('original restored',note)
                        current=Image(path.read_bytes())
                        self.assertEqual(find(current,src,name)[2],original)
                        self.assertIsNone(find(current,dst,name)[2])
                        self.assertEqual(header_count(current,src),header_count(before,src))
                        self.assertEqual(header_count(current,dst),header_count(before,dst))
                        if name=='HELLO':self.assertEqual(current.read(original),before.read(original))
                        else:
                            key=child_key(before,src,name)
                            self.assertEqual(current.block(key),before.block(key))

    def test_bad_subdirectory_backlink_refuses_every_write(self):
        path=self.volume();original=Image(path.read_bytes());src=child_key(original,2,'SRC')
        key=child_key(original,src,'SUB');damaged=bytearray(path.read_bytes())
        damaged[key*512+4+0x23:key*512+4+0x25]=bytes([1,0]);path.write_bytes(damaged)
        self.run_move(path,'/MOVE/SRC','/MOVE/DST','SUB')
        self.assertEqual(path.read_bytes(),damaged)

    def run_move(self, img, src, dst, name, confirm=1):
        return subprocess.check_output(
            [str(self.exe), str(img), 'MOVE', src, dst, name, str(confirm)],
            text=True).strip()

    def run_copy(self, src, dst, name, confirm=1, ftype=4, size=None, corrupt=-1,
                 io_fault=0):
        """The fallback: host directories, so unit_of finds no volume and MOVE
        has to copy. The image argument is unused but still opened."""
        if size is None:
            size = (Path(src) / name).stat().st_size if (Path(src) / name).exists() else 0
        return subprocess.check_output(
            [str(self.exe), str(self.p / 'vol.po'), 'MOVE', src, dst, name,
             str(confirm), str(ftype), str(size), str(corrupt), str(io_fault)], text=True).strip()

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

    def test_a_path_component_must_still_be_a_directory(self):
        for directory in ('SRC', 'DST'):
            for storage in (1, 2, 3, 5):
                with self.subTest(directory=directory, storage=storage):
                    img = self.volume()
                    data = bytearray(img.read_bytes())
                    block, slot, _ = find(Image(data), 2, directory)
                    offset = block * 512 + 4 + slot * 39
                    # The panel still holds the old directory path. Its
                    # entry on disk has become a file (or is corrupted).
                    data[offset] = (storage << 4) | (data[offset] & 15)
                    data[offset + 16] = 6
                    img.write_bytes(data)
                    note = self.run_move(img, '/MOVE/SRC', '/MOVE/DST', 'HELLO')
                    self.assertIn('cannot be walked', note)
                    self.assertEqual(img.read_bytes(), data,
                                     'walked a file as a directory and rewrote its data')

    def test_locked_source_entries_are_not_moved(self):
        for name in ('HELLO', 'SUB'):
            with self.subTest(name=name):
                img = self.volume()
                data = bytearray(img.read_bytes())
                volume = Image(data)
                srckey = child_key(volume, 2, 'SRC')
                block, slot, _ = find(volume, srckey, name)
                data[block * 512 + 4 + slot * 39 + 30] = 0x01  # core's locked access value
                img.write_bytes(data)
                note = self.run_move(img, '/MOVE/SRC', '/MOVE/DST', name)
                self.assertIn('locked', note)
                self.assertEqual(img.read_bytes(), data, 'MOVE bypassed the source lock')

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

    def test_a_stale_panel_size_never_truncates_the_original(self):
        for cached_size in (0, 512, 1079, 1081):
            with self.subTest(cached_size=cached_size):
                payload = self.fixture(b'x' * 1080)
                note = self.run_copy('/tmp/mv/s', '/tmp/mv/d', 'HELLO',
                                     size=cached_size)
                self.assertIn('NOT removed', note)
                self.assertEqual(Path('/tmp/mv/s/HELLO').read_bytes(), payload)
                self.assertFalse(Path('/tmp/mv/d/HELLO').exists())

    def test_final_read_error_with_stale_size_keeps_the_entire_source(self):
        for cached_size in (0, 4, 512, 1080):
            with self.subTest(cached_size=cached_size):
                payload = self.fixture(b'x' * 1080)
                self.run_copy('/tmp/mv/s', '/tmp/mv/d', 'HELLO',
                              size=cached_size, io_fault=3)
                self.assertEqual(Path('/tmp/mv/s/HELLO').read_bytes(), payload)
                self.assertFalse(Path('/tmp/mv/d/HELLO').exists())

    def test_target_final_read_error_keeps_source_even_after_matching_bytes(self):
        payload = self.fixture()
        self.run_copy('/tmp/mv/s', '/tmp/mv/d', 'HELLO', io_fault=4)
        self.assertEqual(Path('/tmp/mv/s/HELLO').read_bytes(), payload)
        self.assertFalse(Path('/tmp/mv/d/HELLO').exists())

    def test_each_failed_close_blocks_source_removal(self):
        for fault in range(5, 9):
            with self.subTest(close=fault - 4):
                payload = self.fixture()
                self.run_copy('/tmp/mv/s', '/tmp/mv/d', 'HELLO', io_fault=fault)
                self.assertEqual(Path('/tmp/mv/s/HELLO').read_bytes(), payload)
                self.assertFalse(Path('/tmp/mv/d/HELLO').exists())

    def test_cancel_disk_full_and_short_read_preserve_source(self):
        for fault in (9, 10, 11):
            with self.subTest(fault=fault):
                payload = self.fixture()
                self.run_copy('/tmp/mv/s', '/tmp/mv/d', 'HELLO', io_fault=fault)
                self.assertEqual(Path('/tmp/mv/s/HELLO').read_bytes(), payload)
                self.assertFalse(Path('/tmp/mv/d/HELLO').exists())

    def test_an_empty_file_can_be_moved(self):
        self.fixture(b'')
        note = self.run_copy('/tmp/mv/s', '/tmp/mv/d', 'HELLO')
        self.assertIn('copied to the other volume and removed', note)
        self.assertEqual(Path('/tmp/mv/d/HELLO').read_bytes(), b'')
        self.assertFalse(Path('/tmp/mv/s/HELLO').exists())

    def test_a_name_already_there_is_refused(self):
        self.fixture()
        (Path('/tmp/mv/d') / 'HELLO').write_bytes(b'mine')
        note = self.run_copy('/tmp/mv/s', '/tmp/mv/d', 'HELLO')
        self.assertIn('already in the other panel', note)
        self.assertEqual(Path('/tmp/mv/d/HELLO').read_bytes(), b'mine')
        self.assertTrue(Path('/tmp/mv/s/HELLO').exists())

    def test_a_failed_destination_probe_does_not_authorize_overwriting(self):
        payload = self.fixture()
        destination = Path('/tmp/mv/d/HELLO')
        destination.write_bytes(b'irreplaceable destination')
        note = self.run_copy('/tmp/mv/s', '/tmp/mv/d', 'HELLO', io_fault=1)
        self.assertIn('already in the other panel', note)
        self.assertEqual(destination.read_bytes(), b'irreplaceable destination')
        self.assertEqual(Path('/tmp/mv/s/HELLO').read_bytes(), payload)

    def test_failed_exclusive_creation_keeps_the_source(self):
        payload = self.fixture()
        note = self.run_copy('/tmp/mv/s', '/tmp/mv/d', 'HELLO', io_fault=2)
        self.assertIn('NOT removed', note)
        self.assertEqual(Path('/tmp/mv/s/HELLO').read_bytes(), payload)
        self.assertFalse(Path('/tmp/mv/d/HELLO').exists())

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
