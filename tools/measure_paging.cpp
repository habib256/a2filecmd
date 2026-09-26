// Deterministic cycles of paging through large directories on the HDV card.
// No host clock, no disk write-back. Usage:
//   measure_paging POM2_ROOT disk.hdv a2fc.lbl enh|unenh DIR...
// For each DIR (an entry of the boot volume's root), opens it, pages forward
// with '>' to the last window, then back with '<' to the first, and prints
// one line per window change: "fwd DIR k first cycles" / "back ...".
#include "Memory.h"
#include "M6502.h"
#include "ProDOSHardDiskCard.h"
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <memory>
#include <regex>
#include <string>

struct StopAt : M6502DebugHook {
    unsigned target; bool hit=false;
    bool onInstruction(uint16_t pc) override { return hit=(pc==target); }
};
static Memory* M; static M6502* C; static StopAt hook;

static unsigned char cell(int y,int x){
    int a=0x400+(y%8)*128+(y/8)*40+x/2;
    return x%2?M->data()[a]:M->auxData()[a];
}
static std::string row(int y){
    std::string s;
    for(int x=0;x<80;++x){unsigned char c=cell(y,x)&127;if(c<32)c+=64;s+=c;}
    return s;
}
static std::string screen(){std::string s;for(int y=0;y<24;++y)s+=row(y)+"\n";return s;}
static std::string line(){          // the inverse row of the left panel
    for(int y=2;y<20;++y){
        bool inv=true;
        for(int x=0;x<16;++x)if(cell(y,x)>=0x80){inv=false;break;}
        if(inv)return row(y).substr(0,38);
    }
    return "";
}
static unsigned long long key(const char* k){
    auto start=M->getCycleCounter();hook.hit=false;
    if(k)M->pasteRawKeys(k,1);
    C->setDebugHook(nullptr);C->step();
    C->setDebugHook(&hook);
    while(!hook.hit && M->getCycleCounter()-start<2000000000ULL)C->run(4096);
    C->setDebugHook(nullptr);
    if(!hook.hit){fprintf(stderr,"no keyboard wait after %d\n%s",k?k[0]:-1,screen().c_str());exit(1);}
    return M->getCycleCounter()-start;
}
static long first(){               // "N   + disk order" on row 1, or 0
    static const std::regex re("^(\\d+) *\\+ disk order");
    std::smatch m; std::string r=row(1);
    return std::regex_search(r,m,re)?std::stol(m[1]):0;
}
static void select(const std::string& name){
    for(int i=0;i<12;++i)key("<");
    for(int i=0;i<200;++i){
        std::string l=line();
        if(l.rfind(name+" ",0)==0||l.rfind(name+"/",0)==0)return;
        key("\x0a");
    }
    fprintf(stderr,"missing %s\n%s",name.c_str(),screen().c_str());exit(1);
}
int main(int argc,char**argv){
    assert(argc>=6);
    unsigned wait=0; std::string kind,addr,name;
    std::ifstream labels(argv[3]);
    while(labels>>kind>>addr>>name)if(name=="._cgetc")wait=std::stoul(addr,nullptr,16);
    assert(wait);
    bool enh=std::string(argv[4])=="enh";
    Memory m; m.setIIEMode(true); M=&m;
    assert(m.loadAppleIIRom((std::string(argv[1])+(enh?"/roms/apple2e.rom":"/roms/apple2e_unenh.rom")).c_str()));
    auto card=std::make_unique<ProDOSHardDiskCard>(5);
    assert(card->loadImage(argv[2]));
    card->setWriteBackEnabled(false);
    m.slotBus().plug(5,std::move(card));
    M6502 cpu(&m);m.setCpu(&cpu);C=&cpu;
    cpu.setCpuMode(enh?M6502::CpuMode::CMOS:M6502::CpuMode::NMOS);
    m.clearRam();m.resetSoftSwitches();m.slotBus().reset();cpu.hardReset();cpu.setProgramCounter(0xC500);
    hook.target=wait;
    setvbuf(stdout,nullptr,_IOLBF,0);
    key(nullptr);
    for(int i=0;i<100000&&screen().find("Type  Aux")==std::string::npos;++i)key(nullptr);
    if(screen().find("Type  Aux")==std::string::npos){fprintf(stderr,"no panels\n%s",screen().c_str());return 1;}
    // To the root of the boot volume: '/' lists the volumes.
    key("/"); select("/WORKHD"); key("\r");
    for(int d=5;d<argc;++d){
        std::string dir=argv[d];
        select(dir);
        printf("open %s 0 0 %llu\n",dir.c_str(),key("\r"));
        if(row(0).find("/WORKHD/"+dir)==std::string::npos){fprintf(stderr,"not in %s\n%s",dir.c_str(),screen().c_str());return 1;}
        int k=0; long f=first(); int idle=0;
        while(idle<12){
            auto c=key(">"); long g=first();
            if(g!=f){printf("fwd %s %d %ld %llu %d\n",dir.c_str(),++k,g,c,idle+1);f=g;idle=0;}else ++idle;
        }
        printf("last %s %d %ld\n",dir.c_str(),k,f);
        idle=0;
        while(idle<12){
            auto c=key("<"); long g=first();
            // A build whose Up/Left pages forward (the cc65 2.19 signed
            // compare in move_cursor, fixed 2026-09-26) is reported, not
            // measured.
            if(g>f){printf("wrongway %s %d %ld %llu %d\n",dir.c_str(),k,g,c,idle+1);break;}
            if(g!=f){printf("back %s %d %ld %llu %d\n",dir.c_str(),--k,g,c,idle+1);f=g;idle=0;
                if(getenv("MEASURE_DUMP"))fprintf(stderr,"%s",screen().c_str());}
            else ++idle;
        }
        fflush(stdout);
        key("\x1b");   // back to the root
    }
}
