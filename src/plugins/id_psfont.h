/* The reader reuses these bounds and validates the entire body before
 * display. Only MAIN layout state is written during identification. */
#include "ps_font_layout.h"
static const char* psfont_content(void){
 unsigned char modern;
 modern=!id_dos && e->type==0xF5;
 if(e->type!=6 && !modern)return NULL;
 if(n<(modern?392U:e->aux==0x5FF4?248U:236U) || sz.l>16384UL)return NULL;
 if(!ps_font_layout(b,(unsigned int)sz.l,e->aux,modern))return NULL;
 reader="PSFONT";return "Print Shop font?";
}
