#!/usr/bin/env python3
"""Banc de FIXIT et REPAIR sur un volume de plus d'une page de bitmap.

    make all disk && python3 bench/bigvol.py
    A2FC_IMG=A2FILECMD-full python3 bench/bigvol.py      # la 65C02

Au-dela de 4 096 blocs, FIXIT et REPAIR gardent leurs reclamations de blocs
dans la memoire AUXILIAIRE ($4000-$5FFF, src/plugins/fixit_bits.inc) et ne
parcourent l'arbre qu'une fois, la ou la 0.8.8 le parcourait une fois par
page de bitmap. Le banc amorce un disque dur jetable et place en S5,D2
(`pom2_playtest --hd2`) un volume de 20 000 blocs, cinq pages de bitmap,
construit par `tools/mkvolume.py` puis casse sur l'hote en deux endroits
que l'oracle `tools/prodos_check.py` nomme : un sous-dossier, loin dans le
volume, qui compte mal ses fichiers (FILE_COUNT), et un bloc de la
quatrieme page marque occupe que personne ne reclame (BM_LOST).

Une seule session POM2 :

1. FIXIT pose la question de la profondeur, « Q quick (directories)  F full
   ESC back » ; Echap rend la main sans rien lire de plus, la memoire AUX
   intacte, et le verdict dit « Scan cancelled » ;
2. Q, puis N a la question « ALL /RAM files will be LOST. Continue? » :
   rien n'est parcouru, la memoire AUX est intacte, meme verdict ;
3. Q, puis Y : le controle rapide, titre « - QUICK », ne nomme que
   FILE_COUNT, au bloc et au rang de l'oracle ;
4. R repose la question de la profondeur mais pas celle de /RAM ; F : le
   controle complet nomme FILE_COUNT et BM_LOST au bloc de l'oracle, et
   prend plus de cycles que le rapide ;
5. Echap : le verdict compte deux constats, resident et pile C preserves,
   /RAM toujours en ligne ;
6. REPAIR : la question de /RAM est reposee (autre surcouche), le plan
   compte deux corrections sur deux blocs, F puis FIX, « rescan clean:
   repaired ».

Sur l'hote, a l'arret de POM2 : le volume est sain pour l'oracle et les
seuls blocs modifies sont la cle du sous-dossier et la page de bitmap du
bloc perdu. Les cycles des deux controles sont affiches : sur un vrai IIe,
un million de cycles font une seconde.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from xplug import boot_hd, menu_run, ok_all, wait_note, RET, ESC
from pom2 import ROOT
import corrupt_prodos
import prodos_check

PORT = 6851
BLOCKS = 20000
VOLUME = 'BIGVOL'
LOST = 13000                     # dans la quatrieme page de bitmap
MODES = 'Q quick (directories)  F full  ESC back'
AUXASK = 'ALL /RAM files will be LOST. Continue?'
SUMMARY = '%u findings.  R rescan  ESC/RETURN back'
FOUND = '%u findings, nothing written: FIXIT only reads.'
PLAN = 'Plan: %u corrections over %u blocks. Nothing written yet.'
KEYS = 'F fix  ESC back'
ASK = 'Type FIX to confirm'
DONE = 'Applied %u of %u blocks; rescan clean: repaired.'
CANCEL = 'Scan cancelled: no plan from an incomplete scan.'
# Pose en AUX $4000 avant les refus : ni Echap ni N ne doivent y toucher, et
# le controle accepte doit l'effacer (c'est la que vivent les reclamations).
PATTERN = bytes(range(0x40, 0x60)) * 8


def make_big(tmp):
    """Le volume de 20 000 blocs, sain, puis casse ; rend (image, attendu)."""
    stage = tmp / 'stage-big'
    (stage / 'SUB').mkdir(parents=True)
    # Un gros fichier d'abord : tout ce qui suit tombe dans la deuxieme page.
    (stage / 'BIG.BIN').write_bytes(bytes(range(256)) * 12000)
    for i in range(20):
        (stage / 'SUB' / ('F%02d.TXT' % i)).write_bytes(b'line %d\r' % i * (i * 40 + 1))
    (stage / 'C.TXT').write_bytes(b'last\r' * 100)
    po = tmp / 'BIGVOL.po'
    subprocess.run([sys.executable, str(ROOT / 'tools/mkvolume.py'), str(stage), str(po),
                    '--volume', VOLUME, '--blocks', str(BLOCKS)],
                   check=True, capture_output=True)
    data = bytearray(po.read_bytes())
    assert prodos_check.check(bytes(data)).findings == [], 'le volume de depart doit etre sain'
    inv = corrupt_prodos.Inventory(data)
    sub = inv.first(prodos_check.SUBDIR).key
    assert sub >= 4096, ('le sous-dossier doit vivre apres la premiere page', sub)
    # FILE_COUNT : l'en-tete du sous-dossier annonce trois fichiers de trop
    at = sub * 512 + 4 + 0x21
    data[at:at + 2] = (int.from_bytes(data[at:at + 2], 'little') + 3).to_bytes(2, 'little')
    # BM_LOST : un bloc libre marque occupe
    page = inv.bitmap + (LOST >> 12)
    byte = page * 512 + ((LOST & 4095) >> 3)
    assert data[byte] & (0x80 >> (LOST & 7)), 'le bloc perdu doit etre libre'
    data[byte] &= ~(0x80 >> (LOST & 7))
    po.write_bytes(bytes(data))
    result = prodos_check.check(bytes(data))
    expect = {}
    for f in result.findings:
        expect.setdefault(f.id, [0, f.block, f.slot])
        expect[f.id][0] += 1
    assert set(expect) == {'FILE_COUNT', 'BM_LOST'}, expect
    assert result.complete
    return po, expect, {sub, page}


def line_of(rows, id):
    for row in rows:
        if row.strip().startswith(id + ' '):
            return row.split()
    return None


def cycles(p):
    return p.rq('/status')['cpu']['cycles']


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-bigvol-') as tmp:
        tmp = Path(tmp)
        big, expect, touched = make_big(tmp)
        before = big.read_bytes()
        home = tmp / 'boot'
        home.mkdir()
        with boot_hd(home, {}, port=PORT, plugins=['fixit', 'repair'], hd2=big) as (p, s):
            stack = p.peek(0x80, 2)
            floor = s.sym['__HIMEM__'] - s.sym['__STACKSIZE__']
            p.poke(floor, b'\xa5' * 8)
            p.poke(s.sym['_a2fc_ops'], b'\x2a\x00')

            def back(label):
                s.wait(lambda: s.has('! More'), 'retour aux panneaux', 120)
                p.stable()
                s.ok(label + ' : resident et pile C preserves',
                     s.value('ops') == 42 and p.peek(0x80, 2) == stack)
                s.ok(label + ' : budget de pile respecte', p.peek(floor, 8) == b'\xa5' * 8)

            def volume_list():
                s.key(b'/')
                s.wait(lambda: s.rows()[0].startswith('[Volumes]'), 'la liste des volumes')
                p.stable()
                return '\n'.join(s.rows())

            def start(name):
                volume_list()
                s.select('/' + VOLUME)
                menu_run(s, p, name)

            vols = volume_list()
            ram = '/RAM' in vols
            s.ok('le gros volume est en ligne', '/' + VOLUME in vols, vols)

            # 1. Echap a la question de la profondeur
            start('FIXIT')
            s.wait(lambda: s.has(MODES), 'la question de la profondeur', 60)
            p.stable()
            s.ok('le titre nomme le volume', s.has('FIXIT /%s - READ ONLY' % VOLUME), s.rows()[0])
            p.poke(0x4000, PATTERN, bank='aux')
            s.key(ESC)
            back('Echap a la profondeur')
            note = wait_note(s, p)
            s.ok('Echap : le verdict dit que le parcours est annule', note == CANCEL, note)
            s.ok('Echap : la memoire AUX est intacte',
                 p.peek(0x4000, len(PATTERN), bank='aux') == PATTERN)

            # 2. N a la question de /RAM
            start('FIXIT')
            s.wait(lambda: s.has(MODES), 'la question de la profondeur', 60)
            p.stable()
            s.key(b'Q')
            s.wait(lambda: AUXASK in s.rows()[22], 'la question de /RAM', 60)
            p.stable()
            s.key(b'N')
            back('/RAM gardee')
            note = wait_note(s, p)
            s.ok('/RAM gardee : le verdict dit que le parcours est annule', note == CANCEL, note)
            s.ok('/RAM gardee : la memoire AUX est intacte',
                 p.peek(0x4000, len(PATTERN), bank='aux') == PATTERN)

            # 3. le controle rapide
            start('FIXIT')
            s.wait(lambda: s.has(MODES), 'la question de la profondeur', 60)
            p.stable()
            s.key(b'Q')
            s.wait(lambda: AUXASK in s.rows()[22], 'la question de /RAM', 60)
            c0 = cycles(p)
            s.allow_aux()
            s.wait(lambda: s.has('ESC/RETURN back'), 'les constats du controle rapide', 600)
            quick = cycles(p) - c0
            p.stable()
            s.ok('rapide : les reclamations sont en AUX $4000',
                 p.peek(0x4000, len(PATTERN), bank='aux') != PATTERN)
            rows = s.rows()
            text = '\n'.join(rows)
            s.ok('rapide : le titre le dit',
                 rows[0].strip() == 'FIXIT /%s - READ ONLY - QUICK' % VOLUME, rows[0])
            got = line_of(rows, 'FILE_COUNT')
            count, block, slot = expect['FILE_COUNT']
            s.ok('rapide : FILE_COUNT au bloc de l oracle',
                 got is not None and got[1:4] == [str(count), 'block', str(block)], text)
            s.ok('rapide : aucun bloc lu, pas de BM_LOST', line_of(rows, 'BM_LOST') is None, text)
            s.ok('rapide : un constat', SUMMARY % 1 in text, text)

            # 4. R, puis le controle complet
            s.key(b'R')
            s.wait(lambda: s.has(MODES), 'la question de la profondeur apres R', 60)
            p.stable()
            c0 = cycles(p)
            s.key(b'F')
            s.wait(lambda: s.has('ESC/RETURN back') and not s.has(MODES)
                   or AUXASK in s.rows()[22], 'les constats du controle complet', 1200)
            full = cycles(p) - c0
            p.stable()
            rows = s.rows()
            text = '\n'.join(rows)
            s.ok('R : /RAM n est pas redemandee', AUXASK not in rows[22], rows[22])
            s.ok('complet : pas de marque QUICK',
                 rows[0].strip() == 'FIXIT /%s - READ ONLY' % VOLUME, rows[0])
            for id, (count, block, slot) in sorted(expect.items()):
                got = line_of(rows, id)
                s.ok('complet : %s au bloc de l oracle' % id,
                     got is not None and got[1:4] == [str(count), 'block', str(block)], text)
            s.ok('complet : deux constats', SUMMARY % 2 in text, text)
            s.ok('le complet coute plus que le rapide', full > quick, (quick, full))
            print('cycles : rapide %d, complet %d' % (quick, full), flush=True)

            # 5. le verdict
            s.key(ESC)
            back('FIXIT')
            note = wait_note(s, p)
            s.ok('FIXIT : le verdict compte les deux constats', note == FOUND % 2, note)
            if ram:
                s.ok('/RAM est toujours en ligne', '/RAM' in volume_list())

            # 6. REPAIR
            start('REPAIR')
            s.allow_aux()
            s.wait(lambda: s.has(KEYS), 'l ecran de plan de REPAIR', 1200)
            p.stable()
            text = '\n'.join(s.rows())
            s.ok('REPAIR : deux corrections sur deux blocs', PLAN % (2, 2) in text, text)
            s.key(b'F')
            s.wait(lambda: ASK in s.rows()[22], 'la question FIX', 60)
            p.stable()
            s.type('FIX')
            s.key(RET)
            note = wait_note(s, p, 2400)
            s.ok('REPAIR : repare', note == DONE % (2, 2), note)
            back('REPAIR')
            if ram:
                s.ok('/RAM est toujours en ligne apres REPAIR', '/RAM' in volume_list())

        after = big.read_bytes()
        result = prodos_check.check(after)
        s.ok('le volume est sain pour l oracle', result.findings == [], result.findings[:3])
        changed = {i // 512 for i, (a, b) in enumerate(zip(after, before)) if a != b}
        s.ok('seuls la cle du sous-dossier et la page de bitmap ont bouge',
             changed == touched, (sorted(changed), sorted(touched)))
    return ok_all(s, 'bigvol')


if __name__ == '__main__':
    sys.exit(main())
