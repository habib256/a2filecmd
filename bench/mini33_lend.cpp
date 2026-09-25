// The two JSRs rwts.s lends to its heartbeat, checked against the same
// run with the lending refused. Disposable images only: argv[2] boot,
// argv[3] a file that backs a never formatted diskette in drive 2.
// argv[4]: "lend" runs A2FC Mini as built; "plain" first spoils the
// signature table in memory, so that rwts.s takes this DOS for another one
// and lends nothing -- the behaviour before the hooks, and the proof that
// another DOS is left alone. Both runs print one line per RWTS call:
// command, drive, track, sector, carry, DOS's return code, and for a
// read the checksum of the 256 bytes it brought back. The Python side
// runs both and requires the two logs and the two disks to be identical.
//
// Checked here, in either mode, at every RWTS entry:
//   - a WRITE runs with both sites exactly as DOS had them;
//   - a READ runs with $BDC4 lent (lend) or untouched (plain), and $BED6
//     untouched; a FORMAT the other way round;
//   - between two calls, both sites hold DOS's own bytes.
// And after Q: with the whole resident overwritten, DOS still catalogs
// both disks from the BASIC prompt, so nothing points into it any more.
#include "Memory.h"
#include "M6502.h"
#include "DiskIICard.h"
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <string>
#include <vector>

static std::string screen(Memory& m) {
    std::string s;
    for(int y=0;y<24;++y) { for(int x=0;x<40;++x) {
        unsigned char c=m.data()[0x400+(y&7)*128+(y>>3)*40+x]&127;
        if(c<32) c+=64; s+=c;
    } s+='\n'; } return s;
}
static std::string mini_files(const char* suffix) {
    const char* n=getenv("MINI_FILES"); return std::string(n?n:"4")+suffix;
}
static void run(M6502& c,long cycles) { for(long n=0;n<cycles;) n+=c.run(1024); }
static void expect(Memory& m,const char* needle) {
    if(screen(m).find(needle)==std::string::npos) {
        fprintf(stderr,"Missing %s\n%s",needle,screen(m).c_str()); std::exit(1);
    }
}
static void fail(const char* what) { fprintf(stderr,"%s\n",what); std::exit(1); }

static const unsigned char RD_SIG[3]={0x20,0x44,0xB9};   // $BDC4: JSR $B944
static const unsigned char FM_SIG[3]={0x20,0x5A,0xBE};   // $BED6: JSR $BE5A

struct Lend : M6502DebugHook {
    Memory& m; M6502& c; bool lend; unsigned hook=0;
    bool inside=false; unsigned char sp=0; unsigned short iob=0;
    std::vector<std::string> log;
    long reads_lent=0, formats_lent=0, writes=0;
    Lend(Memory& mm,M6502& cc,bool l):m(mm),c(cc),lend(l){}
    bool site(unsigned a,const unsigned char* sig) {
        return !memcmp(&m.data()[a],sig,3);
    }
    bool lent(unsigned a) {
        return m.data()[a]==0x20 && (m.data()[a+1]|m.data()[a+2]<<8)==hook;
    }
    bool onInstruction(uint16_t pc) override {
        const unsigned char* d=m.data();
        if(!inside) {
            if(pc!=0x03D9) {
                // Outside RWTS, DOS's bytes: checked where Mini's code
                // runs, which covers every exit of rwts.s.
                if(pc>=0x4000 && pc<0x9600 && !(site(0xBDC4,RD_SIG) && site(0xBED6,FM_SIG))) {
                    // rwts.s is between its patch and RWTS_ENTRY, or its
                    // restore: allowed only inside rwts.s itself, which
                    // runs from the resident right before and after.
                    if(!in_rwts(pc)) fail("a site left lent outside an RWTS call");
                }
                return false;
            }
            iob=(unsigned short)((c.getAccumulator()<<8)|c.getYRegister());
            int cmd=d[iob+12];
            bool rd_lent=lent(0xBDC4), fm_lent=lent(0xBED6);
            bool rd_dos=site(0xBDC4,RD_SIG), fm_dos=site(0xBED6,FM_SIG);
            if(cmd==2) { writes++; if(!rd_dos||!fm_dos) fail("a WRITE ran with a site lent"); }
            else if(cmd==1) {
                if(!fm_dos) fail("a READ ran with the FORMAT site lent");
                if(lend ? !rd_lent : !rd_dos) fail("READ site not as expected");
                reads_lent+=rd_lent;
            } else if(cmd==4) {
                if(!rd_dos) fail("a FORMAT ran with the READ site lent");
                if(lend ? !fm_lent : !fm_dos) fail("FORMAT site not as expected");
                formats_lent+=fm_lent;
            } else fail("unexpected RWTS command");
            sp=c.getStackPointer(); inside=true;
            char b[80]; snprintf(b,sizeof b,"%d %d %d %d",cmd,d[iob+2],d[iob+4],d[iob+5]);
            log.push_back(b);
        } else if(c.getStackPointer()>sp) {
            inside=false;
            int cmd=d[iob+12];
            unsigned buf=d[iob+8]|d[iob+9]<<8, sum=0;
            if(cmd==1) for(int i=0;i<256;++i) sum=(sum*31+d[(buf+i)&0xFFFF])&0xFFFFFF;
            char b[80]; snprintf(b,sizeof b," carry %d rc %02X data %06X",
                                 c.getStatusRegister()&1,d[iob+13],sum);
            log.back()+=b;
        }
        return false;
    }
    unsigned rwts_lo=0, rwts_hi=0;
    bool in_rwts(unsigned pc) { return pc>=rwts_lo && pc<rwts_hi; }
};

