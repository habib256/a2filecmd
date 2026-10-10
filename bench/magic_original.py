#!/usr/bin/env python3
"""Original Magic Window editor text vs actual C reader, disposable disks.
Checks ten literal labels; this is not a typography/pixel comparison.
"""
import os,sys,shutil,tempfile,time,json,hashlib
from pathlib import Path
from xplug import stage_hd
from pom2 import Pom2,ROOT
sys.path.insert(0,str(ROOT/'tools'))
from test_nexttext import NextText,real_files

def main():
    root=Path(os.environ.get('A2FC_NEXT_CORPUS','/tmp/a2fc-next-corpus'))
    source=root/'images/productivity/word_processing/magic_window/MagicWindowIIe.DSK'
    before=hashlib.sha256(source.read_bytes()).hexdigest()
    document=next(d for r,n,t,a,d in real_files() if n=='PRINTER TEST.MW')
    labels=['PICA','ELITE','CONDENSED','UNDERLINED','BOLDFACE','SUPERSCRIPT','SUBSCRIPT','DOUBLE SIZE','ALTERNATE FONT','DOUBLE STRIKE']
    NextText.setUpClass()
    try:rows,_,_=NextText().run_file('magwin',document)
    finally:NextText.tearDownClass()
    with tempfile.TemporaryDirectory(prefix='magic-original-') as tmp:
        tmp=Path(tmp);hd=stage_hd(tmp);floppy=tmp/'magic.dsk';shutil.copyfile(source,floppy)
        with Pom2(hd,floppy=floppy,port=6942) as p:
            time.sleep(2);p.raw(b'\x1b');time.sleep(3)
            p.raw(b'2\r');time.sleep(2);p.raw(b'4\r');time.sleep(2)
            p.raw(b'6\r');time.sleep(3);p.raw(b'1\r');time.sleep(2)
            p.raw(b'1\r');time.sleep(2);original='\n'.join(p.screen())
            assert 'FILE PRINTER TEST' in original,original
            for label in labels:
                assert label in original and any(label in row for row in rows),label
        assert hashlib.sha256(floppy.read_bytes()).hexdigest()==before
    assert hashlib.sha256(source.read_bytes()).hexdigest()==before
    result={'date':'2026-10-10','original':'Magic Window //e','document':'PRINTER TEST.MW','source_sha256':before,'literal_labels_compared':len(labels),'sources_preserved':True,'scope':'Literal labels only, no typography/pixel equivalence; control bytes shown as caret notation by A2FC.'}
    output=Path('/tmp/a2fc-next-oracle');output.mkdir(exist_ok=True)
    (output/'magic.json').write_text(json.dumps(result,indent=2)+'\n')
    print('10/10 labels, original and C; source disks unchanged')

if __name__=='__main__':main()
