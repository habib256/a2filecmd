#!/usr/bin/env python3
"""Automatic existing graphics/font/source readers, disposable DOS/ProDOS disks."""
import os,sys,tempfile
if "--enh" in sys.argv:
 os.environ["A2FC_BUILD"]="build"
 os.environ["A2FC_IMG"]="A2FILECMD-full"
from pathlib import Path
if "--6502" in sys.argv:
 os.environ["A2FC_BUILD"]="build-6502"
 os.environ["A2FC_PRESET"]="iie_unenh"
from xplug import boot_hd,RET,ESC,ok_all
from pom2 import ROOT
sys.path.insert(0,str(ROOT/'tools'))
from test_fontrix import fixture,preview
from test_sample_media import clip_page
from test_fontview import raw_page
from test_retrotext import lisa
from test_dos_names import display_name
from test_printshop_extras import font as shop_font,font5 as shop_font5
from mkdos33 import build

def font_matches(s,expected):
 rows=s.rows()
 return all(rows[i+1][8:72]==expected[i][8:72] for i in range(16))

def main():
 borders_only='--borders-only' in sys.argv
 hrcg={name:bytes((i*13+i//8)&255 for i in range(n)) for name,n in [('HRCG.FONT',768),('HRCG.SET',1024)]}
 clip=bytes((i*37)&255 for i in range(572));font=fixture(height=32)
 merlin=bytes(c|128 for c in b'LABEL LDA #$20 ;note\r ASC "A B" ;quoted space\r*Comment\r')
 unnamed=bytes(c|128 for c in b'LABEL LDA #$20 ;note\r STA $300\r RTS\r')
 lisa_source=lisa(b'*comment\r',b'LABEL   \xcd\x02#$20\xbbnote\r',b' \xa0\0\r')
 long_fonts={'BLIPPO BLACK.SET':hrcg['HRCG.FONT'],'ABCDEFGHIJKLMNOPQRSTUVWXY.FONT':hrcg['HRCG.SET']}
 mw=bytearray(256);mw[0]=0x8d;mw[2]=32;mw+=b'Magic Window complete DOS name\r'
 shop_fonts={'ALPHABET':(0x6000,shop_font(prefix=0)),'TYPEFACE':(0x5ff4,shop_font())}
 border=bytearray(264);border[12]=128;border[12+42+3*3+1]=64;border[12+84+13*3+2]=1
 legacy=bytearray(144);legacy[24]=1;legacy[0]=64;legacy[48+24+23]=1;legacy[96+10]=2
 shop_borders={'MOTIF':(0x4800,bytes(legacy)),'ORNAMENT':(0x7800,b'\x03\0\0\0'+legacy)}
 dos=build([(name,4,aux.to_bytes(2,'little')+len(b).to_bytes(2,'little')+b) for name,aux,b in [('CLIP',0x4800,clip),('SET.TEST',0x6400,font),('FASTLOADER/DOCS.MW',0x2000,mw)]+[(name,0x6100,b) for name,b in {**hrcg,**long_fonts}.items()]+[(name,aux,b) for name,(aux,b) in {**shop_fonts,**shop_borders}.items()]]+[('SAMPLE.S',0,merlin),('LONG.MERLIN.SOURCE.ASM',0,merlin),('SOURCE',0,unnamed),('LISA.SRC',0x40,lisa_source),('PLAIN.TXT',0,b'Simple generic DOS text\r')])
 data={f'WORK/{name}#066100':b for name,b in hrcg.items()}
 data.update({'WORK/CLIP#064800':clip,'WORK/CLIP.NEXT#064800':bytes(c^255 for c in clip),'WORK/SET.TEST#066400':font,'WORK/SAMPLE.S#040000':merlin,'WORK/SOURCE#040000':unnamed,'WORK/LISA.SRC#F40000':lisa_source,'WORK/READERS.DSK#060000':dos})
 data.update({f'WORK/{name}#06{aux:04X}':b for name,(aux,b) in shop_fonts.items()})
 data.update({f'WORK/{name}#06{aux:04X}':b for name,(aux,b) in shop_borders.items()})
 data.update({'WORK/TYPO#F51000':shop_font5(),'WORK/FRAME#F52000':bytes(border)})
 with tempfile.TemporaryDirectory(prefix='direct-readers-native-') as tmp:
  tmp=Path(tmp);physical=tmp/'readers.dsk';physical.write_bytes(dos)
  with boot_hd(tmp,data,port=6941 if "--6502" in sys.argv else 6940,plugins=['printshop','fontrix','fontview','dosfont','merlin','lisav2','magwin','dosview','psfont','psborder'],floppy2=physical) as (p,s):
   s.key(b'/');s.select('/WORKHD');s.key(RET);s.select('WORK');s.key(RET);p.stable()
   source=Path(p.hdv).read_bytes();aux=p.peek(0x1000,0xb000,'aux');floor=s.sym['__HIMEM__']-s.sym['__STACKSIZE__'];p.poke(floor,b'\xa5'*8)
   panel_x=0
   for backend in ('ProDOS','DOS image','DOS drive'):
    if backend=='DOS image':s.select('READERS.DSK');s.key(RET);s.wait(lambda:s.has('SET.TEST'),'DOS image mounted',30)
    if backend=='DOS drive':
     s.key(b'/');s.wait(lambda:s.has('DOS 3.3'),'physical DOS volume',30)
     row=next(i for i,r in enumerate(s.rows()) if 'DOS 3.3' in r)
     # Select the actual volume-list entry by its displayed name.
     panel_x=40 if s.rows()[row][40:].startswith('DOS 3.3') else 0
     if s.cursor_row(panel_x) is None:s.key(b'\t')
     s.select('DOS 3.3',panel_x);s.key(RET);s.wait(lambda:s.has('SET.TEST'),'DOS drive mounted',30)
    for key in (RET,b'I'):
     for name in [*shop_borders]+(['FRAME'] if backend=='ProDOS' else []):
      s.select(name,panel_x);s.key(key)
      s.wait(lambda:s.has('Print Shop border:') and s.has('ESC or any key back'),'renamed border '+name,30)
      rows=s.rows()
      if name=='FRAME':correct=rows[4][0]=='*' and rows[7][35]=='*' and rows[17][75]=='*'
      else:correct=rows[4][0]=='*' and rows[4][49]=='*' and rows[17][0]=='*' and rows[12][62]=='*' and sum(r.count('*') for r in rows[4:18])==4
      s.ok('Renamed Print Shop border '+name+' '+backend+' '+repr(key),correct)
      s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'Print Shop border exit',30)
      s.wait(lambda:s.line(panel_x).startswith(name+' '),'Print Shop border remains selected',10)
     if borders_only:continue
     for name in [*shop_fonts]+(['TYPO'] if backend=='ProDOS' else []):
      s.select(name,panel_x);s.key(key)
      s.wait(lambda:s.has('Print Shop font:') and s.has('Left/Right glyph'),'renamed Print Shop font '+name,30)
      s.ok('Renamed Print Shop font '+name+' '+backend+' '+repr(key),all(s.rows()[r][4:20]=='**            **' for r in range(1,8)))
      s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'Print Shop font exit',30)
      s.wait(lambda:s.line(panel_x).startswith(name+' '),'Print Shop font remains selected',10)
     if backend=='ProDOS':
      s.select('SOURCE',panel_x);s.key(key)
      s.wait(lambda:s.has('End - press a key'),'ProDOS Merlin without suffix',30)
      s.ok('ProDOS Merlin without suffix '+repr(key),s.rows()[1].startswith('LABEL    LDA   #$20       ;note') and s.rows()[2].startswith('         STA   $300') and s.rows()[3].startswith('         RTS'))
      s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'ProDOS source exit',30)
      s.wait(lambda:s.line(panel_x).startswith('SOURCE '),'ProDOS source remains selected',10)
     if backend!='ProDOS':
      for name,b in long_fonts.items():
       shown_name=display_name(name);s.select(shown_name,panel_x);s.key(key)
       s.wait(lambda:p.peek(0x2000,8192)==raw_page(b),'long DOS font '+name,30)
       s.ok('Full DOS name HRCG '+name+' '+backend+' '+repr(key),True)
       s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'long font exit',30)
       s.wait(lambda:s.line(panel_x).startswith(shown_name+' '),'long font remains selected',10)
      for name,expected in [('LONG.MERLIN.SOURCE.ASM','LABEL    LDA   #$20       ;note'),('SOURCE','LABEL    LDA   #$20       ;note'),('FASTLOADER/DOCS.MW','Magic Window complete DOS name')]:
       shown_name=display_name(name);s.select(shown_name,panel_x);s.key(key)
       s.wait(lambda:s.has('End - press a key'),'long DOS document '+name,30)
       s.ok('Full DOS name text '+name+' '+backend+' '+repr(key),s.rows()[1].startswith(expected))
       s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'long document exit',30)
       s.wait(lambda:s.line(panel_x).startswith(shown_name+' '),'long document remains selected',10)
      if key==RET:
       s.select('PLAIN.TXT',panel_x);s.key(key);s.wait(lambda:s.rows()[0].startswith('Simple generic DOS text') and s.has('Space next, B previous, R first'),'generic fallback',30)
       s.ok('Generic DOS fallback '+backend,s.rows()[0].startswith('Simple generic DOS text'))
       s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'generic fallback exit',30)
     s.select('LISA.SRC',panel_x);s.key(key)
     s.wait(lambda:s.has('End - press a key'),'LISA v2 '+backend,30)
     rows=s.rows()
     s.ok('LISA v2 tokens '+backend+' '+repr(key),rows[1].startswith('*comment') and rows[2].startswith('LABEL    LDA #$20            ;note') and rows[3].startswith('         NOP'))
     s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'LISA v2 exit',30)
     s.wait(lambda:s.line(panel_x).startswith('LISA.SRC '),'LISA v2 remains selected',10)
     s.select('SAMPLE.S',panel_x);s.key(key)
     s.wait(lambda:s.has('End - press a key'),'Merlin '+backend,30)
     rows=s.rows()
     s.ok('Merlin columns '+backend+' '+repr(key),rows[1].startswith('LABEL    LDA   #$20       ;note') and rows[2].startswith('         ASC   "A B"      ;quoted space') and rows[3].startswith('*Comment'))
     s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'Merlin exit',30)
     s.wait(lambda:s.line(panel_x).startswith('SAMPLE.S '),'Merlin remains selected',10)
     s.select('CLIP',panel_x);s.key(key);s.wait(lambda:p.peek(0x2000,8192)==clip_page(clip),'clip '+backend,30);s.ok('Clip '+backend+' '+repr(key),True)
     if backend=='ProDOS':
      s.key(b'\x15');s.wait(lambda:p.peek(0x2000,8192)==clip_page(bytes(c^255 for c in clip)),'next clip in album',30)
      s.key(b'\x08');s.wait(lambda:p.peek(0x2000,8192)==clip_page(clip),'previous clip in album',30)
      s.ok('Print Shop album '+repr(key),True)
     s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'clip exit',30)
     s.wait(lambda:s.line(panel_x).startswith('CLIP '),'clip remains selected',10)
     s.select('SET.TEST',panel_x);s.key(key);s.wait(lambda:s.has('Fontrix: A'),'font '+backend,30)
     expected=preview(font,65);s.wait(lambda:font_matches(s,expected),'complete font bitmap',10);rows=s.rows();s.ok('Font pixels '+backend+' '+repr(key),all(rows[i+1][8:72]==expected[i][8:72] for i in range(16)))
     s.key(b'\x15');s.wait(lambda:s.has('Fontrix: B'),'next glyph',10)
     s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'font exit',30);p.stable()
     for name,b in hrcg.items():
      s.select(name,panel_x);s.key(key)
      s.wait(lambda:p.peek(0x2000,8192)==raw_page(b),'HRCG '+name+' '+backend,30)
      s.ok('HRCG '+name+' '+backend+' '+repr(key),True)
      s.key(ESC);s.wait(lambda:s.has('Type  Aux'),'HRCG exit',30)
      s.wait(lambda:s.line(panel_x).startswith(name+' '),'HRCG remains selected',10);p.stable()
   s.ok('AUX preserved',p.peek(0x1000,0xb000,'aux')==aux)
   s.ok('Stack floor preserved',p.peek(floor,8)==b'\xa5'*8)
   p.sync_disks();s.ok('ProDOS source volume preserved',Path(p.hdv).read_bytes()==source)
   s.ok('DOS source disk preserved',physical.read_bytes()==dos)
 return ok_all(s,'direct_readers')
if __name__=='__main__':raise SystemExit(main())
