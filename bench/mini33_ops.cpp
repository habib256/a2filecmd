// Tags, hi-res, exclusive TXT create, and delete, on disposable disks only.
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
static void expect(Memory& m,const char* needle) {
    if(screen(m).find(needle)==std::string::npos) {
        fprintf(stderr,"Missing %s\n%s",needle,screen(m).c_str()); std::exit(1);
    }
}
static void absent(Memory& m,const char* needle) {
    if(screen(m).find(needle)!=std::string::npos) {
        fprintf(stderr,"Unexpected %s\n%s",needle,screen(m).c_str()); std::exit(1);
    }
}
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
    run(cpu,180000000); expect(m,mini_files(" FILES").c_str());
    auto keys=[&](const char* s) { m.pasteRawKeys(s,strlen(s)); run(cpu,20000000); };
    auto wait=[&](const char* s) {
        for(int n=0;n<800 && screen(m).find(s)==std::string::npos;++n) run(cpu,1000000);
        expect(m,s);
    };
    // A result on the footer is followed by a reread of both panels; give
    // it time before looking at the panels again.
    auto settle=[&]() { run(cpu,40000000); };
    // Picture on the other drive: G loads it into $2000 and any key returns.
    keys("\t/"); expect(m,"PIC");
    // Write-protected drive: a delete or a lock, single or tagged, is
    // refused as itself, never reported done.
    d->setDriveHostWriteProtected(1,true);
    keys("D"); wait("DELETE PIC"); keys("Y"); wait("DISK IS WRITE PROTECTED"); settle();
    expect(m,"PIC             B  ");
    keys("L"); wait("LOCK PIC"); keys("Y"); wait("DISK IS WRITE PROTECTED"); settle();
    absent(m,"PIC             B L");
    keys(" "); expect(m,"1 MARKED");
    keys("D"); wait("DELETE 1 MARKED?"); keys("Y"); wait("DISK IS WRITE PROTECTED"); settle();
    expect(m,"PIC"); absent(m,"DELETED");
    d->setDriveHostWriteProtected(1,false);
    keys("G");
    for(int n=0;n<400 && m.data()[0x2000]!=0x55;++n) run(cpu,1000000);
    assert(m.data()[0x2000]==0x55);
    assert(m.data()[0x2001]==0x2A);
    keys(" "); expect(m,"PIC");
    keys("\t");
    // New exclusive text file on the boot disk (0.7 footer prompts).
    keys("N"); wait("NEW: ");
    keys("NOTE"); wait("NEW: NOTE");
    keys("\rHELLO\x13"); wait("CREATE TEXT FILE");
    keys("Y"); wait("COPIED"); settle();
    expect(m,"NOTE");
    keys("]"); expect(m,"NOTE");
    keys("L"); wait("LOCK NOTE"); keys("Y"); wait("LOCKED"); settle();
    keys("D"); wait("DELETE NOTE"); keys("Y"); wait("LOCKED - NOT DELETED"); settle();
    keys("L"); wait("UNLOCK NOTE"); keys("Y"); wait("UNLOCKED"); settle();
    keys("R"); wait("RENAME: "); keys("MEMO"); wait("RENAME: MEMO");
    keys("\r"); wait("RENAMED"); settle();
    expect(m,"MEMO");
    keys("]"); expect(m,"MEMO");
    keys("D"); wait("DELETE MEMO");
    keys("Y"); wait("DELETED"); settle();
    assert(screen(m).find("NOTE")==std::string::npos);
    assert(screen(m).find("MEMO")==std::string::npos);
    // A new text under a name that exists: the save asks for another name
    // instead of dropping the text, and Escape there gives it up.
    keys("N"); wait("NEW: ");
    keys("HELLO\r"); wait("SAVE");              // the editor's key bar
    keys("LIKE JIM\x13"); wait("EXISTS: ");   // I, J, K, L are text
    keys("NOTE2\r"); wait("CREATE TEXT FILE");
    keys("Y"); wait("COPIED"); settle();
    expect(m,"NOTE2");
    // Tagged batch: HELLO and README onto the other disk. A2FC stays.
    keys("[ "); keys("KK ");
    keys("C"); wait("COPY 2");
    // The banner row reads COPY and the file at every moment of the batch.
    // The Disk II screen holes are $0478+slot: taken at $0478+slot*16, the
    // save and restore around each RWTS call put stale characters back at
    // column 8 of rows 5, 8, 11, 14, 17, 20 and 23.
    m.pasteRawKeys("Y",1);
    for(int n=0;n<4000;++n) {
        run(cpu,100000);
        std::string s=screen(m), banner=s.substr(21*41,40);
        if(banner.compare(0,5,"COPY ")==0 && banner.find("MARKED")==std::string::npos &&
           banner.substr(5,5)!="HELLO" && banner.substr(5,5)!="READM") {
            fprintf(stderr,"Torn copy banner\n%s",s.c_str()); std::exit(1);
        }
        if(s.find("COPIED")!=std::string::npos) break;
    }
    wait("COPIED"); settle();
    keys("\t"); expect(m,"4 FILES");            // drive 2: PIC, KEEP.DST and the two copies
    expect(m,"HELLO"); expect(m,"README"); expect(m,"PIC");
    assert(d->flushPendingWrites());
    puts("PASS: tags/HGR/create/delete/batch copy on disposable disks");
}
