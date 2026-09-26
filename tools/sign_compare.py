#!/usr/bin/env python3
"""Relational comparisons whose sign the two editions do not read alike.

cc65 2.19, the compiler of the 65C02 edition, still applies the integer
rules of the old cc65 (`promoteint` in its expr.c): in `a OP b`, the result
is unsigned as soon as ONE operand is unsigned -- an `unsigned char`
included, where C promotes it to a signed `int`. So `target >= pan->count`,
an int against an unsigned char, is an unsigned comparison there, and a
negative target is larger than any count; `uc - 1 < n` is unsigned too, and
`long < unsigned int` is an unsigned long comparison. cc65 master, the 6502
edition's compiler, follows C. A second 2.19 defect makes it worse: the
difference of two unsigned chars is often computed on eight bits
(`int d = a - b` gives 254 for 1 - 3, not -2 nor 65534).

A regular expression cannot see any of this: the types of both operands, the
integer promotions and the conversions decide it. So this reads clang's
syntax tree of each unit (a 16-bit `int` target, `char` unsigned, the cc65
headers: the types cc65 sees) and, for every `<`, `<=`, `>`, `>=`, works out

- the sign of the comparison in C (clang's own conversions, which is what
  cc65 master compiles),
- the sign cc65 2.19 gives it (the operands' types re-derived bottom-up with
  its rule: unsigned if either side is unsigned, `unsigned char` included;
  shifts promote their left operand as C does; unary `-` and `~` keep an
  unsigned char unsigned),
- the range of values each operand can take in C, from its type and the
  arithmetic that builds it (an unsigned char is 0..255, `b * 256` of one
  overflows a 16-bit int, `x & 0x7F` is 0..127...).

A comparison is reported when it is unsigned in either edition while one
operand may be negative, or when an operand is byte arithmetic that may
overflow a signed int (`b * 256`). Those are exactly the sites where an
edition can answer differently from arithmetic. The same reasoning covers
the other operations whose bits depend on the sign: `/`, `%`, `>>` and a
widening to `long` of such an operand. Also reported: every difference of
two unsigned chars that may be negative and whose high byte is used (the
second 2.19 defect); one narrowed back to a char, alone or through `+`,
`-`, `&`..., is exact on eight bits.

The model is checked against both real compilers by
tools/test_sign_compare.py, which also runs this over the sources.

A site proven harmless is written so that both editions and C agree: the
signed side cast to `unsigned` (cc65 2.19 already compiled it so, and the
6502 edition's unsigned comparison is the shorter one), or a sign test
first. When neither reads well, `/* sign-ok: <why> */` on the line of the
operator, or alone on the line above it, accepts it, with the proof.

    python3 tools/sign_compare.py [--arch enh|6502|both] [FILE.c ...]
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANNOTATION = 'sign-ok:'

# Every C unit the Makefile compiles for the Apple II (as test_cc65_traps).
UNITS = ([ROOT / name for name in ('src/a2fc.c', 'src/format.c', 'src/loader.c',
                                   'src/memory_swap.c')]
         + sorted((ROOT / 'src/plugins').glob('*.c')))

# The defines of each edition (Makefile CLDEFS), plus what the launcher's
# floppy variant adds. The two editions compile different #ifdef branches.
EDITIONS = {
    'enh': ['-D__APPLE2ENH__', '-DA2FC_BIG_BINARY2'],
    '6502': ['-DA2FC_6502', '-DA2FC_NOMOUSE', '-DA2FC_BIG_BINARY2'],
}
EXTRA_VARIANTS = {'loader.c': [[], ['-DA2FC_FLOPPY']]}

RELATIONAL = {'<', '<=', '>', '>='}
SHIFT = {'<<', '>>'}
BOOLEAN = {'<', '<=', '>', '>=', '==', '!=', '&&', '||'}

INT_TYPES = {
    '_Bool': (8, True), 'char': (8, True), 'unsigned char': (8, True),
    'signed char': (8, False), 'short': (16, False), 'short int': (16, False),
    'unsigned short': (16, True), 'int': (16, False), 'signed int': (16, False),
    'signed': (16, False), 'unsigned int': (16, True), 'unsigned': (16, True),
    'long': (32, False), 'long int': (32, False), 'signed long': (32, False),
    'unsigned long': (32, True), 'unsigned long int': (32, True),
}


HEAD = Path(os.environ.get('CC65_HEAD', str(Path.home() / 'opt/cc65-head')))


def cc65_include(arch='enh'):
    """The include directory of the cc65 that builds an edition: the
    machine's cc65 for the 65C02, cc65 master (CC65_HEAD) for the 6502."""
    if arch == '6502':
        c = HEAD / 'share/cc65/include'
        return c if (c / 'conio.h').exists() else None
    exe = shutil.which('cc65')
    candidates = []
    if os.environ.get('CC65_INC'):
        candidates.append(Path(os.environ['CC65_INC']))
    if exe:
        base = Path(exe).resolve().parent.parent
        candidates += [base / 'share/cc65/include', base / 'include']
    candidates += [Path('/usr/share/cc65/include'), Path('/usr/local/share/cc65/include')]
    for c in candidates:
        if (c / 'conio.h').exists():
            return c
    return None


