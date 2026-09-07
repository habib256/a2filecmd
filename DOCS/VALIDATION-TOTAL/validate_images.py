"""Banc POM2 du visionneur d'images de TOTAL : un volume de test avec les
quatre formats (HGR brut, HGR RLE HGRR, DHGR brut AUX+MAIN, DHGR RLE DHRR),
demarre directement dans TOTAL ; chaque image est ouverte, la page graphique
comparee octet a octet a l'attendu, le format annonce verifie.

    python3 DOCS/VALIDATION-TOTAL/validate_images.py DOCS/VALIDATION-TOTAL
"""
import sys, os, re, json, time, shutil, tempfile, subprocess, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path.insert(0, 'SCOSWAMP.MORE/TOOLS')
import playtest as pt
out = pathlib.Path(sys.argv[1]); out.mkdir(parents=True, exist_ok=True)
labels = {n: int(a, 16) for a, n in re.findall(r'al ([0-9A-F]+) \.(\w+)', pathlib.Path('SCOSWAMP/SRC/total.lbl').read_text())}
TOOLS = ROOT / 'SCOSWAMP.MORE/TOOLS'

def decode(b, size):
    o = bytearray(); i = 8
    while len(o) < size:
        t = b[i]; i += 1
        if t & 128: o.extend([b[i]] * ((t & 127) + 3)); i += 1
        else: o.extend(b[i:i + t + 1]); i += t + 1
    assert len(o) == size and i == len(b)
    return bytes(o)

checks = []
def ok(label, cond, detail=''):
    print(('PASS ' if cond else 'FAIL ') + label, detail, flush=True)
    checks.append(dict(label=label, ok=bool(cond)))
    if not cond: raise AssertionError(label + ' ' + str(detail))

with tempfile.TemporaryDirectory(prefix='total-images-') as work:
    work = pathlib.Path(work); stage = work / 'vol'; (stage / 'IMG').mkdir(parents=True); (stage / 'TOTAL').mkdir()
    shutil.copy('SCOSWAMP/PRODOS.SYS', stage); shutil.copy('dist/.floppy/TOTAL.SYSTEM.SYS', stage); shutil.copy('SCOSWAMP/TOTAL/TOTAL.CODE.BIN', stage / 'TOTAL')
    hgr_raw = pathlib.Path('SPACETRIP/IMG/N001.HGR.BIN').read_bytes(); assert len(hgr_raw) == 8192
    (stage / 'IMG/HGR.RAW.BIN').write_bytes(hgr_raw)
    subprocess.run([str(TOOLS / 'build/scoswamp_hgr'), 'encode', 'SPACETRIP/IMG/N001.HGR.BIN', str(stage / 'IMG/HGR.RLE.BIN')], check=True, capture_output=True)
    hgrr = (stage / 'IMG/HGR.RLE.BIN').read_bytes(); assert hgrr[:8] == b'HGRR\x01\x00\x00\x20' and decode(hgrr, 8192) == hgr_raw
    dhrr = pathlib.Path('SCOSWAMP/DHGR/N000/N000.RLE.BIN').read_bytes(); dhgr_raw = decode(dhrr, 16384)
    (stage / 'IMG/DHGR.RAW.BIN').write_bytes(dhgr_raw); (stage / 'IMG/DHGR.RLE.BIN').write_bytes(dhrr)
    (stage / 'IMG/NOTE.TXT').write_bytes(b'not an image\r')
    subprocess.run([str(TOOLS / 'build/build_prodos_volume'), str(stage), str(TOOLS / 'prodos_boot.tmpl'), str(work / 'IMGTEST.hdv'), 'IMGTEST'], check=True, capture_output=True)
    p = pt.Pom2(str(work / 'IMGTEST.hdv'), port=6535)
    def value(name, n=2): return int.from_bytes(p.peek(labels['_total_' + name], n), 'little')
    def wait(test, what, seconds=15):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if test(): return
            time.sleep(.02)
        print('\n'.join(p.screen()), flush=True); raise AssertionError('Timed out: ' + what)
    def rows(): return p.screen()
    def has(needle): return any(needle in r for r in rows())
    def key(k): p.raw(k); time.sleep(.15)
    def cursor_row(x):
        main = p.peek(0x400, 1024); aux = p.peek(0x400, 1024, 'aux')
        for r in range(2, 20):
            base = 0x80 * (r % 8) + 0x28 * (r // 8)
            cells = [aux[base + c // 2] if c % 2 == 0 else main[base + c // 2] for c in range(x, x + 38)]
            if all(v < 0x80 for v in cells[:16]): return r
    def select(x, name):
        for _ in range(12): key(b'<')
        for _ in range(40):
            r = cursor_row(x); line = rows()[r][x:x + 38] if r is not None else ''
            if line.startswith(name + ' '): return
            key(b'\x0a')
        raise AssertionError('cannot select ' + name)
    def page(): return p.peek(0x2000, 8192, 'aux') + p.peek(0x2000, 8192)
    try:
        p.start(); wait(lambda: has('Type  Aux     Size'), 'TOTAL boot', 40); p.stable()
        ok('le volume de test demarre dans TOTAL', has('/IMGTEST'))
        select(0, 'IMG'); key(b'\r'); wait(lambda: has('/IMGTEST/IMG'), 'IMG'); p.stable()
        cases = [('HGR.RAW', 'HGR raw, 8192 bytes', None, hgr_raw, 'hgr'),
                 ('HGR.RLE', 'HGR RLE, 8192 bytes', None, hgr_raw, 'hgr'),
                 ('DHGR.RAW', 'DHGR raw, 16384 bytes', dhgr_raw[:8192], dhgr_raw[8192:], 'dhgr'),
                 ('DHGR.RLE', 'DHGR RLE, 16384 bytes', dhgr_raw[:8192], dhgr_raw[8192:], 'dhgr')]
        for name, text, aux_expected, main_expected, mode in cases:
            select(0, name); key(b'\r'); wait(lambda: value('view', 1) == 1, 'image ' + name); time.sleep(2.5)
            got = page()
            ok(name + ' : page MAIN identique', got[8192:] == main_expected)
            if aux_expected is not None: ok(name + ' : page AUX identique', got[:8192] == aux_expected)
            # une capture par format, pour l'oeil : HGR simple ou DHGR
            import urllib.request
            (out / ('img-' + name.lower() + '.ppm')).write_bytes(urllib.request.urlopen(p.base + '/screen.ppm').read())
            key(b' '); wait(lambda: value('view', 1) == 0, 'back ' + name); p.stable()
            ok(name + ' : format annonce', has(name + ': ' + text))
        select(0, 'NOTE'); key(b'I'); wait(lambda: value('view', 1) == 0, 'not image'); p.stable()
        ok('I sur un texte : refus explicite', has('NOTE: not an image'))
        (out / 'images-result.json').write_text(json.dumps(dict(checks=checks), indent=2) + '\n')
        print('PASS', len(checks), 'controles', flush=True)
    finally:
        p.stop()
