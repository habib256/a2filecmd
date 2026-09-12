#!/usr/bin/env python3
"""Build an independent SDK plugin and launch it through the Other category.

The plugin knows only a2fc_plugin.h and sdk/plugin.cfg, never core addresses.
Each CPU uses a disposable hard disk with the matching complete build.
"""
import shutil
import subprocess
import tempfile
from pathlib import Path
from pom2 import ROOT, BUILD
from xplug import boot_hd, menu_run, RET, ok_all


def main():
    with tempfile.TemporaryDirectory(prefix='a2fc-plugin-') as tmp:
        tmp=Path(tmp)
        target='apple2' if BUILD.name=='build-6502' else 'apple2enh'
        compiler=Path(shutil.which('cc65')).resolve()
        lib=compiler.parent.parent/'share/cc65/lib'/f'{target}.lib'
        for cmd in [
            ['cc65','-t',target,'-O','-Oirs','-Cl','-o',str(tmp/'hello.s'),str(ROOT/'sdk/hello.c')],
            ['ca65','-t',target,'-o',str(tmp/'hello.o'),str(tmp/'hello.s')],
            ['ld65','-C',str(ROOT/'sdk/plugin.cfg'),'-o',str(tmp/'HELLO.PLG'),str(tmp/'hello.o'),str(lib)],
        ]:
            subprocess.run(cmd,check=True)
        plugin=(tmp/'HELLO.PLG').read_bytes()
        files={'A2FILE/HELLO.PLG#061B00':plugin,'WORK/NOTE#040000':b'Unchanged.\r'}
        with boot_hd(tmp,files,port=6667) as (p,s):
            s.ok('independent SDK signature',plugin[:2]==b'\xfc\xa2')
            s.select('WORK');s.key(RET);s.select('NOTE')
            s.key(b'!');s.wait(lambda:s.has('the overlays'),'categories');p.stable()
            from xplug import menu_category
            menu_category(s,p,'HELLO')
            s.ok('third-party plugin is in Other',s.rows()[1].strip()=='Other' and s.has('Example third-party plugin'))
            s.key(RET);p.stable()
            row=s.rows()[22]
            s.ok('plugin reads selected name/type/path','"NOTE"' in row and '04' in row and '/WORKHD/WORK' in row,row)
            s.ok('plugin returns to panels',s.has('Type  Aux'))
        return ok_all(s,'independent plugin')

if __name__=='__main__':raise SystemExit(main())