def clang():
    return shutil.which('clang')


def int_type(node):
    """(bits, unsigned) of an expression node, None when not an integer."""
    t = node.get('type') or {}
    q = t.get('desugaredQualType') or t.get('qualType') or ''
    q = re.sub(r'\b(const|volatile|register|static)\b', '', q).strip()
    q = re.sub(r'\s+', ' ', q)
    if q in INT_TYPES:
        return INT_TYPES[q]
    if q.startswith('enum '):
        return (16, False)
    return None


def full(t):
    bits, uns = t
    return (0, (1 << bits) - 1) if uns else (-(1 << (bits - 1)), (1 << (bits - 1)) - 1)


def promote_c(t):
    """C's integer promotion on a 16-bit int machine."""
    return (16, False) if t[0] < 16 else t


def promote_219(a, b):
    """cc65 2.19's promoteint: long if either is, unsigned if either is."""
    return (32 if 32 in (a[0], b[0]) else 16, a[1] or b[1])


class Info:
    """What a node computes: its cc65 2.19 type, its C value range,
    whether its C arithmetic may have overflowed, its constant value."""
    __slots__ = ('k', 'lo', 'hi', 'wrapped', 'const')

    def __init__(self, k, lo, hi, wrapped=False, const=None):
        self.k, self.lo, self.hi, self.wrapped, self.const = k, lo, hi, wrapped, const


class Sources(dict):
    """The text of the project's files, by the name clang gives them (a
    path relative to the repository, absolute, or through `..`); the cc65
    headers are not ours and are left out."""
    def __init__(self, unit):
        super().__init__()
        self.unit = os.path.normpath(str(unit))

    def canonical(self, name):
        if name is None:
            return None
        path = os.path.normpath(os.path.join(str(ROOT), name))
        if path == self.unit or path.startswith(str(ROOT / 'src') + os.sep):
            return path
        return None

    def __contains__(self, name):
        return self.canonical(name) is not None

    def __missing__(self, name):
        path = self.canonical(name)
        if path is None:
            raise KeyError(name)
        data = Path(path).read_bytes()
        self[name] = data
        return data

    def get(self, name, default=None):
        return self[name] if name in self else default


