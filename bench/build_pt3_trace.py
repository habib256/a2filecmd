#!/usr/bin/env python3
"""Build a disposable POM2 host with read-only AY register tracing.

Does not edit POM2. Builds an isolated core library in /tmp and uses the usual headless
bench driver, adding a periodic dump of the first AY and VIA IER and flushing the
disposable hard disk on orderly shutdown for byte-exact persistence checks.
"""
import subprocess
import tempfile
from pathlib import Path
root=Path.home()/'src'
pom=root/'pom2'
source=root/'pom2adventure/SCOSWAMP.MORE/TOOLS/pom2_playtest.cpp'
needle='while (!stopped) std::this_thread::sleep_for(std::chrono::milliseconds(100));'
s=source.read_text()
# Opt-in MB4c on the //c internal connector. POM2 maps it to $C400 even
# though the host parks it on virtual slot 3, leaving the IOU mouse alone.
needle_iic = 'mem.slotBus().plug(5, std::move(sp));'
assert s.count(needle_iic) == 1, 'Review //c host adapter'
s = '#include <cstdlib>\n' + s.replace(needle_iic, needle_iic + '''
            if (std::getenv("A2FC_MB4C")) {
                auto mb4c = std::make_unique<MockingboardCard>(3);
                mb4c->setCpu(&ctrl.cpu());
                mem.slotBus().plug(3, std::move(mb4c));
            }
''')
assert s.count(needle)==1,'Headless host loop changed; review trace adapter'
s='#include <cstdio>\n'+s.replace(needle,'''while (!stopped) {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
            auto state = ctrl.lockState();
            auto* mb = dynamic_cast<MockingboardCard*>(mem.slotBus().peripheral(iic ? 3 : 2));
            if (mb) {
                std::printf("AYTRACE ");
                for (int r=0;r<16;++r) std::printf("%02X",mb->getAyRegister(0,r));
                std::printf(" %02X\\n",mb->peekViaRegister(0,14));
                std::fflush(stdout);
            }
        }''')
s=s.replace('diskCard = hdv.get();', 'hdv->setWriteBackEnabled(true); // only disposable bench images\n            diskCard = hdv.get();')
s=s.replace('if (floppyCard) (void)floppyCard->flushPendingWrites();', 'if (floppyCard) (void)floppyCard->flushPendingWrites();\n        if (diskCard && !diskCard->saveDirty()) throw std::runtime_error(\"HDV flush failed\");')
core=Path('/tmp/a2fc-pom2-native')
subprocess.run(['cmake','-S',str(pom),'-B',str(core),'-DCMAKE_BUILD_TYPE=Release','-DPOM2_ENABLE_TESTS=OFF','-DPOM2_ENABLE_SLIRP=OFF'],check=True)
subprocess.run(['cmake','--build',str(core),'--target','pom2_core','-j','6'],check=True)
with tempfile.TemporaryDirectory(prefix='a2fc-pt3-host-') as tmp:
    src=Path(tmp)/'host.cpp';src.write_text(s)
    cmd=['c++','-std=c++17','-O2','-DNDEBUG']
    for sub in ('src','include','imgui'):cmd+=['-I'+str(pom/sub)]
    cmd+=['-I'+str(core/'generated')]
    cmd+=['-DPOM2_ROOT="'+str(pom)+'"',str(src),str(core/'libpom2_core.a'),'-framework','CoreAudio','-framework','AudioToolbox','-framework','AudioUnit','-o','/tmp/a2fc-pt3-trace']
    subprocess.run(cmd,check=True)
print('/tmp/a2fc-pt3-trace')
