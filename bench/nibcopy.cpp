// POM2 Disk II / real ROM AUXMOVE; only paths created by nibcopy.py are writable.
#include "Memory.h"
#include "M6502.h"
#include "DiskIICard.h"
#include <cassert>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <map>
#include <memory>
#include <string>
#include <vector>
static std::map<std::string,unsigned> labels(const char* path) {
 std::ifstream f(path);std::map<std::string,unsigned> r;std::string k,v,n;
 while(f>>k>>v>>n)r[n]=std::stoul(v,nullptr,16);return r;
}
int main(int argc,char** argv) {
 assert(argc==7);bool nmos=std::string(argv[6])=="6502";
 Memory m;m.setIIEMode(true);
 assert(m.loadAppleIIRom((std::string(argv[1])+"/roms/"+(nmos?"apple2e_unenh.rom":"apple2e.rom")).c_str()));
 auto card=std::make_unique<DiskIICard>();auto* d=card.get();
 assert(d->loadBootRom(std::string(argv[1])+"/roms/disk2.rom"));
 assert(d->insertDisk(0,argv[4]));assert(d->insertDisk(1,argv[5]));
 d->setWriteBackEnabled(true);d->setDriveHostWriteProtected(0,true);m.slotBus().plug(6,std::move(card));
 M6502 cpu(&m);m.setCpu(&cpu);cpu.setCpuMode(nmos?M6502::CpuMode::NMOS:M6502::CpuMode::CMOS);
 m.clearRam();m.resetSoftSwitches();m.slotBus().reset();
 std::ifstream f(argv[2],std::ios::binary);std::vector<unsigned char> code((std::istreambuf_iterator<char>(f)),{});
 assert(!code.empty());for(unsigned i=0;i<code.size();++i)m.writeRamUnchecked(0x1B00+i,code[i]);auto sym=labels(argv[3]);
 for(int i=0;i<8192;++i)m.writeRamUnchecked(0x6500+i,0xA5);memset(m.auxDataMutable(),0x5A,65536);
 for(int i=0;i<128;++i)m.writeRamUnchecked(0x100+i,0xCC);
 // cc65 software stack; zero page allocations match production target library.
 m.writeRamUnchecked(0x80,0);m.writeRamUnchecked(0x81,0xBF);
 bool failread=false,irqmasked=false;
 auto call=[&](const char* name,unsigned char a=0) {
  auto at=sym.at(std::string(".")+name);m.writeRamUnchecked(0x600,0x20);m.writeRamUnchecked(0x601,at);m.writeRamUnchecked(0x602,at>>8);
  cpu.setProgramCounter(0x600);cpu.setStackPointer(0xFF);cpu.setAccumulator(a);cpu.setXRegister(0);cpu.setStatusRegister(0x20|(irqmasked?4:0));
  unsigned long cycles=0;
  while(cpu.getProgramCounter()!=0x603 && cycles<100000000) {
   // Inject an unready latch at the real polling instruction. Exercise the
   // timeout/restore path even though an empty Disk II emits amplifier noise.
   if(failread && cpu.getProgramCounter()>=sym.at("._nb_poll") && cpu.getProgramCounter()<sym.at("._nb_poll")+96 && (cpu.getProgramCounter()-sym.at("._nb_poll"))%8==0) {
    cpu.setAccumulator(0);cpu.setStatusRegister(cpu.getStatusRegister()&0x7F);
    cpu.setProgramCounter(cpu.getProgramCounter()+3);
   }
   cycles+=cpu.run(1);
  }
  if(cpu.getProgramCounter()!=0x603){fprintf(stderr,"Timeout %s PC=%04x\n",name,cpu.getProgramCounter());std::abort();}
  assert(cpu.getStackPointer()==0xFF);assert(bool(cpu.getStatusRegister()&4)==irqmasked);
  for(int i=0;i<8192;++i)assert(m.data()[0x6500+i]==0xA5);
  for(int i=0;i<128;++i)assert(m.data()[0x100+i]==0xCC);
  for(int i=0;i<0x4000;++i)assert(m.auxData()[i]==0x5A);
  for(int i=0xC000;i<65536;++i)assert(m.auxData()[i]==0x5A);
  return cpu.getAccumulator();
 };
 for(unsigned char t: {0,1,17,34}) {
  m.writeRamUnchecked(sym.at("._nb_track"),t);
  call("_nb_begin",0x60);assert(call("_nb_protected"));
  auto r=call("_nb_test",0);
  if(r!=1){std::ofstream out(std::string(argv[5])+".capture",std::ios::binary);out.write((char*)m.auxData()+0x4000,8192);fprintf(stderr,"Source parse failed track %d\n",t);return 2;}
  assert(call("_nb_test",1)==1);call("_nb_end");call("_nb_test",2);
  call("_nb_begin",0xE0);d->setDriveHostWriteProtected(1,true);
  auto writes=d->getWriteFlushCount();assert(call("_nb_write")==0x2B);assert(d->getWriteFlushCount()==writes);
  d->setDriveHostWriteProtected(1,false);assert(call("_nb_write")==0);
  r=call("_nb_test",1);
  if(r!=1){std::ofstream out(std::string(argv[5])+".capture",std::ios::binary);out.write((char*)m.auxData()+0x6000,8192);fprintf(stderr,"Target verify failed track %d code %d\n",t,r);return 3;}
  call("_nb_end");printf("%s track %u: fields verified, protected target refused, main/stack/AUX bounds intact\n",argv[6],t);
 }
 assert(d->flushPendingWrites());
 // Empty drive must time out and restore the entire borrowed resident.
 d->ejectDisk(0);call("_nb_begin",0x60);m.writeRamUnchecked(sym.at("._nb_bank"),0x40);
 assert(call("_nb_test",0)==2);
 failread=irqmasked=true;assert(call("_nb_read")==0x27);failread=irqmasked=false;
 call("_nb_end");
 // Emulate the resident /RAM driver's destructive main buffer. The final
 // tail-call must return directly to the loader, without touching C again.
 unsigned char formatter[]={0xA9,0,0xA2,0,0x9D,0,0x20,0x9D,0,0x21,0xE8,0xD0,0xF7,0x60};
 for(unsigned i=0;i<sizeof formatter;++i)m.writeRamUnchecked(0x700+i,formatter[i]);
 m.writeRamUnchecked(sym.at("._nb_cleanup_fn"),0);m.writeRamUnchecked(sym.at("._nb_cleanup_fn")+1,7);
 m.writeRamUnchecked(sym.at("._nb_note"),0);m.writeRamUnchecked(sym.at("._nb_note")+1,0x11);
 const char* failure="RAM cleanup failure reported";
 for(unsigned i=0;i<=strlen(failure);++i)m.writeRamUnchecked(sym.at("._nb_ram_note")+i,failure[i]);
 call("_nb_finish",1);
 assert(!memcmp(m.data()+0x1100,failure,strlen(failure)+1));
 for(int i=0x2000;i<0x2200;++i)assert(m.data()[i]==0);
}
