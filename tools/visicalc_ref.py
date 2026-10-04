#!/usr/bin/env python3
"""VisiCalc worksheets (/SS files): the reference the VISICALC overlay is
tested against -- parser, evaluator and display, written from observations
of VisiCalc itself (docs/VISICALC-FORMAT.md).

    visicalc_ref.py FILE [--width N]     # prints the sheet as VisiCalc shows it
    visicalc_ref.py --selftest

A /SS file is the keystrokes that rebuild the sheet: one line per non-empty
cell, `>B3:` (go to B3) then what was typed there, from the bottom right to
the top left, then the global settings (`/W1`, `/GOC`, `/GRA`, `/GC9`...)
and `/X...` (the window's corner and the cursor). Only what was typed is
stored, never a result: the sheet is recalculated on load, once, in the
recalculation order, and a formula that refers to a formula not yet
recalculated in that pass reads ERROR (its value before the pass).

Numbers are VisiCalc's: decimal, six base-100 digits (12 decimal digits
aligned on pairs), every operation TRUNCATED to them, exponent such that
1E-66 <= |x| < 1E62, outside of which a result is ERROR. Operators are
evaluated strictly from left to right (2+3*4 is 20), unary minus binds
first (-2^2 is 4).
"""
import sys
from fractions import Fraction

EMAX, EMIN = 31, -32            # value = 0.p1p2..p6 (base 100) x 100^e
ONE_E12, ONE_E10 = 10 ** 12, 10 ** 10


class Err(Exception):
    pass


# -- numbers -----------------------------------------------------------------

class Num:
    """A VisiCalc number: sign, mantissa m (0, or 10^10 <= m < 10^12: six
    base-100 digits, the first non-zero), exponent e; value = m * 100^(e-6)."""
    __slots__ = ('neg', 'm', 'e')

    def __init__(self, neg=False, m=0, e=0):
        self.neg, self.m, self.e = (neg and m != 0), m, (e if m else 0)

    @staticmethod
    def norm(neg, m, e):
        """Normalize, truncating: what every VisiCalc operation does."""
        if m == 0:
            return Num()
        while m >= ONE_E12:
            m //= 100
            e += 1
        while m < ONE_E10:
            m *= 100
            e -= 1
        if e > EMAX or e < EMIN:
            raise Err('range')
        return Num(neg, m, e)

    @staticmethod
    def from_fraction(fr):
        """An exact rational, truncated to VisiCalc's digits."""
        if fr == 0:
            return Num()
        neg = fr < 0
        fr = abs(fr)
        e = 0
        while fr >= Fraction(100) ** e:
            e += 1
        while fr < Fraction(100) ** (e - 1):
            e -= 1
        m = int(fr * Fraction(100) ** (6 - e))
        return Num.norm(neg, m, e)

    def frac(self):
        v = Fraction(self.m) * Fraction(100) ** (self.e - 6)
        return -v if self.neg else v

    @staticmethod
    def from_int(i):
        return Num.from_fraction(Fraction(i))

    def is_zero(self):
        return self.m == 0

    def __neg__(self):
        return Num(not self.neg, self.m, self.e)

    def __repr__(self):
        return 'Num(%s)' % digits_plain(self)


def add(a, b):
    if a.m == 0:
        return b
    if b.m == 0:
        return a
    if (a.e, a.m) < (b.e, b.m):
        a, b = b, a                    # a: the larger magnitude
    mb = b.m // 100 ** (a.e - b.e) if a.e - b.e < 7 else 0
    if a.neg == b.neg:
        return Num.norm(a.neg, a.m + mb, a.e)
    return Num.norm(a.neg, a.m - mb, a.e)


def sub(a, b):
    return add(a, -b)


def mul(a, b):
    if a.m == 0 or b.m == 0:
        return Num()
    return Num.norm(a.neg != b.neg, a.m * b.m, a.e + b.e - 6)


def div(a, b):
    if b.m == 0:
        raise Err('div0')
    if a.m == 0:
        return Num()
    q = a.m * 10 ** 14 // b.m          # at least 12 significant digits
    return Num.norm(a.neg != b.neg, q, a.e - b.e - 1)


def cmp(a, b):
    fa, fb = a.frac(), b.frac()
    return (fa > fb) - (fa < fb)


