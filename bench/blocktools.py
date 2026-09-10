#!/usr/bin/env python3
"""Tagged VERIFY, streamed VOLINFO reports and read-only BLKVIEW under POM2."""
import sys
import tempfile
from pathlib import Path
from pom2 import Pom2, Session, ROOT
from xplug import stage_hd, menu_run, RET, ESC, TAB, ok_all
sys.path.insert(0,str(ROOT/'tools'))
from prodos_read import Image
from test_volinfo import fixture
from six import make_disk


def named(img,key,name):
    return next(e for e in img.entries(key) if e[1:1+(e[0]&15)].decode()==name)


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-inspect-') as t:
        tmp=Path(t)
        raw=fixture()
        raw[3*512+510:3*512+514]=bytes.fromhex('DEADBEEF')
        raw[5*512+10:5*512+14]=bytes.fromhex('DEADBEEF')
        target=make_disk(tmp)
        hd=stage_hd(tmp,{'WORK/BIG.BIN':bytes(range(256))*80,
            'WORK/SMALL.TXT':b'hello\r','WORK/EMPTY.BIN':b'',
            'WORK/BAD.BIN':b'unreadable','WORK/DIR/INNER.TXT':b'inner',
            'WORK/IMAGE.PO#060000':raw},plugins=['verify','volinfo','blkview'])
        data=bytearray(hd.read_bytes()); img=Image(data)
        work=int.from_bytes(named(img,2,'WORK')[17:19],'little')
        bad=named(img,work,'BAD'); off=data.index(bad,work*512)
        data[off+17:off+19]=b'\xff\xff';hd.write_bytes(data)
        with Pom2(hd,floppy2=target,port=6846) as p:
            s=Session(p);s.boot();s.select('WORK');s.key(RET);p.stable()
            stack=p.peek(0x80,2)
            floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xa5'*8)
            s.select('SMALL');menu_run(s,p,'VERIFY')
            s.ok('single file verified',s.has('VERIFY: 1 read, 0 errors'),s.rows()[22])
            for name in ('BIG','SMALL','EMPTY','BAD','DIR'):
                s.select(name);s.key(b' ')
            menu_run(s,p,'VERIFY')
            s.ok('four tagged files, one unreadable, directory skipped',s.has('VERIFY: 4 read, 1 errors'),s.rows()[22])
            # Marks survive the small overlay and the BIG menu round trip.
            menu_run(s,p,'VERIFY')
            s.ok('tags preserved across repeated verification',s.has('VERIFY: 4 read, 1 errors'),s.rows()[22])
            for name in ('BIG','SMALL','EMPTY','BAD','DIR'):
                s.select(name);s.key(b' ')
            s.select('SMALL');menu_run(s,p,'VOLINFO')
            s.wait(lambda:s.has('M Bitmap'),'audit',90)
            s.key(b'F');s.wait(lambda:s.has('End of block list'),'file blocks')
            small=named(img,work,'SMALL');key=int.from_bytes(small[17:19],'little')
            s.ok('selected file physical data block',s.has('D %5u ($%04X)'%(key,key)),'\n'.join(s.rows()))
            s.key(RET);s.key(ESC);p.stable()
            s.key(TAB);s.key(b'/');s.select('/TARGET',40);s.key(RET);p.stable();s.key(TAB)
            s.select('BIG');menu_run(s,p,'VOLINFO');s.wait(lambda:s.has('M Bitmap'),'audit',90)
            s.key(b'E');s.wait(lambda:s.has('Report name'),'report name');s.key(RET)
            s.wait(lambda:s.has('Report saved'),'report saved',60);s.ok('report exported',True)
            s.key(RET);s.key(b'E');s.wait(lambda:s.has('Report name'),'same name');s.key(RET)
            s.wait(lambda:s.has('Cannot create report'),'existing report refused');s.ok('report never overwritten',True)
            s.key(RET);s.key(ESC);p.stable()
            s.select('IMAGE.PO');menu_run(s,p,'BLKVIEW')
            s.wait(lambda:s.has('BLKVIEW - READ ONLY'),'viewer')
            s.ok('image opened at first block',s.has('Block 0 ($0000) / 280 blocks'))
            s.key(b'G');s.wait(lambda:s.has('Block number'),'jump');s.type('0002');s.key(RET);p.stable()
            s.key(b'D');p.stable();s.ok('directory header decoded',s.has('HEADER entries=0'),'\n'.join(s.rows()))
            s.key(b'I');p.stable();s.key(b' ');p.stable()
            s.ok('index pagination covers next 32 pointers',s.has('entries 32..63'))
            s.key(b'H');s.key(b' ');p.stable();s.ok('second 256-byte half',s.has('Page 2') and s.has('100  '))
            s.key(b'N');p.stable();s.ok('next block',s.has('Block 3 ($0003)'))
            s.key(b'P');p.stable();s.ok('previous block',s.has('Block 2 ($0002)'))
            s.key(b'G');s.wait(lambda:s.has('Block number'),'jump outside');s.type('FFFF');s.key(RET)
            s.wait(lambda:s.has('Block outside'),'bounds');s.key(RET);p.stable()
            s.ok('invalid jump preserves current block',s.has('Block 2 ($0002)'))
            s.key(b'F');s.wait(lambda:s.has('Find 4 bytes'),'signature');s.type('DEADBEEF');s.key(RET)
            s.wait(lambda:s.has('Match at block 3, offset $1FE'),'cross-block match',90);p.stable()
            s.ok('search crosses block boundary',s.has('Block 3 ($0003)') and s.has('Page 2'))
            s.key(b'A');s.wait(lambda:s.has('Match at block 5, offset $00A'),'next match',90)
            s.ok('find next advances',True)
            s.key(b'A');s.wait(lambda:s.has('No further match'),'exhausted',90);s.ok('no wrap after final match',True);s.key(RET);p.stable()
            s.key(b'X');s.wait(lambda:s.has('Block count'),'invalid range');s.type('FFFF');s.key(RET)
            s.wait(lambda:s.has('Invalid block range'),'range refused');s.ok('invalid extraction range refused',True);s.key(RET);p.stable()
            s.key(b'X');s.wait(lambda:s.has('Block count'),'range');s.type('0002');s.key(RET)
            s.wait(lambda:s.has('New binary file'),'new file');s.type('CUT.BIN');s.key(RET)
            s.wait(lambda:s.has('Blocks extracted'),'extracted',60);s.ok('block extraction completed',True);s.key(RET);p.stable()
            s.key(b'X');s.wait(lambda:s.has('Block count'),'range again');s.type('0002');s.key(RET)
            s.wait(lambda:s.has('New binary file'),'existing file');s.type('CUT.BIN');s.key(RET)
            s.wait(lambda:s.has('Cannot create file'),'existing refused');s.ok('extraction never overwrites',True);s.key(RET);p.stable()
            s.key(ESC);p.stable()
            s.key(TAB);s.key(b'/');s.select('/WORKHD',40);s.key(RET);p.stable();s.key(TAB)
            s.select('SMALL');menu_run(s,p,'BLKVIEW');s.wait(lambda:s.has('BLKVIEW - READ ONLY'),'volume viewer')
            s.ok('regular file selects containing volume',s.has('/ 4000 blocks'))
            s.key(b'X');s.wait(lambda:s.has('Choose another destination volume'),'source protected')
            s.ok('device extraction cannot write source volume',True);s.key(RET);p.stable()
            s.key(ESC);p.stable();s.ok('resident stack restored and budget respected',p.peek(0x80,2)==stack and p.peek(floor,8)==b'\xa5'*8)
            p.eject(1)  # POM2 commits dirty media when ejected, before SIGTERM.
        after=Image(hd.read_bytes());out=Image(target.read_bytes());report=out.read(named(out,2,'VOLINFO.TXT'))
        big=named(img,work,'BIG');key=int.from_bytes(big[17:19],'little')
        s.ok('report contains summary and selected index/data blocks',report.endswith(b'END REPORT\r\n') and b'VOLINFO /WORKHD' in report and b'FILE BIG:' in report and ('I %5u ($%04X)'%(key,key)).encode() in report,report.decode())
        s.ok('extracted bytes exact',out.read(named(out,2,'CUT.BIN'))==raw[5*512:7*512])
        s.ok('image and source files unchanged',after.read(named(after,work,'IMAGE.PO'))==raw and after.read(named(after,work,'BIG'))==bytes(range(256))*80)
        return ok_all(s,'blocktools')
if __name__=='__main__': raise SystemExit(main())
