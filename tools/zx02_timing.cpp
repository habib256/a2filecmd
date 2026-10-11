// A2FC timing with POM2's CPU and actual disk controllers, no host pacing.
// Every input image must be a disposable copy. Runtime writes are flushed
// and the complete image and auxiliary RAM are compared before success.
#include "Memory.h"
#include "M6502.h"
#include "DiskIICard.h"
#include "Disk35Image.h"
#include "Sony35Drive.h"
#include "IWMDevice.h"
#include "SmartPortHub.h"
#include <algorithm>
#include <fstream>
#include <iostream>
#include <iterator>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>

static std::vector<unsigned char> bytes(const std::string& path) {
    std::ifstream f(path, std::ios::binary);
    if (!f) throw std::runtime_error("cannot read image");
    std::vector<unsigned char> b((std::istreambuf_iterator<char>(f)), {});
    if (f.bad()) throw std::runtime_error("image read failed");
    return b;
}
static std::string screen(const Memory& mem) {
    std::string out;
    for (int row=0;row<24;++row) {
        int at=0x400+(row%8)*128+(row/8)*40;
        for (int col=0;col<40;++col) {
            out += char(mem.auxData()[at+col]&127);
            out += char(mem.data()[at+col]&127);
        }
        out+='\n';
    }
    return out;
}
int main(int argc,char** argv) try {
    if (argc!=5) throw std::runtime_error("usage: zx02_timing POM2_ROOT disk2|sony35 6502|65c02 DISPOSABLE_IMAGE");
    std::string root=argv[1], medium=argv[2], arch=argv[3], path=argv[4];
    bool sony=medium=="sony35", nmos=arch=="6502";
    if ((!sony && medium!="disk2") || (arch!="6502" && arch!="65c02") || (sony && nmos))
        throw std::runtime_error("invalid machine: Sony uses CMOS //c+ at 1 MHz");
    auto before=bytes(path);
    Memory mem; M6502 cpu(&mem); mem.setCpu(&cpu);
    mem.setIIEMode(true); mem.clearRam(); mem.resetSoftSwitches();
    pom2::IWMDevice iwm; pom2::SmartPortHub hub;
    pom2::Disk35Image image, empty; pom2::Sony35Drive internal, external;
    DiskIICard* drive=nullptr;
    if (sony) {
        internal.setImage(&image); external.setImage(&empty);
        hub.attach(&iwm); hub.setSony35(&internal,&external);
        mem.setIWM(&iwm); mem.setSmartPortHub(&hub);
        image.setWriteBackEnabled(true);
        if (!mem.loadAppleIIRom((root+"/roms/apple2cp.rom").c_str(),true) || !image.loadFile(path))
            throw std::runtime_error("Sony ROM/image unavailable");
        internal.notifyMediaChange();
        auto card=std::make_unique<DiskIICard>(6);
        card->setIWM(&iwm); drive=card.get(); mem.slotBus().plug(6,std::move(card));
    } else {
        if (!mem.loadAppleIIRom((root+(nmos?"/roms/apple2e_unenh.rom":"/roms/apple2e.rom")).c_str()))
            throw std::runtime_error("IIe ROM unavailable");
        auto card=std::make_unique<DiskIICard>(6);
        if (!card->loadBootRom((root+"/roms/disk2.rom").c_str()) ||
            !card->loadLssRom((root+"/roms/diskii_p6.rom").c_str()))
            throw std::runtime_error("Disk II ROM unavailable");
        card->setWriteBackEnabled(true);
        if (!card->insertDisk(path)) throw std::runtime_error("Disk II mount failed");
        card->seekTrack0(); drive=card.get(); mem.slotBus().plug(6,std::move(card));
    }
    cpu.setCpuMode(nmos?M6502::CpuMode::NMOS:M6502::CpuMode::CMOS);
    cpu.hardReset(); if (!sony) cpu.setProgramCounter(0xC600);
    uint64_t launcher=0, entry=0, panels=0, nextScreen=0;
    std::vector<unsigned char> aux;
    while (mem.getCycleCounter()<150000000) {
        if (!entry && cpu.getProgramCounter()==0x4000) entry=mem.getCycleCounter();
        cpu.step();
        auto cycles=mem.getCycleCounter();
        if (sony) iwm.tick(cycles);
        if (cycles>=nextScreen) {
            nextScreen=cycles+1024;
            auto text=screen(mem);
            if (!launcher && text.find("Loading A2FILE.CODE")!=std::string::npos) {
                launcher=cycles; aux.assign(mem.auxData()+0x1000,mem.auxData()+0xC000);
            }
            auto first=text.find("Type  Aux     Size");
            bool rightReady=text.find("Volume          Slot   Free/Total")!=std::string::npos ||
                            (first!=std::string::npos && text.find("Type  Aux     Size",first+1)!=std::string::npos);
            if (first!=std::string::npos && rightReady &&
                text.find("RECOVER")!=std::string::npos) {
                panels=cycles;break;
            }
            if (text.find("Compressed image invalid")!=std::string::npos)
                throw std::runtime_error("compressed image rejected");
        }
    }
    if (!panels || !entry || !launcher) throw std::runtime_error("boot did not reach launcher/core/panels");
    if (!std::equal(aux.begin(),aux.end(),mem.auxData()+0x1000)) throw std::runtime_error("AUX changed");
    if (sony && !image.saveDirty()) throw std::runtime_error("Sony flush failed");
    if (!sony && !drive->flushPendingWrites()) throw std::runtime_error("Disk II flush failed");
    if (before!=bytes(path)) throw std::runtime_error("boot image changed");
    std::cout << "{\"medium\":\"" << medium << "\",\"arch\":\"" << arch
              << "\",\"clock_hz\":1022727,\"launcher_cycles\":" << launcher
              << ",\"entry_cycles\":" << entry << ",\"panels_cycles\":" << panels
              << ",\"aux_preserved\":true,\"volume_preserved\":true}" << std::endl;
    return 0;
} catch(const std::exception& e) { std::cerr << e.what() << '\n';return 1; }
