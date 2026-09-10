/* Streaming BIN/SYS disassembler. No execution and no source writes.
 * File offsets are 24-bit; displayed CPU addresses wrap at 16 bits.
 * All state is initialized on entry: the overlay loader does not clear BSS. */
#define UTIL_CREATE
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
static char record[96];
static char* export_status;

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

/* A common row for the viewer and the text export. */
static unsigned char line(const unsigned char* bytes,unsigned char available,unsigned long pos)
{
    unsigned char n,i;
    unsigned int pc=(origin+(unsigned int)pos)&0xFFFFU;
    n=decode(bytes,available,pc);
    a.sprintf(record,"%06lX  %04X  ",pos,pc);
    for(i=0;i<3;++i) {
        if(i<n)a.sprintf(record+14+i*3,"%02X ",bytes[i]);
        else a.strcpy(record+14+i*3,"   ");
    }
    a.sprintf(record+23," %s\r\n",instruction);
    return n;
}

static unsigned int read_page(unsigned long pos)
{
    unsigned int want,got;
    failed=0;
    want=size-pos>LINES*3 ? LINES*3 : (unsigned int)(size-pos);
    if(a.fseek(file,(long)pos,SEEK_SET)) { failed=1;return 0; }
    got=want ? a.fread(buf,1,want,file) : 0;
    if(got!=want)failed=1;
    return got;
}

static unsigned char write_record(FILE* out)
{
    unsigned int n=a.strlen(record);
    return a.fwrite(record,1,n,out)==n;
}

/* Two open streams fit the resident's two I/O buffers. Read 57 bytes and
 * consume at most 19 instructions, then seek to the next instruction.
 * 0 complete, 1 output failure, 2 input failure, 3 cancelled. */
static unsigned char export_text(FILE* out)
{
    unsigned long pos=offset;
    unsigned int got,used;
    unsigned char row;
    if(stop())return 3;
    a.sprintf(record,"; DISASM %s\r\n",a.full);
    if(!write_record(out))return 1;
    a.sprintf(record,"; CPU %s  LOAD $%04X  OFFSET $%06lX\r\n",cpu ? "65C02" : "6502",origin,offset);
    if(!write_record(out))return 1;
    while(pos<size) {
        if(stop())return 3;
        got=read_page(pos);
        if(failed)return 2;
        used=0;
        for(row=0;row<LINES && used<got;++row) {
            if(stop())return 3;
            used+=line(buf+used,(unsigned char)(got-used),pos+used);
            if(!write_record(out))return 1;
        }
        pos+=used;
    }
    a.strcpy(record,"; END DISASM\r\n");
    return write_record(out) ? 0 : 1;
}

static void export(void)
{
    FILE* out;
    unsigned char result;
    if(other->fs || !other->path[0]) { a.message("Open destination in other panel.");a.cgetc();return; }
    a.sprintf(record,"Export from $%06lX: new TXT file",offset);
    if(!a.prompt(record,"DISASM.TXT",0))return;
    if(!join(a.other_full,other->path,a.input)) { a.message("Path too long.");a.cgetc();return; }
    if(newfile(a.other_full,4,0,1)) { a.message("Cannot create file (name in use?).");a.cgetc();return; }
    *a.filetype=4;*a.auxtype=0;
    out=a.fopen(a.other_full,"wb");
    if(!out) { a.message("Cannot open output; empty file remains.");a.cgetc();return; }
    cancelled=0;a.message("Exporting... ESC cancels");
    result=export_text(out);
    if(a.fclose(out))result=1;
    export_status=result==3 ? "Export cancelled; partial file kept." :
        result ? "Export incomplete; partial file kept." : "Disassembly exported to other panel.";
}

/* Read at most one page's maximum byte count. Compare with the known EOF:
 * a failed seek or a short read is an error, never a clean end-of-file. */
static void render(void)
{
    unsigned int got,used;
    unsigned char row;
    following=offset;failed=0;
    a.clrscr();a.cprintf("DISASM - %s - READ ONLY\r\n",cpu ? "65C02" : "6502");
    a.cprintf("%s  Load $%04X\r\n",a.selected->name,origin);
    got=read_page(offset);
    used=0;
    for(row=0;row<LINES && used<got;++row) {
        used+=line(buf+used,(unsigned char)(got-used),offset+used);
        a.cputs(record);
    }
    following=offset+used;
    a.gotoxy(0,21);
    a.cputs(failed ? "Read error: incomplete page." : export_status ? export_status : following==size ? "End of file." : "");
    a.gotoxy(0,22);a.cputs("N/SPACE Next P Previous C CPU G Offset L Load R Start E Export ESC Back");
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
    offset=0;depth=0;export_status=NULL;
#ifdef A2FC_6502
    cpu=0;
#else
    cpu=1;
#endif
    for(;;) {
        render();key=a.cgetc();if(key==KEY_ESC)break;
        export_status=NULL;
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
        if(key=='E')export();
        if(key=='L' && a.prompt("Load address (4 hex digits)",NULL,4))origin=(unsigned int)hex_number(4);
        if(key=='G' && a.prompt("File offset (6 hex digits)",NULL,6)) {
            dest=hex_number(6);
            if(dest<size) { offset=dest;depth=0; }
            else { a.message("Offset outside file.");a.cgetc(); }
        }
    }
    a.fclose(file);note("");
}
