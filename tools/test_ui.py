"""Execute native question rendering and menu grouping as host C."""
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'src/a2fc.c').read_text()
def section(a,b):
    start=SOURCE.index(a)
    return SOURCE[start:SOURCE.index(b,start)]

class UserInterface(unittest.TestCase):
    def test_questions_and_grouping(self):
        code=r'''
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#define KEY_ESC 27
#define KEY_RETURN 13
#define KEY_LEFT 8
#define KEY_DELETE 127
static char input[64], line[128];
static unsigned char inverse, styles[128];
static unsigned int col, waits;
static const char* keys;
static void clear_row(unsigned char row) { assert(row==22); memset(line,0,sizeof line); col=0; }
static void gotoxy(unsigned char x,unsigned char y) { assert(y==22); col=x; }
static void revers(unsigned char v) { inverse=v; }
static void cputsxy(unsigned char x,unsigned char y,const char* s) {
    gotoxy(x,y);while(*s) { styles[col]=inverse;line[col++]=*s++; } line[col]=0;
}
static void cputs(const char* s) { cputsxy(col,22,s); }
static void cputc(char c) { char s[2]={c,0};cputs(s); }
static void cprintf(const char* format,...) {
    char buf[128];va_list args;va_start(args,format);vsnprintf(buf,sizeof buf,format,args);va_end(args);
    cputsxy(col,22,buf);
}
static char cgetc(void) {
    unsigned int i;assert(!inverse);assert(line[0]);
    for(i=0;line[i];++i)assert(styles[i]);
    ++waits;assert(*keys);return *keys++;
}
'''
        code+=section('static void message(', '#pragma code-name (pop)')
        code+=section('static void question_begin(', 'unsigned int __fastcall__ hex_value(')
        code+=section('static const char mn_cat0', 'static const char mn_count')
        code+=r'''
int main(void) {
    unsigned int i;
    message("\1Choose P or D");assert(!strcmp(line,"Choose P or D"));assert(!inverse);
    for(i=0;line[i];++i)assert(styles[i]);
    revers(1);message("Read complete.");assert(!strcmp(line,"Read complete."));assert(!inverse);
    for(i=0;line[i];++i)assert(!styles[i]);
    keys="xY";assert(confirm("Delete NOTE?"));assert(!line[0]);assert(waits==2);
    keys="N";assert(!confirm("Delete NOTE?"));
    keys="\33";assert(!confirm("Erase RAM?"));
    keys="ab\10c\r";assert(prompt("Name",0,0));assert(!strcmp(input,"AC"));
    keys="\33";assert(!prompt("Name","NOTE",0));assert(!line[0]);
    keys="0f\r";assert(prompt("Type",0,2));assert(!strcmp(input,"0F"));
    keys="f\r";assert(!prompt("Type",0,2));assert(!inverse);
    assert(menu_category("TEXT")==0);assert(menu_category("FONTVIEW")==1);
    assert(menu_category("PT3")==2);assert(menu_category("VOLINFO")==3);
    assert(menu_category("INTBASIC")==4);assert(menu_category("DATE")==5);
    assert(menu_category("UNSHRINK")==6);assert(menu_category("HELLO")==7);
    assert(menu_category("VIEW")==7);assert(menu_category("TEXTMORE")==7);
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='a2fc-ui-') as tmp:
            c=Path(tmp)/'test.c';exe=Path(tmp)/'test';c.write_text(code)
            subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas',str(c),'-o',str(exe)],check=True)
            subprocess.run([str(exe)],check=True)

if __name__=='__main__':unittest.main()
