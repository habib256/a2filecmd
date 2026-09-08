#!/usr/bin/env python3
"""Banc VDrive : deux volumes ProDOS par la ligne serie (src/vsdrive.s).

    make disk && POM2=/chemin/vers/pom2_playtest python3 bench/vdrive.py

POM2 branche sa Super Serial Card en slot 2 et ouvre son pont TCP en mode
brut (`pom2_playtest --ssc PORT`) ; bench/vsdrive_server.py s'y connecte et
sert une image .po comme le ferait ADTPro, veserver.py ou surl-server. On
verifie que le volume parait dans la liste, qu'un fichier s'y copie et s'en
relit, et qu'un hote qui ne repond plus donne une erreur d'E/S propre.

Sans le drapeau --ssc dans pom2_playtest (voir le TODO de POM2), le banc
s'arrete la, en le disant : rien n'est verifie."""

import shutil, subprocess, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pom2 import Pom2, Session, ROOT, POM2
from run import scratch_volume, RET, TAB, ESC, volume
from vsdrive_server import Server
sys.path.insert(0, str(ROOT / 'tools'))
from prodos_read import Image

SSC_PORT = 6740


def playtest_has_ssc():
    """pom2_playtest rend 2 sur un drapeau inconnu, avant toute autre chose."""
    r = subprocess.run([POM2, '--ssc', str(SSC_PORT)], capture_output=True)
    return r.returncode != 2


def main():
    if not playtest_has_ssc():
        print('SKIP pom2_playtest n a pas --ssc : le banc VDrive attend POM2 (voir son TODO)')
        return 0
    checks = []
    def ok(label, cond, detail=''):
        checks.append(bool(cond))
        print(('PASS ' if cond else 'FAIL ') + label + (' ' + str(detail) if detail else ''), flush=True)

    with tempfile.TemporaryDirectory(prefix='a2fc-vdrive-') as tmp:
        tmp = Path(tmp)
        floppy = tmp / 'A2FILECMD.po'
        shutil.copyfile(ROOT / 'dist/A2FILECMD.po', floppy)
        hdv = scratch_volume(tmp)
        remote = tmp / 'remote'
        remote.mkdir()
        (remote / 'FAR.TXT').write_bytes(b'served over the serial line\r' * 4)
        image = volume(remote, tmp / 'REMOTE.po', 'REMOTE', 800)
        server = Server([str(image)], port=SSC_PORT).start()
        try:
            with Pom2(hdv, floppy=floppy, port=6741, ssc=SSC_PORT) as p:
                s = Session(p)
                s.boot()
                ok('VDrive annonce sa carte serie et son slot', s.has('VDrive:'), s.rows()[22].strip()[:70])
                s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes'); p.stable()
                ok('le volume distant parait dans la liste', s.has('/REMOTE'),
                   [r[:40] for r in s.rows()[2:8]])
                ok("l'hote a vu des lectures", any(e[0] == 'read' for e in server.log), len(server.log))
                s.select('/REMOTE'); s.key(RET)
                s.wait(lambda: s.rows()[0][:8] == '/REMOTE ', 'ouvrir REMOTE'); p.stable()
                s.select('FAR'); s.key(RET)
                s.wait(lambda: s.value('view', 1) == 2, 'lire FAR', 30); p.stable()
                ok('un fichier du volume distant se lit', s.has('served over the serial line'), s.rows()[0][:40])
                s.key(ESC); s.wait(lambda: s.value('view', 1) == 0, 'retour'); p.stable()
                # copier vers le distant : le panneau droit sur /SCRATCH, C depuis WORK/NOTE
                s.key(TAB); s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
                s.select('/SCRATCH', 40); s.key(RET)
                s.wait(lambda: s.rows()[0][40:].startswith('/SCRATCH '), 'scratch'); p.stable()
                s.select('WORK', 40); s.key(RET); s.wait(lambda: s.has('/SCRATCH/WORK'), 'WORK'); p.stable()
                s.select('NOTE', 40); s.key(b'C')
                s.wait(lambda: s.has('copied') or s.has('failed'), 'copie', 60); p.stable()
                ok('C ecrit sur le volume distant', s.has('1 file copied') and any(e[0] == 'write' for e in server.log),
                   s.rows()[22].strip()[:50])
                img = Image(image.read_bytes())
                got = {name: (kind, size) for name, kind, size in img.walk()}
                note = next((img.read(e) for e in img.entries(2) if e[1:5] == b'NOTE'), None)
                ok("l'image sur l'hote porte le fichier, octet pour octet",
                   got.get('/NOTE') == ('TXT', 8) and note == b'scratch\r', (got.get('/NOTE'), note))
                devcnt = p.peek(0xBF31, 1)[0]
                ok('les deux unites sont dans DEVLST', devcnt >= 2, devcnt)
                # l'hote s'en va : la prochaine lecture doit echouer proprement
                server.close(); time.sleep(0.5)
                s.key(TAB); s.key(ESC); s.wait(lambda: s.has('[Volumes]'), 'volumes sans hote', 60); p.stable()
                ok("sans hote, la liste des volumes revient quand meme", s.has('[Volumes]') and s.has('/SCRATCH'))
                # Q : le destructeur retire les deux unites et rend DEVADR
                s.key(b'Q'); s.wait(lambda: s.has('Quit to ProDOS?'), 'Q'); s.key(b'Y')
                s.wait(lambda: not s.has('Type  Aux     Size'), 'sortie', 30); time.sleep(1)
                ok('en quittant, les deux unites quittent DEVLST (le destructeur)',
                   p.peek(0xBF31, 1)[0] == devcnt - 2, (devcnt, p.peek(0xBF31, 1)[0]))
        finally:
            server.close()

    passed = sum(1 for c in checks if c)
    print(f'\n{passed}/{len(checks)} controles', flush=True)
    return 0 if passed == len(checks) else 1


if __name__ == '__main__':
    sys.exit(main())
