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
int mock_ferror(FILE*);
void move_copy_entry(const struct A2fcApi*);
void cancel_copy(void);
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
int mock_ferror(FILE* f) { return f == read_error || ferror(f); }
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
    if (io_fault == 32 && close_number == 4) cancel_copy();
    if (io_fault >= 5 && io_fault <= 8 && close_number == io_fault - 4)
        return EOF;
    return result;
}
static unsigned int write_number, fail_write;
static unsigned char fail_after;
/* What happens while the question is on screen: one byte of the disk
 * changed, or the whole disk swapped for another image. */
static long poke_at = -1;
static unsigned char poke_xor;
static const char* swap_with;
static unsigned int fail_read = 0xFFFF;         /* this block's next read fails, once */
static unsigned char twin;                      /* a second drive carries the volume's name */

struct Blk { unsigned char n, unit; unsigned char* buffer; unsigned int block; };
struct Onl { unsigned char n, unit; unsigned char* buffer; };
struct New { unsigned char n; unsigned char* path; };
struct CopyCreate { unsigned char n; unsigned char* path; unsigned char access,type;
    unsigned int aux; unsigned char storage; unsigned int date,time; };
struct Gfi { unsigned char n; unsigned char* path; unsigned char access,type;
    unsigned int aux; unsigned char storage; unsigned int blocks,mdate,mtime,cdate,ctime; };
static unsigned int metadata_queries;

