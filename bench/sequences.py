#!/usr/bin/env python3
"""Banc des sequences entre outils : l'etat, les ressources et les octets
apres un enchainement, pas le seul code de retour de chaque outil.

Trois enchainements sur un disque dur jetable (relu apres la sortie, POM2
le reecrit) :
  A. image HGR (AUX) -> musique (Mockingboard, MEDIA en lecteur 2) -> copie
     de deux fichiers marques : la copie reste exacte apres les visionneuses.
  B. annulation -> reprise : ESC pendant une copie de 300 Ko (partiel
     retire), puis la meme copie menee au bout, puis le fichier deplace dans
     un autre dossier du volume : octets exacts, source disparue.
  C. changement de disque en lecteur 2 : une disquette SWAP ouverte dans
     le panneau droit, remplacee par SWAP2 ; le panneau ne casse pas, la
     liste des volumes voit la nouvelle, et la copie depuis chacune est
     exacte.
Lancer avec A2FC_IMG=A2FILECMD-full (65C02, `make benchfloppy ARCH=enh`),
puis A2FC_BUILD=build-6502 A2FC_PRESET=iie_unenh A2FC_IMG=A2FILECMD-full
(`make benchfloppy ARCH=6502`). La disquette de session porte IMAGE.
"""
import os, re, shutil, sys, tempfile, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from pom2 import Pom2, Session, ROOT, DISK, VERSION
from run import scratch_volume, volume, RET, TAB, ESC
from data_safety import contents
sys.path.insert(0, str(ROOT / 'tools'))
from prodos_read import Image

BIG = bytes(range(256)) * 1200                       # 300 Ko


def listing(path, *parts):
    """Les noms d'un dossier du volume `path` (contents() rend celui du
    dernier dossier traverse, pas celui vise)."""
    img = Image(path.read_bytes()); key = 2
    for part in parts:
        e = next(e for e in img.entries(key) if e[1:1 + (e[0] & 15)].decode() == part)
        key = int.from_bytes(e[17:19], 'little')
    return sorted(e[1:1 + (e[0] & 15)].decode() for e in img.entries(key))
BAR = re.compile(r'^ *1/1 {2,}BIG +\[[#.]{40}\] +\d+/\d+ *$')


