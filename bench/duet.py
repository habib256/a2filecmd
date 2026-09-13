#!/usr/bin/env python3
"""Foreground Electric Duet on a disposable disk: both outputs, pause, tracks, exit, bad data."""
import os
import re
import sys
import time
import tempfile
from pathlib import Path
from xplug import boot_hd,menu_run,RET,ESC,ok_all
from pom2 import BUILD
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from mkdemo import duet
from prodos_read import Image
from sample_media import sample_directory

RIGHT=bytes([21]);LEFT=bytes([8])


def jesu():
    """A2DeskTop's Jesu.Joy ($D5/$D0E7) from the sample disk, or None."""
    path=Path(os.environ.get('A2FC_SAMPLE_DISK',str(Path.home()/'src/pom2/hdv/GISTDATA.hdv')))
    if not path.exists():return None
    im=Image(path.read_bytes());k=sample_directory(im)
    for e in im.entries(k):
        if e[1:1+(e[0]&15)].decode()=='JESU.JOY' and e[16]==0xD5:return im.read(e)
    return None


def main():
    tune=duet()
    files={'WORK/CANON.ED#D5D0E7':tune,'WORK/BAD.ED#D5D0E7':tune[:-4],
           'WORK/PLAIN.ED':tune,'WORK/NOTE.TXT':b'Not a song\r'}
    real=jesu()
    if real:files['WORK/JESU.JOY#D5D0E7']=real
    # The speaker player's cycle-counted loop: its own aligned segment.
    lo,hi=[int(x,16) for x in re.search(r'^LOOP\s+([0-9A-F]{6})\s+([0-9A-F]{6})',(BUILD/'duet.map').read_text(),re.M).groups()]
    pulse_entry=int(re.search(r'^al ([0-9A-Fa-f]{6}) \._ed_pulse$',(BUILD/'duet.lbl').read_text(),re.M)[1],16)
    binary=(BUILD/'duet.PLG').read_bytes()
    setter=binary[pulse_entry-0x1B00:pulse_entry-0x1B00+11]
    assert setter[:9]==bytes.fromhex('A2 4A C9 02 90 02 A2 EA 8E'), 'unexpected pulse setter'
    pulse_code=int.from_bytes(setter[9:11],'little')
    with tempfile.TemporaryDirectory(prefix='a2fc-duet-') as tmp:
        with boot_hd(Path(tmp),files,port=6905,plugins=['duet']) as (p,s):
            def in_loop():
                pc=p.rq('/status')['cpu']['pc'];return lo<=pc<=hi
            def loop_seen(n=12):
                return any(in_loop() or time.sleep(.05) for _ in range(n))
            def playing(name):
                return s.has('Electric Duet - '+name) and s.has('Patalenski')
            s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('WORK');s.key(RET);p.stable()
            aux=p.peek(0x1000,0xB000,'aux');floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xA5'*8)
            p.rq('/speed',{'preset':'1x'})
            s.select('CANON.ED');s.key(RET)
            s.wait(lambda:playing('CANON.ED'),'DUET foreground',30)
            s.ok('the staged song is at $2400',p.peek(0x2400,len(tune))==tune)
            s.ok('a Mockingboard plays by default, not the speaker loop',not loop_seen())
            s.key(b'1');s.wait(in_loop,'speaker loop',10);s.ok('1 switches to the speaker player',True)
            s.ok('speaker defaults to 1/8 with three actual shifts',p.peek(pulse_code,4)==bytes.fromhex('4A EA 4A 4A'))
            for width,opcodes in [('1/4','EA EA 4A 4A'),('1/16','4A 4A 4A 4A'),('1/8','4A EA 4A 4A')]:
                s.key(b'D')
                s.wait(lambda:s.has('Speaker pulse '+width) and p.peek(pulse_code,4)==bytes.fromhex(opcodes),'pulse '+width,10)
                s.wait(in_loop,'speaker continues at '+width,10)
                s.ok('D selects '+width+' in the running 6502 player',True)
            s.key(b'P');time.sleep(.5);s.ok('P pauses the speaker player',not loop_seen())
            s.key(b'P');s.wait(in_loop,'resume',10);s.ok('P resumes the speaker player',True)
            s.key(b'2');time.sleep(.5);s.ok('2 returns to the Mockingboard',not loop_seen())
            nxt='JESU.JOY' if real else 'PLAIN.ED'   # the next Electric Duet file by name; NOTE is skipped
            s.key(RIGHT);s.wait(lambda:playing(nxt),'next track',30);s.ok('Right plays the next song',True)
            s.key(LEFT);s.wait(lambda:playing('CANON.ED'),'previous track',30);s.ok('Left plays the previous song',True)
            s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'DUET exit');p.stable()
            s.ok('Escape returns to the song',s.line(0).startswith('CANON.ED') or s.line(40).startswith('CANON.ED'))
            p.rq('/speed',{'preset':'max'})
            s.select('CANON.ED');s.key(RET);s.wait(lambda:playing('CANON.ED'),'reopen',30)
            s.wait(lambda:s.has('Type  Aux'),'Mockingboard natural end',60);s.ok('the Mockingboard rendition ends by itself',True)
            s.select('CANON.ED');s.key(RET);s.wait(lambda:playing('CANON.ED'),'reopen for the speaker',30);s.key(b'1')
            s.wait(lambda:s.has('Type  Aux'),'speaker natural end',60);s.ok('the speaker rendition ends by itself',True)
            s.select('PLAIN.ED');s.key(RET);s.wait(lambda:playing('PLAIN.ED'),'.ED suffix',30);s.ok('a BIN named .ED opens the player',True)
            s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'exit');p.stable()
            if real:
                p.rq('/speed',{'preset':'1x'})
                s.select('JESU.JOY');s.key(RET);s.wait(lambda:playing('JESU.JOY'),'Jesu.Joy',30)
                s.key(b'1');s.wait(in_loop,'Jesu.Joy on the speaker',10);s.ok("A2DeskTop's Jesu.Joy plays on the speaker",True)
                s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'exit');p.stable()
                p.rq('/speed',{'preset':'max'})
            s.select('BAD.ED');s.key(RET);s.wait(lambda:s.has('Bad/large Electric Duet'),'bad ED rejected');s.ok('a truncated song returns safely',s.has('Type  Aux'))
            s.select('NOTE');menu_run(s,p,'DUET');s.wait(lambda:s.has('Bad/large Electric Duet'),'text refused');s.ok('the menu refuses a text file',s.has('Type  Aux'))
            s.ok('AUX unchanged',p.peek(0x1000,0xB000,'aux')==aux)
            s.ok('stack floor unchanged',p.peek(floor,8)==b'\xA5'*8)
    return ok_all(s,'duet')


if __name__=='__main__':raise SystemExit(main())