static unsigned char mock_mli(unsigned char cmd, void* p)
{
    struct Blk* b = p;
    struct Onl* o = p;
    if (cmd == 0xC4) {
        struct Gfi* info=p;
        ++metadata_queries;
        if(io_fault==25 || (io_fault==27 && metadata_queries>1))return 0x27;
        if(io_fault==33)return 0x46;
        info->access=0xC3;info->type=4;info->aux=0;info->storage=1;
        if(io_fault==22 || (io_fault==26 && metadata_queries>1))info->storage=5;
        if(io_fault==23)info->storage=0;
        if(io_fault==24)info->storage=13;
        if(io_fault==28 && metadata_queries>1)info->access=0x43;
        if(io_fault==29)info->access=0x43;
        if(io_fault==30)info->storage=2;
        if(io_fault==31)info->storage=3;
        if(io_fault==34 || (io_fault==38 && metadata_queries>1))info->type=6;
        if(io_fault==35 || (io_fault==39 && metadata_queries>1))info->aux=0x2000;
        if(io_fault==36)info->aux=1;
        if(io_fault==37)info->aux=0x0100;
        if(io_fault==40){info->type=6;info->aux=0x2000;}
        if(io_fault==41){info->type=0xB3;info->aux=0xFFFF;}
        return 0;
    }
    if (cmd == 0xC0) {                          /* exclusive CREATE */
        if(io_fault>=34){struct CopyCreate* c=p;fprintf(stderr,"CREATE %u %u\n",c->type,c->aux);}
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
    if (cmd == 0x80 && b->block == fail_read) { fail_read = 0xFFFF; return 0x27; }   /* once */
    if (cmd == 0x80 || cmd == 0x81) {
        if (fseek(disk, (long)b->block * 512, SEEK_SET)) return 0x27;
        if (cmd == 0x80) return fread(b->buffer, 1, 512, disk) == 512 ? 0 : 0x27;
        if (io_fault == 21) fprintf(stderr, "WRITE\n");
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
        if (twin) { o->buffer[16] = 0xE0 | vollen; memcpy(o->buffer + 17, volname, vollen); }
        return 0;
    }
    return 0x01;
}

static unsigned char mock_confirm(const char* q)
{
    unsigned char block[512];
    (void)q;
    if (io_fault == 21) fprintf(stderr, "CONFIRM\n");
    if (poke_at >= 0) {
        fseek(disk, poke_at, SEEK_SET); fread(block, 1, 1, disk);
        block[0] ^= poke_xor;
        fseek(disk, poke_at, SEEK_SET); fwrite(block, 1, 1, disk); fflush(disk);
    }
    if (swap_with) {
        FILE* f = fopen(swap_with, "rb");
        size_t n;
        fseek(disk, 0, SEEK_SET);
        while ((n = fread(block, 1, 512, f)) > 0) fwrite(block, 1, n, disk);
        fclose(f); fflush(disk);
    }
    return answer;
}
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
{ if (io_fault == 9) { cancelled = 1; cancel_copy(); } if (io_fault == 20) fprintf(stderr, "BAR %s %lu %lu\n", n, d, t); }

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
    if(io_fault==40){host_sel.type=6;host_sel.aux=0x2000;}
    if(io_fault==41){host_sel.type=0xB3;host_sel.aux=0xFFFF;}
    if (argc > 11) fail_write = atoi(argv[11]);
    if (argc > 12) fail_after = atoi(argv[12]);
    api.cfg_path = argc > 13 ? argv[13] : "/NOWHERE/A2FILE/A2FILE.CFG";
    if (argc > 14) poke_at = atol(argv[14]);
    if (argc > 15) poke_xor = atoi(argv[15]);
    if (argc > 16 && strcmp(argv[16], "-")) swap_with = argv[16];
    if (argc > 17) fail_read = atoi(argv[17]);
    if (argc > 18) twin = atoi(argv[18]);
    host_note[0] = 0;
    host_active = 0;

    api.panels = host_panels; api.active = &host_active;
    api.selected = &host_sel; api.full = host_full;
    api.other_full = host_target;
    api.note = host_note; api.reselect = host_reselect;
    api.copy_buf = host_buf;
    api.mli = mock_mli; api.confirm = mock_confirm;
    api.progress_bar = mock_bar;
    api.fopen = mock_fopen; api.fread = mock_fread; api.fwrite = mock_fwrite;
    api.fclose = mock_fclose; api.remove = remove;
    api.filetype = &host_type; api.auxtype = &host_aux;
    api.memcpy = memcpy; api.memset = memset;
    api.strcpy = strcpy; api.strcmp = strcmp; api.strlen = strlen;
    api.sprintf = sprintf;
    api.arg = argc > 19 && atoi(argv[19]) ? 'B' : 0;

    plugin_entry(&api);
    if (host_note[0] == 3) move_copy_entry(&api);
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


E_EOF = 0x15


def header_count(img, key):
    return int.from_bytes(img.block(key)[4 + 0x21:4 + 0x23], 'little')


class Move(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='move-')
        cls.p = Path(cls.tmp.name)
        (cls.p / 'test.c').write_text(HARNESS)
        (cls.p / 'copy.c').write_text(PREFIX + r'''
int mock_ferror(FILE*);
#define ferror mock_ferror
#define plugin_entry move_copy_entry
#define __plugin_header move_copy_header
#include "src/plugins/movecopy.c"
void cancel_copy(void) { cancelled = 1; }
''')
        cls.exe = cls.p / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(cls.p / 'test.c'), str(cls.p / 'copy.c'), '-o', str(cls.exe)],
                       check=True, capture_output=True)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def volume(self, extra_source=0):
        """A fresh /MOVE volume: SRC with a file and a subdirectory, DST empty."""
        stage = self.p / 'stage'
        subprocess.run(['rm', '-rf', str(stage)], check=True)
        (stage / 'SRC' / 'SUB').mkdir(parents=True)
        (stage / 'DST').mkdir(parents=True)
        (stage / 'SRC' / 'HELLO#040000').write_bytes(bytes(range(256)) * 6)
        (stage / 'SRC' / 'SUB' / 'INSIDE#040000').write_bytes(b'inside' * 100)
        (stage / 'DST' / 'KEEP#040000').write_bytes(b'keep' * 64)
        for i in range(extra_source):
            (stage / 'SRC' / ('Z%02d#040000' % i)).write_bytes(bytes((i,)) * 100)
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

    def test_invalid_directory_counts_refuse_before_any_write_or_growth(self):
        for full in (False, True):
            for directory, count in (('SRC', 0), ('DST', 65535)):
                with self.subTest(full=full, directory=directory, count=count):
                    img = self.full_volume() if full else self.volume()
                    data = bytearray(img.read_bytes())
                    key = child_key(Image(data), 2, directory)
                    offset = key * 512 + 4 + 0x21
                    data[offset:offset + 2] = count.to_bytes(2, 'little')
                    img.write_bytes(data)
                    note = self.run_move(img, '/MOVE/SRC', '/MOVE/DST', 'HELLO')
                    self.assertNotIn('moved', note)
                    self.assertEqual(img.read_bytes(), data,
                        'invalid counts must not change entries, links, data or the bitmap')

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

    def test_full_multiblock_directory_grows_without_hiding_any_entry(self):
        for files in (25, 38):
            with self.subTest(files=files):
                img = self.full_volume(files=files)
                before = Image(img.read_bytes())
                dst = child_key(before, 2, 'DST')
                blocks = len(chain(before, dst))
                self.assertEqual(files, blocks * 13 - 1)
                note = self.run_move(img, '/MOVE/SRC', '/MOVE/DST', 'HELLO')
                self.assertIn('moved', note)
                after = Image(img.read_bytes())
                self.assertEqual(len(chain(after, dst)), blocks + 1)
                _, _, parent = find(after, 2, 'DST')
                self.assertEqual(int.from_bytes(parent[0x13:0x15], 'little'), blocks + 1)
                self.assertEqual(int.from_bytes(parent[0x15:0x18], 'little'), (blocks + 1) * 512)
                self.assertEqual(header_count(after, dst), files + 1)
                _, _, moved = find(after, dst, 'HELLO')
                self.assertEqual(after.read(moved), b'hello' * 20)
                for i in range(files):
                    _, _, entry = find(after, dst, 'F%02d' % i)
                    self.assertEqual(after.read(entry), b'x' * 16)

    def test_growth_refuses_inconsistent_parent_size_before_any_write(self):
        for blocks, eof in ((0, 0), (2, 1024), (65535, 512), (1, 0),
                            (1, 1), (1, 511), (1, 513), (1, 1024),
                            (1, 0xFFFF00), (65535, 0xFFFE00),
                            (5041, 5041 * 512), (5042, 5042 * 512)):
            with self.subTest(blocks=blocks, eof=eof):
                img = self.full_volume()
                data = bytearray(img.read_bytes())
                block, slot, entry = find(Image(data), 2, 'DST')
                offset = block * 512 + 4 + slot * 39
                data[offset + 0x13:offset + 0x15] = blocks.to_bytes(2, 'little')
                data[offset + 0x15:offset + 0x18] = eof.to_bytes(3, 'little')
                img.write_bytes(data)
                result = subprocess.run(
                    [str(self.exe), str(img), 'MOVE', '/MOVE/SRC', '/MOVE/DST',
                     'HELLO', '1', '0', '0', '-1', '21'],
                    capture_output=True, text=True, check=True)
                self.assertTrue(img.read_bytes() == data,
                    'inconsistent directory size changed bitmap, links or source entry')
                self.assertNotIn('WRITE', result.stderr)
                self.assertIn('could not be made longer', result.stdout)

    def test_growth_never_allocates_reserved_blocks_marked_free(self):
        for block in (0, 1, 2, 3, 5, 6):
            with self.subTest(block=block):
                img = self.full_volume()
                data = bytearray(img.read_bytes())
                bitmap = int.from_bytes(data[1024 + 39:1024 + 41], 'little')
                data[bitmap * 512 + block // 8] |= 0x80 >> (block & 7)
                img.write_bytes(data)
                note = self.run_move(img, '/MOVE/SRC', '/MOVE/DST', 'HELLO')
                self.assertIn('could not be made longer', note)
                self.assertEqual(img.read_bytes(), data,
                    'reserved free bit must not change bitmap, boot, directory or file bytes')

    def test_growth_never_reuses_referenced_blocks_marked_free(self):
        for directory, name in (('SRC', 'HELLO'), ('DST', 'F00'),
                                ('SRC', 'SUB'), ('SRC/SUB', 'INSIDE')):
            with self.subTest(directory=directory, name=name):
                img = self.full_volume()
                data = bytearray(img.read_bytes())
                volume = Image(data)
                key = 2
                for component in directory.split('/'):
                    key = child_key(volume, key, component)
                _, _, entry = find(volume, key, name)
                block = int.from_bytes(entry[0x11:0x13], 'little')
                bitmap = int.from_bytes(data[1024 + 39:1024 + 41], 'little')
                data[bitmap * 512 + block // 8] |= 0x80 >> (block & 7)
                img.write_bytes(data)
                note = self.run_move(img, '/MOVE/SRC', '/MOVE/DST', 'HELLO')
                self.assertTrue(img.read_bytes() == data,
                    'live file or directory was overwritten through its free bit')
                self.assertIn('could not be made longer', note)

    def test_growth_checks_sapling_tree_and_both_extended_forks(self):
        for kind in (2, 3, 5):
            for damage in ('none', 'free_key', 'free_index', 'free_data', 'read_error'):
                with self.subTest(kind=kind, damage=damage):
                    img = self.full_volume()
                    data = bytearray(img.read_bytes())
                    dst = child_key(Image(data), 2, 'DST')
                    block, slot, old = find(Image(data), dst, 'F00')
                    entry = block * 512 + 4 + slot * 39
                    data[entry] = (kind << 4) | (old[0] & 15)
                    data[entry + 17:entry + 19] = (190).to_bytes(2, 'little')
                    for used in range(190, 194):
                        data[6 * 512 + used // 8] &= ~(0x80 >> (used & 7))
                        data[used * 512:(used + 1) * 512] = bytes(512)
                    def pointer(index, target):
                        data[index * 512] = target & 255
                        data[index * 512 + 256] = target >> 8
                    if kind == 2:
                        pointer(190, 193)
                        index = 190
                    elif kind == 3:
                        pointer(190, 191)
                        pointer(191, 193)
                        index = 191
                    else:
                        # Seedling data fork, sapling resource fork.
                        data[190 * 512:190 * 512 + 3] = bytes((1, 192, 0))
                        data[190 * 512 + 256:190 * 512 + 259] = bytes((2, 191, 0))
                        pointer(191, 193)
                        index = 191
                    if damage.startswith('free_'):
                        bad = dict(free_key=190, free_index=index, free_data=193)[damage]
                        data[6 * 512 + bad // 8] |= 0x80 >> (bad & 7)
                    img.write_bytes(data)
                    note = self.run_ext(img, '/MOVE/SRC', '/MOVE/DST', 'HELLO',
                                        fail_read=index if damage == 'read_error' else 65535)
                    if damage == 'none':
                        self.assertIn('moved', note)
                        self.assertEqual(img.read_bytes()[190 * 512:194 * 512],
                                         data[190 * 512:194 * 512])
                    else:
                        self.assertNotIn('moved', note)
                        self.assertEqual(img.read_bytes(), data)

    def test_growth_cancel_or_unknown_storage_preserves_volume(self):
        for fault in ('cancel', 'storage'):
            with self.subTest(fault=fault):
                img = self.full_volume()
                data = bytearray(img.read_bytes())
                if fault == 'storage':
                    dst = child_key(Image(data), 2, 'DST')
                    block, slot, entry = find(Image(data), dst, 'F00')
                    data[block * 512 + 4 + slot * 39] = 0x40 | (entry[0] & 15)
                    img.write_bytes(data)
                note = subprocess.check_output(
                    [str(self.exe), str(img), 'MOVE', '/MOVE/SRC', '/MOVE/DST',
                     'HELLO', '1', '4', '100', '-1',
                     '9' if fault == 'cancel' else '0'], text=True).strip()
                self.assertNotIn('moved', note)
                self.assertEqual(img.read_bytes(), data)

    def test_growth_unreadable_unrelated_directory_preserves_all_bytes(self):
        img = self.full_volume()
        before = img.read_bytes()
        src = child_key(Image(before), 2, 'SRC')
        sub = child_key(Image(before), src, 'SUB')
        note = self.run_ext(img, '/MOVE/SRC', '/MOVE/DST', 'HELLO',
                            fail_read=sub)
        self.assertNotIn('moved', note)
        self.assertEqual(img.read_bytes(), before)

    def test_growth_refuses_invalid_bitmap_bounds_without_writing(self):
        for bitmap in (0, 2, 5, 280, 65535):
            with self.subTest(bitmap=bitmap):
                img = self.full_volume()
                data = bytearray(img.read_bytes())
                data[1024 + 39:1024 + 41] = bitmap.to_bytes(2, 'little')
                img.write_bytes(data)
                note = self.run_move(img, '/MOVE/SRC', '/MOVE/DST', 'HELLO')
                self.assertIn('could not be made longer', note)
                self.assertEqual(img.read_bytes(), data)

    def test_growth_with_unreadable_bitmap_or_full_disk_preserves_volume(self):
        for full in (False, True):
            with self.subTest(full=full):
                img = self.full_volume()
                data = bytearray(img.read_bytes())
                if full:
                    data[6 * 512:7 * 512] = bytes(512)
                    img.write_bytes(data)
                note = self.run_ext(img, '/MOVE/SRC', '/MOVE/DST', 'HELLO',
                                    fail_read=65535 if full else 6)
                self.assertIn('could not be made longer', note)
                self.assertEqual(img.read_bytes(), data)

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

    def run_ext(self, img, src, dst, name, cfg='/NOWHERE/A2FILE/A2FILE.CFG',
                poke=-1, xor=0, swap='-', fail_read=65535, timeout=30):
        """run_move with what the question may hide: a byte of the disk
        changed or the disk swapped while it is on screen, a block whose
        next read fails, the program's settings path."""
        return subprocess.check_output(
            [str(self.exe), str(img), 'MOVE', src, dst, name, '1', '0', '0', '-1', '0', '0', '0',
             cfg, str(poke), str(xor), swap, str(fail_read)], text=True, timeout=timeout).strip()

    def test_a_disk_changed_during_the_question_is_not_written(self):
        """Block numbers read before the question must not be written to
        whatever is in the drive after it (the DOSWRITE guard)."""
        base = Image(self.volume().read_bytes())
        srckey, dstkey = child_key(base, 2, 'SRC'), child_key(base, 2, 'DST')
        sblk, sslot, _ = find(base, srckey, 'HELLO')
        entry = sblk * 512 + 4 + 39 * sslot
        free = dstkey * 512 + 4 + 39 * (len(entries(base, dstkey)) + 1)
        other = self.p / 'other'
        subprocess.run(['rm', '-rf', str(other)], check=True)
        (other / 'SRC').mkdir(parents=True)
        (other / 'DST').mkdir()
        (other / 'EXTRA#040000').write_bytes(b'e' * 700)
        (other / 'SRC' / 'HELLO#040000').write_bytes(b'another disk' * 9)
        swap = self.p / 'other.po'
        subprocess.run(['python3', str(ROOT / 'tools' / 'mkvolume.py'), str(other), str(swap),
                        '--volume', 'MOVE', '--blocks', '280'], check=True, capture_output=True)
        cases = {
            'source entry type': dict(poke=entry + 0x10, xor=0x01),
            'source entry length': dict(poke=entry + E_EOF, xor=0x40),
            'destination slot taken': dict(poke=free, xor=0x11),
            'volume creation date': dict(poke=2 * 512 + 4 + 0x18, xor=0x01),
            'same name, another disk': dict(swap=str(swap)),
        }
        for label, change in cases.items():
            with self.subTest(label):
                img = self.volume()
                expect = bytearray(img.read_bytes())
                if 'poke' in change:
                    expect[change['poke']] ^= change['xor']
                else:
                    expect = bytearray(swap.read_bytes())
                note = self.run_ext(img, '/MOVE/SRC', '/MOVE/DST', 'HELLO', **change)
                self.assertNotIn('moved', note)
                self.assertEqual(img.read_bytes(), bytes(expect), 'written after the disk changed')
        # Nothing changed: the second reading agrees and the move goes ahead.
        img = self.volume()
        self.assertIn('moved', self.run_ext(img, '/MOVE/SRC', '/MOVE/DST', 'HELLO'))

    def test_a_failed_read_of_the_target_is_not_a_free_name(self):
        stage = self.p / 'twice'
        subprocess.run(['rm', '-rf', str(stage)], check=True)
        (stage / 'SRC').mkdir(parents=True)
        (stage / 'DST').mkdir()
        (stage / 'SRC' / 'KEEP#040000').write_bytes(b'source keep')
        (stage / 'DST' / 'KEEP#040000').write_bytes(b'target keep')
        img = self.p / 'twice.po'
        subprocess.run(['python3', str(ROOT / 'tools' / 'mkvolume.py'), str(stage), str(img),
                        '--volume', 'MOVE', '--blocks', '280'], check=True, capture_output=True)
        before = img.read_bytes()
        dstkey = child_key(Image(before), 2, 'DST')
        for key in (dstkey, child_key(Image(before), 2, 'SRC')):
            with self.subTest(block=key):
                note = self.run_ext(img, '/MOVE/SRC', '/MOVE/DST', 'KEEP', fail_read=key)
                self.assertNotIn('moved', note)
                self.assertEqual(img.read_bytes(), before)
        self.assertEqual([e for e in entries(Image(img.read_bytes()), dstkey)
                          if e[2][1:5] == b'KEEP'].__len__(), 1)

    def test_found_source_does_not_hide_a_broken_or_unreadable_tail(self):
        for damage in ('self_loop', 'bad_previous', 'unreadable', 'duplicate_name'):
            with self.subTest(damage=damage):
                img = self.volume()
                data = bytearray(img.read_bytes())
                src = child_key(Image(data), 2, 'SRC')
                tail = src if damage == 'self_loop' else 200
                data[src * 512 + 2:src * 512 + 4] = tail.to_bytes(2, 'little')
                if tail != src:
                    data[tail * 512:(tail + 1) * 512] = bytes(512)
                    previous = 0 if damage == 'bad_previous' else src
                    data[tail * 512:tail * 512 + 2] = previous.to_bytes(2, 'little')
                    data[6 * 512 + tail // 8] &= ~(0x80 >> (tail & 7))
                    if damage == 'duplicate_name':
                        _, _, entry = find(Image(data), src, 'HELLO')
                        data[tail * 512 + 4:tail * 512 + 43] = entry
                img.write_bytes(data)
                result = subprocess.run(
                    [str(self.exe), str(img), 'MOVE', '/MOVE/SRC', '/MOVE/DST',
                     'HELLO', '1', '0', '0', '-1', '21', '0', '0',
                     '/NOWHERE/A2FILE/A2FILE.CFG', '-1', '0', '-',
                     str(tail if damage == 'unreadable' else 65535)],
                    capture_output=True, text=True, check=True, timeout=10)
                self.assertTrue(img.read_bytes() == data,
                    'finding the source hid a malformed or unreadable directory tail')
                self.assertNotIn('WRITE', result.stderr)
                self.assertNotIn('CONFIRM', result.stderr)
                self.assertIn('cannot be walked', result.stdout)

    def test_continuation_must_point_back_to_the_previous_directory_block(self):
        img = self.wide_volume()
        data = bytearray(img.read_bytes())
        dst = child_key(Image(data), 2, 'DST')
        tail = chain(Image(data), dst)[1]
        data[tail * 512:tail * 512 + 2] = bytes(2)
        img.write_bytes(data)
        note = self.run_move(img, '/MOVE/SRC', '/MOVE/DST', 'SUB')
        self.assertTrue(img.read_bytes() == data,
                        'MOVE wrote through an inconsistent directory backlink')
        self.assertIn('cannot be walked', note)

    def test_valid_multiblock_source_restores_the_matched_entry_before_moving(self):
        for name in ('HELLO', 'Z13'):
            with self.subTest(name=name):
                img = self.volume(extra_source=14)
                before = Image(img.read_bytes())
                src = child_key(before, 2, 'SRC')
                dst = child_key(before, 2, 'DST')
                blocks = chain(before, src)
                self.assertEqual(len(blocks), 2)
                original_block, _, entry = find(before, src, name)
                self.assertEqual(original_block, blocks[0 if name == 'HELLO' else 1])
                payload = before.read(entry)
                note = self.run_move(img, '/MOVE/SRC', '/MOVE/DST', name)
                self.assertIn('moved', note)
                after = Image(img.read_bytes())
                self.assertIsNone(find(after, src, name)[1])
                _, _, moved = find(after, dst, name)
                self.assertEqual(after.read(moved), payload)
                changed = {b for b in range(280) if before.block(b) != after.block(b)}
                self.assertTrue(changed <= set(blocks + chain(before, dst)))
                for other_name in ('HELLO',) + tuple('Z%02d' % i for i in range(14)):
                    if other_name != name:
                        original = find(before, src, other_name)[2]
                        remaining = find(after, src, other_name)[2]
                        self.assertEqual(after.read(remaining), before.read(original))

    def test_changes_after_the_source_match_are_rechecked_after_confirmation(self):
        img = self.volume(extra_source=14)
        before = bytearray(img.read_bytes())
        src = child_key(Image(before), 2, 'SRC')
        tail = chain(Image(before), src)[1]
        offset = tail * 512 + 511
        note = self.run_ext(img, '/MOVE/SRC', '/MOVE/DST', 'HELLO', poke=offset, xor=1)
        before[offset] ^= 1
        self.assertEqual(img.read_bytes(), before,
                         'a change after the matched entry was ignored by the recheck')
        self.assertIn('Disk changed', note)

    def test_a_directory_chain_that_loops_is_refused_without_hanging(self):
        for label in ('target loops on itself', 'source loops on itself',
                      'second target block loops back', 'full target loops'):
            with self.subTest(label):
                img = (self.wide_volume() if label.startswith('second') else
                       self.full_volume() if label.startswith('full') else self.volume())
                data = bytearray(img.read_bytes())
                vol = Image(data)
                key = child_key(vol, 2, 'SRC' if label.startswith('source') else 'DST')
                blocks = chain(vol, key)
                last = blocks[-1]
                data[last * 512 + 2:last * 512 + 4] = key.to_bytes(2, 'little')
                img.write_bytes(data)
                # The source loop matters only when the walk must follow it:
                # a name found in the first block never reaches the link.
                name = ('SUB' if label.startswith('second') else
                        'NOPE' if label.startswith('source') else 'HELLO')
                try:
                    note = self.run_ext(img, '/MOVE/SRC', '/MOVE/DST', name, timeout=20)
                except subprocess.TimeoutExpired:
                    self.fail('MOVE hangs on a looping directory chain')
                self.assertNotIn('moved', note)
                self.assertEqual(img.read_bytes(), bytes(data))

    def test_only_the_program_directory_and_its_parents_are_protected(self):
        """A2FC in /MOVE/A2FILE: the root /MOVE itself stays usable; the
        A2FILE directory, and any directory holding it, never move."""
        cfg = '/MOVE/A2FILE/A2FILE.CFG'
        img = self.volume()
        self.assertIn('moved', self.run_ext(img, '/MOVE/SRC', '/MOVE', 'HELLO', cfg=cfg))
        self.assertIn('moved', self.run_ext(img, '/MOVE', '/MOVE/DST', 'HELLO', cfg=cfg))
        self.assertIn('moved', self.run_ext(img, '/MOVE', '/MOVE/DST', 'SRC', cfg=cfg))
        for src, dst, name, where in (
                ('/MOVE/SRC', '/MOVE/DST', 'HELLO', '/MOVE/SRC/A2FILE.CFG'),      # out of it
                ('/MOVE/SRC', '/MOVE/DST', 'HELLO', '/MOVE/DST/A2FILE.CFG'),      # into it
                ('/MOVE/SRC', '/MOVE/DST', 'SUB', '/MOVE/SRC/SUB/A2FILE.CFG'),    # the directory itself
                ('/MOVE/SRC', '/MOVE/DST', 'SUB', '/MOVE/SRC/SUB/A2FILE/A2FILE.CFG'),  # a parent
                ('/MOVE', '/MOVE/DST', 'SRC', '/MOVE/SRC/SUB/A2FILE/A2FILE.CFG')):     # a grandparent
            with self.subTest(src=src, name=name, cfg=where):
                img = self.volume()
                before = img.read_bytes()
                note = self.run_ext(img, src, dst, name, cfg=where)
                self.assertIn("program's A2FILE", note)
                self.assertEqual(img.read_bytes(), before)

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
        run = subprocess.run(
            [str(self.exe), str(self.p / 'vol.po'), 'MOVE', src, dst, name,
             str(confirm), str(ftype), str(size), str(corrupt), str(io_fault)],
            text=True,capture_output=True,check=True)
        self.copy_trace=run.stderr
        return run.stdout.strip()

    def test_two_volumes_of_one_name_get_no_raw_write(self):
        """Before: with a second drive named /MOVE on line, unit_of took the
        first ON_LINE record for both panels, called them one volume, and the
        directory entries were moved by raw writes on that unit, whichever
        /MOVE ProDOS showed in the panels. Now unit_of refuses the name and
        MOVE falls back to the copy across volumes, which goes through
        ProDOS paths only: not one block of the image is written."""
        img = self.volume()
        before = img.read_bytes()
        note = subprocess.check_output(
            [str(self.exe), str(img), 'MOVE', '/MOVE/SRC', '/MOVE/DST', 'HELLO', '1', '4',
             '1536', '-1', '0', '0', '0', '/NOWHERE/A2FILE/A2FILE.CFG', '-1', '0', '-', '65535', '1'],
            text=True).strip()
        # the copy fallback, which here finds no host file /MOVE/SRC/HELLO
        self.assertEqual(note, 'Copy failed: HELLO was NOT removed.')
        self.assertEqual(img.read_bytes(), before)
        # the same call with one /MOVE on line moves the entry
        note = subprocess.check_output(
            [str(self.exe), str(img), 'MOVE', '/MOVE/SRC', '/MOVE/DST', 'HELLO', '1', '4',
             '1536', '-1', '0', '0', '0', '/NOWHERE/A2FILE/A2FILE.CFG', '-1', '0', '-', '65535', '0'],
            text=True).strip()
        self.assertIn('HELLO moved:', note)

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

    def test_invalid_directory_headers_refuse_before_confirmation_or_writes(self):
        for full in (False, True):
            for directory in ('/', 'SRC', 'DST'):
                for damage in ('storage', 'previous', 'entry_length', 'slots'):
                    with self.subTest(full=full, directory=directory, damage=damage):
                        img = self.full_volume() if full else self.volume()
                        data = bytearray(img.read_bytes())
                        key = 2 if directory == '/' else child_key(Image(data), 2, directory)
                        base = key * 512
                        if damage == 'storage':
                            data[base + 4] = 0x10 | (data[base + 4] & 15)
                        elif damage == 'previous':
                            data[base] = 1
                        elif damage == 'entry_length':
                            data[base + 0x23] = 38
                        else:
                            data[base + 0x24] = 12
                        img.write_bytes(data)
                        result = subprocess.run(
                            [str(self.exe), str(img), 'MOVE', '/MOVE/SRC', '/MOVE/DST',
                             'HELLO', '1', '0', '0', '-1', '21'],
                            capture_output=True, text=True, check=True)
                        self.assertTrue(img.read_bytes() == data,
                            'MOVE wrote into a directory with an invalid header')
                        self.assertNotIn('WRITE', result.stderr)
                        self.assertNotIn('CONFIRM', result.stderr)
                        self.assertIn('cannot be walked', result.stdout)

    def test_directory_header_is_revalidated_after_confirmation(self):
        for directory in ('SRC', 'DST'):
            for field in (0, 4, 0x23, 0x24):
                with self.subTest(directory=directory, field=field):
                    img = self.volume()
                    before = bytearray(img.read_bytes())
                    key = child_key(Image(before), 2, directory)
                    offset = key * 512 + field
                    xor = 0x10 if field == 4 else 1
                    note = self.run_ext(img, '/MOVE/SRC', '/MOVE/DST', 'HELLO',
                                        poke=offset, xor=xor)
                    before[offset] ^= xor
                    self.assertEqual(img.read_bytes(), before,
                        'a header corrupted during confirmation still received writes')
                    self.assertIn('cannot be walked', note)

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

    def test_write_protected_directories_preserve_all_bytes(self):
        for full in (False, True):
            for directory in ('SRC', 'DST'):
                for protection in ('header', 'parent_entry', 'both'):
                    with self.subTest(full=full, directory=directory, protection=protection):
                        img = self.full_volume() if full else self.volume()
                        data = bytearray(img.read_bytes())
                        volume = Image(data)
                        key = child_key(volume, 2, directory)
                        block, slot, _ = find(volume, 2, directory)
                        if protection != 'parent_entry':
                            data[key * 512 + 0x22] &= ~2
                        if protection != 'header':
                            data[block * 512 + 4 + slot * 39 + 30] &= ~2
                        img.write_bytes(data)
                        result = subprocess.run(
                            [str(self.exe), str(img), 'MOVE', '/MOVE/SRC', '/MOVE/DST',
                             'HELLO', '1', '0', '0', '-1', '21'],
                            capture_output=True, text=True, check=True)
                        self.assertTrue(img.read_bytes() == data,
                            'MOVE bypassed directory write protection')
                        self.assertNotIn('WRITE', result.stderr)
                        self.assertNotIn('CONFIRM', result.stderr)
                        self.assertNotIn('moved', result.stdout)

    def test_moved_subdirectory_write_protection_preserves_its_backlink(self):
        for protection in ('header', 'parent_entry', 'both'):
            with self.subTest(protection=protection):
                img = self.volume()
                data = bytearray(img.read_bytes())
                volume = Image(data)
                src = child_key(volume, 2, 'SRC')
                key = child_key(volume, src, 'SUB')
                block, slot, _ = find(volume, src, 'SUB')
                if protection != 'parent_entry':
                    data[key * 512 + 0x22] &= ~2
                if protection != 'header':
                    data[block * 512 + 4 + slot * 39 + 30] &= ~2
                img.write_bytes(data)
                note = self.run_move(img, '/MOVE/SRC', '/MOVE/DST', 'SUB')
                self.assertTrue(img.read_bytes() == data,
                    'MOVE rewrote a protected subdirectory backlink')
                self.assertNotIn('moved', note)

    def test_directory_protection_is_rechecked_after_confirmation(self):
        for directory in ('SRC', 'DST'):
            for protection in ('header', 'parent_entry'):
                with self.subTest(directory=directory, protection=protection):
                    img = self.full_volume()
                    before = bytearray(img.read_bytes())
                    volume = Image(before)
                    key = child_key(volume, 2, directory)
                    block, slot, _ = find(volume, 2, directory)
                    offset = (key * 512 + 0x22 if protection == 'header'
                              else block * 512 + 4 + slot * 39 + 30)
                    note = self.run_ext(img, '/MOVE/SRC', '/MOVE/DST', 'HELLO',
                                        poke=offset, xor=2)
                    before[offset] ^= 2
                    self.assertEqual(img.read_bytes(), before)
                    self.assertNotIn('moved', note)

    def test_readonly_ancestor_does_not_prevent_writing_a_writable_child(self):
        img = self.volume()
        data = bytearray(img.read_bytes())
        volume = Image(data)
        src = child_key(volume, 2, 'SRC')
        block, slot, _ = find(volume, 2, 'SRC')
        data[src * 512 + 0x22] &= ~2
        data[block * 512 + 4 + slot * 39 + 30] &= ~2
        img.write_bytes(data)
        note = self.run_move(img, '/MOVE/SRC/SUB', '/MOVE/DST', 'INSIDE')
        self.assertIn('moved', note)
        after = Image(img.read_bytes())
        self.assertEqual(after.block(src), data[src * 512:(src + 1) * 512])
        self.assertEqual(after.block(block), data[block * 512:(block + 1) * 512])
        dst = child_key(after, 2, 'DST')
        _, _, moved = find(after, dst, 'INSIDE')
        self.assertEqual(after.read(moved), b'inside' * 100)

    def test_write_protected_volume_refuses_before_confirmation_or_writes(self):
        for full in (False, True):
            for name in ('HELLO', 'SUB'):
                for access in (0, 1, 0xC1):
                    for batch in (False, True):
                        with self.subTest(full=full, name=name, access=access, batch=batch):
                            img = self.full_volume() if full else self.volume()
                            data = bytearray(img.read_bytes())
                            data[2 * 512 + 0x22] = access
                            img.write_bytes(data)
                            result = subprocess.run(
                                [str(self.exe), str(img), 'MOVE', '/MOVE/SRC', '/MOVE/DST',
                                 name, '1', '0', '0', '-1', '21', '0', '0',
                                 '/NOWHERE/A2FILE/A2FILE.CFG', '-1', '0', '-', '65535',
                                 '0', str(int(batch))], capture_output=True, text=True, check=True)
                            self.assertTrue(img.read_bytes() == data,
                                'raw MOVE bypassed volume write protection')
                            self.assertNotIn('WRITE', result.stderr)
                            self.assertNotIn('CONFIRM', result.stderr)
                            self.assertIn('write protected', result.stdout.lower())

    def test_volume_write_permission_is_rechecked_after_confirmation(self):
        for full in (False, True):
            img = self.full_volume() if full else self.volume()
            before = bytearray(img.read_bytes())
            offset = 2 * 512 + 0x22
            note = self.run_ext(img, '/MOVE/SRC', '/MOVE/DST', 'HELLO',
                                poke=offset, xor=0x02)
            before[offset] ^= 0x02
            self.assertEqual(img.read_bytes(), before,
                'permission revoked during confirmation still allowed directory writes')
            self.assertIn('write protected', note.lower())

    def test_unreadable_volume_header_never_gets_confirmation_or_writes(self):
        img = self.full_volume()
        before = img.read_bytes()
        result = subprocess.run(
            [str(self.exe), str(img), 'MOVE', '/MOVE/SRC', '/MOVE/DST', 'HELLO',
             '1', '0', '0', '-1', '21', '0', '0', '/NOWHERE/A2FILE/A2FILE.CFG',
             '-1', '0', '-', '2'], capture_output=True, text=True, check=True)
        self.assertEqual(img.read_bytes(), before)
        self.assertNotIn('WRITE', result.stderr)
        self.assertNotIn('CONFIRM', result.stderr)
        self.assertIn('cannot be walked', result.stdout)

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

    def test_unsupported_or_unreadable_source_metadata_refuses_creation(self):
        for fault in (22,23,24,25,29,33):
            with self.subTest(fault=fault):
                payload=self.fixture()
                note=self.run_copy('/tmp/mv/s','/tmp/mv/d','HELLO',io_fault=fault)
                self.assertIn('NOT removed',note)
                self.assertEqual(Path('/tmp/mv/s/HELLO').read_bytes(),payload)
                self.assertFalse(Path('/tmp/mv/d/HELLO').exists())

    def test_source_becoming_forked_locked_or_unreadable_retains_both_files(self):
        for fault in (26,27,28,32):
            with self.subTest(fault=fault):
                payload=self.fixture()
                note=self.run_copy('/tmp/mv/s','/tmp/mv/d','HELLO',io_fault=fault)
                self.assertIn('not removed',note)
                self.assertEqual(Path('/tmp/mv/s/HELLO').read_bytes(),payload)
                self.assertEqual(Path('/tmp/mv/d/HELLO').read_bytes(),payload)

    def test_supported_sapling_and_tree_metadata_allow_a_verified_move(self):
        for fault in (30,31):
            with self.subTest(fault=fault):
                payload=self.fixture(b'x'*8192)
                note=self.run_copy('/tmp/mv/s','/tmp/mv/d','HELLO',io_fault=fault)
                self.assertIn('copied to the other volume and removed',note)
                self.assertEqual(Path('/tmp/mv/d/HELLO').read_bytes(),payload)
                self.assertFalse(Path('/tmp/mv/s/HELLO').exists())

    def test_stale_type_or_aux_refuses_before_creating_destination(self):
        for fault in (34,35,36,37):
            for size in (0,1,512,1600):
                with self.subTest(fault=fault,size=size):
                    payload=self.fixture(bytes(i%251 for i in range(size)))
                    Path('/tmp/mv/d/KEEP').write_bytes(b'unrelated bytes')
                    note=self.run_copy('/tmp/mv/s','/tmp/mv/d','HELLO',io_fault=fault)
                    self.assertIn('NOT removed',note)
                    self.assertEqual(Path('/tmp/mv/s/HELLO').read_bytes(),payload)
                    self.assertFalse(Path('/tmp/mv/d/HELLO').exists())
                    self.assertEqual(Path('/tmp/mv/d/KEEP').read_bytes(),b'unrelated bytes')
                    self.assertNotIn('CREATE ',self.copy_trace)

    def test_type_or_aux_change_during_move_retains_verified_copy_and_source(self):
        for fault in (38,39):
            for size in (0,1,512,1600):
                with self.subTest(fault=fault,size=size):
                    payload=self.fixture(bytes(i%251 for i in range(size)))
                    Path('/tmp/mv/d/KEEP').write_bytes(b'unrelated bytes')
                    note=self.run_copy('/tmp/mv/s','/tmp/mv/d','HELLO',io_fault=fault)
                    self.assertIn('not removed',note)
                    self.assertEqual(Path('/tmp/mv/s/HELLO').read_bytes(),payload)
                    self.assertEqual(Path('/tmp/mv/d/HELLO').read_bytes(),payload)
                    self.assertEqual(Path('/tmp/mv/d/KEEP').read_bytes(),b'unrelated bytes')
                    self.assertEqual(self.copy_trace,'CREATE 4 0\n')

    def test_matching_nondefault_type_and_aux_are_preserved(self):
        for fault,ftype,aux in ((40,6,0x2000),(41,0xB3,0xFFFF)):
            for size in (0,512,1600):
                with self.subTest(fault=fault,size=size):
                    payload=self.fixture(bytes(i%251 for i in range(size)))
                    note=self.run_copy('/tmp/mv/s','/tmp/mv/d','HELLO',io_fault=fault)
                    self.assertIn('copied to the other volume and removed',note)
                    self.assertFalse(Path('/tmp/mv/s/HELLO').exists())
                    self.assertEqual(Path('/tmp/mv/d/HELLO').read_bytes(),payload)
                    self.assertEqual(self.copy_trace,'CREATE %u %u\n'%(ftype,aux))

    def test_the_bar_covers_the_copy_and_the_check(self):
        # The read-back is as long as the copy: its bar starts again at 0
        # instead of staying full while the machine reads.
        payload = self.fixture(b'y' * 1300)
        run = subprocess.run(
            [str(self.exe), str(self.p / 'vol.po'), 'MOVE', '/tmp/mv/s', '/tmp/mv/d', 'HELLO',
             '1', '4', '1300', '-1', '20'], text=True, capture_output=True, check=True)
        self.assertIn('copied to the other volume and removed', run.stdout)
        self.assertEqual(Path('/tmp/mv/d/HELLO').read_bytes(), payload)
        bars = [l for l in run.stderr.splitlines() if l.startswith('BAR ')]
        self.assertEqual(bars, ['BAR HELLO %d 1300' % k for k in (0, 512, 1024) * 2])

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

    def test_a_directory_across_volumes_is_handed_to_the_core(self):
        self.fixture()
        note = self.run_copy('/tmp/mv/s', '/tmp/mv/d', 'HELLO', ftype=0x0F)
        self.assertEqual(note, '\x02')   # the core walks the tree, marked or not
        self.assertTrue(Path('/tmp/mv/s/HELLO').exists())

    def test_declining_copies_nothing(self):
        self.fixture()
        self.run_copy('/tmp/mv/s', '/tmp/mv/d', 'HELLO', confirm=0)
        self.assertTrue(Path('/tmp/mv/s/HELLO').exists())
        self.assertFalse(Path('/tmp/mv/d/HELLO').exists())


if __name__ == '__main__':
    unittest.main()