class Unit:
    def __init__(self, data, sources):
        self.sources = sources
        self.findings = []
        self.inventory = []             # every comparison the editions sign differently
        self.enums = {}
        self.cur_file = None
        self.cur_line = None
        self.collect_enums(data)
        self.walk(data, None)

    # -- locations (the JSON dump prints file and line only when they change)
    def bare(self, loc):
        if 'file' in loc:
            self.cur_file = loc['file']
        if 'line' in loc:
            self.cur_line = loc['line']
        return self.cur_file, self.cur_line, loc.get('offset'), loc.get('tokLen', 0)

    def location(self, loc):
        """The expansion point (file, line, offset, tokLen) of a location."""
        if not loc:
            return None
        if 'spellingLoc' in loc or 'expansionLoc' in loc:
            where = None
            if 'spellingLoc' in loc:
                where = self.bare(loc['spellingLoc'])
            if 'expansionLoc' in loc:
                where = self.bare(loc['expansionLoc'])
            return where
        return self.bare(loc)

    def visit_locations(self, node):
        loc = self.location(node.get('loc'))
        rng = node.get('range') or {}
        begin = self.location(rng.get('begin'))
        end = self.location(rng.get('end'))
        return loc, begin, end

    # -- enums
    def collect_enums(self, node):
        stack = [node]
        while stack:
            n = stack.pop()
            if n.get('kind') == 'EnumDecl':
                value = -1
                for c in n.get('inner', []):
                    if c.get('kind') != 'EnumConstantDecl':
                        continue
                    init = c.get('inner')
                    if init and init[0].get('kind') == 'ConstantExpr' and 'value' in init[0]:
                        value = int(init[0]['value'])
                    else:
                        value += 1
                    self.enums[c['id']] = value
            stack.extend(n.get('inner', []))

    # -- the value analysis
    def info(self, n):
        kind = n.get('kind')
        t = int_type(n)
        inner = n.get('inner', [])
        if kind in ('ParenExpr', 'ConstantExpr') and inner:
            i = self.info(inner[0])
            if kind == 'ConstantExpr' and 'value' in n and t:
                v = int(n['value'])
                return Info(i.k if i else t, v, v, False, v)
            return i
        if t is None:
            return None
        if kind == 'IntegerLiteral':
            v = int(n['value'])
            return Info(t, v, v, False, v)
        if kind == 'CharacterLiteral':
            v = int(n['value'])
            return Info((16, False), v, v, False, v)
        if kind == 'DeclRefExpr':
            ref = n.get('referencedDecl', {})
            if ref.get('kind') == 'EnumConstantDecl' and ref.get('id') in self.enums:
                v = self.enums[ref['id']]
                return Info((16, False), v, v, False, v)
        if kind == 'UnaryExprOrTypeTraitExpr':
            return Info((16, True), 0, 65535)
        if kind in ('ImplicitCastExpr', 'CStyleCastExpr') and inner:
            i = self.info(inner[0])
            if i is None:
                return Info(t, *full(t))
            cast = n.get('castKind')
            if kind == 'ImplicitCastExpr' and cast in ('LValueToRValue', 'NoOp'):
                return i
            lo, hi = full(t)
            if lo <= i.lo and i.hi <= hi:
                r = (i.lo, i.hi)
            else:
                r = (lo, hi)
            const = i.const if i.const is not None and lo <= i.const <= hi else None
            if const is None and i.const is not None:
                const = i.const & ((1 << t[0]) - 1)
                if not t[1] and const > hi:
                    const -= 1 << t[0]
                r = (const, const)
            # An implicit conversion is invisible to cc65 2.19's typing;
            # an explicit cast gives the type written.
            k = i.k if kind == 'ImplicitCastExpr' else t
            return Info(k, r[0], r[1], i.wrapped, const)
        if kind == 'BinaryOperator' and len(inner) == 2:
            op = n['opcode']
            if op in BOOLEAN:
                self.info(inner[0]), self.info(inner[1])
                return Info((16, False), 0, 1)
            if op == '=':
                self.info(inner[1])
                return Info(t, *full(t))
            if op == ',':
                return self.info(inner[1])
            a, b = self.info(inner[0]), self.info(inner[1])
            if a is None or b is None:
                return Info(t, *full(t))
            if op in SHIFT:
                k = promote_c(a.k)
            else:
                k = promote_219(a.k, b.k)
            lo, hi = self.arith(op, a, b, t)
            const = None
            if a.const is not None and b.const is not None:
                const = self.fold(op, a.const, b.const)
                if const is not None:
                    lo = hi = const
            wrapped = a.wrapped or b.wrapped
            tl, th = full(t)
            if not (tl <= lo and hi <= th):
                # A signed overflow of values that came from narrower types
                # (`b * 256`, `b << 8` of a byte). An int variable plus one
                # may overflow too, in theory: that is not this defect.
                bounded = all((i.lo, i.hi) != (tl, th) for i in (a, b))
                wrapped = wrapped or (not t[1] and bounded)
                lo, hi = tl, th
            return Info(k, lo, hi, wrapped, const if const is not None and tl <= const <= th else None)
        if kind == 'CompoundAssignOperator':
            for c in inner:
                self.info(c)
            return Info(t, *full(t))
        if kind == 'UnaryOperator' and inner:
            op = n['opcode']
            a = self.info(inner[0])
            if a is None:
                return Info(t, *full(t))
            if op == '!':
                return Info((16, False), 0, 1)
            if op in ('-', '~', '+'):
                k = (16, a.k[1]) if a.k[0] < 16 else a.k
                if op == '+':
                    lo, hi = a.lo, a.hi
                elif op == '-':
                    lo, hi = -a.hi, -a.lo
                else:
                    lo, hi = ~a.hi, ~a.lo
                const = None if a.const is None else (a.const if op == '+' else
                                                      -a.const if op == '-' else ~a.const)
                tl, th = full(t)
                wrapped = a.wrapped
                if not (tl <= lo and hi <= th):
                    lo, hi, wrapped = tl, th, wrapped or (not t[1] and (a.lo, a.hi) != (tl, th))
                    const = None
                return Info(k, lo, hi, wrapped, const)
            # ++, --, *, &: the operand's own type, any value
            return Info(t, *full(t))
        if kind == 'ConditionalOperator' and len(inner) == 3:
            self.info(inner[0])
            a, b = self.info(inner[1]), self.info(inner[2])
            if a is None or b is None:
                return Info(t, *full(t))
            return Info(promote_219(a.k, b.k), min(a.lo, b.lo), max(a.hi, b.hi),
                        a.wrapped or b.wrapped)
        # A variable, a member, an element, a call: any value of its type.
        return Info(t, *full(t))

    @staticmethod
    def fold(op, a, b):
        try:
            if op == '+': return a + b
            if op == '-': return a - b
            if op == '*': return a * b
            if op == '/': return int(a / b) if b else None
            if op == '%': return (abs(a) % abs(b)) * (1 if a >= 0 else -1) if b else None
            if op == '&': return a & b
            if op == '|': return a | b
            if op == '^': return a ^ b
            if op == '<<': return a << b if 0 <= b < 32 else None
            if op == '>>': return a >> b if 0 <= b < 32 else None
        except (OverflowError, ValueError):
            return None
        return None

    @staticmethod
    def arith(op, a, b, t):
        tl, th = full(t)
        if op == '+':
            return a.lo + b.lo, a.hi + b.hi
        if op == '-':
            return a.lo - b.hi, a.hi - b.lo
        if op == '*':
            c = [a.lo * b.lo, a.lo * b.hi, a.hi * b.lo, a.hi * b.hi]
            return min(c), max(c)
        if op == '/':
            if a.lo >= 0 and b.lo > 0:
                return a.lo // b.hi, a.hi // b.lo
            if a.lo >= 0 and b.lo >= 0:
                return 0, a.hi
            return tl, th
        if op == '%':
            if a.lo >= 0 and b.lo > 0:
                return 0, min(a.hi, b.hi - 1)
            return tl, th
        if op == '&':
            if a.lo >= 0 and b.lo >= 0:
                return 0, min(a.hi, b.hi)
            if a.lo >= 0:
                return 0, a.hi
            if b.lo >= 0:
                return 0, b.hi
            return tl, th
        if op in ('|', '^'):
            if a.lo >= 0 and b.lo >= 0:
                return 0, (1 << max(a.hi, b.hi).bit_length()) - 1
            return tl, th
        if op == '<<':
            if a.lo >= 0 and b.lo >= 0 and b.hi < 32:
                return a.lo << b.lo, a.hi << b.hi
            return tl - 1, th + 1              # may overflow
        if op == '>>':
            if b.lo >= 0 and b.hi < 32:
                if a.lo >= 0:
                    return a.lo >> b.hi, a.hi >> b.lo
                return a.lo >> b.lo, max(a.hi >> b.lo, 0)
            return tl, th
        return tl, th

    # -- the walk
    def text(self, begin, end):
        if not begin or not end or begin[0] != end[0] or begin[0] not in self.sources:
            return '?'
        src = self.sources[begin[0]]
        return re.sub(r'\s+', ' ', src[begin[2]:end[2] + end[3]].decode('latin-1'))[:80]

    def annotated(self, where):
        src = self.sources.get(where[0])
        if src is None:
            return False
        lines = src.split(b'\n')
        n = where[1]
        line = lines[n - 1] if 0 < n <= len(lines) else b''
        above = lines[n - 2].strip() if 1 < n <= len(lines) + 1 else b''
        return ANNOTATION.encode() in line or (
            ANNOTATION.encode() in above and above.startswith(b'/*') and above.endswith(b'*/'))

    def report(self, kind, begin, text, detail):
        if not begin or begin[0] not in self.sources:
            return
        self.findings.append({
            'kind': kind, 'file': self.sources.canonical(begin[0]), 'line': begin[1], 'text': text,
            'detail': detail, 'annotated': self.annotated(begin)})

    def operand(self, n):
        """A comparison operand before its conversion to the common type."""
        while n.get('kind') == 'ImplicitCastExpr' and n.get('castKind') in (
                'IntegralCast', 'LValueToRValue', 'NoOp'):
            n = n['inner'][0]
        return n

    def walk(self, n, parent, low8=False):
        """`low8`: only the low eight bits of this node's value are used
        (it is narrowed to a char, alone or through +, -, *, &, |, ^, <<, a
        cast or a branch of ?:), so an 8-bit difference is exact there."""
        loc, begin, end = self.visit_locations(n)
        kind = n.get('kind')
        op = n.get('opcode')
        if kind == 'BinaryOperator' and op in RELATIONAL:
            self.check_relational(n, begin, end)
        if kind == 'BinaryOperator' and op == '-' and not low8:
            self.check_sub8(n, begin, end)
        if kind == 'BinaryOperator' and op in ('/', '%', '>>'):
            self.check_divide(n, begin, end)
        if kind in ('ImplicitCastExpr', 'CStyleCastExpr') and n.get('castKind') == 'IntegralCast':
            self.check_widen(n, begin, end)
        inner = [c for c in n.get('inner', []) if isinstance(c, dict)]
        keep = [False] * len(inner)
        t = int_type(n)
        if kind in ('ImplicitCastExpr', 'CStyleCastExpr'):
            keep = [low8 or (t is not None and t[0] == 8)] * len(inner)
        elif kind in ('ParenExpr', 'ConstantExpr'):
            keep = [low8] * len(inner)
        elif kind == 'BinaryOperator' and op in ('+', '-', '*', '&', '|', '^') and len(inner) == 2:
            keep = [low8, low8]
        elif kind == 'BinaryOperator' and op == '<<' and len(inner) == 2:
            keep = [low8, False]
        elif kind == 'UnaryOperator' and op in ('-', '~', '+'):
            keep = [low8] * len(inner)
        elif kind == 'ConditionalOperator' and len(inner) == 3:
            keep = [False, low8, low8]
        elif kind == 'CompoundAssignOperator' and len(inner) == 2 and op in (
                '+=', '-=', '*=', '&=', '|=', '^='):
            lhs = int_type(inner[0])
            keep = [False, lhs is not None and lhs[0] == 8]
        for c, k in zip(inner, keep):
            self.walk(c, n, k)

    def check_relational(self, n, begin, end):
        inner = n.get('inner', [])
        if len(inner) != 2:
            return
        ct = int_type(inner[0])
        if ct is None:
            return                              # pointers
        saved = self.cur_file, self.cur_line
        a, b = self.info(inner[0]), self.info(inner[1])
        la, lb = self.info(self.operand(inner[0])), self.info(self.operand(inner[1]))
        self.cur_file, self.cur_line = saved
        if None in (a, b, la, lb):
            return
        c_uns = ct[1]
        k_uns = promote_219(a.k, b.k)[1]
        negative = [s for s, i in (('left', la), ('right', lb)) if i.lo < 0]
        wrapped = [s for s, i in (('left', la), ('right', lb)) if i.wrapped]
        text = self.text(begin, end)
        if c_uns != k_uns or ((c_uns or k_uns) and negative):
            where = self.sources.canonical(begin[0]) if begin else None
            if where:
                self.inventory.append({
                    'file': where, 'line': begin[1], 'text': text,
                    'c': 'unsigned' if c_uns else 'signed',
                    'cc65-2.19': 'unsigned' if k_uns else 'signed',
                    'negative': bool(negative)})
        if (c_uns or k_uns) and negative:
            edition = ('both editions' if c_uns and k_uns else
                       '65C02 only (cc65 2.19)' if k_uns else '6502 only (cc65 master)')
            self.report('unsigned-compare', begin, text,
                        'unsigned in %s; %s operand may be negative'
                        % (edition, ' and '.join(negative)))
        elif wrapped:
            self.report('overflow-compare', begin, text,
                        '%s operand may overflow its type in C' % ' and '.join(wrapped))

    def check_divide(self, n, begin, end):
        """`/`, `%` and `>>` are the arithmetic whose bits depend on the
        sign: a signed operand that cc65 2.19 types unsigned, and that may
        be negative, divides as a large number there."""
        inner = n.get('inner', [])
        t = int_type(n)
        if len(inner) != 2 or t is None or t[1]:
            return
        a, b = self.info(inner[0]), self.info(inner[1])
        if a is None or b is None:
            return
        k = promote_c(a.k) if n['opcode'] == '>>' else promote_219(a.k, b.k)
        operands = [a] if n['opcode'] == '>>' else [a, b]
        if k[1] and any(i.lo < 0 for i in operands):
            self.report('unsigned-divide', begin, self.text(begin, end),
                        'unsigned in 65C02 only (cc65 2.19); an operand may be negative')

    def check_widen(self, n, begin, end):
        """A 16-bit value made a long: C extends the sign of an int, cc65
        2.19 does not when it typed the expression unsigned."""
        t = int_type(n)
        inner = n.get('inner', [])
        if t is None or t[0] != 32 or not inner:
            return
        ct = int_type(inner[0])
        i = self.info(inner[0])
        if ct is None or i is None or ct[0] != 16 or ct[1]:
            return
        if i.k[1] and i.lo < 0:
            self.report('unsigned-widen', begin, self.text(begin, end),
                        'may be negative: C (cc65 master) extends its sign to a long, '
                        'cc65 2.19 does not' + (' (and the int overflowed)' if i.wrapped else ''))
        elif i.wrapped:
            self.report('overflow-widen', begin, self.text(begin, end),
                        'an int that may have overflowed, made a long with that sign')

    def check_sub8(self, n, begin, end):
        inner = n.get('inner', [])
        if len(inner) != 2 or int_type(n) is None:
            return
        saved = self.cur_file, self.cur_line
        a, b = self.info(inner[0]), self.info(inner[1])
        self.cur_file, self.cur_line = saved
        if a is None or b is None or a.k != (8, True) or b.k != (8, True):
            return
        if a.lo >= b.hi:
            return
        self.report('uchar-difference', begin, self.text(begin, end),
                    'difference of two unsigned chars, computed on 8 bits by cc65 2.19')


