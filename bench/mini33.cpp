// Boots the shipped mini disk on a real NMOS core + Apple II+ ROM.
// Only disposable copies may be passed as argv[2]/argv[3].
#include "Memory.h"
#include "M6502.h"
#include "DiskIICard.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <memory>
#include <string>
static std::string screen(Memory& m) {
    std::string s;
    for(int y=0;y<24;y++) { for(int x=0;x<40;x++) {
        unsigned char c=m.data()[0x400+(y&7)*128+(y>>3)*40+x]&127;
        if(c<32) c+=64; s+=c;
    } s+='\n'; } return s;
}
static void run(M6502& c,int cycles=3000000) { for(int n=0;n<cycles;) n+=c.run(1024); }
static void expect(Memory& m,const char* s) {
    if(screen(m).find(s)==std::string::npos) { fprintf(stderr,"Missing %s\n%s",s,screen(m).c_str()); std::exit(1); }
}
struct ScreenWrites : pom2::MemoryWatchSink {
    unsigned int hits[1024]={};
    void noteAccess(uint16_t addr,uint8_t,bool write) override {
        if(write && addr>=0x400 && addr<0x800) ++hits[addr-0x400];
    }
    void reset() { memset(hits,0,sizeof(hits)); }
};
int main(int argc,char**argv) {
    assert(argc==5);
    Memory m; m.setIIEMode(false);
    assert(m.loadAppleIIRom((std::string(argv[1])+"/roms/apple2p.rom").c_str()));
    auto d=std::make_unique<DiskIICard>(); auto* raw=d.get();
    assert(d->loadBootRom(std::string(argv[1])+"/roms/disk2.rom"));
    assert(d->insertDisk(argv[2]));
    assert(d->insertDisk(1,argv[3]));
    d->setWriteBackEnabled(true);
    m.slotBus().plug(6,std::move(d));
    M6502 cpu(&m); m.setCpu(&cpu); cpu.setCpuMode(M6502::CpuMode::NMOS);
    m.clearRam(); m.resetSoftSwitches(); m.slotBus().reset(); cpu.hardReset(); cpu.setProgramCounter(0xc600);
    run(cpu,120000000);
    expect(m,"A2FC MINI DOS 3.3"); expect(m,"4 FILES"); expect(m,"TIGER");
    auto bootScreen=screen(m); run(cpu,3000000); assert(screen(m)==bootScreen);
    // HELLO lives under $1000; the program occupies $1000 and $4000+.
    for(int i=0;i<0x800;++i) m.writeRamUnchecked(0x0800+i,0xa5);
    auto keys=[&](const char* s) { m.pasteRawKeys(s,strlen(s)); run(cpu,12000000); };
    keys(" "); expect(m,"1 MARKED");
    keys("\x0e");
    assert(screen(m).find("MARKED")==std::string::npos);
    ScreenWrites changes; m.setWatchSink(&changes);
    for(int y=0;y<24;++y) for(int x=0;x<40;++x)
        m.setWriteWatch(0x400+(y&7)*128+(y>>3)*40+x,true);
    auto changedOnly=[&](const char* s) {
        std::string before(reinterpret_cast<const char*>(m.data()+0x400),1024);
        changes.reset(); keys(s);
        std::string after(reinterpret_cast<const char*>(m.data()+0x400),1024);
        for(int y=0;y<24;++y) for(int x=0;x<40;++x) {
            auto a=(y&7)*128+(y>>3)*40+x;
            unsigned int expected=before[a]!=after[a]?1:0;
            assert(changes.hits[a]==expected);
        }
    };
    // Only the active header is inverse; the shortcut row is inverse too.
    assert(m.data()[0x400]<0x40); assert(m.data()[0x414]>=0x80);
    const int bar=0x400+(23&7)*128+(23>>3)*40;
    assert(m.data()[bar]<0x40); assert(m.data()[bar+3]<0x40);
    changedOnly("Z"); changedOnly("\x1b"); // root ESC does not quit
    changedOnly("K"); changedOnly("\x0a"); // HELLO -> A2FC.MINI -> README
    auto chosen=screen(m);
    keys("6"); expect(m,"A2FC MINI - COMMANDS");
    keys("\x1b"); assert(screen(m)==chosen);
    keys("T"); expect(m,"APPLE II+ 48 KB");
    keys("H"); expect(m,"00: 41324643");
    keys("T"); expect(m,"APPLE II+ 48 KB"); keys("\x1b");
    auto pane=[&](int side) {
        std::string p; auto s=screen(m);
        for(int y=1;y<20;++y) {
            assert(s[y*41+19]==':'); assert(s[y*41+39]==' ');
            p+=s.substr(y*41+side*20,19);
        } return p;
    };
    changedOnly("1"); // numeric first bar button: TAB
    assert(m.data()[0x400]>=0x80); assert(m.data()[0x414]<0x40);
    auto left=pane(0);
    assert(screen(m).substr(21*41,5)=="HELLO");
    keys("2"); expect(m,"PREVIEW: FIRST SECTOR"); keys("\x1b");
    keys("4"); expect(m,"D2"); expect(m,"20 FILES"); assert(pane(0)==left);
    changedOnly("\x15"); // RIGHT pages by 18; does not switch pane
    assert(screen(m).substr(21*41,6)=="FILE18");
    changedOnly("K"); expect(m,"ABCDEFGHIJKLMN+");
    expect(m,"ABCDEFGHIJKLMNOPQRSTUVWXYZ1234"); assert(pane(0)==left);
    changedOnly("K"); // last entry: no physical screen writes
    keys("\r"); expect(m,"LONG NAME CONTENT"); keys("\x1b");
    changedOnly("\x08"); assert(screen(m).substr(21*41,6)=="FILE01");
    changedOnly("["); assert(screen(m).substr(21*41,9)=="GREETINGS");
    changedOnly("]"); expect(m,"ABCDEFGHIJKLMNOPQRSTUVWXYZ1234");
    changedOnly("-"); assert(screen(m).substr(21*41,6)=="FILE01");
    changedOnly("+"); expect(m,"ABCDEFGHIJKLMNOPQRSTUVWXYZ1234");
    keys("5"); expect(m,"ABCDEFGHIJKLMNOPQRSTUVWXYZ1234"); assert(pane(0)==left);
    changedOnly("\t"); assert(screen(m).substr(21*41,6)=="README");
    auto right=pane(1);
    keys("\x12"); assert(screen(m).substr(21*41,6)=="README"); assert(pane(1)==right);
    keys("H"); expect(m,"00: 41324643"); keys("\x1b");
    keys("\t"); left=pane(0);
    assert(raw->insertDisk(1,argv[4]));
    keys("\x12"); expect(m,"INVALID CATALOG"); assert(pane(0)==left);
    keys("\r"); expect(m,"INVALID CATALOG");
    keys("\t"); keys("T"); expect(m,"APPLE II+ 48 KB"); keys("\x1b"); keys("\t");
    assert(raw->ejectDisk(1));
    keys("\x12"); run(cpu,120000000); expect(m,"READ ERROR"); assert(pane(0)==left);
    assert(raw->insertDisk(1,argv[3]));
    keys("\x12"); expect(m,"GREETINGS"); assert(pane(0)==left);
    keys("="); keys("\t"); expect(m,"20 FILES");
    assert(screen(m).substr(21*41,9)=="GREETINGS");
    keys("/"); expect(m,"4 FILES"); expect(m,"GREETINGS");
    for(int i=0;i<0x800;++i) assert(m.data()[0x0800+i]==0xa5);
    puts(screen(m).c_str());
    auto beforeQuit=screen(m);
    keys("7"); expect(m,"QUIT TO DOS 3.3?"); keys("Z"); expect(m,"CANCEL");
    keys("N"); assert(screen(m)==beforeQuit);
    keys("Q"); keys("Y"); expect(m,"\n]");
    keys("CATALOG\r"); expect(m,"DISK VOLUME"); expect(m,"A2FC.MINI");
    keys("BRUN A2FC.MINI\r"); run(cpu,40000000); expect(m,"4 FILES");
    m.clearWriteWatches(); m.setWatchSink(nullptr);
    assert(raw->getWriteFlushCount()==0); assert(!raw->hasUnsavedChanges());
    puts("PASS: II+ NMOS boot, ProDOS ergonomics, inverse key blocks, numeric shortcuts, help, changed-character-only writes, two panes, pagination, long names, preview, drive isolation, malformed/missing disk, recovery, quit/relaunch; zero disk writes");
}
