// RETURN and B: a DOS binary run from the panels, on disposable disks only.
#include "Memory.h"
#include "M6502.h"
#include "DiskIICard.h"
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
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
int main(int argc,char** argv) {
    assert(argc==4);
    Memory m; m.setIIEMode(false);
    assert(m.loadAppleIIRom((std::string(argv[1])+"/roms/apple2p.rom").c_str()));
    auto card=std::make_unique<DiskIICard>(); auto *d=card.get();
    assert(d->loadBootRom(std::string(argv[1])+"/roms/disk2.rom"));
    assert(d->insertDisk(0,argv[2])); assert(d->insertDisk(1,argv[3]));
    d->setWriteBackEnabled(true); m.slotBus().plug(6,std::move(card));
    M6502 cpu(&m); m.setCpu(&cpu); cpu.setCpuMode(M6502::CpuMode::NMOS);
    m.clearRam(); m.resetSoftSwitches(); m.slotBus().reset(); cpu.hardReset();
    cpu.setProgramCounter(0xc600);
    auto fail=[&](const char* what) {
        fprintf(stderr,"FAIL %s\n%s",what,screen(m).c_str()); std::exit(1);
    };
    auto keys=[&](const char* s) { m.pasteRawKeys(s,strlen(s)); run(cpu,20000000); };
    auto wait=[&](const char* s) {
        for(int n=0;n<800 && screen(m).find(s)==std::string::npos;++n) run(cpu,1000000);
        if(screen(m).find(s)==std::string::npos) fail(s);
    };
    // GAME counts its runs in $06 and writes $5A to $07.
    auto ran=[&](unsigned char times) {
        for(int n=0;n<800 && !(m.data()[6]==times && m.data()[7]==0x5A);++n) run(cpu,1000000);
        return m.data()[6]==times && m.data()[7]==0x5A;
    };
    if(m.data()[6]!=0) fail("$06 starts at zero");
    run(cpu,180000000); wait("4 FILES");
    // The right panel on drive 2: PIC first, GAME second.
    keys("\t/"); wait("PIC");
    // RETURN on a picture-sized binary: the hi-res viewer, not BRUN.
    keys("\r");
    for(int n=0;n<400 && m.data()[0x2000]!=0x55;++n) run(cpu,1000000);
    if(m.data()[0x2000]!=0x55 || m.data()[0x2001]!=0x2A) fail("RETURN on PIC shows the picture");
    if(screen(m).find("BRUN")!=std::string::npos) fail("no BRUN prompt for a picture");
    keys(" "); wait("PIC");
    // RETURN on GAME: the BRUN question, N keeps the panels.
    keys("K"); keys("\r"); wait("BRUN GAME");
    keys("N"); run(cpu,20000000);
    if(m.data()[6]!=0) fail("N runs nothing");
    // Y: A2FC Mini leaves and DOS runs GAME from drive 2.
    keys("\r"); wait("BRUN GAME"); keys("Y");
    if(!ran(1)) fail("RETURN then Y runs GAME (A2FC Mini started by HELLO)");
    wait("]");
    // From the DOS prompt this time, with B.
    keys("BRUN A2FC.MINI,D1\r"); wait("FILES");
    keys("\t/"); wait("GAME"); keys("K"); keys("B"); wait("BRUN GAME"); keys("Y");
    if(!ran(2)) fail("B then Y runs GAME (A2FC Mini started from the DOS prompt)");
    wait("]");
    assert(d->flushPendingWrites());
    puts("PASS: RETURN shows a picture; RETURN and B BRUN a binary from HELLO and from the DOS prompt");
}