def clang_args(unit, defines, inc):
    return [clang(), '--target=msp430', '-std=c99', '-fsyntax-only', '-funsigned-char',
            '-nostdinc', '-ferror-limit=0', '-isystem', str(inc),
            '-I', str(ROOT / 'src'), '-I', str(ROOT / 'src/plugins'),
            '-D__CC65__', '-D__APPLE2__', '-D__fastcall__=', '-D__cdecl__=',
            '-D__near__=', '-D__far__=', '-Dasm(...)=', '-D__A__=0', '-D__AX__=0',
            '-D__EAX__=0', '-DA2FC_VERSION="test"', *defines,
            '-Wno-everything', '-Xclang', '-ast-dump=json', str(unit)]


def scan_unit(unit, defines, inc):
    """The findings of one unit compiled with one set of defines."""
    result = subprocess.run(clang_args(unit, defines, inc), capture_output=True, cwd=ROOT)
    if not result.stdout:
        raise RuntimeError('%s: clang produced no tree: %s' % (unit, result.stderr[:500]))
    errors = [l for l in result.stderr.decode('latin-1').splitlines()
              if 'error:' in l and 'cc65' not in l and 'include/' not in l]
    if errors:
        raise RuntimeError('%s: clang cannot read it: %s' % (unit, errors[:3]))
    data = json.loads(result.stdout)
    u = Unit(data, Sources(unit))
    for f in u.findings + u.inventory:
        f['file'] = os.path.relpath(f['file'], ROOT)
    return u.findings, u.inventory