def main():
    checks = []
    def ok(label, cond, detail=''):
        checks.append(bool(cond))
        print(('PASS ' if cond else 'FAIL ') + label + (' ' + str(detail) if detail else ''), flush=True)

    with tempfile.TemporaryDirectory(prefix='a2fc-seq-') as tmp:
        tmp = Path(tmp)
        floppy = tmp / 'A2FILECMD.po'
        shutil.copyfile(DISK, floppy)
        media = tmp / 'MEDIA.po'
        shutil.copyfile(ROOT / 'build-6502/legacy/MEDIA.po', media)
        hdv = scratch_volume(tmp)                    # DEMO, WORK, OUT, TINY.PO...
        stage = tmp / 'scratch'
        (stage / 'BIG').write_bytes(BIG)
        hdv = volume(stage, tmp / 'SCRATCH.hdv', 'SCRATCH', 3200)   # BIG three times over
        readme = (stage / 'DEMO/README.TXT').read_bytes()
        sample = (stage / 'DEMO/SAMPLE.TXT').read_bytes()   # mkvolume: X.TXT -> X, type TXT
        swaps = {}
        for name, text in (('SWAP', b'first floppy in drive 2\r' * 40), ('SWAP2', b'second floppy, same drive\r' * 30)):
            d = tmp / name.lower(); d.mkdir()
            (d / 'OTHER').write_bytes(text)
            swaps[name] = (volume(d, tmp / (name + '.po'), name, 280), text)

        with Pom2(hdv, floppy=floppy, floppy2=media, port=6748 + int(os.environ.get('A2FC_PORT_OFFSET', '0'))) as p:
            s = Session(p)
            s.boot()

            def open_panel(x, *names, vol='SCRATCH'):
                if s.cursor_row(x) is None:
                    s.key(TAB)
                s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
                if s.cursor_row(x) is None:
                    s.key(TAB)
                s.select('/' + vol, x); s.key(RET)
                s.wait(lambda: s.rows()[0][x:].startswith('/' + vol + ' '), vol); p.stable()
                for n in names:
                    s.select(n, x); s.key(RET)
                    s.wait(lambda: ('/' + vol + '/' + n) in s.rows()[0][x:], 'dossier ' + n); p.stable()

            def copy(x, *names):
                """Marque les noms dans le panneau x et copie vers l'autre."""
                if s.cursor_row(x) is None:
                    s.key(TAB)
                for n in names:
                    s.select(n, x); s.key(b' ')
                p.stable()
                s.key(b'C'); s.wait(lambda: s.has('copied') or s.has('failed') or s.has('Cannot'), 'copie', 90); p.stable()
                return s.rows()[22].strip()

            def shows(x, name):
                return any(r[x:].startswith(name + ' ') for r in s.rows()[2:20])

            # ── A. image -> musique -> copie ─────────────────────────────
            open_panel(0, 'OUT')                     # gauche : la cible
            open_panel(40, 'DEMO')                   # droite : la source
            s.select('HGR.RLE', 40); s.key(RET); s.allow_aux()
            s.wait(lambda: s.value('view', 1) == 1, 'image HGR', 40); time.sleep(1)
            s.key(ESC); s.wait(lambda: s.value('view', 1) == 0, 'retour image'); p.stable()
            ok('A : retour de l image sur les panneaux, source encore affichee', shows(40, 'HGR.RLE'))
            s.select('WELCOME.MB', 40)
            p.rq('/speed', {'preset': '1x'}); s.key(RET)
            s.wait(lambda: s.has('MB1 - WELCOME.MB'), 'lecteur MB1', 30)
            s.wait(lambda: s.has('Type  Aux     Size'), 'fin du flux MB1', 30); p.stable()
            p.rq('/speed', {'cycles_per_frame': p.speed})
            ok('A : la musique rend les panneaux, curseur sur le morceau', s.line(40).startswith('WELCOME.MB'))
            msg = copy(40, 'README', 'SAMPLE')
            ok('A : deux fichiers copies apres image et musique', msg.startswith('2 files copied'), msg)
            ok('A : la cible les montre', shows(0, 'README') and shows(0, 'SAMPLE'))

            # ── B. annulation -> reprise -> deplacement ──────────────────
            open_panel(40)                           # droite : /SCRATCH (BIG)
            s.select('BIG', 40); p.stable()
            s.key(b'C')
            seen, t0 = None, time.time()
            while time.time() - t0 < 30:
                row = s.rows()[22].rstrip()
                if BAR.match(row) and '#' in row:
                    seen = row; break
                time.sleep(0.05)
            s.key(ESC); s.wait(lambda: s.has('Interrupted'), 'interruption', 60); p.stable()
            ok('B : ESC interrompt la copie de 300 Ko', seen is not None and s.has('Interrupted: 0 of 1 done.'), s.rows()[22].strip()[:50])
            ok('B : le partiel est retire de la cible', not shows(0, 'BIG'))
            msg = copy(40, 'BIG')
            ok('B : la meme copie menee au bout', msg.startswith('1 file copied'), msg)
            ok('B : la cible montre BIG', shows(0, 'BIG'))
            open_panel(40, 'WORK')                   # droite : /SCRATCH/WORK, la cible du deplacement
            s.key(TAB)                               # gauche : /SCRATCH/OUT
            s.select('BIG', 0); s.key(b'V')
            s.wait(lambda: s.has('moved') or s.has('ailed'), 'deplacement', 90); p.stable()
            ok('B : V deplace la copie dans WORK', s.has('moved') and not shows(0, 'BIG') and shows(40, 'BIG'), s.rows()[22].strip()[:50])

            # ── C. changement de disque en lecteur 2 ─────────────────────
            p.eject(1); time.sleep(.5); p.insert(1, 'SWAP.po')
            open_panel(40, vol='SWAP')
            ok('C : la disquette inseree en cours de session s ouvre', shows(40, 'OTHER'))
            msg = copy(40, 'OTHER')
            ok('C : copie depuis SWAP', msg.startswith('1 file copied'), msg)
            p.eject(1); time.sleep(.5); p.insert(1, 'SWAP2.po')
            if s.cursor_row(40) is None:             # le panneau droit, encore sur /SWAP
                s.key(TAB)
            s.select('OTHER', 40); s.key(RET)        # relecture : le fichier n'y est plus tel quel
            s.wait(lambda: s.value('view', 1) != 0 or s.has('Cannot') or s.has('Not ') or s.has('failed') or s.has('[Volumes]'), 'disque change', 30)
            if s.value('view', 1):
                s.key(ESC); s.wait(lambda: s.value('view', 1) == 0, 'retour')
            p.stable()
            ok('C : le panneau survit au changement de disquette', s.has('Type  Aux'), s.rows()[22].strip()[:60])
            open_panel(40, vol='SWAP2')
            ok('C : la nouvelle disquette est vue dans les volumes', s.rows()[0][40:].startswith('/SWAP2 ') and shows(40, 'OTHER'))
            if s.cursor_row(0) is None:
                s.key(TAB)
            s.select('OTHER', 0); s.key(b'D')
            s.wait(lambda: s.has('Delete '), 'confirmation'); s.key(b'Y')
            s.wait(lambda: s.has('deleted') or s.has('failed'), 'suppression', 30); p.stable()
            msg = copy(40, 'OTHER')
            ok('C : copie depuis SWAP2 apres suppression de la premiere', msg.startswith('1 file copied'), msg)
            p.eject(1)

        # ── les octets, apres la sortie ───────────────────────────────────
        ok('A : README et SAMPLE copies octet a octet',
           contents(hdv, ['OUT', 'README']) == readme and contents(hdv, ['OUT', 'SAMPLE']) == sample)
        work = listing(hdv, 'WORK')
        ok('B : BIG deplace dans WORK, exact', 'BIG' in work and contents(hdv, ['WORK', 'BIG']) == BIG, work)
        ok('B : BIG absent de OUT apres le deplacement', 'BIG' not in listing(hdv, 'OUT'), listing(hdv, 'OUT'))
        ok('B : BIG source intact', contents(hdv, ['BIG']) == BIG)
        ok('C : OTHER vient de la seconde disquette', contents(hdv, ['OUT', 'OTHER']) == swaps['SWAP2'][1])
        for name, (po, text) in swaps.items():
            ok(f'C : {name} intacte', contents(po, ['OTHER']) == text)

    passed = sum(1 for c in checks if c)
    print(f'\n{passed}/{len(checks)} controles (sequences)', flush=True)
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    sys.exit(main())
