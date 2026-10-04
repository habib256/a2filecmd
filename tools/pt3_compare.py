#!/usr/bin/env python3
"""Compare GROUiK's PT3 engine with pt3_lib, register by register, frame by frame.

    python3 tools/pt3_compare.py [--frames N] [--limit K] [--cpu 6502|65c02] FILE_OR_DIR...

Runs, under sim65 (tools/ppt3_sim.py), on each module:
  G  GROUiK's engine as A2FC plays it (PPT3_OUT), and its raw AYREGS (the
     player's own ZX values, before the conversion);
  P  pt3_lib as A2FC plays it;
  U  pt3_lib without the conversion: the ZX Spectrum values.
Since 2026-10-03 both convert every period the same way, to the
Mockingboard's 1.0227 MHz: round(P x 1181/2048) (1.0227/1.7734).
and classifies every difference:
  tone    R0-R5: G's period vs P's, and both against the exact Mockingboard
          period U x 1.0227/1.7734 (cents; > 0 = sharp);
  noise   R6: both (ZX value & 31) converted;
  mixer   R7, volumes R8-R10, envelope shape R13: expected identical;
  env     R11-R12: both converted;
  end     the frame each engine stops at;
  logic   GROUiK run again with the ZX note table written over its own: its
          registers must then equal U's; any difference is a difference of
          the players' logic, not of scaling (first frame/register reported).
Prints a summary per module and overall; --json writes the numbers.
No file is written outside a temporary directory unless --json is given.
"""
import argparse
import json
import math
import sys
import tempfile
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ppt3_sim

EXACT = 1.0227 / 1.7734
REFERENCE = json.loads((Path(__file__).with_name('pt3_frequency_reference.json')).read_text())


def zx_table(m):
    """The ZX note table both players select for this header (Ivan Roshin's
    rules: table number at 99, versions 3.0-3.3 take the old variants)."""
    v = m[13] - 48
    if not 0 <= v <= 9:
        v = 6
    old = v < 4
    name = {0: 'PT_33_34r' if old else 'PT_34_35', 1: 'ST', 2: 'ASM_34r' if old else 'ASM_34_35',
            3: 'REAL_34r' if old else 'REAL_34_35'}[m[99] & 3]
    return REFERENCE[name]


def logic(gz, u):
    """GROUiK with the ZX table vs pt3_lib unconverted: the first frame and
    the registers where the players' LOGIC differs (scaling set aside)."""
    first, regs = None, Counter()
    for i in range(1, min(len(gz), len(u))):
        if gz[i][0] or u[i][0]:
            break
        a, b = gz[i][2], u[i][1]
        for r in range(14):
            x, y = a[r], b[r]
            if r == 6:
                x, y = x & 31, y & 31
            elif r in (1, 3, 5):
                x, y = x & 15, y & 15
            if x != y:
                regs[r] += 1
                if first is None:
                    first = (i, r, a.hex(), b.hex())
    return first, regs


def tone(r, i):
    return r[2 * i] | (r[2 * i + 1] & 15) << 8


def cents(period, ref):
    if period <= 0 or ref <= 0:
        return None
    return 1200 * math.log2(ref / period)


