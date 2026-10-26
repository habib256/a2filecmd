"""Le creux maximal de la pile C, mesure en faisant travailler le programme.

La pile logicielle de cc65 part de $BF00 vers le bas et rien ne la surveille :
si elle descend sous le bout froid du binaire, elle mange du code. Le lien
reserve 256 octets (A2FC_STACK dans le Makefile) et tools/check_layout.py
verifie que le code s'arrete au-dessus ; ce banc mesure ce qui est REELLEMENT
consomme, arbre de dossiers, images, visionneuses, editeur et copie recursive
compris.

    make disk && POM2=... python3 bench/memory.py
"""
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pom2 import Pom2, Session, ROOT, labels
from run import scratch_volume, ESC, RET, DOWN, TAB
from xplug import stage_hd, ok_all

def main():
    sym = labels()
    budget = sym['__STACKSIZE__']
    lo, hi = sym['__ONCE_RUN__'], sym['__HIMEM__']
    with tempfile.TemporaryDirectory(prefix='a2fc-stack-') as tmp:
        tmp = Path(tmp)
        # Exercise the release's IDENT relay, absent from the compact bench
        # floppy. Both disks are disposable; retain the real resident binary
        # and its symbols, and copy its complete tool directory at the end.
        program = stage_hd(tmp, name='A2FILECMD')
        with Pom2(program, hd2=scratch_volume(tmp, blocks=4000), port=6620) as p:
            s = Session(p, sym)
            s.boot()
            # The relocated LC tag routine must preserve entry identities,
            # cursor, the other panel and all non-screen AUX bytes. Panel
            # offsets are frozen by tools/test_abi_freeze.py (98 bytes).
            s.select('A2FILE'); s.key(RET)
            s.wait(lambda: '/A2FILE ' in s.rows()[0][:40], 'A2FILE tags'); p.stable()
            panel = sym['_panels']
            before = p.peek(panel, 196)
            count = before[64]
            entries = int.from_bytes(before[74:76], 'little')
            table = p.peek(entries, count * 29)
            aux = p.peek(0x0800, 0xB800, 'aux')
            expected = bytearray(18)
            for i in range(count):
                if table[i * 29:i * 29 + 3] != b'..\0':
                    expected[i >> 3] |= 1 << (i & 7)
            s.ok('tag fixture includes parent and files',
                 count > 1 and table[:3] == b'..\0')
            for key, marks in ((b'\x14', bytes(expected)), (b'*', bytes(18)),
                               (b'*', bytes(expected)), (b'\x0e', bytes(18))):
                s.key(key); p.stable()
                after = p.peek(panel, 196)
                want = before[:76] + marks + before[94:]
                s.ok('LC tags %r preserve both panels and entry bytes' % key,
                     after == want and p.peek(entries, count * 29) == table)
            s.ok('LC tags preserve AUX outside screen memory',
                 p.peek(0x0800, 0xB800, 'aux') == aux)
            s.key(ESC); p.stable()
            # ONCE est mort une fois main() lance : tout ce qui est au-dessus
            # du bout froid est a la pile, et a personne d'autre.
            p.poke(lo, bytes([0xEE]) * (hi - lo))

            def low_water():
                d = p.peek(lo, hi - lo)
                for i, b in enumerate(d):
                    if b != 0xEE:
                        return lo + i
                return hi

            s.ok('le motif est pose sur toute la pile', low_water() == hi)
            s.select('A2FILE'); s.key(RET)
            s.wait(lambda: s.has('/A2FILECMD/A2FILE'), 'dossier'); s.key(ESC)
            s.wait(lambda: s.has('/A2FILECMD '), 'retour'); p.stable()
            s.key(TAB)                                    # le panneau droit : /SCRATCH/DEMO (la disquette n'a pas de DEMO)
            s.select('/SCRATCH', 40); s.key(RET)
            s.wait(lambda: s.rows()[0][40:].startswith('/SCRATCH '), 'SCRATCH droit'); p.stable()
            s.select('DEMO', 40); s.key(RET)
            s.wait(lambda: s.has('/SCRATCH/DEMO'), 'DEMO droit'); p.stable()
            s.select('DHGR.RLE', 40); s.key(RET); s.allow_aux()
            s.wait(lambda: s.value('view', 1) == 1, 'image', 40); time.sleep(1)
            s.key(ESC); s.wait(lambda: s.value('view', 1) == 0, 'retour'); p.stable()
            s.select('SAMPLE', 40); s.key(RET)
            s.wait(lambda: s.value('view', 1) == 2, 'texte'); s.key(ESC)
            s.wait(lambda: s.value('view', 1) == 0, 'retour')
            s.key(b'H'); s.wait(lambda: s.value('view', 1) == 3, 'hexa'); s.key(ESC)
            s.wait(lambda: s.value('view', 1) == 0, 'retour')
            s.key(b'E'); s.wait(lambda: s.value('view', 1) == 5, 'editeur')
            s.type('X'); s.key(ESC); s.wait(lambda: s.has('Discard') or s.has('Save and exit'), 'menu')
            s.key(b'Q'); s.wait(lambda: s.has('Discard'), 'abandon'); s.key(b'Y')
            s.wait(lambda: s.value('view', 1) == 0, 'sortie'); p.stable()
            after_views = low_water()
            # la copie d'un arbre entier : le chemin le plus profond du programme
            # le panneau droit devient la cible, le gauche reste sur la disquette
            s.key(b'/'); s.wait(lambda: s.has('[Volumes]'), 'volumes')
            s.select('/SCRATCH', 40); s.key(RET)
            s.wait(lambda: s.rows()[0][40:].startswith('/SCRATCH '), 'scratch'); p.stable()
            s.key(TAB)
            s.select('A2FILE'); s.key(b'C')
            s.wait(lambda: s.has('files copied.') or s.has('Failed'), 'copie recursive', 180); p.stable()
            s.ok('la copie recursive aboutit', s.has('files copied.'), s.rows()[22])
            deep = low_water()
            used = hi - deep
            print(f'creux apres les visionneuses : ${after_views:04X}', flush=True)
            print(f'creux le plus bas            : ${deep:04X}  ({used} octets sous ${hi:04X})',
                  flush=True)
            s.ok(f'la pile reste sous les {budget} octets reserves ({used} utilises)',
                 used <= budget, f'${deep:04X}')
            # The tree walks are not recursive: walk_tree descends only while
            # tree_stack_ok sees 80 bytes above the stack floor, so a deep copy
            # is meant to use more than half the budget (145 bytes measured at
            # 0.8.6 and 0.8.7). What must hold is a real margin at the lowest
            # point, not half of it.
            s.ok('et garde au moins 32 octets de marge', used <= budget - 32, f'{used} octets, {budget - used} de marge')
    return ok_all(s, 'memory stack')


if __name__ == '__main__':
    sys.exit(main())
