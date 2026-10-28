// Executes the production Disk II protection sensor on both CPUs.

#include "Memory.h"
#include "M6502.h"
#include "DiskIICard.h"
#include <cstdio>
#include <memory>
#ifndef POM2_ROOT
#error POM2_ROOT must name the matching emulator source and library
#endif
int main(int argc,char**argv){
 if(argc!=3)return 1;
 int errors=0;
 for(int slot=5;slot<7;slot++)for(int drive=0;drive<2;drive++)for(int cpu=0;cpu<2;cpu++)for(int motor=0;motor<3;motor++)for(int wp=0;wp<2;wp++){
 Memory m;m.setIIEMode(true);if(!m.loadAppleIIRom(POM2_ROOT "/roms/apple2e.rom"))return 1;
 auto d=std::make_unique<DiskIICard>(slot);auto* disk=d.get();d->setIwmHost(false);if(!d->loadBootRom(POM2_ROOT "/roms/disk2.rom") || !d->loadLssRom(POM2_ROOT "/roms/diskii_p6.rom"))return 2;
 if(!d->insertDisk(drive,argv[2]))return 2;d->setWriteBackEnabled(true);d->setDriveHostWriteProtected(drive,wp);m.slotBus().plug(slot,std::move(d));
 M6502 c(&m);m.setCpu(&c);disk->setCpu(&c);c.setCpuMode(cpu?M6502::CpuMode::CMOS:M6502::CpuMode::NMOS);m.clearRam();m.resetSoftSwitches();m.slotBus().reset();c.hardReset();
 unsigned char b[4096];FILE*f=fopen(argv[1],"rb");if(!f)return 3;size_t n=fread(b,1,sizeof b,f);fclose(f);for(size_t i=0;i<n;i++)m.writeRamUnchecked(0x800+i,b[i]);
 m.writeRamUnchecked(0x801,slot*16+(drive?0x80:0));
 for(int j=0;j<65536;j++)m.auxDataMutable()[j]=0xA5;
 const int base=0xC080+slot*16;
 if(motor){
 m.memRead(base+(drive?11:10));m.memRead(base+14);m.memRead(base+12);m.memRead(base+9);
 // Let the real CPU repeatedly read the controller, leaving its data latch set.
 unsigned char loop[]={0xAD,(unsigned char)(base+12),0xC0,0x4C,0x00,0x03};for(int j=0;j<6;j++)m.writeRamUnchecked(0x300+j,loop[j]);c.setProgramCounter(0x300);for(int j=0;j<10000;j++)c.run(1);
 if(motor==2){m.memRead(base+8);unsigned char idle[]={0x4C,0x10,0x03};for(int j=0;j<3;j++)m.writeRamUnchecked(0x310+j,idle[j]);c.setProgramCounter(0x310);for(int j=0;j<500000;j++)c.run(1);}
 }const auto sp=c.getStackPointer();c.setStatusRegister(0x24);c.setProgramCounter(0x800);int k=0;for(;k<10000&&c.getProgramCounter()!=0xfff0;k++)c.run(1);
 if(!disk->flushPendingWrites())errors++;
 for(int j=0;j<65536;j++)if(m.auxData()[j]!=0xA5){errors++;break;}
 if(c.getProgramCounter()!=0xFFF0 || m.data()[0x200]!=(wp?0x80:0) || disk->getWriteFlushCount()!=0 || c.getStackPointer()!=sp || !(c.getStatusRegister()&4))errors++;
 printf("slot=%d drive=%d cpu=%d motor=%d wp=%d got=%02x flush=%llu pc=%04x\n",slot,drive,cpu,motor,wp,m.data()[0x200],(unsigned long long)disk->getWriteFlushCount(),c.getProgramCounter());
 }
 return errors?4:0;
}
