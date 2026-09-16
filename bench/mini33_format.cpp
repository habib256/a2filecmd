// F, the format, from the panels on disposable disks only. Mode "format":
// the boot-drive refusal, cancel, write protection, then a real RWTS
// format with DOS copied from the boot disk and every file copied onto
// it. Mode "blank": drive 2 holds a zero-filled image (formatted to
// zeros, no VTOC), F formats it while the progress bar fills and the main
// key bar is back on the last row, then every file of drive 1 is copied
// onto it. Mode "fresh": the same on a diskette that has never been
// formatted (POM2's insertBlankDisk: no address fields at all), which the
// panel cannot read and the write-protect probe cannot sense. Mode
// "boot": the disk made any of these ways boots into A2FC Mini.
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
    assert(argc==5);
    std::string mode=argv[4];
    Memory m; m.setIIEMode(false);
    assert(m.loadAppleIIRom((std::string(argv[1])+"/roms/apple2p.rom").c_str()));
    auto card=std::make_unique<DiskIICard>(); auto *d=card.get();
    assert(d->loadBootRom(std::string(argv[1])+"/roms/disk2.rom"));
    assert(d->insertDisk(0,argv[2]));
    if(mode=="fresh") assert(d->insertBlankDisk(1,argv[3]));
    else assert(d->insertDisk(1,argv[3]));
    d->setWriteBackEnabled(true); m.slotBus().plug(6,std::move(card));
    M6502 cpu(&m); m.setCpu(&cpu); cpu.setCpuMode(M6502::CpuMode::NMOS);
    m.clearRam(); m.resetSoftSwitches(); m.slotBus().reset(); cpu.hardReset();
    cpu.setProgramCounter(0xc600);
    run(cpu,180000000); expect(m,mini_files(" FILES").c_str());
    if(mode=="boot") {
        // The formatted disk is drive 1 here: HELLO ran and BRUN A2FC came up.
        expect(m,"A2FC MINI DOS 3.3"); expect(m,"HELLO"); expect(m,"README");
        expect(m,"TIGER"); expect(m,"A2FC");
        puts("PASS: the formatted disk boots into A2FC Mini");
        return 0;
    }
    auto keys=[&](const char* s) { m.pasteRawKeys(s,strlen(s)); run(cpu,20000000); };
    auto wait=[&](const char* s, int slices=800) {
        for(int n=0;n<slices && screen(m).find(s)==std::string::npos;++n) run(cpu,1000000);
        expect(m,s);
    };
    auto settle=[&]() { run(cpu,40000000); };
    // Every file of the boot disk onto the fresh one, then the panel shows them.
    auto copy_all=[&]() {
        keys("\t"); expect(m,mini_files(" FILES").c_str());
        keys("\x14"); expect(m,mini_files(" MARKED").c_str());
        keys("C"); wait(("COPY "+mini_files(" MARKED?")).c_str());
        m.pasteRawKeys("Y",1);
        wait("COPIED",3000); settle();
        keys("\t"); expect(m,mini_files(" FILES").c_str()); expect(m,"A2FC"); expect(m,"TIGER");
        assert(d->flushPendingWrites());
    };
    if(mode=="blank"||mode=="fresh") {
        // No catalog to show: a zero image reads as an invalid one, a never
        // formatted diskette cannot be read at all. F formats either.
        // A never formatted surface costs RWTS its whole retry sequence
        // (48 tries with recalibrations) before it reports the error.
        keys("\t/"); wait(mode=="fresh" ? "READ ERROR" : "INVALID CATALOG", 3000);
        keys("F"); wait("FORMAT D2 WITH DOS: ERASE ALL FILES?");
        m.pasteRawKeys("Y",1);
        // While it formats: the message, a bar that fills on row 22, and the
        // main key bar on row 23 instead of the Y/N/ESC question.
        bool bar_seen=false, stars_seen=false, question_seen=false;
        for(int n=0;n<3000;++n) {
            run(cpu,1000000);
            std::string s=screen(m);
            std::string row22=s.substr(22*41,40), row23=s.substr(23*41,40);
            if(s.find("FORMATTING...")!=std::string::npos && row22[0]=='[') {
                bar_seen=true;
                if(row22.find('*')!=std::string::npos) stars_seen=true;
                if(row23.find("YES")!=std::string::npos) question_seen=true;
            }
            if(s.find("FORMATTED WITH DOS 3.3")!=std::string::npos) break;
        }
        expect(m,"FORMATTED WITH DOS 3.3");
        if(!bar_seen||!stars_seen||question_seen) {
            fprintf(stderr,"progress bar %d, stars %d, question left on row 23 %d\n",bar_seen,stars_seen,question_seen);
            std::exit(1);
        }
        settle(); expect(m,"EMPTY DISK"); expect(m,"V254");
        copy_all();
        printf("PASS: a %s drive 2 formatted with a progress bar, every file copied onto it\n",
               mode=="fresh" ? "never formatted" : "zero-filled");
        return 0;
    }
    assert(mode=="format");
    // The boot drive is refused before any question.
    keys("F"); wait("BOOT DRIVE - FORMAT THE OTHER ONE"); settle(); expect(m,mini_files(" FILES").c_str());
    keys("\t/"); expect(m,"OLD"); expect(m,"KEEP");
    // N and Escape cancel; other keys are ignored at the question.
    keys("F"); wait("FORMAT D2 WITH DOS: ERASE ALL FILES?");
    keys("3O"); expect(m,"FORMAT D2 WITH DOS: ERASE ALL FILES?");
    keys("N"); settle(); expect(m,"OLD"); absent(m,"FORMATT");
    keys("F"); wait("FORMAT D2 WITH DOS: ERASE ALL FILES?");
    keys("\x1b"); settle(); expect(m,"OLD"); absent(m,"FORMATT");
    // Write protection is refused before the first write.
    d->setDriveHostWriteProtected(1,true);
    keys("F"); wait("FORMAT D2 WITH DOS: ERASE ALL FILES?");
    keys("Y"); wait("DISK IS WRITE PROTECTED"); settle(); expect(m,"OLD"); expect(m,"KEEP");
    d->setDriveHostWriteProtected(1,false);
    // The real thing: RWTS formats 35 tracks, then DOS, catalog, VTOC.
    keys("F"); wait("FORMAT D2 WITH DOS: ERASE ALL FILES?");
    m.pasteRawKeys("Y",1);
    wait("FORMATTING...",50);
    wait("FORMATTED WITH DOS 3.3",3000); settle();
    expect(m,"EMPTY DISK"); expect(m,"V254"); absent(m,"OLD");
    copy_all();
    puts("PASS: refusal, cancel, protection, format with DOS, tagged copy onto the fresh disk");
}