def parse_number(s, i):
    """A number literal at s[i:]: digits, an optional point, an optional
    E exponent (signed). Returns (Num, next index) or None."""
    j = i
    n = len(s)
    while j < n and s[j].isdigit():
        j += 1
    if j < n and s[j] == '.':
        j += 1
        while j < n and s[j].isdigit():
            j += 1
    body = s[i:j]
    if body in ('', '.'):
        return None
    ex = 0
    if j < n and s[j] == 'E':
        k = j + 1
        sign = 1
        if k < n and s[k] in '+-':
            sign = -1 if s[k] == '-' else 1
            k += 1
        k0 = k
        while k < n and s[k].isdigit():
            k += 1
        if k > k0:
            ex = sign * int(s[k0:k])
            j = k
    if '.' in body:
        a, b = body.split('.')
        fr = Fraction(int(a or '0') * 10 ** len(b) + int(b or '0'), 10 ** len(b))
    else:
        fr = Fraction(int(body))
    if fr == 0:
        return Num(), j
    try:
        if abs(ex) > 99:
            raise Err('range')
        return Num.from_fraction(fr * Fraction(10) ** ex), j
    except Err as e:
        e.end = j                         # out of range: where it ends
        raise


# -- display -----------------------------------------------------------------

def digits_plain(x):
    """The exact decimal writing of x, VisiCalc style (.5, not 0.5)."""
    d, X = sig_digits(x)
    if not d:
        return '0'
    return ('-' if x.neg else '') + plain(d, X)


def sig_digits(x):
    """(digit string without leading or trailing zeros, decimal exponent X)
    with |x| = d[0].d[1:] x 10^X."""
    if x.m == 0:
        return '', 0
    s = str(x.m)
    # m has 11 or 12 digits; value = m * 10^(2e-12)
    X = len(s) - 1 + 2 * x.e - 12
    return s.rstrip('0'), X


def plain(d, X):
    """Digits d with exponent X written without exponent."""
    if X >= 0:
        ip = d[:X + 1].ljust(X + 1, '0')
        fp = d[X + 1:]
        return ip + ('.' + fp if fp else '')
    return '.' + '0' * (-X - 1) + d


def round_digits(d, keep):
    """d rounded half up to its first `keep` digits (keep >= 0): (digits,
    carried) where carried means one more leading digit (999 -> 1000)."""
    if keep >= len(d):
        return d.ljust(keep, '0'), False
    if keep < 0:
        return '', False
    head = d[:keep]
    if d[keep] >= '5':
        v = int(head or '0') + 1
        t = str(v).rjust(keep, '0') if keep else str(v)
        if len(t) > keep:
            return t, True
        return t, False
    return head, False


def fmt_general(x, n):
    """x in at most n characters (n = column width - 1), the way VisiCalc's
    general format writes it; None if it cannot."""
    d, X = sig_digits(x)
    if not d:
        return '0'
    sgn = '-' if x.neg else ''
    exact = sgn + plain(d, X)
    if len(exact) <= n:
        return exact
    if X >= -3:                           # at most two zeros after the point
        I = X + 1 if X >= 0 else 0        # integer digits
        dec = n - len(sgn) - I - 1        # decimals that fit after the point
        if X <= -2 and dec < 3:           # below .1, three decimals or nothing
            return fmt_sci(sgn, d, X, n)
        if dec >= 0:
            keep = X + 1 + dec            # significant digits kept
            r, carried = round_digits(d, keep)
            if carried:                   # a power of ten, written short
                t = sgn + plain('1', X + 1)
                if '.' not in t:
                    t += '.'
                return t if len(t) <= n else (t[:n] if t.index('.') <= n else None)
            if keep <= 0:                 # rounds to nothing: 0., unsigned
                return '0.' if n >= 2 else '0'
            if X >= 0:
                return sgn + r[:X + 1] + '.' + r[X + 1:]
            return sgn + '.' + '0' * (-X - 1) + r
        if dec == -1:                     # the integer part fills the field
            r, carried = round_digits(d, X + 1)
            if not carried:
                return sgn + r
            return fmt_sci(sgn, '1', X + 1, n)
    return fmt_sci(sgn, d, X, n)


def fmt_sci(sgn, d, X, n):
    es = 'E%d' % X
    k = n - len(sgn) - len(es)            # room for the mantissa
    if k < 1:
        return None
    if len(d) == 1:                       # an exact one-digit mantissa
        if X < 0 and k >= 2:
            return sgn + d + '.' + es
        return sgn + d + es
    if len(d) + 1 <= k:
        return sgn + d[0] + '.' + d[1:] + es
    dec = k - 2
    if dec < 0:
        r, carried = round_digits(d, 1)
        return None if carried else sgn + r + es
    r, carried = round_digits(d, 1 + dec)
    ip = 2 if carried else 1
    return sgn + (r[:ip] + '.' + r[ip:])[:k] + es


