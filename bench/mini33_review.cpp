// Review fixes seen from the keyboard, on disposable disks only: the
// destination reread after a source-side failure, marks kept when nothing
// was tried, honest batch summaries, rename to the same name, a text file
// too large to edit whole, and DOS's $8D line ends in the editor.
//
// Checks do not stop the run, so one pass reports every finding that
// still reproduces; the exit code is the number of failed checks.
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
// the file rows of one panel: rows 2-20, 19 columns
static std::string panel(Memory& m,int side) {
    std::string s=screen(m),out;
    for(int y=2;y<21;++y) out+=s.substr(y*41+side*20,19)+"\n";
    return out;
}
static std::string mini_files(const char* suffix) {
    // the boot disk's file count, from the driver: the shipped disk may carry more than the four built files
    const char* n=getenv("MINI_FILES"); return std::string(n?n:"4")+suffix;
}
static void run(M6502& c,int cycles) { for(int n=0;n<cycles;) n+=c.run(1024); }
static int failures=0;
static void check(bool ok,const char* what,Memory& m) {
    if(ok) { printf("ok   %s\n",what); return; }
    ++failures; fprintf(stderr,"FAIL %s\n%s",what,screen(m).c_str());
}
int main(int argc,char** argv) {
    assert(argc==5);
    Memory m; m.setIIEMode(false);
    assert(m.loadAppleIIRom((std::string(argv[1])+"/roms/apple2p.rom").c_str()));
    auto card=std::make_unique<DiskIICard>(); auto *d=card.get();
    assert(d->loadBootRom(std::string(argv[1])+"/roms/disk2.rom"));
    assert(d->insertDisk(0,argv[2])); assert(d->insertDisk(1,argv[3]));
    d->setWriteBackEnabled(true); m.slotBus().plug(6,std::move(card));
    M6502 cpu(&m); m.setCpu(&cpu); cpu.setCpuMode(M6502::CpuMode::NMOS);
    m.clearRam(); m.resetSoftSwitches(); m.slotBus().reset(); cpu.hardReset();
    cpu.setProgramCounter(0xc600);
    run(cpu,180000000);
    if(screen(m).find(mini_files(" FILES").c_str())==std::string::npos) { fprintf(stderr,"no boot\n%s",screen(m).c_str()); return 99; }
    auto keys=[&](const char* s) { m.pasteRawKeys(s,strlen(s)); run(cpu,20000000); };
    auto wait=[&](const char* s) {
        for(int n=0;n<800 && screen(m).find(s)==std::string::npos;++n) run(cpu,1000000);
        return screen(m).find(s)!=std::string::npos;
    };
    auto settle=[&]() { run(cpu,40000000); };

    // 1. Tagged copy from drive 2: GOOD.A lands on drive 1, then BAD.B
    //    (a wrong sector count) fails while `drive` is the source.
    keys("\t/"); check(wait("BAD.B"),"drive 2 panel shows the copy fixture",m);
    keys("[ "); keys("K ");
    keys("C"); check(wait("COPY 2 MARKED"),"batch copy prompt",m);
    keys("Y"); check(wait("UNSUPPORTED"),"BAD.B refused",m); settle();
    check(panel(m,0).find("GOOD.A")!=std::string::npos,
          "F1: the destination panel is reread and shows GOOD.A",m);

    // 8. Both panels on drive 1: C tries nothing, so the mark stays.
    keys("\t="); keys(" ");
    auto flushes=d->getWriteFlushCount();
    keys("C"); check(wait("SELECT TWO DIFFERENT DRIVES"),"same-drive refusal",m); settle();
    check(screen(m).find("1 MARKED")!=std::string::npos,"F8: the mark survives a refused C",m);
    check(d->getWriteFlushCount()==flushes,"F8: nothing written",m);
    keys(" ");

    // The second fixture in drive 2, on the right panel.
    assert(d->insertDisk(1,argv[4]));
    keys("\t/"); check(wait("SAME.NAME"),"drive 2 panel shows the edit fixture",m);

    // 5. FULL.TXT: 32 sectors of text, the last byte not a NUL.
    keys("[K");
    keys("E");
    bool refused=wait("FILE TOO LARGE TO EDIT");
    check(refused,"F5: a text file that fills the area is not opened",m);
    if(!refused) { keys("\x1b"); keys("N"); }
    settle();

    // 7. Rename SAME.NAME to itself.
    keys("[KK");
    keys("R"); check(wait("RENAME: "),"rename prompt",m);
    keys("SAME.NAME"); keys("\r");
    check(wait("SAME NAME"),"F7: a same-name rename says so",m);
    check(screen(m).find("LOCKED - UNLOCK FIRST")==std::string::npos,
          "F7: not reported as a lock refusal",m);
    settle();

    // 4. TEXT.DOS is DOS text: ONE$8D TWO$8D, bit 7 set throughout.
    keys("[");
    keys("E"); check(wait("LEAVE"),"editor open",m);
    std::string s=screen(m);
    check(s.substr(0,3)=="ONE" && s.substr(41,3)=="TWO","F4: $8D ends a line on screen",m);
    keys("\x0a"); keys("X"); keys("\r"); keys("\x13");   // Ctrl-J: down a line; K is a letter now
    check(wait("NEW: "),"save asks for a name",m);
    keys("EDITED"); keys("\r");
    check(wait("CREATE TEXT FILE"),"create prompt",m);
    keys("Y"); check(wait("COPIED"),"edited text saved",m); settle();

    // 6. Lock batch: DEL.1 is unlocked, LOCKED.3 locked, so U-nlock both.
    keys("[KKK "); keys("KK ");
    keys("L"); check(wait("UNLOCK 2 MARKED"),"batch unlock prompt",m);
    keys("Y"); check(wait("1 UNLOCKED, 1 ALREADY SET"),"F6: lock batch summary",m); settle();

    // 6. Delete batch: DEL.1, DEL.2 and the still-locked KEEP.4.
    keys("[KKK "); keys("K "); keys("KK ");
    keys("D"); check(wait("DELETE 3 MARKED"),"batch delete prompt",m);
    keys("Y"); check(wait("2 DELETED, 1 LOCKED"),"F6: delete batch summary",m); settle();

    assert(d->flushPendingWrites());
    printf("%s: %d failed checks\n",failures?"FAIL":"PASS",failures);
    return failures;
}