def compare(g, p, u):
    s = Counter()
    tone_g, tone_p = [], []
    examples = {}
    n = min(len(g), len(p), len(u))
    for i in range(1, n):
        gr, go, graw = g[i]
        pr, po = p[i]
        ur, uo = u[i]
        if gr or pr or ur:
            break
        s['frames'] += 1
        for c in range(3):
            if graw[8 + c] == 0 and po[8 + c] == 0 and uo[8 + c] & 31 == 0:
                continue                         # silent channel: its period is moot
            G, P, U = tone(go, c), tone(po, c), tone(uo, c)
            ref = U * EXACT
            s['tone'] += 1
            if G != P:
                s['tone_diff'] += 1
                if abs(G - P) > max(2, P // 32):
                    s['tone_far'] += 1
                    examples.setdefault('tone_far', (i, c, G, P, U))
            cg, cp = cents(G, ref), cents(P, ref)
            if cg is not None and cp is not None and U >= 24:
                tone_g.append(cg)
                tone_p.append(cp)
        if go[6] != (((graw[6] & 31) * 1181 + 1024) >> 11):
            s['noise_not_converted'] += 1
        if (graw[6] & 31) != (uo[6] & 31):
            s['noise_raw_diff'] += 1
            examples.setdefault('noise_raw', (i, graw[6], uo[6]))
        if graw[6] > 31:
            s['noise_raw_over_31'] += 1
        for name, regs in (('mixer', (7,)), ('volume', (8, 9, 10)), ('shape', (13,))):
            if any(go[r] != po[r] for r in regs):
                s[name + '_diff'] += 1
                examples.setdefault(name, (i, go[regs[0]:regs[-1] + 1].hex(), po[regs[0]:regs[-1] + 1].hex()))
        ge, pe, ue = go[11] | go[12] << 8, po[11] | po[12] << 8, uo[11] | uo[12] << 8
        re_ = graw[11] | graw[12] << 8
        if re_ != ue:
            s['env_raw_diff'] += 1
            examples.setdefault('env_raw', (i, re_, ue))
        if ge != pe:
            s['env_diff'] += 1
    s['g_end'] = next((i for i, f in enumerate(g) if f[0]), 0)
    s['p_end'] = next((i for i, f in enumerate(p) if f[0]), 0)
    s['g_result'] = g[-1][0]
    s['p_result'] = p[-1][0]
    return s, tone_g, tone_p, examples


def stats(xs):
    if not xs:
        return None
    xs = sorted(xs)
    return {'mean': sum(xs) / len(xs), 'min': xs[0], 'max': xs[-1], 'median': xs[len(xs) // 2]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('paths', nargs='+')
    ap.add_argument('--frames', type=int, default=3000)
    ap.add_argument('--limit', type=int, default=0)
    ap.add_argument('--cpu', default='6502')
    ap.add_argument('--json')
    a = ap.parse_args()
    files = []
    for p in map(Path, a.paths):
        files += sorted(q for q in p.rglob('*') if q.suffix.upper() == '.PT3') if p.is_dir() else [p]
    if a.limit:
        step = max(1, len(files) // a.limit)
        files = files[::step][:a.limit]
    total = Counter()
    all_g, all_p = [], []
    report = {}
    with tempfile.TemporaryDirectory(prefix='pt3-compare-') as t:
        G = ppt3_sim.Grouik(t, a.cpu)
        P = ppt3_sim.Pt3lib(t, a.cpu, True)
        U = ppt3_sim.Pt3lib(t, a.cpu, False)
        for f in files:
            data = f.read_bytes()
            if len(data) > 0x4000 or len(data) < 202:
                total['skipped'] += 1
                continue
            try:
                g, p, u = G.run(data, a.frames), P.run(data, a.frames), U.run(data, a.frames)
            except Exception as e:      # a harness failure is reported, not hidden
                total['harness_error'] += 1
                print(f'{f}: harness error {e}')
                continue
            s, tg, tp, ex = compare(g, p, u)
            first, regs = logic(G.run(data, a.frames, note_table=zx_table(data)), u)
            s['logic_same'] = first is None
            total['logic_same'] += first is None
            if first:
                ex['logic_first'] = first
                for r, k in regs.items():
                    total['logic_r%d' % r] += k
            total.update({k: v for k, v in s.items() if k not in ('g_end', 'p_end', 'g_result', 'p_result', 'logic_same')})
            total['modules'] += 1
            total['g_trip'] += s['g_result'] == 1
            total['p_error'] += s['p_result'] == 1
            total['end_same'] += s['g_end'] == s['p_end']
            all_g += tg
            all_p += tp
            report[str(f)] = {'counts': dict(s), 'examples': {k: list(v) for k, v in ex.items()}}
            print(f'{f.name}: frames {s["frames"]} g_end {s["g_end"]} p_end {s["p_end"]} '
                  f'tone_diff {s["tone_diff"]}/{s["tone"]} far {s["tone_far"]} vol {s["volume_diff"]} '
                  f'mix {s["mixer_diff"]} shape {s["shape_diff"]} env {s["env_diff"]} '
                  f'noise_raw {s["noise_raw_diff"]} env_raw {s["env_raw_diff"]} '
                  f'g_res {s["g_result"]} p_res {s["p_result"]} logic {"same" if first is None else first[:2]}')
    summary = {'totals': dict(total), 'cents_grouik': stats(all_g), 'cents_pt3lib': stats(all_p)}
    print(json.dumps(summary, indent=1))
    if a.json:
        Path(a.json).write_text(json.dumps({'summary': summary, 'modules': report}, indent=1))


if __name__ == '__main__':
    main()
