"""Category menu and inverse questions, on a disposable volume only."""
import tempfile
from pathlib import Path
from xplug import boot_hd, menu_run, ok_all, RET, ESC

EXPECTED = {
 'Files': 'ATTR AWP COMPARE DELETE EDIT FIND FIXTYPES GOTO HEX MDVIEW MOVE RENAME SEARCH SYNC TAGPAT TEXT TREE TXTCONV',
 'Images': 'DGRVIEW EXTASIE FONTVIEW IMAGE LZ4FH PACKFOT PAINT816 PRINTSHOP',
 'Music': 'MUSIC PT3',
 'Disks': 'BLKEDIT BLKVIEW BOOTBLK DISKCMP DISKIMG DOS33 FORMAT IMGCONV IMGFS MKIMAGE RESCUE UNDELETE VERIFY VOLINFO VOLNAME WIPE',
 'Programming': 'BASLIST CRC DISASM IDENT INTBASIC RUN',
 'System': 'DATE HELP',
 'Archives': 'BINARY2 UNSHRINK',
 'Other': '',
}

def cells(p, row=22):
    addr = 0x400 + (row % 8)*0x80 + (row//8)*0x28
    m, a = p.peek(addr,40), p.peek(addr,40,'aux')
    return [a[c//2] if c%2==0 else m[c//2] for c in range(80)]

def question(s,p,label):
    p.stable()
    text=s.rows()[22].rstrip()
    s.ok(label+' inverse', bool(text) and all(v<128 for v in cells(p)[:len(text)]),text)
    s.ok(label+' restores conio',p.peek(0x32,1)==b'\xff')

def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-menu-') as tmp:
        with boot_hd(Path(tmp),{'WORK/NOTE#040000':b'Preserve this file.\r'},port=6891) as (p,s):
            s.select('WORK');s.key(RET);s.select('NOTE')
            aux=p.peek(0x1000,0xb000,'aux')
            s.key(b'!');s.wait(lambda:s.has('the overlays'),'categories');p.stable()
            for number,(name,names) in enumerate(EXPECTED.items()):
                s.ok('category '+name,s.rows()[2+number].strip().upper()==name.upper(),s.rows()[2+number])
                s.key(RET);p.stable()
                actual=[r[2:14].strip() for r in s.rows()[2:20] if r[2:14].strip()]
                s.ok(name+' complete and sorted',actual==names.split() if names else s.has('No overlay here.'),actual)
                if len(names.split())>6:
                    s.key(b'\x15');p.stable();s.ok(name+' right +6',s.cursor_row(2)==8)
                    s.key(b'\x08');p.stable();s.ok(name+' left -6',s.cursor_row(2)==2)
                s.key(ESC);p.stable()
                s.ok(name+' escape returns to category',s.cursor_row()==2+number)
                if number<7:s.key(b'\x0a')
            s.key(ESC);p.stable()
            s.ok('menu preserves AUX RAM',p.peek(0x1000,0xb000,'aux')==aux)
            s.ok('escape returns to panels',s.has('Type  Aux'))
            s.key(b'R');s.wait(lambda:'NOTE' in s.rows()[22],'rename prompt');question(s,p,'Rename')
            s.key(ESC);p.stable()
            s.key(b'D');s.wait(lambda:'Y/N' in s.rows()[22],'delete confirmation');question(s,p,'Delete')
            s.key(b'N');p.stable();s.ok('refusal preserves entry',s.has('NOTE'))
            menu_run(s,p,'TXTCONV');question(s,p,'Conversion choice');s.key(ESC)
            menu_run(s,p,'TAGPAT');question(s,p,'Pattern label');s.key(b'N');p.stable();question(s,p,'Pattern echo');s.key(ESC)
            menu_run(s,p,'GOTO');s.key(b'P');question(s,p,'Path');s.key(ESC)
            menu_run(s,p,'DATE');s.key(b'S');p.stable()
            # DATE holds INVFLG during its incremental input; both exits restore it.
            s.ok('Date label inverse',all(v<128 for v in cells(p)[:12]))
            s.key(b'1');p.stable();s.ok('Date echo inverse',all(v<128 for v in cells(p)[:13]))
            s.key(ESC);p.stable();s.ok('Date cancellation restores video',p.peek(0x32,1)==b'\xff')
    return ok_all(s,'menu and questions')
if __name__=='__main__':raise SystemExit(main())
