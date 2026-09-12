#!/usr/bin/env python3
"""Standard 02TS, unaligned second module, two AYs, unequal durations and AUX."""
import sys,time,re,tempfile
from pathlib import Path
from xplug import boot_hd,RET,ESC,ok_all
from pom2 import ROOT,BUILD,labels
sys.path.insert(0,str(ROOT/'tools'))
from pt3_fixture import module

def snapshot(p):
 time.sleep(.15)
 log=(Path(p.hdv).parent/'pom2.log').read_text()
 return [bytes.fromhex(''.join(re.findall(prefix+r' ([0-9A-F]{32}) ([0-9A-F]{2})',log)[-1])) for prefix in ('AYTRACE','AYTRACE2')]
def quiet(ay):return ay[7]&63==63 and not any(ay[8:11]) and not ay[16]&127

def compact(rows):
 data=bytearray(module(2048,rows=rows)[:512])
 for target,source,length in [(224,512,6),(212,766,6),(218,1022,3)]:
  data[target:target+length]=module(2048,rows=rows)[source:source+length]
 for offset,value in [(103,224),(107,212),(169,218)]:data[offset:offset+2]=value.to_bytes(2,'little')
 for channel,target in enumerate((256,320,384)):
  data[224+channel*2:226+channel*2]=target.to_bytes(2,'little')
  data[target:target+rows+1]=bytes(0x60+(i//8+channel*4)%24 for i in range(rows))+b'\0'
 return bytes(data)

def main():
 a=module(2048,rows=16)+b'\0'
 b=bytearray(module(16384,rows=48));b[13]=ord('3');b[99]=2
 footer=b'PT3!'+len(a).to_bytes(2,'little')+b'PT3!'+len(b).to_bytes(2,'little')+b'02TS'
 song=a+b+footer
 bad=bytearray(song);bad[-6:-4]=b'\xff\xff'
 fast=compact(16)+compact(48)+b'PT3!'+(512).to_bytes(2,'little')+b'PT3!'+(512).to_bytes(2,'little')+b'02TS'
 files={'WORK/D.FAST.PT3#000000':fast,'WORK/A.DUAL.PT3#000000':song,'WORK/B.SINGLE.PT3#000000':module(2048),'WORK/C.BAD.PT3#000000':bad}
 with tempfile.TemporaryDirectory(prefix='pt3-dual-') as d:
  with boot_hd(Path(d),files,port=6974,plugins=['pt3']) as(p,s):
   disk=Path(p.hdv);original=disk.read_bytes()
   s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('WORK');s.key(RET)
   before=p.peek(0x800,0xF800,'aux');sym=labels();cold=sym['__ONCE_RUN__'];floor=sym['__HIMEM__']-sym['__STACKSIZE__'];guard=b'\xd7'*(floor-cold);p.poke(cold,guard)
   p.rq('/speed',{'preset':'1x'});s.select('A.DUAL.PT3');s.key(RET)
   s.wait(lambda:s.has('ESC Back'),'dual start',60)
   s.wait(lambda:all(any(x[8:11]) for x in snapshot(p)),'both AYs playing',10)
   ay=snapshot(p)
   s.ok('both actual AY chips receive notes',all(any(x[8:11]) for x in ay),str([x.hex() for x in ay])+' '+str(s.rows()[22]))
   s.key(b'P');s.ok('pause silences both chips',all(quiet(x) for x in snapshot(p)))
   s.key(b'P');s.key(b'\x15');s.wait(lambda:s.has('ProTracker 3 - B.SINGLE.PT3'),'next single',60)
   s.ok('next track leaves second chip silent',not any(snapshot(p)[1][8:11]))
   s.key(b'\x08');s.wait(lambda:s.has('ProTracker 3 - A.DUAL.PT3') and s.has('ESC Back'),'dual restart',60)
   counter=int(re.search(r'al ([0-9A-Fa-f]{6}) \._pt_frames',(BUILD/'pt3.lbl').read_text())[1],16)
   s.wait(lambda:0<int.from_bytes(p.peek(counter+2,2),'little')<16,'dual timer started')
   started=time.monotonic();cycles=p.rq('/status')['cpu']['cycles']
   s.wait(lambda:quiet(snapshot(p)[0]) and any(snapshot(p)[1][8:11]),'first ends before second',30)
   ay=snapshot(p);s.ok('first song ends while second keeps playing',quiet(ay[0]) and any(ay[1][8:11]))
   s.wait(lambda:int.from_bytes(p.peek(counter+2,2),'little')>=289,'last decoded frame',30)
   guest=(p.rq('/status')['cpu']['cycles']-cycles)/1022727;elapsed=time.monotonic()-started
   s.wait(lambda:s.has('Type  Aux'),'both songs end',30)
   s.ok('natural end after both songs, no decoder/I/O error',not s.has('Invalid PT3.') and not s.has('error.'))
   s.ok('sparse pair decodes all 97/289 frames',p.peek(counter,4)==bytes.fromhex('61002101'),'%.2f guest s / %.2f wall s (cache pressure)'%(guest,elapsed))
   s.ok('both chips silent on natural end',all(quiet(x) for x in snapshot(p)))
   s.select('D.FAST.PT3');s.key(RET);s.wait(lambda:s.has('ProTracker 3 - D.FAST.PT3') and s.has('ESC Back'),'compact pair')
   # Measure decoder time, excluding the much slower //c panel reread.
   s.wait(lambda:0<int.from_bytes(p.peek(counter+2,2),'little')<16,'compact timer started')
   cycles=p.rq('/status')['cpu']['cycles']
   s.wait(lambda:int.from_bytes(p.peek(counter+2,2),'little')>=289,'compact last frame',30)
   guest=(p.rq('/status')['cpu']['cycles']-cycles)/1022727
   s.ok('cached dual stream keeps 50 Hz at 1x',4.8<guest<7.5,'%.2f guest s'%guest)
   s.wait(lambda:s.has('Type  Aux'),'compact pair panels',30)
   s.ok('compact pair preserves both frame counts',p.peek(counter,4)==bytes.fromhex('61002101'))
   s.select('A.DUAL.PT3');s.key(RET);s.wait(lambda:s.has('ESC Back'),'replay',60);s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'Escape',20)
   s.ok('Escape silences both chips',all(quiet(x) for x in snapshot(p)))
   s.select('C.BAD.PT3');s.key(RET);s.wait(lambda:s.has('Invalid PT3.'),'bad footer',60)
   s.ok('invalid footer rejected before sound',all(not any(x[8:11]) for x in snapshot(p)))
   s.ok('AUX outside text screen unchanged',p.peek(0x800,0xF800,'aux')==before)
   s.ok('reserved C-stack floor preserved',p.peek(cold,len(guard))==guard)
  s.ok('source volume unchanged',disk.read_bytes()==original)
 return ok_all(s,'TurboSound')
if __name__=='__main__':raise SystemExit(main())
