// RETURN opens by content, and RETURN or B runs a DOS binary, on disposable disks only.
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
static std::string mini_files(const char* suffix) {
    // the boot disk's file count, from the driver: the shipped disk may carry more than the four built files
    const char* n=getenv("MINI_FILES"); return std::string(n?n:"4")+suffix;
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
    run(cpu,180000000); wait(mini_files(" FILES").c_str());
    // The right panel on drive 2: PIC first, GAME second.
    keys("\t/"); wait("PIC");
    // RETURN on a picture-sized binary: the hi-res viewer, not BRUN.
    keys("\r");
    for(int n=0;n<400 && m.data()[0x2000]!=0x55;++n) run(cpu,1000000);
    if(m.data()[0x2000]!=0x55 || m.data()[0x2001]!=0x2A) fail("RETURN on PIC shows the picture");
    // The key bar reads B+RUN: look for the question itself.
    if(screen(m).find("BRUN PIC")!=std::string::npos) fail("no BRUN prompt for a picture");
    keys(" "); wait("PIC");
    // RETURN on GAME: the BRUN question, N keeps the panels.
    keys("K"); keys("\r"); wait("BRUN GAME");
    keys("N"); run(cpu,20000000);
    if(m.data()[6]!=0) fail("N runs nothing");
    // RETURN reads the first sector: the header and the bytes pick the view.
    auto back=[&]() { keys("\x1b"); wait("8 FILES"); };
    keys("K"); keys("\r"); // PIC2: BSAVEd at $2000, 8 KB, header skipped
    for(int n=0;n<400 && m.data()[0x2000]!=0x11;++n) run(cpu,1000000);
    if(m.data()[0x2000]!=0x11 || m.data()[0x2001]!=0x22) fail("RETURN on a BSAVEd picture shows it");
    if(screen(m).find("BRUN PIC2")!=std::string::npos) fail("no BRUN prompt for PIC2");
    keys(" "); wait("8 FILES");
    keys("K"); keys("\r"); wait("THIS BINARY HOLDS TEXT"); // after its header
    if(screen(m).find("SECOND LINE")==std::string::npos) fail("NOTE.BIN in the text viewer");
    back();
    keys("K"); keys("\r"); wait("00: 00 C0 08 00"); back();   // ROMPATCH cannot run
    keys("K"); keys("\r"); wait("00: 00 03 08 00"); back();   // PAGE3 would load over DOS's page 3
    keys("K"); keys("\r"); wait("BRUN BIGGAME");           // 33 sectors, yet a program
    keys("N"); wait("8 FILES");
    if(m.data()[6]!=0) fail("N runs nothing on BIGGAME");
    keys("K"); keys("\r"); wait("00: 01 02 03 04"); back();   // JUNK: a T file that is not text
    keys("["); keys("K");                                    // back on GAME
    // Y: A2FC Mini leaves and DOS runs GAME from drive 2.
    keys("\r"); wait("BRUN GAME"); keys("Y");
    if(!ran(1)) fail("RETURN then Y runs GAME (A2FC Mini started by HELLO)");
    wait("]");
    // From the DOS prompt this time, with B.
    keys("BRUN A2FC,D1\r"); wait("FILES");
    keys("\t/"); wait("GAME"); keys("K"); keys("B"); wait("BRUN GAME"); keys("Y");
    if(!ran(2)) fail("B then Y runs GAME (A2FC Mini started from the DOS prompt)");
    wait("]");
    assert(d->flushPendingWrites());
    puts("PASS: RETURN picks hi-res, text, hex or BRUN by content; RETURN and B BRUN a binary from HELLO and from the DOS prompt");
}
