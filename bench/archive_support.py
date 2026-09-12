"""A 140K boot fixture for one archive reader, with matching native code."""
import shutil,subprocess,sys
from pathlib import Path
from pom2 import BUILD,ROOT,DISK

def archive_floppy(tmp, name):
    out=tmp/'A2FILECMD.po'
    if DISK.name!='A2FILECMD-full.po':
        shutil.copyfile(DISK,out)
        return out
    # The session floppy cannot contain all archive readers as well as the
    # large FORMAT/DISKIMG tools. Work only on this disposable staging copy.
    stage=tmp/'archive-boot'
    shutil.copytree(BUILD/'benchvol',stage)
    for tool in ('FORMAT','DISKIMG'):
        (stage/'A2FILE'/f'{tool}.PLG#061B00').unlink()
    shutil.copyfile(BUILD/f'A2FILE.CODE.BIN.{name}',stage/'A2FILE'/f'{name}.PLG#061B00')
    subprocess.run([sys.executable,str(ROOT/'tools/mkvolume.py'),str(stage),str(out),
                    '--volume','A2FILECMD','--boot',str(ROOT/'data/prodos_boot.tmpl'),'--blocks','280'],
                   check=True,capture_output=True)
    return out
