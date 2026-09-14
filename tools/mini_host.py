"""Drive the real 6502 Mini modules under sim65, with the disks over here.

The catalog and copy engines are assembled exactly as the Apple II build
assembles them; only RWTS is replaced, by a stub that asks this process
for each sector. That keeps the fault injection the C edition's tests
relied on -- a chosen read or write fails, tears in half, or silently
corrupts a byte -- while the code being exercised is the shipped one.

Two 140 KB images cannot live in a 64 KB address space, which is why the
disks stay here rather than in the simulator.
"""
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIZE = 143360

MODULES = ('data.s', 'catalog.s', 'copy.s', 'delete.s')

CATALOG, PREVIEW, PREPARE, EXECUTE, CANCEL, PEEK, POKE, QUIT = 1, 2, 3, 4, 5, 6, 7, 0
LOAD, CREATE_PREPARE, CREATE_EXECUTE, DELETE_PREPARE, DELETE_EXECUTE = 8, 9, 10, 11, 12
MEASURE = 13
LOCK_PREPARE, LOCK_EXECUTE, RENAME_PREPARE, RENAME_EXECUTE = 14, 15, 16, 17
COPY_SIDE = 18


class SimError(RuntimeError):
    pass


def build(target):
    """Assemble and link the harness once; returns (program, symbols).

    cc65 drops its intermediate assembly and objects beside each source,
    so the sources are copied into the build directory first and the
    repository stays clean. They are copies of the shipped files, not
    variants of them.
    """
    target = Path(target)
    target.mkdir(parents=True, exist_ok=True)
    program = target / 'harness.prg'
    labels = target / 'harness.lbl'
    cl65 = shutil.which('cl65')
    if not cl65:
        raise SimError('cl65 not found')
    sources = [ROOT / 'tools/mini_sim.c', ROOT / 'tools/mini_glue.s',
               *[ROOT / 'src/mini' / m for m in MODULES]]
    shutil.copy(ROOT / 'src/mini/mini.inc', target)
    for source in sources:
        shutil.copy(source, target)
    subprocess.run([cl65, '-t', 'sim6502', '--cpu', '6502', '-O', '-DSIM65',
                    '-o', program.name, '-Ln', labels.name,
                    *[s.name for s in sources]],
                   check=True, capture_output=True, cwd=target)
    symbols = {}
    for line in labels.read_text().split('\n'):
        parts = line.split()
        if len(parts) == 3 and parts[0] == 'al':
            symbols[parts[2].lstrip('.')] = int(parts[1], 16)
    return program, symbols


