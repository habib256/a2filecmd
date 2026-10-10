#!/usr/bin/env python3
"""Direct DOSVIEW on Disk II drive 2 and DOS image; disposable disks only."""
import sys
import tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'bench'))
sys.path.insert(0, str(ROOT / 'tools'))
from xplug import boot_hd, menu_run, RET, ESC, ok_all
from mini33_fixture import make_disk


def main():
    text=b'FIRST DOS PAGE\r'*22+b'SECOND DOS PAGE\r'*22+b'THIRD DOS PAGE\r'
    binary=bytes(range(256))*4
    picture=bytes((i*17+(i//128)*3)&255 for i in range(1024))
    hgr=bytes((i*13+(i//256)*7)&255 for i in range(8192))
    raw=make_disk([('TEXT',0x80,text),('BYTES',4,b'\0 '+len(binary).to_bytes(2,'little')+binary),
                   ('COLORS',4,b'\0\x04\0\x04'+picture),
                   ('HIRES',4,b'\0 \0 '+hgr),
                   ('SHORT',4,b'\0\x40\xf8\x1f'+hgr[:8184])])
    files={'WORK/DIRECT.DSK#060000':raw}
    with tempfile.TemporaryDirectory(prefix='direct-dos-native-') as tmp:
        tmp=Path(tmp);floppy=tmp/'SOURCE.DSK';floppy.write_bytes(raw);floppy.chmod(0o444)
        with boot_hd(tmp, files, port=6922, plugins=['dosview'], floppy2=floppy) as (p,s):
            hd=Path(p.hdv);hd_before=hd.read_bytes()
            s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('WORK');s.key(RET);p.stable()
            aux=p.peek(0x1000,0xb000,'aux')
            floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xa5'*8)
            s.key(b'\t');s.key(b'/');p.stable()
            for _ in range(15):
                if 'DOS 3.3 disk' in s.line(41):break
                s.key(b'\x0a')
            s.key(RET);s.wait(lambda:s.has('TEXT') and '/DOS 3.3' in s.rows()[0], 'real DOS disk catalog',60)
            for backend in ('Disk II drive 2 (write-protected)', 'DOS-order image'):
                def launch(name,command):
                    s.select(name,40 if backend.startswith('Disk II') else 0);s.key(command)
                def back():
                    s.key(ESC);s.wait(lambda:s.has('Type  Aux'), 'panels restored',30);p.stable()
                launch('TEXT',b'T');s.wait(lambda:s.has('FIRST DOS PAGE'),'first page',30)
                s.key(b' ');s.wait(lambda:s.has('SECOND DOS PAGE'),'second page',30)
                s.key(b'B');s.wait(lambda:s.has('FIRST DOS PAGE'),'previous page',30)
                s.ok(backend+': text and bidirectional paging',True);back()
                launch('BYTES',b'H');s.wait(lambda:s.has('000000: 00 01 02 03'),'hex first bytes',30)
                s.key(b' ');s.wait(lambda:s.has('000130: 30 31 32 33'),'hex seek',30)
                s.ok(backend+': exact hex offset across sectors',True);back()
                s.select('COLORS',40 if backend.startswith('Disk II') else 0);before=p.peek(0x400,1024);s.key(b'I')
                visible={((r&7)*128+(r>>3)*40+i) for r in range(24) for i in range(40)}
                def lores_ready():
                    page=p.peek(0x400,1024)
                    return all(page[i]==picture[i] for i in visible)
                s.wait(lores_ready,'lo-res page copied',30)
                shown=p.peek(0x400,1024)
                s.ok(backend+': all 960 visible lo-res bytes exact',all(shown[i]==picture[i] for i in visible))
                back()
                # Capture after the core's loader/catalog firmware calls:
                # those legitimately update live screen holes themselves.
                s.select('COLORS',40 if backend.startswith('Disk II') else 0);menu_run(s,p,'DOSVIEW')
                s.wait(lambda:s.has('Direct DOS: T text'),'menu viewer choice',30)
                before=p.peek(0x400,1024);s.key(b'I')
                s.wait(lores_ready,'menu lo-res page copied',30)
                shown=p.peek(0x400,1024)
                s.ok(backend+': reader preserves screen holes',all(shown[i]==before[i] for i in range(1024) if i not in visible))
                back()
                launch('TEXT',RET);s.wait(lambda:s.has('FIRST DOS PAGE'),'Return opens DOS text',30);back()
                launch('BYTES',RET);s.wait(lambda:s.has('000000: 00 01 02 03'),'Return opens DOS hex',30);back()
                s.ok(backend+': Return routes text and binary streams',True)
                for name,command,expected in (('HIRES',b'I',hgr),('HIRES',RET,hgr),
                                              ('SHORT',b'I',hgr[:8184]+bytes(8))):
                    launch(name,command)
                    s.wait(lambda:p.peek(0x2000,8192)==expected,'HGR page loaded',30)
                    s.ok(backend+': '+name+' HGR bytes exact',p.peek(0x2000,8192)==expected)
                    back()
                for command in b'RKALDXEWM':
                    s.key(bytes([command]));s.wait(lambda:s.has('Read-only disk.'),'write/execute guard',30)
                s.ok(backend+': write and execution commands remain blocked',True)
                s.ok(backend+': AUX RAM-disk storage preserved',p.peek(0x1000,0xb000,'aux')==aux)
                if backend.startswith('Disk II'):
                    p.eject(1);s.ok('physical DOS source byte-identical',floppy.read_bytes()==raw)
                    s.key(b'\t');s.select('DIRECT.DSK');s.key(RET)
                    s.wait(lambda:s.has('COLORS') and s.has('BYTES'),'DOS image catalog',30);p.stable()
            s.ok('C-stack floor unchanged',p.peek(floor,8)==b'\xa5'*8)
        s.ok('physical source still byte-identical after shutdown',floppy.read_bytes()==raw)
        s.ok('ProDOS source image and metadata byte-identical (no temporary)',hd.read_bytes()==hd_before)
    return ok_all(s,'integrated DOS viewers')


if __name__=='__main__':
    raise SystemExit(main())
