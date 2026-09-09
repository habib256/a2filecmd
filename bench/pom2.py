#!/usr/bin/env python3
"""Le pilote d'emulateur des bancs : POM2 sans fenetre, par son API HTTP.

POM2 (https://github.com/habib256/pom2) sait tourner sans interface et
accepte des commandes sur un port local : lire la memoire, taper des
touches, rendre l'ecran. C'est tout ce qu'il faut pour jouer d'A2 File Cmd
comme un utilisateur et verifier ce qu'il affiche.

L'ecran texte 80 colonnes est lu directement en $400-$7FF : colonnes paires
en banque auxiliaire, impaires en banque principale. Cela reste valable meme
quand une image occupe l'ecran, ce qui permet de verifier ce que le
programme croit afficher.

Les adresses des variables de diagnostic (a2fc_view, a2fc_ops...) viennent
de la table de symboles du lien (build/a2fc.lbl) : aucune constante ecrite a
la main, aucune porte derobee dans le binaire livre.

    POM2=/chemin/vers/pom2_headless python3 bench/run.py
"""
import json
import os
import re
import signal
import subprocess
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
POM2 = os.environ.get('POM2', str(Path.home() / 'src/pom2adventure/SCOSWAMP.MORE/TOOLS/build/pom2_playtest'))
# A2FC_IMG=A2FILECMD-6502 A2FC_BUILD=build-6502 : le banc sur la version 6502
# (make disk ARCH=6502), qui tourne aussi sur le IIe enhanced de POM2.
IMG = os.environ.get('A2FC_IMG', 'A2FILECMD')
BUILD = ROOT / os.environ.get('A2FC_BUILD', 'build')
DISK = ROOT / ('dist/%s.po' % IMG)
# A2FC_PRESET=iie_unenh : la machine de POM2, le IIe non enhanced (6502 NMOS,
# firmware de 1983) -- la seule qui prouve la version 6502.
PRESET = os.environ.get('A2FC_PRESET', 'iie')


def labels(path=None):
    """Les symboles du lien : {'_a2fc_view': 0x1234, ...}"""
    text = (path or BUILD / 'a2fc.lbl').read_text()
    return {n: int(a, 16) for a, n in re.findall(r'al ([0-9A-F]+) \.(\w+)', text)}


class Timeout(AssertionError):
    pass


