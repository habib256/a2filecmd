"""A small NMOS 6502 interpreter that records every memory access.

Documented opcodes only, binary arithmetic only (SED raises: the code under
test runs with D clear), no interrupts. Used by tools/test_ppt3_engine.py
to prove which addresses the PT3 engine reads and writes; the register
streams themselves come from sim65 (tools/ppt3_sim.py).
"""


class Halt(Exception):
    pass


class CPU:
    def __init__(self, mem=None):
        self.m = bytearray(65536) if mem is None else mem
        self.a = self.x = self.y = 0
        self.s = 0xFF
        self.pc = 0
        self.n = self.v = self.z = self.c = self.i = self.d = 0
        self.reads = set()
        self.writes = set()
        self.steps = 0
        self.ops = self._table()

    # -- memory ------------------------------------------------------------
    def rd(self, a):
        self.reads.add(a)
        return self.m[a]

    def wr(self, a, v):
        self.writes.add(a)
        self.m[a] = v & 255

    def fetch(self):
        v = self.m[self.pc]
        self.reads.add(self.pc)
        self.pc = (self.pc + 1) & 0xFFFF
        return v

    def fetch16(self):
        lo = self.fetch()
        return lo | self.fetch() << 8

    def push(self, v):
        self.wr(0x100 | self.s, v)
        self.s = (self.s - 1) & 255

    def pull(self):
        self.s = (self.s + 1) & 255
        return self.rd(0x100 | self.s)

    def p(self, b=0x30):
        return (self.n << 7 | self.v << 6 | b | self.d << 3 | self.i << 2 | self.z << 1 | self.c)

    def setp(self, v):
        self.n, self.v, self.d, self.i, self.z, self.c = v >> 7 & 1, v >> 6 & 1, v >> 3 & 1, v >> 2 & 1, v >> 1 & 1, v & 1
        if self.d:
            raise Halt('decimal mode')

    def nz(self, v):
        self.n = v >> 7
        self.z = int(v == 0)
        return v

    # -- addressing: return an effective address --------------------------
    def zp(self): return self.fetch()
    def zpx(self): return (self.fetch() + self.x) & 255
    def zpy(self): return (self.fetch() + self.y) & 255
    def ab(self): return self.fetch16()
    def abx(self): return (self.fetch16() + self.x) & 0xFFFF
    def aby(self): return (self.fetch16() + self.y) & 0xFFFF
    def izx(self):
        z = (self.fetch() + self.x) & 255
        return self.rd(z) | self.rd((z + 1) & 255) << 8
    def izy(self):
        z = self.fetch()
        return ((self.rd(z) | self.rd((z + 1) & 255) << 8) + self.y) & 0xFFFF

    def _table(self):
        t = {}
        modes = {'zp': self.zp, 'zpx': self.zpx, 'zpy': self.zpy, 'ab': self.ab, 'abx': self.abx,
                 'aby': self.aby, 'izx': self.izx, 'izy': self.izy}

        def imm_or(mode):
            if mode == 'imm':
                return lambda: self.fetch()
            f = modes[mode]
            return lambda: self.rd(f())

        def load(reg, mode):
            g = imm_or(mode)
            def op():
                setattr(self, reg, self.nz(g()))
            return op

        def store(reg, mode):
            f = modes[mode]
            return lambda: self.wr(f(), getattr(self, reg))

        def alu(kind, mode):
            g = imm_or(mode)
            def op():
                v = g()
                if kind == 'ora': self.a = self.nz(self.a | v)
                elif kind == 'and': self.a = self.nz(self.a & v)
                elif kind == 'eor': self.a = self.nz(self.a ^ v)
                elif kind in ('adc', 'sbc'):
                    if kind == 'sbc': v ^= 255
                    r = self.a + v + self.c
                    self.v = int(((self.a ^ r) & (v ^ r) & 0x80) != 0)
                    self.c = r >> 8
                    self.a = self.nz(r & 255)
                elif kind == 'cmp': self.cmp(self.a, v)
            return op

        def rmw(kind, mode):
            if mode == 'acc':
                def op():
                    self.a = self.shift(kind, self.a)
                return op
            f = modes[mode]
            def op():
                a = f()
                self.wr(a, self.shift(kind, self.rd(a)))
            return op

        enc = {
            'ora': (0x09, 0x05, 0x15, 0x0D, 0x1D, 0x19, 0x01, 0x11),
            'and': (0x29, 0x25, 0x35, 0x2D, 0x3D, 0x39, 0x21, 0x31),
            'eor': (0x49, 0x45, 0x55, 0x4D, 0x5D, 0x59, 0x41, 0x51),
            'adc': (0x69, 0x65, 0x75, 0x6D, 0x7D, 0x79, 0x61, 0x71),
            'cmp': (0xC9, 0xC5, 0xD5, 0xCD, 0xDD, 0xD9, 0xC1, 0xD1),
            'sbc': (0xE9, 0xE5, 0xF5, 0xED, 0xFD, 0xF9, 0xE1, 0xF1),
        }
        for k, codes in enc.items():
            for code, mode in zip(codes, ('imm', 'zp', 'zpx', 'ab', 'abx', 'aby', 'izx', 'izy')):
                t[code] = alu(k, mode)
        lda = (0xA9, 0xA5, 0xB5, 0xAD, 0xBD, 0xB9, 0xA1, 0xB1)
        for code, mode in zip(lda, ('imm', 'zp', 'zpx', 'ab', 'abx', 'aby', 'izx', 'izy')):
            t[code] = load('a', mode)
        for code, mode in zip((0xA2, 0xA6, 0xB6, 0xAE, 0xBE), ('imm', 'zp', 'zpy', 'ab', 'aby')):
            t[code] = load('x', mode)
        for code, mode in zip((0xA0, 0xA4, 0xB4, 0xAC, 0xBC), ('imm', 'zp', 'zpx', 'ab', 'abx')):
            t[code] = load('y', mode)
        for code, mode in zip((0x85, 0x95, 0x8D, 0x9D, 0x99, 0x81, 0x91), ('zp', 'zpx', 'ab', 'abx', 'aby', 'izx', 'izy')):
            t[code] = store('a', mode)
        for code, mode in zip((0x86, 0x96, 0x8E), ('zp', 'zpy', 'ab')):
            t[code] = store('x', mode)
        for code, mode in zip((0x84, 0x94, 0x8C), ('zp', 'zpx', 'ab')):
            t[code] = store('y', mode)
        for k, base in (('asl', 0x00), ('rol', 0x20), ('lsr', 0x40), ('ror', 0x60)):
            for off, mode in ((0x0A, 'acc'), (0x06, 'zp'), (0x16, 'zpx'), (0x0E, 'ab'), (0x1E, 'abx')):
                t[base + off] = rmw(k, mode)
        for k, codes in (('inc', (0xE6, 0xF6, 0xEE, 0xFE)), ('dec', (0xC6, 0xD6, 0xCE, 0xDE))):
            for code, mode in zip(codes, ('zp', 'zpx', 'ab', 'abx')):
                t[code] = rmw(k, mode)
        for code, mode in ((0xE0, 'imm'), (0xE4, 'zp'), (0xEC, 'ab')):
            g = imm_or(mode)
            t[code] = (lambda g: lambda: self.cmp(self.x, g()))(g)
        for code, mode in ((0xC0, 'imm'), (0xC4, 'zp'), (0xCC, 'ab')):
            g = imm_or(mode)
            t[code] = (lambda g: lambda: self.cmp(self.y, g()))(g)

        def bit(f):
            def op():
                v = self.rd(f())
                self.n, self.v, self.z = v >> 7, v >> 6 & 1, int((self.a & v) == 0)
            return op
        t[0x24] = bit(self.zp)
        t[0x2C] = bit(self.ab)

        def branch(flag, want):
            def op():
                off = self.fetch()
                if getattr(self, flag) == want:
                    self.pc = (self.pc + (off - 256 if off & 128 else off)) & 0xFFFF
            return op
        for code, flag, want in ((0x10, 'n', 0), (0x30, 'n', 1), (0x50, 'v', 0), (0x70, 'v', 1),
                                 (0x90, 'c', 0), (0xB0, 'c', 1), (0xD0, 'z', 0), (0xF0, 'z', 1)):
            t[code] = branch(flag, want)

        def jmp():
            self.pc = self.fetch16()
        def jmpi():
            a = self.fetch16()
            self.pc = self.rd(a) | self.rd((a & 0xFF00) | ((a + 1) & 255)) << 8
        def jsr():
            a = self.fetch16()
            r = (self.pc - 1) & 0xFFFF
            self.push(r >> 8)
            self.push(r & 255)
            self.pc = a
        def rts():
            lo = self.pull()
            self.pc = ((self.pull() << 8 | lo) + 1) & 0xFFFF
        def rti():
            self.setp(self.pull())
            lo = self.pull()
            self.pc = self.pull() << 8 | lo
        def brk():
            raise Halt('BRK at %04X' % ((self.pc - 1) & 0xFFFF))
        t.update({0x4C: jmp, 0x6C: jmpi, 0x20: jsr, 0x60: rts, 0x40: rti, 0x00: brk})
        t.update({
            0xEA: lambda: None,
            0x18: lambda: setattr(self, 'c', 0), 0x38: lambda: setattr(self, 'c', 1),
            0x58: lambda: setattr(self, 'i', 0), 0x78: lambda: setattr(self, 'i', 1),
            0xB8: lambda: setattr(self, 'v', 0), 0xD8: lambda: setattr(self, 'd', 0),
            0xF8: lambda: (_ for _ in ()).throw(Halt('SED')),
            0xAA: lambda: setattr(self, 'x', self.nz(self.a)), 0x8A: lambda: setattr(self, 'a', self.nz(self.x)),
            0xA8: lambda: setattr(self, 'y', self.nz(self.a)), 0x98: lambda: setattr(self, 'a', self.nz(self.y)),
            0xBA: lambda: setattr(self, 'x', self.nz(self.s)), 0x9A: lambda: setattr(self, 's', self.x),
            0xE8: lambda: setattr(self, 'x', self.nz((self.x + 1) & 255)),
            0xCA: lambda: setattr(self, 'x', self.nz((self.x - 1) & 255)),
            0xC8: lambda: setattr(self, 'y', self.nz((self.y + 1) & 255)),
            0x88: lambda: setattr(self, 'y', self.nz((self.y - 1) & 255)),
            0x48: lambda: self.push(self.a), 0x68: lambda: setattr(self, 'a', self.nz(self.pull())),
            0x08: lambda: self.push(self.p()), 0x28: lambda: self.setp(self.pull()),
        })
        return t

    def cmp(self, r, v):
        d = r - v
        self.c = int(d >= 0)
        self.nz(d & 255)

    def shift(self, kind, v):
        if kind == 'asl': self.c, v = v >> 7, (v << 1) & 255
        elif kind == 'lsr': self.c, v = v & 1, v >> 1
        elif kind == 'rol': c = self.c; self.c, v = v >> 7, ((v << 1) | c) & 255
        elif kind == 'ror': c = self.c; self.c, v = v & 1, (v >> 1) | (c << 7)
        elif kind == 'inc': v = (v + 1) & 255
        elif kind == 'dec': v = (v - 1) & 255
        return self.nz(v)

    def call(self, addr, a=0, sentinel=0xFFF0, limit=2_000_000):
        """JSR addr with A set; run until it returns to the sentinel."""
        r = (sentinel - 1) & 0xFFFF
        self.push(r >> 8)
        self.push(r & 255)
        self.a = a
        self.pc = addr
        ops = self.ops
        n = 0
        while self.pc != sentinel:
            op = self.fetch()
            f = ops.get(op)
            if f is None:
                raise Halt('illegal opcode %02X at %04X' % (op, (self.pc - 1) & 0xFFFF))
            f()
            n += 1
            if n > limit:
                raise Halt('no return after %d instructions' % limit)
        self.steps += n
        return self.a
