// Run the production classifier at its fixed sample address. Cases are
// read-only records: name[17], type, aux16, size32, count16, DOS flag,
// expected reader[16], sample[512], all integers little endian.
#include "Memory.h"
#include "M6502.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
int main(int argc,char**argv){
 if(argc!=10)return 1;
 unsigned addr[6];for(int i=0;i<6;i++)addr[i]=std::strtoul(argv[2+i],nullptr,16);
 unsigned char code[9472];FILE*f=fopen(argv[1],"rb");if(!f)return 2;
 size_t length=fread(code,1,sizeof code,f);fclose(f);
 FILE*cases=fopen(argv[9],"rb");if(!cases)return 2;
 unsigned char record[555];int errors=0,total=0;
 while(size_t got=fread(record,1,sizeof record,cases)){
  if(got!=sizeof record){fclose(cases);return 2;}
  ++total;Memory m;m.setIIEMode(true);M6502 c(&m);m.setCpu(&c);
  m.setTestMode(true);m.clearRam();c.setCpuMode(argv[8][0]=='1'?M6502::CpuMode::CMOS:M6502::CpuMode::NMOS);c.hardReset();
  for(size_t j=0;j<length;j++)m.writeRamUnchecked(0x1B00+j,code[j]);
  auto word=[&](unsigned at,unsigned value){m.writeRamUnchecked(at,value&255);m.writeRamUnchecked(at+1,value>>8);};
  for(int j=0x80;j<0x9A;j++)m.writeRamUnchecked(j,0xA5);word(0x80,0xB000);
  for(int j=0;j<29;j++)m.writeRamUnchecked(addr[0]+j,0);
  for(int j=0;j<17;j++)m.writeRamUnchecked(addr[0]+j,record[j]);
  m.writeRamUnchecked(addr[0]+17,record[17]);
  for(int j=0;j<2;j++)m.writeRamUnchecked(addr[0]+19+j,record[18+j]);
  for(int j=0;j<4;j++){
   m.writeRamUnchecked(addr[0]+21+j,record[20+j]);
   m.writeRamUnchecked(addr[2]+j,record[20+j]);
  }
  for(int j=0;j<512;j++)m.writeRamUnchecked(0x0E00+j,record[43+j]);
  word(addr[1],record[24]|(record[25]<<8));m.writeRamUnchecked(addr[3],record[26]);word(addr[4],0);
  c.setStatusRegister(0x24);c.setStackPointer(0xFD);word(0x1FE,0xFFF0-1);c.setProgramCounter(addr[5]);
  int steps=0;for(;steps<200000&&c.getProgramCounter()!=0xFFF0;steps++)c.run(1);
  unsigned r=m.data()[addr[4]]|(m.data()[addr[4]+1]<<8);
  std::string actual;
  if(r>=0x1B00&&r<0x4000)for(unsigned j=0;j<16&&m.data()[r+j];j++)actual+=char(m.data()[r+j]);
  bool failed=c.getProgramCounter()!=0xFFF0 || (r&&actual.empty()) || actual!=reinterpret_cast<char*>(record+27) || m.data()[0x80]!=0 || m.data()[0x81]!=0xB0;
  for(int j=0;j<512;j++)if(m.data()[0xE00+j]!=record[43+j])failed=true;
  if(failed){++errors;if(errors<25)printf("FAIL %d name=%s type=%02x DOS=%d expected=%s actual=%s pc=%04x\n",total,record,record[17],record[26],record+27,actual.c_str(),c.getProgramCounter());}
 }
 bool bad=ferror(cases);fclose(cases);
 printf("%d classification cases, %d errors\n",total,errors);
 return bad?2:errors?3:0;
}