def fmt_fixed(x, places, n=99):
    """x rounded half up (away from zero) to `places` decimals, written with
    exactly that many: /F$ (2) and /FI (0). A leading 0 before the point,
    and no minus sign on a result that rounds to zero (its place is kept);
    None if it does not fit in n characters."""
    d, X = sig_digits(x)
    keep = X + 1 + places
    r, carried = round_digits(d, keep) if d else ('', False)
    if carried:
        X += 1
        keep += 1
    v = int(r) if r else 0
    s = str(v).rjust(places + 1, '0')
    body = s[:len(s) - places] + ('.' + s[len(s) - places:] if places else '')
    sgn = '-' if x.neg else ''
    if len(sgn + body) > n and body.startswith('0.') and d:
        body = body[1:]                   # the leading zero goes first
    if len(sgn + body) > n:
        return None
    if not v:
        sgn = ' ' if sgn else ''          # -0.00: the sign's place, blank
    return sgn + body


def fit_right(t, w):
    """A number's text in a column of width w: one blank at least on the
    left, right-aligned; '>' across the field when it does not fit."""
    n = w - 1
    if t is None or len(t) > n:
        t = '>' * n
    return (' ' * w + t)[-w:] if w > 0 else ''


# -- cells and values ------------------------------------------------------------

MAXCOL, MAXROW = 62, 254        # A..BK, 1..254: VisiCalc's sheet
ERROR, NA, TRUE, FALSE = 'ERROR', 'NA', 'TRUE', 'FALSE'
EMPTY = 'EMPTY'                 # a blank cell, or a label, read by a formula


