// End-to-end DOS writes, on disposable disks only. No ProDOS or IIe hardware.
#include "Memory.h"
#include "M6502.h"
#include "DiskIICard.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <memory>
#include <string>
static std::string screen(Memory& m) {
    std::string s;
    for(int y=0;y<24;++y) { for(int x=0;x<40;++x) {
        unsigned char c=m.data()[0x400+(y&7)*128+(y>>3)*40+x]&127;
        if(c<32) c+=64; s+=c;
    } s+='\n'; } return s;
}
static void run(M6502& c,int cycles) { for(int n=0;n<cycles;) n+=c.run(1024); }
static void expect(Memory& m,const char* needle) {
    if(screen(m).find(needle)==std::string::npos) {
        fprintf(stderr,"Missing %s\n%s",needle,screen(m).c_str()); std::exit(1);
    }
}
int main(int argc,char**argv) {
    assert(argc==5);
    Memory m; m.setIIEMode(false);
    assert(m.loadAppleIIRom((std::string(argv[1])+"/roms/apple2p.rom").c_str()));
    auto card=std::make_unique<DiskIICard>(); auto *d=card.get();
    assert(d->loadBootRom(std::string(argv[1])+"/roms/disk2.rom"));
    assert(d->insertDisk(0,argv[2])); assert(d->insertDisk(1,argv[3]));
    d->setWriteBackEnabled(true); m.slotBus().plug(6,std::move(card));
    M6502 cpu(&m); m.setCpu(&cpu); cpu.setCpuMode(M6502::CpuMode::NMOS);
    m.clearRam(); m.resetSoftSwitches(); m.slotBus().reset(); cpu.hardReset(); cpu.setProgramCounter(0xc600);
    run(cpu,120000000); expect(m,"3 FILES");
    for(int i=0;i<0x800;++i) m.writeRamUnchecked(0x0800+i,0xa5);
    auto keys=[&](const char* s) { m.pasteRawKeys(s,strlen(s)); run(cpu,12000000); };
    auto wait=[&](const char* s) {
        for(int n=0;n<600 && screen(m).find(s)==std::string::npos;++n) run(cpu,1000000);
        expect(m,s);
    };
    keys("\t/"); expect(m,"KEEP.DST"); keys("\tK");
    keys("3"); wait("CANCEL");
    keys("3"); wait("CANCEL"); // numeric bar keys do not confirm writes
    expect(m,"COPY "); expect(m,"KEEP.DST"); // stays on the two panels
    assert(d->getWriteFlushCount()==0);
    keys("\x1b"); expect(m,"3 FILES"); assert(d->getWriteFlushCount()==0);
    // Hardware write protection: even VTOC reservation must be refused.
    d->setDriveHostWriteProtected(1,true);
    keys("C"); wait("CANCEL"); keys("O"); expect(m,"CANCEL");
    assert(d->getWriteFlushCount()==0);
    keys("Y"); wait("DISK IS WRITE PROTECTED");
    assert(d->getWriteFlushCount()==0);
    keys(" "); d->setDriveHostWriteProtected(1,false);
    assert(screen(m).substr(21*41,9)=="A2FC.MINI");
    keys("C"); wait("CANCEL"); keys("Y"); wait("COPIED");
    assert(d->getWriteFlushCount()>0); assert(d->flushPendingWrites());
    for(int i=0;i<0x800;++i) assert(m.data()[0x0800+i]==0xa5);
    keys(" ");
    auto writes=d->getWriteFlushCount();
    assert(screen(m).substr(21*41,9)=="A2FC.MINI");
    keys("C"); wait("NAME EXISTS");
    assert(d->getWriteFlushCount()==writes); keys(" ");
    keys("Q"); keys("Y"); expect(m,"\n]");
    keys("CATALOG,D2\r"); wait("A2FC.MINI");
    // DOS itself loads the new binary and then allocates another file.
    keys("BLOAD A2FC.MINI,D2\r"); run(cpu,30000000);
    std::ifstream in(argv[4],std::ios::binary);
    std::string binary((std::istreambuf_iterator<char>(in)),{});
    assert(!binary.empty());
    assert(memcmp(m.data()+0x1000,binary.data(),binary.size())==0);
    keys("NEW\r10 PRINT \"SAFE\"\rSAVE CHECK.DOS,D2\r"); run(cpu,60000000);
    assert(screen(m).find("I/O ERROR")==std::string::npos);
    keys("CATALOG,D2\r"); expect(m,"CHECK.DOS");
    assert(d->flushPendingWrites());
    puts("PASS: II+ NMOS cancel, protection, verified binary copy, collision, DOS BLOAD/SAVE, stack guard");
}