def run(units=None, arches=('enh', '6502')):
    """(findings, inventory) over the units and editions, each entry once
    per source site, with the editions it was seen in. Raises when clang or
    the cc65 headers are missing."""
    if not clang():
        raise FileNotFoundError('clang is missing')
    incs = {arch: cc65_include(arch) for arch in arches}
    if incs.get('enh', 1) is None:
        raise FileNotFoundError('the cc65 headers are missing')
    arches = [arch for arch in arches if incs[arch] is not None]
    jobs = []
    for unit in units or UNITS:
        for arch in arches:
            for extra in EXTRA_VARIANTS.get(unit.name, [[]]):
                jobs.append((unit, arch, EDITIONS[arch] + extra, incs[arch]))
    # The walk recurses along the tree: a long `||` chain is deep.
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 20000))
    threading.stack_size(64 << 20)
    with ThreadPoolExecutor(max_workers=os.cpu_count() or 4) as pool:
        results = list(pool.map(lambda j: (j, scan_unit(j[0], j[2], j[3])), jobs))
    out = []
    for which in (0, 1):
        merged = {}
        for (unit, arch, _, _), both in results:
            for f in both[which]:
                key = (f['file'], f['line'], f.get('kind'), f['text'])
                entry = merged.setdefault(key, dict(f, arches=set(), units=set()))
                entry['arches'].add(arch)
                entry['units'].add(unit.name)
        out.append(sorted(merged.values(), key=lambda f: (f['file'], f['line'], f.get('kind', ''))))
    return out[0], out[1]