class Pom2:
    """Un emulateur, sa copie de la disquette, et de quoi la piloter."""

    def __init__(self, hdv, floppy=None, port=6600, speed=200000, exe=POM2, mouse=False,
                 preset=None, floppy2=None, ssc=None, uthernet=False, chatmauve=None):
        """`hdv` : le disque dur (toujours present, POM2 en veut un).
        `floppy` : la disquette 5,25 a mettre en slot 6 et a amorcer.
        `floppy2` : une seconde disquette, lecteur 2 du meme Disk II, presente
        des l'amorcage (un vrai DOS 3.3 dans un lecteur, sans passer par /disk).
        `mouse` : une AppleMouse II en slot 4, que mouse() fait bouger.
        `ssc` : le port TCP du pont de la Super Serial Card (slot 2), en mode
        brut, pour le banc VDrive -- si pom2_playtest a le drapeau --ssc.
        `uthernet` : une Uthernet II (W5100) en slot 3, loopback ouvert, pour
        la version reseau du meme banc (pom2_playtest --uthernet).
        `preset` : la machine, `iie` (enhanced), `iic` ou `iie_unenh` (le IIe
        de 1983, 6502 NMOS, pour la version 6502) ; par defaut A2FC_PRESET.
        `chatmauve` : la carte RGB Le Chat Mauve en slot 7, l'ecran rendu par
        elle (`True` = Feline, ou une variante : feline, iic, eve, video7,
        rvbgraph)."""
        self.port, self.base = port, 'http://127.0.0.1:%d' % port
        self.hdv, self.floppy = str(hdv), str(floppy) if floppy else None
        self.floppy2 = str(floppy2) if floppy2 else None
        self.speed, self.exe, self.proc = speed, exe, None
        self.preset = preset or PRESET
        self.chatmauve = chatmauve
        self.with_mouse = mouse
        self.ssc = ssc
        self.uthernet = uthernet

    # ── cycle de vie ───────────────────────────────────────────────────────
    def start(self):
        cwd = os.path.dirname(self.hdv)
        log = open(os.path.join(cwd, 'pom2.log'), 'w')
        args = [self.exe, '--preset', self.preset, '--ai-control=%d' % self.port,
                '--speed', str(self.speed)]
        if self.floppy:
            args += ['--disk', self.floppy, '--boot', '6']
        if self.floppy2:
            args += ['--disk2', self.floppy2]
        if self.with_mouse:
            args += ['--mouse']
        if self.ssc:
            args += ['--ssc', str(self.ssc)]
        if self.uthernet:
            args += ['--uthernet']
        if self.chatmauve:
            args += ['--chatmauve'] + ([self.chatmauve] if isinstance(self.chatmauve, str) else [])
        args += [os.path.basename(self.hdv)]
        self.proc = subprocess.Popen(args, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                                     start_new_session=True)
        deadline = time.time() + 30
        while time.time() < deadline:
            try:
                self.rq('/status')
                return self
            except Exception:
                time.sleep(0.2)
        raise RuntimeError('POM2 ne repond pas sur le port %d' % self.port)

    def stop(self):
        if self.proc is not None:
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(os.getpgid(self.proc.pid), sig)
                    self.proc.wait(timeout=5)
                    break
                except Exception:
                    pass
            self.proc = None
        subprocess.call(['pkill', '-f', 'ai-control=%d' % self.port])

    def __enter__(self):
        return self.start()

    def __exit__(self, *exc):
        self.stop()

    # ── transport ──────────────────────────────────────────────────────────
    def rq(self, path, body=None, timeout=10):
        req = urllib.request.Request(
            self.base + path, data=json.dumps(body).encode() if body is not None else None)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())

    def peek(self, addr, n, bank='main'):
        out = b''
        while n:
            k = min(n, 256)
            q = '/mem?addr=%d&len=%d' % (addr, k) + ('&bank=aux' if bank == 'aux' else '')
            chunk = bytes.fromhex(self.rq(q)['data'])
            assert len(chunk) == k, f'lecture courte en ${addr:04X}'
            out += chunk
            addr += k
            n -= k
        return out

    def poke(self, addr, data):
        return self.rq('/mem?addr=%d' % addr, {'data': data.hex()})['written']

    def keys(self, text):
        return self.rq('/keyboard', {'text': text})['queued']

    def mouse(self, x=None, y=None, dx=None, dy=None, btn=None, reset=False):
        """La souris : une position absolue du compteur de l'hote, ou un
        deplacement (127 au plus par appel), le bouton, la remise a zero du
        compteur. La carte ne voit que des deplacements, que le firmware
        borne a l'ecran : apres home(), tant qu'on reste dans les bornes, x
        et y sont des cases de l'ecran 80 colonnes."""
        body = {}
        if reset: body['reset'] = 1
        if x is not None: body['x'] = x
        if y is not None: body['y'] = y
        if dx is not None: body['dx'] = dx
        if dy is not None: body['dy'] = dy
        if btn is not None: body['btn'] = btn
        return self.rq('/mouse', body)

    def home(self):
        """Ramene la souris en (0, 0) des deux cotes : le pointeur de l'Apple II
        contre ses bornes, puis le compteur de l'hote a zero -- par des pas
        negatifs, jamais par reset : la carte garde sa derniere position et
        verrait dans la suivante un deplacement qui deborde."""
        r = None
        for _ in range(2):
            r = self.mouse(dx=-127, dy=-127)
            time.sleep(0.05)
        while r['x'] or r['y']:
            r = self.mouse(dx=-min(r['x'], 127), dy=-min(r['y'], 127))
            time.sleep(0.05)

    def click(self, x, y, pause=0.3):
        """Un clic en (x, y) : la souris y va, le bouton s'enfonce, se relache."""
        self.mouse(x=x, y=y); time.sleep(0.15)
        self.mouse(btn=1); time.sleep(0.15)
        self.mouse(btn=0); time.sleep(pause)

    def insert(self, drive, path):
        """Une disquette dans le lecteur `drive` (0 ou 1) du Disk II : `path`
        est relatif au dossier de l'emulateur (celui du disque dur)."""
        return self.rq('/disk', {'drive': drive, 'path': path})

    def eject(self, drive):
        """Sort la disquette du lecteur : POM2 la recopie dans son fichier."""
        return self.rq('/eject', {'drive': drive})

    def raw(self, data):
        """Des octets bruts (ESC = \\x1b, Bas = \\x0a).

        Le corps est bati a la main : le lecteur JSON de POM2 ne connait pas
        les echappements \\uXXXX et prend la lettre qui suit une contre-oblique
        telle quelle. Un json.dumps lui ferait taper cinq touches au lieu
        d'une -- le genre de bug qu'on met une heure a ne pas croire."""
        if isinstance(data, str):
            data = data.encode('latin-1')
        body = b'{"raw":"' + data + b'"}'
        req = urllib.request.Request(self.base + '/keyboard', data=body)
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())['queued']

    # ── l'ecran ────────────────────────────────────────────────────────────
    # Le firmware 80 colonnes allume ALTCHARSET : l'inverse occupe alors
    # $00-$7F en entier, et un simple & 0x7F rendrait $13 (S inverse)
    # illisible. D'ou ce decodage en quatre branches -- sans quoi la barre de
    # chemin d'un panneau, ecrite en inverse, se lirait vide.
    @staticmethod
    def _cell(b):
        if b >= 0x80:
            return chr(b & 0x7F)          # normal
        if b < 0x20:
            return chr(b + 0x40)          # inverse @ A-Z [ \\ ] ^ _
        if b < 0x40:
            return chr(b)                 # inverse espace et ponctuation
        if b < 0x60:
            return '\u25af'               # MouseText
        return chr(b)                     # inverse minuscules

    def screen(self):
        """Les 24 lignes de 80 colonnes, banques entrelacees."""
        main, aux = self.peek(0x400, 1024), self.peek(0x400, 1024, 'aux')
        rows = []
        for r in range(24):
            base = 0x80 * (r % 8) + 0x28 * (r // 8)
            rows.append(''.join(self._cell(aux[base + c // 2] if c % 2 == 0 else main[base + c // 2])
                                for c in range(80)))
        return rows

    def screen40(self):
        """Les 24 lignes de 40 colonnes : ce que montre BASIC.SYSTEM."""
        main = self.peek(0x400, 1024)
        return [''.join(self._cell(b) for b in main[0x80 * (r % 8) + 0x28 * (r // 8):][:40])
                for r in range(24)]

    def stable(self, tries=200, pause=0.05, need=6):
        """Attend que l'ecran cesse de bouger."""
        last, same = None, 0
        for _ in range(tries):
            now = self.screen()
            same = same + 1 if now == last else 0
            if same >= need:
                return now
            last = now
            time.sleep(pause)
        return last


class Session:
    """Un banc : l'emulateur, l'ecran, les touches et les panneaux."""

    def __init__(self, pom, sym=None):
        self.p = pom
        self.sym = sym if sym is not None else labels()
        self.checks = []

    # ── observation ────────────────────────────────────────────────────────
    def rows(self):
        return self.p.screen()

    def rows40(self):
        return self.p.screen40()

    def has(self, needle):
        return any(needle in r for r in self.rows())

    def value(self, name, n=2):
        return int.from_bytes(self.p.peek(self.sym['_a2fc_' + name], n), 'little')

    def wait(self, test, what, seconds=30):
        deadline = time.time() + seconds
        while time.time() < deadline:
            if test():
                return
            time.sleep(0.05)
        print('\n'.join(self.rows()), flush=True)
        raise Timeout('delai depasse : ' + what)

    # ── action ─────────────────────────────────────────────────────────────
    def key(self, k, pause=0.15):
        self.p.raw(k if isinstance(k, bytes) else k.encode())
        time.sleep(pause)

    def type(self, text):
        self.p.keys(text)
        time.sleep(0.2)

    def cursor_row(self, x=0):
        """La ligne en video inverse du panneau qui commence en colonne x."""
        main, aux = self.p.peek(0x400, 1024), self.p.peek(0x400, 1024, 'aux')
        for r in range(2, 20):
            base = 0x80 * (r % 8) + 0x28 * (r // 8)
            cells = [aux[base + c // 2] if c % 2 == 0 else main[base + c // 2]
                     for c in range(x, x + 16)]
            if all(v < 0x80 for v in cells):
                return r
        return None

    def line(self, x=0):
        r = self.cursor_row(x)
        return self.rows()[r][x:x + 38] if r is not None else ''

    def select(self, name, x=0, tries=80):
        """Amene le curseur sur `name` dans le panneau qui commence en x."""
        for _ in range(12):
            self.key(b'<')                       # remonter page par page
        for _ in range(tries):
            if self.line(x).startswith(name + ' ') or self.line(x).startswith(name + '/'):
                return
            self.key(b'\x0a')
        raise AssertionError(f'introuvable dans le panneau : {name}\n' + '\n'.join(self.rows()))

    def boot(self):
        self.wait(lambda: self.has('Type  Aux     Size'), 'demarrage', 60)
        self.p.stable()
        return self

    # ── verdict ────────────────────────────────────────────────────────────
    def ok(self, label, cond, detail=''):
        print(('PASS ' if cond else 'FAIL ') + label, detail, flush=True)
        self.checks.append({'label': label, 'ok': bool(cond), 'detail': str(detail)})
        if not cond:
            raise AssertionError(label + ' ' + str(detail))