class Mini:
    """One run of the harness. Disks, faults and symbol access."""

    def __init__(self, program, symbols):
        self.symbols = symbols
        self.disks = [bytearray(SIZE), bytearray(SIZE)]
        self.reads = 0
        self.writes = 0
        self.fail_read = -1
        self.fail_write = -1
        self.protect_write = -1
        self.partial_write = -1
        self.corrupt_write = -1
        self.protected_drive = 0
        self.write_log = []
        # A routine that follows a looping chain never returns; the cap
        # turns that hang into a test failure.
        self.max_reads = 4000
        sim65 = shutil.which('sim65')
        if not sim65:
            raise SimError('sim65 not found')
        self.proc = subprocess.Popen([sim65, str(program)],
                                     stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE)

    # ---- plumbing -------------------------------------------------
    def _recv(self, n):
        data = self.proc.stdout.read(n)
        if not data or len(data) != n:
            raise SimError(f'simulator stopped (wanted {n} bytes)')
        return data

    def _send(self, data):
        self.proc.stdin.write(data)
        self.proc.stdin.flush()

    def _serve_sector(self):
        cmd, drive, track, sector = self._recv(4)
        payload = self._recv(256) if cmd == 2 else None
        placed = 1 <= drive <= 2 and track < 35 and sector < 16
        offset = (track * 16 + sector) * 256 if placed else 0
        if cmd == 1:
            if not placed:
                self._send(bytes([1, 0x80]))
                return
            n = self.reads
            self.reads += 1
            if n >= self.max_reads:
                raise SimError(f'{n} sector reads: the 6502 code is looping')
            if n == self.fail_read:
                self._send(bytes([1, 0x80]))
                return
            self._send(bytes([0, 0]) + bytes(self.disks[drive - 1][offset:offset + 256]))
            return
        n = self.writes
        self.writes += 1
        self.write_log.append((drive, track, sector))
        if self.protected_drive == drive or n == self.protect_write:
            self._send(bytes([1, 0x10]))
            return
        if not placed or n == self.fail_write:
            self._send(bytes([1, 0x80]))
            return
        if n == self.partial_write:
            self.disks[drive - 1][offset:offset + 128] = payload[:128]
            self._send(bytes([1, 0x80]))
            return
        self.disks[drive - 1][offset:offset + 256] = payload
        if n == self.corrupt_write:
            self.disks[drive - 1][offset + 255] ^= 1
        self._send(bytes([0, 0]))

    def _command(self, code, extra=b''):
        tag = self._recv(1)
        if tag != b'P':
            raise SimError(f'expected a poll, got {tag!r}')
        self._send(bytes([code]) + extra)
        while True:
            tag = self._recv(1)
            if tag == b'S':
                self._serve_sector()
            elif tag == b'R':
                return
            else:
                raise SimError(f'unexpected tag {tag!r}')

    # ---- the routines under test ----------------------------------
    def catalog(self):
        self._command(CATALOG)
        return self._recv(1)[0]

    def preview(self, index):
        self.poke('prv_index', bytes([index]))
        self._command(PREVIEW)
        return self._recv(1)[0]

    def prepare(self, index, destination):
        self.poke('cp_index', bytes([index]))
        self.poke('cp_dest', bytes([destination]))
        self._command(PREPARE)
        return self._recv(1)[0]

    def execute(self):
        self._command(EXECUTE)
        return self._recv(1)[0]

    def cancel(self):
        self._command(CANCEL)
        return self._recv(1)[0]

    def load_file(self, index):
        self.poke('prv_index', bytes([index]))
        self._command(LOAD)
        return self._recv(1)[0]

    def create_prepare(self):
        self._command(CREATE_PREPARE)
        return self._recv(1)[0]

    def create_execute(self):
        self._command(CREATE_EXECUTE)
        return self._recv(1)[0]

    def delete_prepare(self, index):
        self.poke('del_index', bytes([index]))
        self._command(DELETE_PREPARE)
        return self._recv(1)[0]

    def delete_execute(self):
        self._command(DELETE_EXECUTE)
        return self._recv(1)[0]

    def measure_text(self):
        self._command(MEASURE)
        return self._recv(1)[0]

    def lock_prepare(self, index, op=0):
        self.poke('del_index', bytes([index]))
        self.poke('lock_op', bytes([op]))
        self._command(LOCK_PREPARE)
        return self._recv(1)[0]

    def lock_execute(self):
        self._command(LOCK_EXECUTE)
        return self._recv(1)[0]

    def rename_prepare(self, index, name):
        padded = name.encode('ascii').ljust(30)
        self.poke('del_index', bytes([index]))
        self.poke('ren_name', padded)
        self._command(RENAME_PREPARE)
        return self._recv(1)[0]

    def rename_execute(self):
        self._command(RENAME_EXECUTE)
        return self._recv(1)[0]

    def copy_side(self, src, dst):
        self.poke('side_from', bytes([src]))
        self.poke('side_to', bytes([dst]))
        self._command(COPY_SIDE)
        return self._recv(1)[0]

    # ---- memory ---------------------------------------------------
    def address(self, name):
        if name in self.symbols:
            return self.symbols[name]
        if '_' + name in self.symbols:
            return self.symbols['_' + name]
        raise SimError(f'no symbol {name}')

    def peek(self, name, length=1, offset=0):
        addr = self.address(name) + offset
        self._command(PEEK, bytes([addr & 255, addr >> 8, length & 255]))
        return self._recv(length)

    def poke(self, name, data, offset=0):
        addr = self.address(name) + offset
        self._command(POKE, bytes([addr & 255, addr >> 8, len(data) & 255]) + bytes(data))
        self._recv(1)

    def byte(self, name, offset=0):
        return self.peek(name, 1, offset)[0]

    def word(self, name, offset=0):
        lo, hi = self.peek(name, 2, offset)
        return lo | (hi << 8)

    def image(self, drive):
        return bytes(self.disks[drive - 1])

    def load(self, drive, data):
        if len(data) != SIZE:
            raise SimError('not a 140 KB image')
        self.disks[drive - 1][:] = data

    def reset_faults(self):
        self.reads = 0
        self.writes = 0
        self.fail_read = -1
        self.fail_write = -1
        self.protect_write = -1
        self.partial_write = -1
        self.corrupt_write = -1
        self.protected_drive = 0
        self.write_log = []

    def close(self):
        """The disks live here, so the simulator can simply be dropped."""
        for stream in (self.proc.stdin, self.proc.stdout):
            try:
                stream.close()
            except Exception:
                pass
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait(timeout=30)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


class Harness:
    """Builds once, then hands out a fresh simulator per test."""

    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='a2fc-mini-sim-')
        self.program, self.symbols = build(self.tmp.name)

    def start(self):
        return Mini(self.program, self.symbols)

    def cleanup(self):
        self.tmp.cleanup()
