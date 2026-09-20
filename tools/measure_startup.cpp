// Deterministic NMOS + Disk II timing. No host clock, no disk write-back.
#include "Memory.h"
#include "M6502.h"
#include "DiskIICard.h"
#include <cassert>
#include <cstdio>
#include <fstream>
#include <memory>
#include <string>

struct StopAt : M6502DebugHook {
    unsigned target; bool hit=false;
    bool onInstruction(uint16_t pc) override { return hit=(pc==target); }
};
static std::string screen(Memory& m) {
    std::string s;
    for (int y=0;y<24;++y) {
        for (int x=0;x<80;++x) {
            int a=0x400+(y%8)*128+(y/8)*40+x/2;
            unsigned char c=(x%2?m.data()[a]:m.auxData()[a])&127;
            if(c<32)c+=64;
            s+=c;
        }
        s+='\n';
    }
    return s;
}
int main(int argc,char**argv) {
    assert(argc==4);
    unsigned wait=0; std::string kind,addr,name;
    std::ifstream labels(argv[3]);
    while(labels>>kind>>addr>>name)if(name=="._cgetc")wait=std::stoul(addr,nullptr,16);
    assert(wait);
    Memory m; m.setIIEMode(true);
    assert(m.loadAppleIIRom((std::string(argv[1])+"/roms/apple2e_unenh.rom").c_str()));
    auto card=std::make_unique<DiskIICard>();
    assert(card->loadBootRom(std::string(argv[1])+"/roms/disk2.rom"));
    assert(card->insertDisk(0,argv[2]));
    card->setWriteBackEnabled(false);
    m.slotBus().plug(6,std::move(card));
    M6502 cpu(&m);m.setCpu(&cpu);cpu.setCpuMode(M6502::CpuMode::NMOS);
    m.clearRam();m.resetSoftSwitches();m.slotBus().reset();cpu.hardReset();cpu.setProgramCounter(0xC600);
    StopAt hook;hook.target=wait;
    auto measure=[&](const char*label,const char*key) {
        auto start=m.getCycleCounter();hook.hit=false;
        if(key){m.pasteRawKeys(key,1);cpu.setDebugHook(nullptr);cpu.step();}
        cpu.setDebugHook(&hook);
        while(!hook.hit && m.getCycleCounter()-start<200000000)cpu.run(4096);
        if(!hook.hit || screen(m).find("Type  Aux")==std::string::npos){
            fprintf(stderr,"%s did not reach panels\n%s",label,screen(m).c_str());exit(1);
        }
        printf("%s: %llu cycles\n",label,(unsigned long long)(m.getCycleCounter()-start));fflush(stdout);
    };
    measure("boot",nullptr);
    measure("first_down","\x0a");
    measure("open_a2file","\r");
    assert(screen(m).substr(0,38).find("/A2FILE")!=std::string::npos);
    for(int i=0;i<20;++i)measure(i<17?"cursor":"scroll","\x0a");
    cpu.setDebugHook(nullptr);
}
