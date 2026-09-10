/* Streaming BIN/SYS disassembler. No execution and no source writes.
 * File offsets are 24-bit; displayed CPU addresses wrap at 16 bits.
 * All state is initialized on entry: the overlay loader does not clear BSS. */
#include "util.h"
#include "disasm_ops.h"

void __fastcall__ plugin_entry(const struct A2fcApi* api);
struct PluginHeader {
    unsigned int signature; unsigned char flags;
    void __fastcall__ (*entry)(const struct A2fcApi*);
    unsigned char r0, r1, r2; char desc[52];
};
#pragma rodata-name (push, "OVLHDR")
const struct PluginHeader __plugin_header = {
    PLUGIN_MAGIC, OVERLAY_BIG, plugin_entry, 0, 0, 0,
    "Disassemble BIN/SYS: 6502 or 65C02, read only"
};
#pragma rodata-name (pop)

#define LINES 19
#define HISTORY 64
static FILE* file;
static unsigned long offset, following, size, history[HISTORY];
static unsigned int origin;
static unsigned char cpu, depth, failed;
static char instruction[32];

/* Return the bytes consumed. Incomplete/unknown instructions consume one
 * byte, so the display never invents operands or silently drops a tail. */
static unsigned char decode(const unsigned char* bytes, unsigned char available,
                            unsigned int address)
{
    unsigned char op, mode, n;
    unsigned int value, target;
    const char* fmt;
    op=bytes[0];mode=opcodes[op].mode;
    if(!cpu && (mode&0x80))mode=AM_ILLEGAL;
    mode&=0x7F;n=lengths[mode];
    if(mode==AM_ILLEGAL || n>available) {
        a.sprintf(instruction,".BYTE $%02X",op);return 1;
    }
    value=n>1 ? bytes[1] : 0;
    if(n==3)value|=(unsigned int)bytes[2]<<8;
    fmt="";target=0;
    switch(mode) {
        case AM_ACCUMULATOR: fmt=" A";break;
        case AM_IMMEDIATE: fmt=" #$%02X";break;
        case AM_DIRECT: fmt=" $%02X";break;
        case AM_DIRECTX: fmt=" $%02X,X";break;
        case AM_DIRECTY: fmt=" $%02X,Y";break;
        case AM_ABSOLUTE: fmt=" $%04X";break;
        case AM_ABSOLUTEX: fmt=" $%04X,X";break;
        case AM_ABSOLUTEY: fmt=" $%04X,Y";break;
        case AM_DIRECTXINDIRECT: fmt=" ($%02X,X)";break;
        case AM_DIRECTINDIRECTY: fmt=" ($%02X),Y";break;
        case AM_DIRECTINDIRECT: fmt=" ($%02X)";break;
        case AM_JMPABSOLUTEINDIRECT: fmt=" ($%04X)";break;
        case AM_ABSOLUTEXINDIRECT: fmt=" ($%04X,X)";break;
        case AM_RELATIVE:
            value=(address+2+(signed char)bytes[1])&0xFFFFU;
            fmt=" $%04X";break;
        case AM_BITBRANCH:
            target=(address+3+(signed char)bytes[2])&0xFFFFU;
            value=bytes[1];fmt=" $%02X,$%04X";break;
    }
    a.strcpy(instruction,mnemonics[opcodes[op].name]);
    a.sprintf(instruction+a.strlen(instruction),fmt,value,target);
    return n;
}

static unsigned long hex_number(unsigned char digits)
{
    unsigned long v=0;
    unsigned char i,c;
    for(i=0;i<digits;++i) { c=a.input[i];v=(v<<4)|(c<='9' ? c-'0' : c-'A'+10); }
    return v;
}

/* Read at most one page's maximum byte count. Compare with the known EOF:
 * a failed seek or a short read is an error, never a clean end-of-file. */
static void render(void)
{
    unsigned int want,got,used,pc;
    unsigned char row,n,i;
    following=offset;failed=0;
    a.clrscr();a.cprintf("DISASM - %s - READ ONLY\r\n",cpu ? "65C02" : "6502");
    a.cprintf("%s  Load $%04X\r\n",a.selected->name,origin);
    want=size-offset>LINES*3 ? LINES*3 : (unsigned int)(size-offset);
    got=0;
    if(a.fseek(file,(long)offset,SEEK_SET))failed=1;
    else if(want) { got=a.fread(buf,1,want,file);if(got!=want)failed=1; }
    used=0;
    for(row=0;row<LINES && used<got;++row) {
        pc=(origin+(unsigned int)(offset+used))&0xFFFFU;
        n=decode(buf+used,(unsigned char)(got-used),pc);
        a.cprintf("%06lX  %04X  ",offset+used,pc);
        for(i=0;i<3;++i) {
            if(i<n)a.cprintf("%02X ",buf[used+i]);else a.cputs("   ");
        }
        a.cprintf(" %s\r\n",instruction);used+=n;
    }
    following=offset+used;
    a.gotoxy(0,21);
    a.cputs(failed ? "Read error: incomplete page." : following==size ? "End of file." : "");
    a.gotoxy(0,22);a.cputs("N/SPACE Next P Previous C CPU G Offset L Load R Start ESC Back");
}

void __fastcall__ plugin_entry(const struct A2fcApi* api)
{
    unsigned char key,i;
    unsigned long dest;
    init(api);
    if(pan->fs || !pan->path[0] || !a.full[0] ||
       (a.selected->type!=6 && a.selected->type!=0xFF)) {
        note("Select a BIN or SYS file on a ProDOS volume.");return;
    }
    file=a.fopen(a.full,"rb");
    if(!file) { note("DISASM: cannot open file.");return; }
    size=a.selected->size;origin=a.selected->type==0xFF ? 0x2000 : a.selected->aux;
    offset=0;depth=0;
#ifdef A2FC_6502
    cpu=0;
#else
    cpu=1;
#endif
    for(;;) {
        render();key=a.cgetc();if(key==KEY_ESC)break;
        if(key==KEY_DOWN || key==KEY_RIGHT || key==' ')key='N';
        if(key==KEY_UP || key==KEY_LEFT)key='P';
        key&=0xDF;
        if(key=='N' && !failed && following<size) {
            if(depth==HISTORY) {
                for(i=1;i<HISTORY;++i)history[i-1]=history[i];
                --depth;
            }
            history[depth]=offset;++depth;offset=following;
        }
        if(key=='P' && depth)offset=history[--depth];
        if(key=='R') { offset=0;depth=0; }
        if(key=='C') { cpu^=1;depth=0; }
        if(key=='L' && a.prompt("Load address (4 hex digits)",NULL,4))origin=(unsigned int)hex_number(4);
        if(key=='G' && a.prompt("File offset (6 hex digits)",NULL,6)) {
            dest=hex_number(6);
            if(dest<size) { offset=dest;depth=0; }
            else { a.message("Offset outside file.");a.cgetc(); }
        }
    }
    a.fclose(file);note("");
}
