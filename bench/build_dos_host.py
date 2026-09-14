#!/usr/bin/env python3
"""Build a disposable POM2 host for DOS disk/image persistence tests.

No POM2 sources are edited. Only bench-created HDVs may be passed to this
host: unlike the usual runner, it writes their guest changes back on exit.
--slot 5 reproduces Disk II S5 / ProDOS hard disk S6.
"""
import argparse
import subprocess
import tempfile
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--slot',type=int,choices=(5,6),default=6)
p.add_argument('--pom2',type=Path,default=Path.home()/'src/pom2')
p.add_argument('--source',type=Path,default=Path(__file__).resolve().parent/'pom2_playtest/pom2_playtest.cpp')
a=p.parse_args();s=a.source.read_text()
def change(old,new):
 global s
 assert s.count(old)==1,'Review POM2 test adapter: '+old
 s=s.replace(old,new)
change('diskCard = hdv.get();','hdv->setWriteBackEnabled(true);\n            diskCard = hdv.get();')
change('if (floppyCard) (void)floppyCard->flushPendingWrites();',
       'if (floppyCard) (void)floppyCard->flushPendingWrites();\n        if (diskCard && !diskCard->saveDirty()) throw std::runtime_error("HDV flush failed");')
if a.slot==5:
 for old,new in [('bootSlot = 5','bootSlot = 6'),('make_unique<ProDOSHardDiskCard>(5)','make_unique<ProDOSHardDiskCard>(6)'),
                 ('plug(5, std::move(hdv))','plug(6, std::move(hdv))'),('plug(6, std::move(card))','plug(5, std::move(card))'),
                 ('bootSlot == 6 && !floppyCard','bootSlot == 5 && !floppyCard')]:change(old,new)
out='/tmp/a2fc-slot5' if a.slot==5 else '/tmp/a2fc-dos-host'
with tempfile.TemporaryDirectory(prefix='dos-host-',dir='/tmp') as d:
 src=Path(d)/'host.cpp';src.write_text(s)
 cmd=['c++','-std=c++17','-O2','-DNDEBUG']
 for sub in ('src','include','build/generated','imgui'):cmd+=['-I'+str(a.pom2/sub)]
 cmd+=['-DPOM2_ROOT="'+str(a.pom2)+'"',str(src),str(a.pom2/'build/libpom2_core.a'),
       '-framework','CoreAudio','-framework','AudioToolbox','-framework','AudioUnit','-o',out]
 subprocess.run(cmd,check=True)
print(out)