def col_name(c):
    return chr(65 + c) if c < 26 else chr(64 + c // 26) + chr(65 + c % 26)


def parse_ref(s, i):
    """A cell name at s[i:] (A1, BK254): ((col, row), next) or None."""
    j = i
    while j < len(s) and 'A' <= s[j] <= 'Z' and j - i < 2:
        j += 1
    if j == i:
        return None
    letters = s[i:j]
    k = j
    while k < len(s) and s[k].isdigit() and k - j < 3:
        k += 1
    if k == j:
        return None
    c = ord(letters[0]) - 65 if len(letters) == 1 else (ord(letters[0]) - 64) * 26 + ord(letters[1]) - 65
    r = int(s[j:k])
    if c > MAXCOL or r < 1 or r > MAXROW:
        return None
    return (c, r), k


FMTS = 'GILR$*D'


class Cell:
    __slots__ = ('kind', 'fmt', 'text', 'value', 'raw', 'long')

    def __init__(self, kind, fmt, text, raw='', long=False):
        self.kind = kind        # 'label', 'repeat', 'value', 'blank', 'cmd'
        self.fmt = fmt          # '' (default) or one of G I L R $ *
        self.text = text        # the label, the repeated pattern, or the formula
        self.value = None
        self.raw = raw          # the line, without its '>'
        self.long = long        # longer than the 255 characters read

    def status(self):
        """What the overlay's first row shows after the cell's name: the
        line read again from its first 79 characters."""
        c = parse_cell('>' + self.raw[:79])
        if c is None:
            return ''
        s = ' /F' + c.fmt if c.fmt else ''
        s += ' (L) ' if c.kind in ('label', 'repeat', 'blank') else ' (V) '
        return s + (c.text if c.kind != 'repeat' else '/-' + c.text) \
            if c.kind != 'label' else s + c.text


def parse_cell(line):
    """A cell line: ((col, row), Cell) or None."""
    rr = parse_ref(line, 1)
    if rr is None or rr[1] >= len(line) or line[rr[1]] != ':':
        return None
    body = line[rr[1] + 1:]
    fmt = ''
    while body.startswith('/F') and len(body) >= 3:
        if body[2] in FMTS:
            fmt = '' if body[2] == 'D' else body[2]
        body = body[3:]
    raw = line[1:]
    if body.startswith('"'):
        return Cell('label', fmt, body[1:], raw)
    if 'A' <= body[:1] <= 'Z':
        return Cell('label', fmt, body, raw)     # typed, a letter starts a label
    if body.startswith('/-'):
        return Cell('repeat', fmt, body[2:], raw)
    if body.startswith('/'):
        return Cell('cmd', fmt, body, raw)
    if body == '':
        return Cell('blank', fmt, '', raw)
    return Cell('value', fmt, body, raw)


FUNCS0 = ('NA', 'ERROR', 'PI', 'TRUE', 'FALSE')
FUNCS1 = ('ABS', 'INT', 'SQRT', 'EXP', 'LN', 'LOG10', 'SIN', 'COS', 'TAN',
          'ASIN', 'ACOS', 'ATAN', 'NOT', 'ISNA', 'ISERROR')
FUNCSL = ('SUM', 'MIN', 'MAX', 'COUNT', 'AVERAGE', 'AND', 'OR', 'CHOOSE')
MAXDEPTH = 12                   # parentheses and function calls, nested


class Sheet:
    def __init__(self, text):
        self.cells = {}
        self.width = 9
        self.colw = {}          # per-column widths (/GCC, VisiCalc 2.x)
        self.gfmt = ''
        self.order = 'C'
        self.cursor = (0, 1)
        self.corner = (0, 1)
        self.parse(text)

    # -- the file ----------------------------------------------------------------
    def parse(self, text):
        """The lines as the overlay reads them: high bits off, the text
        ends at a zero byte, CR or LF ends a line, 255 characters kept."""
        text = text.split('\0')[0]
        self.valid = True
        window = 1
        for line in text.replace('\r', '\n').split('\n'):
            long = len(line) > 255
            line = line[:255]
            if not line:
                continue
            if line.startswith('>'):
                pc = None if parse_ref(line, 1) is None else parse_cell(line)
                if pc is None:
                    self.valid = False      # the overlay refuses the file
                    continue
                (c, r) = parse_ref(line, 1)[0]
                if pc.kind == 'cmd':
                    if pc.text.startswith('/GCC') and window == 1:
                        w = 0
                        for ch in pc.text[4:]:
                            if not ch.isdigit():
                                break
                            w = w * 10 + int(ch)
                            if w > 255:
                                w = 0
                                break
                        if 1 <= w <= 77:
                            self.colw[c] = w
                    continue            # a command typed there: the cell keeps its contents
                pc.long = long
                self.cells[(c, r)] = pc
                continue
            if not line.startswith('/'):
                self.valid = False
                continue
            # global settings: those of window 1, before any ';'
            if window == 1:
                self.glob(line.split(';')[0])
            if ';' in line:
                window = 2
        if not self.cells:
            self.valid = False

    def glob(self, g):
        if g.startswith('/X'):
            refs = []
            i = 0
            while i < len(g):
                if g[i] == '>':
                    rr = parse_ref(g, i + 1)
                    if rr and rr[1] < len(g) and g[rr[1]] == ':':
                        refs.append(rr[0])
                i += 1
            if refs:
                self.corner = refs[0]
            if len(refs) > 1:
                self.cursor = refs[1]
        elif g.startswith('/GC') and g[3:4].isdigit():
            w = 0
            for ch in g[3:]:
                if not ch.isdigit():
                    return
                w = w * 10 + int(ch)
                if w > 255:
                    return
            if 3 <= w <= 77:
                self.width = w
        elif g.startswith('/GF') and len(g) == 4 and g[3] in FMTS:
            self.gfmt = '' if g[3] == 'D' else g[3]
        elif g in ('/GOC', '/GOR'):
            self.order = g[3]

    # -- the load-time recalculation ---------------------------------------------
    def recalc(self):
        for cell in self.cells.values():
            if cell.kind == 'value':
                cell.value = ERROR
                v = constant(cell.text)
                if v is not None and not isinstance(v, str):
                    cell.value = v
        keys = sorted((k for k, c in self.cells.items() if c.kind == 'value'),
                      key=(lambda k: (k[0], k[1])) if self.order == 'C' else (lambda k: (k[1], k[0])))
        for k in keys:
            cell = self.cells[k]
            if cell.value == ERROR:
                cell.value = ERROR if cell.long else self.evaluate(cell.text)

    # -- reading cells ----------------------------------------------------------------
    def ref_value(self, c, r):
        cell = self.cells.get((c, r))
        if cell is None or cell.kind != 'value':
            return EMPTY
        return cell.value

    def evaluate(self, text):
        if text.startswith('+'):
            try:
                p = parse_number(text, 1) if not text[1:2].isalpha() else None
            except Err as e:
                p = (ERROR, e.end)
            if p is not None and p[1] == len(text):
                return ERROR             # VisiCalc: "+7" alone reads ERROR
        try:
            ev = Evaluator(self, text)
            v = ev.expr()
            if ev.i != len(text):
                return ERROR
            if v == EMPTY:
                return Num()
            return v
        except Err:
            return ERROR


def constant(text):
    """A number typed as such (5, .5, 1E3): known before the recalculation;
    ERROR when out of range (it is then evaluated, and is ERROR again)."""
    try:
        p = parse_number(text, 0)
    except Err:
        return ERROR
    if p is None or p[1] != len(text):
        return None
    return p[0]


def num_of(v):
    """A value as a number operand: EMPTY counts as 0."""
    if v == EMPTY:
        return Num()
    return v


def worst(*vals):
    """The error a list of operands yields, ERROR before NA; None if none."""
    if ERROR in vals:
        return ERROR
    if NA in vals:
        return NA
    return None


class Evaluator:
    """Recursive descent, as visicalc.s does it -- with its limits: an
    operand nested 24 deep, or more values put aside than its stack holds
    (16 of 9 bytes; a list function's state takes 17), and the formula is
    ERROR."""
    def __init__(self, sheet, s):
        self.sh, self.s, self.i = sheet, s, 0
        self.depth = self.vsp = 0

    def peek(self):
        return self.s[self.i] if self.i < len(self.s) else ''

    def push(self, n, limit):
        if self.vsp >= limit:
            raise Err('stack')
        self.vsp += n

    def expr(self, depth=0):
        v = self.operand()
        while True:
            ch = self.peek()
            if ch in ('+', '-', '*', '/', '^'):
                self.i += 1
                self.push(9, 144)
                w = self.operand()
                self.vsp -= 9
                v = arith(ch, v, w)
            elif ch in ('<', '>', '='):
                op = ch
                self.i += 1
                if op in '<>' and self.peek() in ('=', '>') and not (op == '>' and self.peek() == '>'):
                    op += self.peek()
                    self.i += 1
                self.push(9, 144)
                w = self.operand()
                self.vsp -= 9
                v = compare(op, v, w)
            else:
                return v

    def operand(self):
        self.depth += 1
        if self.depth >= 24:
            raise Err('depth')
        v = self.operand1()
        self.depth -= 1
        return v

    def operand1(self):
        ch = self.peek()
        if ch == '-':
            self.i += 1
            v = num_of(self.operand())
            if isinstance(v, Num):
                return -v
            return v if v in (ERROR, NA) else ERROR
        if ch == '+':
            self.i += 1
            return self.operand()
        if ch == '(':
            self.i += 1
            v = self.expr()
            if self.i == len(self.s):
                return v                 # VisiCalc closes what the end leaves open
            if self.peek() != ')':
                raise Err('paren')
            self.i += 1
            return v
        if ch == '@':
            return self.function()
        if ch.isdigit() or ch == '.':
            try:
                p = parse_number(self.s, self.i)
            except Err as e:              # out of range: an ERROR value, not
                self.i = e.end            # a syntax error (@ISERROR(1E99) is
                return ERROR              # TRUE in VisiCalc)
            if p is None:
                raise Err('number')
            self.i = p[1]
            return p[0]
        rr = parse_ref(self.s, self.i)
        if rr is None:
            raise Err('operand')
        (c, r), self.i = rr
        if self.s.startswith('...', self.i):
            raise Err('range here')
        return self.sh.ref_value(c, r)

    def argend(self):
        """After an argument: False when a comma says more follow, True at
        a closing parenthesis or the formula's end (which closes it)."""
        ch = self.peek()
        if ch == '':
            return True
        self.i += 1
        if ch == ')':
            return True
        if ch != ',':
            raise Err('args')
        return False

    def range_at(self):
        """A range A1...A9 at i: its cells, i after it; None (i unmoved)
        when there is none."""
        rr = parse_ref(self.s, self.i)
        if rr is None or not self.s.startswith('...', rr[1]):
            return None
        (c1, r1), j = rr
        rr2 = parse_ref(self.s, j + 3)
        if rr2 is None:
            raise Err('range')
        (c2, r2), self.i = rr2
        if c1 != c2 and r1 != r2:
            raise Err('range 2d')
        return [(c, r) for c in range(min(c1, c2), max(c1, c2) + 1)
                for r in range(min(r1, r2), max(r1, r2) + 1)]

    def function(self):
        self.i += 1
        j = self.i
        while self.i < len(self.s) and ('A' <= self.s[self.i] <= 'Z' or
                                        (self.i > j and self.s[self.i].isdigit())):
            self.i += 1
        name = self.s[j:self.i]
        if name in FUNCS0:
            return {'NA': NA, 'ERROR': ERROR, 'TRUE': TRUE, 'FALSE': FALSE,
                    'PI': Num.from_fraction(Fraction(31415926536, 10 ** 10))}[name]
        if name not in FUNCS1 + FUNCSL + ('IF', 'NPV', 'LOOKUP'):
            raise Err('unknown function')
        if self.peek() != '(':
            raise Err('args')
        self.i += 1
        if name in FUNCS1:
            v = self.expr()
            if not self.argend():
                raise Err('arity')
            return applied(func1, name, v)
        if name in FUNCSL:
            items = []
            while True:
                cells = self.range_at()
                if cells is not None:
                    items.append(('range', cells))
                else:
                    self.push(17, 127)
                    items.append(('value', self.expr()))
                    self.vsp -= 17
                if self.argend():
                    return applied(self.listfunc, name, items)
        if name == 'IF':
            cnd = num_of(self.expr())
            code = 0 if cnd == TRUE else 1 if cnd == FALSE else 2
            if code == 2:
                self.push(9, 144)
            if self.argend():
                raise Err('arity')
            a = self.expr()
            self.push(9, 144)
            if self.argend():
                raise Err('arity')
            b = self.expr()
            if not self.argend():
                raise Err('arity')
            if code == 2:
                return cnd if cnd in (ERROR, NA) else ERROR
            return a if code == 0 else b
        x = self.expr()                     # NPV, LOOKUP: a value, a range
        if self.argend():
            raise Err('arity')
        cells = self.range_at()
        if cells is None or not self.argend():
            raise Err('arity')
        if name == 'NPV':
            return applied(self.npv, x, cells)
        return applied(self.lookup, x, cells)

    def listfunc(self, name, items):
        vals = []
        for kind, it in items:
            if kind == 'value':
                vals.append(it)
            else:
                for (c, r) in it:
                    v = self.sh.ref_value(c, r)
                    if v == EMPTY and name not in ('MIN', 'MAX'):
                        continue
                    vals.append(v)
        if name == 'CHOOSE':
            if not vals:
                raise Err('arity')
            n = num_of(vals[0])
            if n in (ERROR, NA):
                return n
            if not isinstance(n, Num):
                return ERROR
            k = int(n.frac())
            if k < 1 or k >= len(vals):
                return NA
            return vals[k]
        if name == 'COUNT':
            return Num.from_int(len(vals))
        if name in ('AND', 'OR'):
            e = worst(*vals)
            if e:
                return e
            if any(v not in (TRUE, FALSE) for v in vals):
                return ERROR
            res = all(v == TRUE for v in vals) if name == 'AND' else any(v == TRUE for v in vals)
            return TRUE if res else FALSE
        e = worst(*vals)
        if e:
            return e
        nums = [num_of(v) for v in vals]
        if any(not isinstance(v, Num) for v in nums):
            return ERROR
        if name in ('SUM', 'AVERAGE'):
            acc = Num()
            for v in nums:
                acc = add(acc, v)
            if name == 'SUM':
                return acc
            if not nums:
                return ERROR              # 0/0
            return div(acc, Num.from_int(len(nums)))
        if not vals:
            return Num()
        best = vals[0]
        for v in nums[1:]:
            c = cmp(v, num_of(best))
            if (c < 0) if name == 'MIN' else (c > 0):
                best = v
        return best

    def npv(self, rate, cells):
        rate = num_of(rate)
        if rate in (ERROR, NA):
            return rate
        if not isinstance(rate, Num):
            return ERROR
        f = add(Num.from_int(1), rate)
        p = Num.from_int(1)
        acc = Num()
        for (c, r) in cells:
            v = num_of(self.sh.ref_value(c, r))
            p = mul(p, f)
            if v in (ERROR, NA):
                return v
            if not isinstance(v, Num):
                return ERROR
            acc = add(acc, div(v, p))
        return acc

    def lookup(self, x, cells):
        x = num_of(x)
        if x in (ERROR, NA):
            return x
        if not isinstance(x, Num) or len(cells) < 2:
            return ERROR
        vertical = cells[0][0] == cells[-1][0]
        hit = None
        for (c, r) in cells:
            v = num_of(self.sh.ref_value(c, r))
            if v in (ERROR, NA):
                return v
            if not isinstance(v, Num):
                return ERROR
            if cmp(v, x) > 0:
                break
            hit = (c, r)
        if hit is None:
            return NA
        c, r = hit
        if vertical:
            c += 1
        else:
            r += 1
        if c > MAXCOL or r > MAXROW:
            return ERROR
        return num_of(self.sh.ref_value(c, r))


def applied(f, *args):
    """A function's value: an arithmetic error in it is ERROR, a value,
    not the formula's end (the syntax's are)."""
    try:
        return f(*args)
    except Err:
        return ERROR


def arith(op, a, b):
    a, b = num_of(a), num_of(b)
    e = worst(a, b)
    if e:
        return e
    if not isinstance(a, Num) or not isinstance(b, Num):
        return ERROR
    try:
        return arith_num(op, a, b)
    except Err:
        return ERROR


def arith_num(op, a, b):
    if op == '+':
        return add(a, b)
    if op == '-':
        return sub(a, b)
    if op == '*':
        return mul(a, b)
    if op == '/':
        return div(a, b)
    return power(a, b)


def compare(op, a, b):
    a, b = num_of(a), num_of(b)
    e = worst(a, b)
    if e:
        return e
    if isinstance(a, Num) and isinstance(b, Num):
        c = cmp(a, b)
    elif a in (TRUE, FALSE) and b in (TRUE, FALSE) and op in ('=', '<>'):
        c = 0 if a == b else 1
    else:
        return ERROR
    res = {'=': c == 0, '<>': c != 0, '<': c < 0, '>': c > 0, '<=': c <= 0, '>=': c >= 0}[op]
    return TRUE if res else FALSE


def func1(name, v):
    v = num_of(v)
    if name == 'ISNA':
        return TRUE if v == NA else FALSE
    if name == 'ISERROR':
        return TRUE if v == ERROR else FALSE
    e = worst(v)
    if e:
        return e
    if name == 'NOT':
        if v not in (TRUE, FALSE):
            return ERROR
        return FALSE if v == TRUE else TRUE
    if not isinstance(v, Num):
        return ERROR
    if name == 'ABS':
        return Num(False, v.m, v.e)
    if name == 'INT':
        return Num.from_fraction(Fraction(int(v.frac())))
    return transcendental(name, v)


# The powers and the functions below go through Applesoft's ROM in the
# overlay (its 9-digit binary arithmetic, not VisiCalc's own series): here,
# Python's floats rounded to 9 significant digits, which is what FOUT gives
# back. tools/test_visicalc.py runs the real ROM for the overlay's side.
import math

ROM_FUNCS = {'SQRT': math.sqrt, 'EXP': math.exp, 'LN': math.log, 'LOG10': math.log10,
             'SIN': math.sin, 'COS': math.cos, 'TAN': math.tan, 'ATAN': math.atan,
             'ASIN': math.asin, 'ACOS': math.acos}


def rom_result(f):
    if f != f or abs(f) >= 1.7e38:
        raise Err('rom')
    if f == 0 or abs(f) < 2.94e-39:
        return Num()
    return Num.from_fraction(Fraction(float('%.9g' % f)).limit_denominator(10 ** 12)
                             if False else Fraction('%.9g' % f))


def to_float(x):
    return float(x.frac())


def power(a, b):
    try:
        x, y = to_float(a), to_float(b)
        if x == 0:
            if y <= 0:
                raise Err('pow')
            return Num()
        if x < 0 and y != int(y):
            raise Err('pow')
        return rom_result(x ** y)
    except (OverflowError, ValueError, ZeroDivisionError):
        raise Err('pow')


def transcendental(name, v):
    try:
        return rom_result(ROM_FUNCS[name](to_float(v)))
    except (OverflowError, ValueError, ZeroDivisionError):
        raise Err('math')


# -- what a cell shows ---------------------------------------------------------------

def show_value(v, fmt, w):
    """A value in a column of width w, per its format."""
    n = w - 1
    if v in (ERROR, NA, TRUE, FALSE):
        t = v[:n]
        return (' ' + t).ljust(w)[:w] if fmt == 'L' else (' ' * w + t)[-w:]
    if v == EMPTY or v is None:
        return ' ' * w
    if fmt == '*':
        k = int(v.frac()) if not v.neg else 0
        return (' ' + '*' * min(max(k, 0), n)).ljust(w)[:w]
    if fmt == '$':
        t = fmt_fixed(v, 2, n)
    elif fmt == 'I':
        t = fmt_fixed(v, 0, n)
    else:
        t = fmt_general(v, n)
    if t is None:
        t = '>' * n
    if fmt == 'L':
        return (' ' + t).ljust(w)[:w]
    return (' ' * w + t)[-w:]


def cell_text(sheet, c, r, w=None):
    """Exactly the w characters VisiCalc shows for the cell."""
    if w is None:
        w = sheet.colw.get(c, sheet.width)
    cell = sheet.cells.get((c, r))
    if cell is None:
        return ' ' * w
    fmt = cell.fmt or sheet.gfmt
    if cell.kind == 'label':
        t = cell.text[:w]
        return t.rjust(w) if fmt == 'R' else t.ljust(w)
    if cell.kind == 'repeat':
        pat = cell.text or ' '
        return (pat * w)[:w]
    if cell.kind in ('blank', 'cmd'):
        return ' ' * w
    return show_value(cell.value, fmt, w)


# -- the overlay's screen ------------------------------------------------------------

SHEETROWS = 20
KEYS = 'SPC Page,B Back,<> Cols,R A1,ESC'


class View:
    """The VISICALC overlay's screen: row 0 the cursor's cell, row 1 the
    column names, rows 2-21 the sheet, row 23 the key bar."""

    def __init__(self, sheet, name='SHEET'):
        self.sh, self.name = sheet, name
        self.curc, self.curr = sheet.cursor
        self.leftc, self.top = sheet.corner

    def width(self, c):
        return self.sh.colw.get(c, self.sh.width)

    def layout(self):
        colx, x = {}, 3
        for c in range(self.leftc, MAXCOL + 1):
            w = self.width(c)
            if x + w > 80:
                break
            colx[c] = x
            x += w
        return colx

    def settle(self):
        if self.curr < self.top:
            self.top = self.curr
        if self.curr - (SHEETROWS - 1) > self.top:
            self.top = self.curr - (SHEETROWS - 1)
        if self.curc < self.leftc:
            self.leftc = self.curc
        while self.curc not in self.layout() and self.leftc < self.curc:
            self.leftc += 1

    def screen(self):
        """(rows, inverse) as the harness prints them: 24 x 80 each."""
        self.settle()
        rows = [[' '] * 80 for _ in range(24)]
        inv = [[' '] * 80 for _ in range(24)]

        def put(x, y, s, rv=False):
            for i, ch in enumerate(s):
                if x + i < 80:
                    rows[y][x + i] = ch
                    inv[y][x + i] = '#' if rv else ' '
        colx = self.layout()
        for c, x in colx.items():
            put(x + self.width(c) // 2 - (c >= 26), 1, col_name(c))
        for y in range(SHEETROWS):
            if self.top + y <= MAXROW:
                put(0, y + 2, '%3d' % (self.top + y))
        for (c, r), cell in self.sh.cells.items():
            if c in colx and self.top <= r < self.top + SHEETROWS and not cell.long:
                put(colx[c], r - self.top + 2, cell_text(self.sh, c, r))
        cur = self.sh.cells.get((self.curc, self.curr))
        st = col_name(self.curc) + str(self.curr)
        if cur is not None:
            st += cur.status()
        put(0, 0, st[:79])
        if self.curc in colx:
            t = cell_text(self.sh, self.curc, self.curr) if cur is not None and not cur.long \
                else ' ' * self.width(self.curc)
            if cur is not None and cur.long:
                t = cell_text(self.sh, self.curc, self.curr)
            put(colx[self.curc], self.curr - self.top + 2, t, True)
        put(0, 23, self.name)
        put(30, 23, KEYS)
        return [''.join(r) for r in rows], [''.join(r) for r in inv]

    def key(self, k):
        """One key, as the overlay takes it; False for Escape or Q."""
        o = ord(k) & 0x7F
        if o == 0x1B:
            return False
        if ord('a') <= o:
            o &= 0xDF
        k = chr(o)
        if k == 'Q':
            return False
        if o == 0x0B and self.curr > 1:
            self.curr -= 1
        if o == 0x0A and self.curr < MAXROW:
            self.curr += 1
        if o == 0x08 and self.curc > 0:
            self.curc -= 1
        if o == 0x15 and self.curc < MAXCOL:
            self.curc += 1
        if k in ' \r':
            self.curr = min(self.curr + SHEETROWS, MAXROW)
            self.top = min(self.top + SHEETROWS, MAXROW - SHEETROWS + 1)
        elif k == 'B':
            self.curr = max(self.curr - SHEETROWS, 1)
            self.top = max(self.top - SHEETROWS, 1)
        elif k in '>.':
            colx = self.layout()
            c = self.leftc
            while c <= MAXCOL and c in colx:
                c += 1
            if c <= MAXCOL:
                self.leftc = self.curc = c
        elif k in '<,':
            x = 3
            while self.leftc and x + self.width(self.leftc - 1) <= 80:
                x += self.width(self.leftc - 1)
                self.leftc -= 1
            self.curc = self.leftc
        elif k == 'R':
            self.curc = self.leftc = 0
            self.curr = self.top = 1
        return True


def load(text):
    sh = Sheet(text)
    sh.recalc()
    return sh


def main(argv):
    if '--selftest' in argv:
        return selftest()
    path = argv[1]
    data = open(path, 'rb').read()
    text = bytes(b & 0x7F for b in data).decode('latin-1')
    sh = load(text)
    maxc = max([c for c, r in sh.cells] + [0])
    maxr = max([r for c, r in sh.cells] + [1])
    print('   ' + ''.join(col_name(c).center(sh.colw.get(c, sh.width)) for c in range(maxc + 1)))
    for r in range(1, maxr + 1):
        print('%3d' % r + ''.join(cell_text(sh, c, r) for c in range(maxc + 1)))
    return 0


def selftest():
    sh = load('>C3:2+3*4\n>B3:-2^2\n>A3:7\n>B2:+A2*2\n>A2:+A3\n>C1:5\n>B1:+C1\n>A1:+B1\n/W1\n/GOC\n/GRA\n/GC9\n/X-/X>A1:>B3:\n')
    assert cell_text(sh, 0, 1) == '    ERROR', cell_text(sh, 0, 1)
    assert cell_text(sh, 2, 3) == '       20'
    assert cell_text(sh, 1, 2) == '       14'
    print('visicalc_ref: selftest ok')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
