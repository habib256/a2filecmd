"""Actual resident C rendering/input and 6502/65C02 presentation helpers."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

C = r'''
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#define SORT_MODES 3
#define ROWS 18
#define KEY_ESC 27
#define KEY_RETURN 13
#define KEY_LEFT 8
#define KEY_DELETE 127
struct Entry { char name[16]; unsigned char type,access; unsigned aux,blocks,mdate; unsigned long size; };
struct Panel { char path[64]; unsigned char count,cursor,top,fs,more,tags[8]; unsigned first; struct Entry e[64]; };
static struct Panel panels[2];
static unsigned char active,sort_mode,rev,xpos,ypos,keys[256];
static unsigned a2fc_draws,ki;
static char screen[24][80],inverse[24][80],input[64],question[128];
static struct { unsigned char before[16],data[512],after[16]; } guarded;
#define copy_buf guarded.data
static void gotoxy(unsigned char x,unsigned char y){assert(x<80&&y<24);xpos=x;ypos=y;}
static void revers(unsigned char r){rev=r;}
static void cputc(char c){assert(ypos<24);screen[ypos][xpos]=c;inverse[ypos][xpos]=rev;if(++xpos==80){xpos=0;++ypos;}}
static void cputs(const char*s){while(*s)cputc(*s++);}
static void cputcxy(unsigned char x,unsigned char y,char c){gotoxy(x,y);cputc(c);}
static void cclearxy(unsigned char x,unsigned char y,unsigned char n){gotoxy(x,y);while(n--)cputc(' ');}
static void cprintf(const char*f,...){char b[512];va_list a;va_start(a,f);vsnprintf(b,sizeof b,f,a);va_end(a);cputs(b);}
static char cgetc(void){assert(ki<256);return keys[ki++];}
static void reset(void){memset(screen,'#',sizeof screen);memset(inverse,0,sizeof inverse);memset(&guarded,0xA5,sizeof guarded);rev=ki=0;}
static void guard(void){unsigned i;for(i=0;i<16;++i)assert(guarded.before[i]==0xA5&&guarded.after[i]==0xA5);}
static void line_is(unsigned y,const char*s){unsigned n=strlen(s);assert(!memcmp(screen[y],s,n));while(n<80)assert(screen[y][n++]==' ');}
/* ACTUAL_SOURCE */
int main(void){
 unsigned t,p,m,i; char expected[128]; const char*known[9]={"TXT","BIN","DIR","AWP","S16","INT","BAS","VAR","SYS"};
 unsigned char codes[9]={4,6,15,26,179,250,252,253,255};
 const char*headers[3]={"Name*            Type  Aux     Size","Name             Type  Aux     Size*","Name             Type* Aux     Size"};
 struct Entry*e=&panels[0].e[0];
 for(t=0;t<256;++t){sprintf(expected,"$%02X",t);for(i=0;i<9;++i)if(t==codes[i])strcpy(expected,known[i]);assert(!strcmp(type_name(t),expected));}
 for(p=0;p<2;++p)for(m=0;m<3;++m){reset();strcpy(panels[p].path,"/VOL");sort_mode=m;draw_panel(p);sprintf(expected,"%-38s",headers[m]);assert(!memcmp(screen[1]+p*40,expected,38));assert(screen[1][38]=='#'&&screen[1][39]=='#'&&screen[1][78]=='#'&&screen[1][79]=='#');}
 panels[0].count=1;strcpy(e->name,"ABCDEFGHIJKLMNO");e->type=255;e->access=0;e->aux=65535;e->blocks=65535;e->size=16777215;e->mdate=(127u<<9)|(12<<5)|31;
 for(p=0;p<2;++p){reset();panels[0].fs=p;draw_info();sprintf(expected,"%s  type $FF  aux $FFFF  65535 blocks  16777215 bytes%s",e->name,p?"  (in image)":"  31/12/27  locked");expected[79]=0;line_is(21,expected);guard();}
 reset();panels[0].tags[0]=1;draw_info();assert(!memcmp(screen[21]+70,"1 tagged",8));guard();panels[0].tags[0]=0;
 reset();strcpy(e->name,"..");draw_info();line_is(21,"Parent directory");
 reset();strcpy(e->name,"DIR");e->type=15;draw_info();line_is(21,"DIR  directory  65535 blocks");
 for(t=0;t<256;++t){reset();keys[0]=t;keys[1]='Y';i=confirm("Proceed?");assert(i==(t!='N'&&t!='n'&&t!=27));assert(ki==((t=='Y'||t=='y'||t=='N'||t=='n'||t==27)?1:2));line_is(22,"");assert(!rev);}
 reset();memcpy(keys,"ab.c\r",5);assert(prompt("Name",0,0));assert(!strcmp(input,"AB.C"));line_is(22,"");
 reset();memcpy(keys,"9aF0\r",5);assert(prompt("Aux",0,4));assert(!strcmp(input,"9AF0"));
 reset();memcpy(keys,"AF\r",3);assert(!prompt("Aux",0,4));
 reset();keys[0]=27;assert(!prompt("Name","ORIGINAL",0));assert(!strcmp(input,"ORIGINAL"));line_is(22,"");
 return 0;
}
'''

ASM_C = r'''
#include <string.h>
#include <stdio.h>
void keys_bar(unsigned char,const char*);
unsigned int __fastcall__ hex_value(const char*);
static char text[1024],colors[1024];
static unsigned n;
static unsigned char rev,bad;
void gotoxy(unsigned char x,unsigned char y){if(x!=7||y!=23)bad=1;}
unsigned char __fastcall__ revers(unsigned char r){unsigned char old=rev;rev=r;return old;}
void __fastcall__ cputc(char c){if(n>=1024){bad=1;return;}text[n]=c;colors[n++]=rev;}
static const char*spec[]={"", "A Alpha,ESC Back", "AB Two,LONG Label", "X", " Label", "A ,B Two", "TAB Panel,RET Open,SPC Tag,C Copy,V Move,R Ren,D Del,K Mkdir,! More,? Help"};
/* C reference from before consolidation, rendered into the same capture. */
/* REFERENCE */
int main(void){
 unsigned i,j,refn;static char reftext[1024],refcolors[1024],hex[8];unsigned char r;
 static char boundary[512];void (*api)(unsigned char,const char*)=keys_bar;
 for(i=0;i<sizeof(spec)/sizeof(*spec);++i){
  /* Place the input across an actual page boundary, as plugin constants can be. */
  char*s=boundary+255-((unsigned)boundary&255);strcpy(s,spec[i]);
  n=bad=rev=0;reference(7,s);refn=n;r=rev;memcpy(reftext,text,n);memcpy(refcolors,colors,n);
  n=bad=rev=0;api(7,s);
  if(bad||n!=refn||rev!=r||memcmp(text,reftext,n)||memcmp(colors,refcolors,n)||strcmp(s,spec[i]))return 1;
 }
 for(i=0;;++i){sprintf(hex,"%04X",i);if(hex_value(hex)!=i)return 2;if(i==65535u)break;}
 if(hex_value("")||hex_value("123456")!=0x3456)return 3;
 for(j=0;j<4;++j){hex[j]='F';hex[j+1]=0;if(hex_value(hex)!=(65535u>>(12-4*j)))return 4;}
 return 0;
}
'''


def section(source, start, end):
    return source[source.index(start):source.index(end, source.index(start))]


class Display(unittest.TestCase):
    def test_actual_c_rendering_and_confirmation(self):
        source = (ROOT / 'src/a2fc.c').read_text()
        parts = [section(source, 'static void clear_row(', '#pragma code-name (push, "LC")'),
                 '#include "src/display_types.h"\n',
                 section(source, 'static unsigned char is_up(', '/* The tags of both panels'),
                 section(source, 'static void draw_entry(', '/* The separator line'),
                 section(source, 'static void draw_info(', 'static void draw_all('),
                 section(source, 'static void question_begin(', 'unsigned int __fastcall__ hex_value('),
                 section(source, '\nconst char a2fc_header[]', 'const char MAIN_KEYS[]'),
                 'const char msg_parent[]="Parent directory";\n']
        with tempfile.TemporaryDirectory(prefix='a2fc-display-') as tmp:
            p = Path(tmp)
            (p / 'test.c').write_text(C.replace('/* ACTUAL_SOURCE */', '\n'.join(parts)))
            subprocess.run(['cc', '-std=c99', '-I', str(ROOT), str(p / 'test.c'), '-o', str(p / 'test')], check=True)
            subprocess.run([str(p / 'test')], check=True)

    def test_actual_assembly_on_both_cpus(self):
        # Keep the old parser as an independent oracle, including malformed
        # short specs, padding, clipping and inverse attributes.
        reference = r'''
static void reference(unsigned char x,const char*spec){
 const char*s=spec;unsigned char klen,i;gotoxy(x,23);
 while(*s){for(klen=0;s[klen]&&s[klen]!=' ';++klen){}
 revers(1);if(klen==1){cputc(' ');cputc(*s);cputc(' ');}
 else for(i=0;i<3;++i)cputc(i<klen?s[i]:' ');
 revers(0);s+=klen;if(*s==' ')++s;
 while(*s&&*s!=',')cputc(*s++);if(*s==','){cputc(' ');++s;}}
}
'''
        with tempfile.TemporaryDirectory(prefix='a2fc-display-asm-') as tmp:
            p = Path(tmp)
            (p / 'test.c').write_text(ASM_C.replace('/* REFERENCE */', reference))
            # Only relocate LC for the simulator; execute the production code.
            (p / 'display.s').write_text((ROOT / 'src/display.s').read_text().replace('.segment "LC"', '.segment "CODE"'))
            for cpu, target in [('6502', 'sim6502'), ('65c02', 'sim65c02')]:
                with self.subTest(cpu=cpu):
                    subprocess.run([shutil.which('cl65'), '-t', target, '--cpu', cpu, '-O', '-o', str(p / 'test'), str(p / 'test.c'), str(p / 'display.s')], check=True)
                    subprocess.run([shutil.which('sim65'), str(p / 'test')], check=True, timeout=60)


if __name__ == '__main__':
    unittest.main()
