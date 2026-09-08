#!/usr/bin/env python3
"""Un serveur VSDrive (le protocole du VDrive d'ADTPro) sur une prise TCP.

    python3 bench/vsdrive_server.py IMAGE1.po [IMAGE2.po] --port 6502

C'est ce que font veserver.py (ProDOS-Utils) sur un port serie et
surl-server (a2tools) sur le Raspberry ; ici la ligne serie est la prise TCP
du pont telnet de la Super Serial Card de POM2 (127.0.0.1:port, mode brut),
pour le banc du pilote d'A2 File Cmd (src/vsdrive.s). Le protocole, tel que
le pilote le parle :

  lecture   Apple : $C5, cmd (3 lecteur 1, 5 lecteur 2), bloc lo, hi, XOR
            hote  : les memes quatre, quatre octets d'heure et date ProDOS,
                    le XOR des huit, 512 octets, leur XOR
  ecriture  Apple : $C5, cmd (2 ou 4), bloc, XOR, 512 octets, leur XOR
            hote  : les quatre octets, puis le XOR des 512 (+1 si echec)

Un XOR volontairement faux est la seule facon de dire une erreur.
"""
import argparse
import socket
import sys
import threading
import time
from pathlib import Path

ENV = 0xC5
BLOCK = 512


def datetime_bytes():
    t = time.localtime()
    word1 = t.tm_min | (t.tm_hour << 8)
    word2 = t.tm_mday | ((t.tm_mon) << 5) | ((t.tm_year % 100) << 9)
    return bytes([word1 & 0xFF, word1 >> 8, word2 & 0xFF, word2 >> 8])


def xor(data):
    c = 0
    for b in data:
        c ^= b
    return c


class Server:
    """`images` : un ou deux chemins de .po ; `log` : la liste des requetes vues."""

    def __init__(self, images, port=6502, host='127.0.0.1', verbose=False):
        self.images = [Path(p) if p else None for p in images] + [None] * (2 - len(images))
        self.port, self.host, self.verbose = port, host, verbose
        self.log = []
        self.sock = None
        self.thread = None
        self.stop = threading.Event()

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()
        return self

    def close(self):
        self.stop.set()
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass

    def run(self):
        # Le pont de POM2 ecoute : c'est nous le client, comme un telnet.
        while not self.stop.is_set():
            try:
                s = socket.create_connection((self.host, self.port), timeout=2)
            except OSError:
                time.sleep(0.2)
                continue
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            self.sock = s
            try:
                self.serve(s)
            except OSError:
                pass
            finally:
                s.close()
                self.sock = None

    def recv(self, s, n):
        buf = b''
        while len(buf) < n:
            chunk = s.recv(n - len(buf))
            if not chunk:
                raise OSError('closed')
            buf += chunk
        return buf

    def serve(self, s):
        s.settimeout(None)
        while not self.stop.is_set():
            b = self.recv(s, 1)
            if b[0] != ENV:
                continue                       # du bruit : on attend l'enveloppe
            head = b + self.recv(s, 4)
            cmd, blk = head[1], head[2] | (head[3] << 8)
            if xor(head[:4]) != head[4]:
                self.log.append(('badenv', cmd, blk))
                continue
            drive = (cmd - 2) >> 1
            image = self.images[drive] if drive in (0, 1) else None
            if cmd & 1:                        # lecture
                data, err = bytes(BLOCK), True
                if image:
                    try:
                        with open(image, 'rb') as f:
                            f.seek(blk * BLOCK)
                            data = f.read(BLOCK)
                            err = len(data) != BLOCK
                    except OSError:
                        err = True
                hdr = head[:4] + datetime_bytes()
                s.sendall(hdr + bytes([(xor(hdr) + (1 if err else 0)) & 0xFF]))
                if not err:
                    s.sendall(data + bytes([xor(data)]))
                self.log.append(('read', drive, blk, err))
            else:                              # ecriture
                data = self.recv(s, BLOCK)
                got = self.recv(s, 1)[0]
                chk = xor(data)
                err = got != chk or image is None
                if not err:
                    try:
                        with open(image, 'r+b') as f:
                            f.seek(blk * BLOCK)
                            f.write(data)
                    except OSError:
                        err = True
                s.sendall(head[:4] + bytes([(chk + (1 if err else 0)) & 0xFF]))
                self.log.append(('write', drive, blk, err))
            if self.verbose:
                print(self.log[-1], flush=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('images', nargs='+', help='un ou deux .po')
    ap.add_argument('--port', type=int, default=6502)
    ap.add_argument('--host', default='127.0.0.1')
    a = ap.parse_args()
    srv = Server(a.images[:2], a.port, a.host, verbose=True).start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        srv.close()
    return 0


if __name__ == '__main__':
    sys.exit(main())