def scan(units=None, arches=('enh', '6502')):
    """The findings only."""
    return run(units, arches)[0]


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--arch', choices=('enh', '6502', 'both'), default='both')
    p.add_argument('--all', action='store_true', help='also list annotated sites')
    p.add_argument('--inventory', action='store_true',
                   help='list every comparison the two compilers sign differently, '
                        'and the unsigned ones with an operand that may be negative')
    p.add_argument('files', nargs='*')
    args = p.parse_args()
    units = [Path(f).resolve() for f in args.files] or None
    arches = ('enh', '6502') if args.arch == 'both' else (args.arch,)
    findings, inventory = run(units, arches)
    if args.inventory:
        per = {}
        for f in inventory:
            print('%s:%d: %s  -- C %s, cc65 2.19 %s%s [%s]' % (
                f['file'], f['line'], f['text'], f['c'], f['cc65-2.19'],
                ', an operand may be negative' if f['negative'] else '',
                ','.join(sorted(f['arches']))))
            c = per.setdefault(f['file'], [0, 0])
            c[0] += 1
            c[1] += f['negative']
        for name, (n, neg) in sorted(per.items()):
            print('%-32s %4d sites, %3d with an operand that may be negative' % (name, n, neg))
        print('%d sites, %d with an operand that may be negative'
              % (len(inventory), sum(f['negative'] for f in inventory)))
        return 0
    shown = 0
    for f in findings:
        if f['annotated'] and not args.all:
            continue
        shown += 1
        print('%s:%d: %s: %s  -- %s [%s]%s' %(f['file'], f['line'], f['kind'], f['text'],
                                         f['detail'], ','.join(sorted(f['arches'])),
                                         ' (annotated)' if f['annotated'] else ''))
    print('%d site(s)' % shown, file=sys.stderr)
    return 1 if shown else 0


if __name__ == '__main__':
    sys.exit(main())