int main(int argc,char** argv) {
    assert(argc==5);
    std::string mode=argv[4]; assert(mode=="lend"||mode=="plain");
    Memory m; m.setIIEMode(false);
    assert(m.loadAppleIIRom((std::string(argv[1])+"/roms/apple2p.rom").c_str()));
    auto card=std::make_unique<DiskIICard>(); auto *d=card.get();
    assert(d->loadBootRom(std::string(argv[1])+"/roms/disk2.rom"));
    assert(d->insertDisk(0,argv[2]));
    assert(d->insertBlankDisk(1,argv[3]));
    d->setWriteBackEnabled(true); m.slotBus().plug(6,std::move(card));
    M6502 cpu(&m); m.setCpu(&cpu); cpu.setCpuMode(M6502::CpuMode::NMOS);
    m.clearRam(); m.resetSoftSwitches(); m.slotBus().reset(); cpu.hardReset();
    cpu.setProgramCounter(0xc600);
    run(cpu,180000000); expect(m,mini_files(" FILES").c_str());
    const unsigned char* mem=m.data();
    if(memcmp(&mem[0xBDC4],RD_SIG,3)||memcmp(&mem[0xBED6],FM_SIG,3))
        fail("this DOS does not hold the two JSRs the bench expects");

    // rwts.s's table: the two sites, a spare byte, then the signatures.
    static const unsigned char table[]={0xC4,0xBD,0x00,0xD6,0xBE,
                                        0x20,0x44,0xB9,0x20,0x5A,0xBE};
    unsigned at=0;
    for(unsigned a=0x4000;a<0x9600-sizeof table;++a)
        if(!memcmp(&mem[a],table,sizeof table)) { if(at) fail("table found twice"); at=a; }
    if(!at) fail("lend table not found in the resident");
    Lend t(m,cpu,mode=="lend");
    // The hook: the JSR rwts.s would plant, found by its shape -- PHA,
    // JSR heartbeat, PLA, JSR, RTS -- right before the table's segment
    // is not guaranteed, so search for it.
    for(unsigned a=0x4000;a<0x9600-9;++a)
        if(mem[a]==0x48&&mem[a+1]==0x20&&mem[a+4]==0x68&&mem[a+5]==0x20&&mem[a+8]==0x60) {
            if(t.hook) fail("hook found twice"); t.hook=a;
        }
    if(!t.hook) fail("lend_hook not found");
    // rwts.s's code, for the between-patch-and-call check: from the
    // IOB's builder to the hook, which ends rwts.s's CODE.
    t.rwts_lo=0x4000; t.rwts_hi=t.hook+9;
    if(mode=="plain") {   // no JSR opcode in either signature: no DOS 3.3 matches
        m.writeRamUnchecked(at+5,0x00); m.writeRamUnchecked(at+8,0x00);
    }
    cpu.setDebugHook(&t);

    auto keys=[&](const char* s) { m.pasteRawKeys(s,strlen(s)); run(cpu,20000000); };
    auto wait=[&](const char* s, int slices=800) {
        for(int n=0;n<slices && screen(m).find(s)==std::string::npos;++n) run(cpu,1000000);
        expect(m,s);
    };
    // A read that fails: the never formatted diskette's catalog.
    m.pasteRawKeys("\t/",2); wait("READ ERROR",3000); run(cpu,20000000);
    // FORMAT, the write-protect probe's READ before it included.
    keys("F"); wait("FORMAT D2 WITH DOS: ERASE ALL FILES?");
    m.pasteRawKeys("Y",1); wait("FORMATTED WITH DOS 3.3",3000); run(cpu,40000000);
    expect(m,"EMPTY DISK");
    // Reads of good sectors and writes: every file of drive 1 onto it.
    keys("\t"); expect(m,mini_files(" FILES").c_str());
    keys("\x14"); expect(m,mini_files(" MARKED").c_str());
    keys("C"); wait(("COPY "+mini_files(" MARKED?")).c_str());
    m.pasteRawKeys("Y",1); wait("COPIED",3000); run(cpu,40000000);
    keys("\t"); expect(m,mini_files(" FILES").c_str());
    keys("Q"); keys("Y"); expect(m,"\n]");
    cpu.setDebugHook(nullptr);
    if(memcmp(&mem[0xBDC4],RD_SIG,3)||memcmp(&mem[0xBED6],FM_SIG,3))
        fail("a site still lent after Q");
    // DOS alone now: the resident overwritten with BRK, both disks still
    // cataloged by DOS itself.
    for(unsigned a=0x4000;a<0x9600;++a) m.writeRamUnchecked(a,0x00);
    m.pasteRawKeys("CATALOG,D2\r",11); run(cpu,60000000);
    expect(m,"A2FC"); expect(m,"TIGER");
    m.pasteRawKeys("CATALOG,D1\r",11); run(cpu,60000000);
    expect(m,"HELLO");
    assert(d->flushPendingWrites());

    for(auto& l:t.log) printf("%s\n",l.c_str());
    fprintf(stderr,"%s: %zu RWTS calls, %ld reads lent, %ld formats lent, %ld writes\n",
            mode.c_str(),t.log.size(),t.reads_lent,t.formats_lent,t.writes);
    if(mode=="lend" && (!t.reads_lent || t.formats_lent!=1)) fail("nothing was lent");
    if(mode=="plain" && (t.reads_lent || t.formats_lent)) fail("lent to another DOS");
    return 0;
}
