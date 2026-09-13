/* Native transport bench adapter: compile the same C and assembly as NIBCOPY. */
#include "../src/plugins/nibcopy.c"
unsigned char __fastcall__ nb_test(unsigned char op) {
 buf=(unsigned char*)0x1000;
 if(op==2){build();return 1;}
 if(!capture(op))return 2;
 return op?(equal()?1:3):1;
}
