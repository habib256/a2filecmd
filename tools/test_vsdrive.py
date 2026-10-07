"""Run the real VDrive driver (src/vsdrive.s) under sim65.

Two builds of the same source, on both CPUs:

1. The driver with a host behind it: the two instructions that touch the
   6551's data register (`lda ACIA_DATA,x`, `sta ACIA_DATA,x`, three bytes
   each, in getc, in the page-3 receive loop and in drain) are replaced by
   calls into a host model (feed_rd / feed_wr) that serves a scripted reply
   byte by byte, drops RDRF when the reply is exhausted and arms the next
   reply once the Apple has sent a given number of bytes -- a host does not
   answer before the envelope is complete. On it: install over two distinct
   DEVADR drivers, the interrupt handler's CLD, STATUS's block count, a good
   read (buffer, $44-$45 given back, the ProDOS clock), a bad block XOR
   ($27, $45 given back), a late reply (the reply of a call that timed out
   arrives before the next call: drained, the next call succeeds -- before
   the fix it failed in turn, and so did every call after it), a write (the
   bytes on the line), a 6551 whose transmitter never empties (CTS high) or
   dies mid-block, a silent host, a ProDOS with no interrupt handler left
   (nothing installed, DTR down), seven slots taken (nothing installed,
   the serial slot reported with slot 0 for the status line), the
   destructor giving each drive its own driver back and dropping DTR before
   it removes the handler, a serial card in slot 1 (the printer's) left
   alone, a Super Serial Card whose switches say printer skipped in slot 2
   and a communications card in slot 4 taken instead -- except on a //c.

2. The driver untouched, for its receive loop's cycle budget: at 115,200
   bps a byte arrives every 88.6 cycles (1.0205 MHz) and the 6551 holds one;
   the loop must take a byte (fast path) and notice the next (one poll)
   within that. sim65 counts the cycles of a 512-byte receive with RDRF held
   up, and of a receive that times out (16,384 polls). The former loop cost
   100 cycles a byte on the fast path alone.

sim65 memory is plain RAM: the slot ROM signature, the DIP switches and the
6551 registers are bytes the test writes. Only the software-reset check of
install (DTR must drop, which RAM cannot do) is bypassed."""
import re,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BYTE_CYCLES=1020484*10/115200       # 88.6: one byte (10 bits) at 115,200 bps, 8N1
BUDGET=85
HOST=r'''
.importzp ptr3, ptr4
.import ld_buf
.export _drv, _unit, _res_a, _res_x, _res_y, _res_p, _s_before, _s_after
.export _mli, _mli_cmds, _irq_handler, _hook_at, _patch_ld, _alloc_fails, _cmd_at_dealloc
.export _feed, _feedpos, _feedend, _arm_at, _arm_pos, _arm_end, _sent, _sentbuf
.export feed_rd, feed_wr, _hbuf
.bss
_unit: .res 1
_res_a: .res 1
_res_x: .res 1
_res_y: .res 1
_res_p: .res 1
_s_before: .res 1
_s_after: .res 1
_mli_cmds: .res 1
_irq_handler: .res 2
_hook_at: .res 1
_alloc_fails: .res 1
_cmd_at_dealloc: .res 1
_feedpos: .res 2
_feedend: .res 2
_arm_at: .res 2
_arm_pos: .res 2
_arm_end: .res 2
_sent: .res 2
fy: .res 1
_sentbuf: .res 600
_hbuf:
buf: .res 512
.data
_feed: .res 1100
.code
; unsigned char __fastcall__ drv(unsigned char cmd): one call through the
; page-3 thunk, as ProDOS makes it, interrupts enabled, block 7.
_drv:
 sta $42
 lda _unit
 sta $43
 lda #<buf
 sta $44
 lda #>buf
 sta $45
 lda #7
 sta $46
 lda #0
 sta $47
 php
 cli
 tsx
 stx _s_before
 jsr $0300
 sta _res_a
 stx _res_x
 sty _res_y
 php
 pla
 sta _res_p
 tsx
 stx _s_after
 plp
 lda _res_a
 ldx #0
 rts
; The MLI at $BF00: ALLOC_INTERRUPT ($40) records the handler address and
; returns interrupt number 1 -- or fails (carry set, $25) when alloc_fails;
; DEALLOC_INTERRUPT ($41) succeeds and notes the 6551's command register.
_mli:
 pla
 sta ptr3
 pla
 sta ptr3+1
 inc _mli_cmds
 ldy #1
 lda (ptr3),y
 pha
 iny
 lda (ptr3),y
 sta ptr4
 iny
 lda (ptr3),y
 sta ptr4+1
 pla
 cmp #$41
 bne :+
 pha
 lda $C0AA
 sta _cmd_at_dealloc
 pla
: cmp #$40
 bne ret
 lda _alloc_fails
 bne fail
 ldy #2
 lda (ptr4),y
 sta _irq_handler
 iny
 lda (ptr4),y
 sta _irq_handler+1
 ldy #1
 lda #1
 sta (ptr4),y
ret:
 lda ptr3
 clc
 adc #4
 sta ptr3
 bcc :+
 inc ptr3+1
: lda #0
 clc
 jmp (ptr3)
fail:
 lda ptr3
 clc
 adc #4
 sta ptr3
 bcc :+
 inc ptr3+1
: lda #$25
 sec
 jmp (ptr3)
; The host model. feed_rd stands for `lda ACIA_DATA,x`: the next byte of
; the reply, RDRF (bit 3 of the status at $C0A9, slot 2) dropped with the
; last one. feed_wr stands for `sta ACIA_DATA,x`: the byte goes to sentbuf;
; the arm_at-th byte sent makes the reply arm_pos..arm_end available.
; Unread bytes stay ahead of it, as on a real line (arm_pos is then
; their end). Both keep X, Y and the flags (carry: getc's verdict).
feed_rd:
 php
 sty fy
 lda _feedpos
 cmp _feedend
 bne :+
 lda _feedpos+1
 cmp _feedend+1
 beq rd_none
: lda _feedpos
 clc
 adc #<_feed
 sta ptr3
 lda _feedpos+1
 adc #>_feed
 sta ptr3+1
 ldy #0
 lda (ptr3),y
 inc _feedpos
 bne :+
 inc _feedpos+1
: pha
 lda _feedpos
 cmp _feedend
 bne rd_got
 lda _feedpos+1
 cmp _feedend+1
 bne rd_got
 lda $C0A9
 and #$F7
 sta $C0A9
rd_got:
 pla
 ldy fy
 plp
 rts
rd_none:
 lda #0
 ldy fy
 plp
 rts
feed_wr:
 php
 pha
 sty fy
 lda _sent
 clc
 adc #<_sentbuf
 sta ptr3
 lda _sent+1
 adc #>_sentbuf
 sta ptr3+1
 pla
 pha
 ldy #0
 sta (ptr3),y
 inc _sent
 bne :+
 inc _sent+1
: lda _sent
 cmp _arm_at
 bne wr_done
 lda _sent+1
 cmp _arm_at+1
 bne wr_done
 lda $C0A9          ; the reply joins the line: it follows whatever
 and #$08           ; is still unread there (arm_pos is the end of that)
 bne :+
 lda _arm_pos
 sta _feedpos
 lda _arm_pos+1
 sta _feedpos+1
: lda _arm_end
 sta _feedend
 lda _arm_end+1
 sta _feedend+1
 lda $C0A9
 ora #$08
 sta $C0A9
wr_done:
 pla
 ldy fy
 plp
 rts
; The page-3 block reader of the write path, replaced: at byte hook_at the
; 6551 status drops to 0 -- the transmitter stops emptying mid-block.
_patch_ld:
 lda #$4C
 sta ld_buf
 lda #<hook
 sta ld_buf+1
 lda #>hook
 sta ld_buf+2
 rts
hook:
 cpy _hook_at
 bne :+
 lda #0
 sta $C0A9
: lda ($44),y
 rts
'''
C=r'''
#include <string.h>
extern unsigned char unit,res_a,res_x,res_y,res_p,s_before,s_after,mli_cmds,hook_at,alloc_fails,cmd_at_dealloc;
extern unsigned int irq_handler,feedpos,feedend,arm_at,arm_pos,arm_end,sent;
extern unsigned char feed[1100],sentbuf[600],hbuf[512];
extern void mli(void);
void patch_ld(void);
unsigned char __fastcall__ drv(unsigned char cmd);
unsigned char vsdrive_install(void);
void vsdrive_uninstall(void);
#define DEVADR ((unsigned int*)0xBF10)
#define PEEK(a) (*(unsigned char*)(a))
#define ACIA_STATUS PEEK(0xC0A9)          /* slot 2 */
#define BUF (*(unsigned int*)0x44)
static unsigned char* buf;
/* carry set, A = $27, the 6502 stack and the interrupt flag as before, $44-$45 as given */
static unsigned char io_error(unsigned char cmd){
 unsigned char r=drv(cmd);
 return r==0x27 && (res_p&1) && s_after==s_before && !(res_p&4) && BUF==(unsigned)buf;
}
static unsigned char xorsum(const unsigned char*p,unsigned n){unsigned char c=0;while(n--)c^=*p++;return c;}
/* A read reply at feed[at]: the echo of the envelope (cmd, block), four
 * bytes of time and date (1,2,3,4), their XOR, 512 bytes of fill, their
 * XOR. Returns the end. */
static unsigned reply(unsigned at,unsigned char cmd,unsigned blk,unsigned char fill,unsigned char badxor){
 unsigned i;unsigned char*p=feed+at;
 p[0]=0xC5;p[1]=cmd;p[2]=blk;p[3]=blk>>8;p[4]=1;p[5]=2;p[6]=3;p[7]=4;p[8]=xorsum(p,8);
 for(i=0;i<512;++i)p[9+i]=fill;
 p[521]=xorsum(p+9,512)^badxor;
 return at+522;
}
static unsigned fills(unsigned char v){unsigned i,n=0;for(i=0;i<512;++i)n+=buf[i]==v;return n;}
static void quiet(void){feedpos=feedend=0;arm_at=0;sent=0;ACIA_STATUS=0x10;}
int main(void){
 unsigned char* h;
 unsigned char i,j,r;
 buf=hbuf;
 PEEK(0xBF00)=0x4C;*(unsigned int*)0xBF01=(unsigned int)mli;
 /* Slot 1 is the printer's (//e SSC, //c port 1): a serial card there alone
  * is not VDrive's. Its 6551 registers ($C098-$C09B) must keep every byte:
  * no probe, no baud rate, no envelope. */
 PEEK(0xC105)=0x38;PEEK(0xC107)=0x18;PEEK(0xC10B)=0x01;PEEK(0xC10C)=0x31;
 for(i=0;i<4;++i)PEEK(0xC098+i)=0xA0+i;
 PEEK(0xBF31)=0;PEEK(0xBF32)=0x60;
 if(vsdrive_install()!=0)return 20;
 if(PEEK(0xBF31)!=0||PEEK(0xBF32)!=0x60)return 21;
 for(i=0;i<4;++i)if(PEEK(0xC098+i)!=0xA0+i)return 22;
 /* An SSC in slot 2 whose mode switches (DIP bank 1, $C0A1, bits $03) say
  * printer, or one of the SIC printer emulations: never taken, its 6551
  * ($C0A8-$C0AB) keeps every byte. */
 PEEK(0xC205)=0x38;PEEK(0xC207)=0x18;PEEK(0xC20B)=0x01;PEEK(0xC20C)=0x31;
 for(i=0;i<4;++i)PEEK(0xC0A8+i)=0xB0+i;
 for(j=1;j<4;++j){
  PEEK(0xC0A1)=0xFC|j;
  PEEK(0xBF31)=0;PEEK(0xBF32)=0x60;
  if(vsdrive_install()!=0)return 30;
  if(PEEK(0xBF31)!=0||PEEK(0xBF32)!=0x60||PEEK(0x03B7))return 31;
  for(i=0;i<4;++i)if(PEEK(0xC0A8+i)!=0xB0+i)return 32;
 }
 /* The printer in slot 2, a communications SSC in slot 4: slot 4 is
  * taken, and slot 2 is still untouched after the destructor too. */
 PEEK(0xC0A1)=0xFE;
 PEEK(0xC405)=0x38;PEEK(0xC407)=0x18;PEEK(0xC40B)=0x01;PEEK(0xC40C)=0x31;
 PEEK(0xC0C1)=0xFC;
 PEEK(0xBF31)=0;PEEK(0xBF32)=0x60;
 if(vsdrive_install()!=0x41)return 33;
 if(PEEK(0xC0CB)!=0x10||PEEK(0xC0CA)!=0x0B)return 34;   /* slot 4: 115,200 bps, DTR */
 vsdrive_uninstall();
 if(PEEK(0xBF31)!=0||PEEK(0xBF32)!=0x60)return 35;
 for(i=0;i<4;++i)if(PEEK(0xC0A8+i)!=0xB0+i)return 36;
 PEEK(0xC40C)=0;
 /* A //c (MACHID $88: bits 7,6,3 = 1,0,1) has no switches: $C0A1 means
  * nothing there, and port 2 is taken as it always was. */
 PEEK(0xBF98)=0xBB;          /* //c, 128K, 80 columns, clock */
 PEEK(0xBF31)=0;PEEK(0xBF32)=0x60;
 if(vsdrive_install()!=0x21)return 37;
 vsdrive_uninstall();
 PEEK(0xBF98)=0;
 PEEK(0xC0A1)=0xFC;                      /* communications mode, 19,200 bps */
 /* A SmartPort unit in slot 1 (DEVLST $1B and $9B: a low nibble that is not
  * 0) and /RAM ($BF): their slots are taken. Compared as whole bytes with
  * $10 and $90, slot 1 passed for free -- measured before the fix: 0x21,
  * and the two DEVADR entries of the SmartPort drives given to VDrive. */
 DEVADR[1]=0x1111;DEVADR[9]=0x2222;
 PEEK(0xBF31)=3;PEEK(0xBF32)=0x60;PEEK(0xBF33)=0x1B;PEEK(0xBF34)=0x9B;PEEK(0xBF35)=0xBF;
 if(vsdrive_install()!=0x22)return 40;   /* serial slot 2, volumes in slot 2 */
 if(DEVADR[1]!=0x1111||DEVADR[9]!=0x2222)return 41;
 vsdrive_uninstall();
 if(PEEK(0xBF31)!=3||PEEK(0xBF33)!=0x1B||PEEK(0xBF34)!=0x9B||PEEK(0xBF35)!=0xBF)return 42;
 /* Every slot has a unit: nothing is installed, the 6551 is left as the
  * probe left it -- not programmed (control $10, DTR $0B) --, and the
  * answer is the serial slot with slot 0, so that the status line says
  * "no free slot" (it used to be 0: silent, as if there were no card). */
 for(i=0;i<7;++i)PEEK(0xBF32+i)=(i+1)<<4;
 PEEK(0xBF31)=6;PEEK(0xC0AB)=0;PEEK(0xC0AA)=0;
 if(vsdrive_install()!=0x20)return 43;
 if(PEEK(0xBF31)!=6||PEEK(0x03B7)||PEEK(0xC0AB)==0x10||PEEK(0xC0AA)==0x0B)return 44;
 /* ProDOS has no interrupt handler left: nothing is installed either --
  * DEVLST and DEVADR untouched, no DTR -- rather than a 6551 whose
  * DCD/DSR interrupts nobody would claim. */
 alloc_fails=1;mli_cmds=0;
 DEVADR[1]=0x1111;DEVADR[9]=0x2222;
 PEEK(0xBF31)=0;PEEK(0xBF32)=0x60;PEEK(0xC0AB)=0;PEEK(0xC0AA)=0;
 if(vsdrive_install()!=0)return 45;
 if(PEEK(0xBF31)!=0||PEEK(0xBF32)!=0x60||PEEK(0x03B7)||DEVADR[1]!=0x1111)return 46;
 if(PEEK(0xC0AB)==0x10||PEEK(0xC0AA)==0x0B||mli_cmds!=1)return 47;
 vsdrive_uninstall();
 if(mli_cmds!=1)return 48;               /* nothing to remove */
 alloc_fails=0;mli_cmds=0;
 DEVADR[1]=0x1111;DEVADR[9]=0x2222;      /* slot 1: drive 1, drive 2 */
 PEEK(0xBF31)=0;PEEK(0xBF32)=0x60;
 if(vsdrive_install()!=0x21)return 1;    /* serial slot 2, volumes in slot 1 */
 if(DEVADR[1]!=0x0300||DEVADR[9]!=0x0300)return 2;
 if(PEEK(0xBF31)!=2||PEEK(0xBF33)!=0x10||PEEK(0xBF34)!=0x90)return 3;
 h=(unsigned char*)irq_handler;
 if(irq_handler<0x0300||irq_handler>=0x03B0)return 4;
 if(h[0]!=0xD8||h[1]!=0xAD||h[2]!=0xA9||h[3]!=0xC0)return 5;   /* cld; lda $C0A9 */
 unit=0x10;
 if(drv(0)||res_x||res_y||(res_p&1))return 6;                  /* STATUS: 0 blocks */
 /* A good read of block 7, drive 1: the reply armed once the five bytes
  * of the envelope are out. The buffer, $44-$45 as given, the clock. */
 quiet();memset(buf,0x55,512);PEEK(0xBF90)=0;PEEK(0xBF93)=0;
 arm_pos=0;arm_end=reply(0,3,7,0xAA,0);arm_at=5;
 r=drv(1);
 if(r||(res_p&1)||fills(0xAA)!=512||BUF!=(unsigned)buf)return 50;
 if(sent!=5||sentbuf[0]!=0xC5||sentbuf[1]!=3||sentbuf[2]!=7||sentbuf[3]!=0||sentbuf[4]!=(0xC5^3^7))return 51;
 if(PEEK(0xBF92)!=1||PEEK(0xBF93)!=2||PEEK(0xBF90)!=3||PEEK(0xBF91)!=4)return 52;  /* TIME, DATE */
 /* A bad block XOR: $27, $45 as given (it used to come back two pages
  * high). What arrived is in the buffer, as with the Disk II driver. */
 quiet();memset(buf,0x55,512);
 arm_pos=0;arm_end=reply(0,3,7,0xAA,1);arm_at=5;
 if(!io_error(1)||fills(0xAA)!=512)return 53;
 /* A reply for another block (the envelope's echo differs): $27 before a
  * single byte of the block is taken. */
 quiet();memset(buf,0x55,512);
 arm_pos=0;arm_end=reply(0,3,9,0xAA,0);arm_at=5;
 if(!io_error(1)||fills(0x55)!=512)return 54;
 /* A late reply: the host answers a read after the Apple gave up on it
  * (silence: ~0.3 s), so its reply (block 7, $AA) sits on the line when
  * the next read of block 7 begins; that one is answered too ($BB), once
  * its envelope is out. The stale reply is drained: the second call is
  * served the right block. Before the fix the stale echo failed the
  * second call, whose own reply then failed the third, and so on. */
 quiet();memset(buf,0x55,512);
 unit=0x10;if(!io_error(1))return 55;
 feedpos=0;feedend=reply(0,3,7,0xAA,0);ACIA_STATUS=0x18;    /* the late reply, on the line */
 arm_pos=feedend;arm_end=reply(feedend,3,7,0xBB,0);arm_at=5;sent=0;
 r=drv(1);
 if(r||(res_p&1)||fills(0xBB)!=512||BUF!=(unsigned)buf)return 56;
 /* A write of block 7, drive 2: the envelope, the 512 bytes and their
  * XOR go out; the host echoes the envelope and the XOR it computed. */
 quiet();memset(buf,0x33,512);
 feed[0]=0xC5;feed[1]=4;feed[2]=7;feed[3]=0;feed[4]=0x00;   /* 512 x $33: XOR 0 */
 arm_pos=0;arm_end=5;arm_at=5+512+1;
 unit=0x90;r=drv(2);
 if(r||(res_p&1)||BUF!=(unsigned)buf||sent!=518)return 57;
 if(sentbuf[0]!=0xC5||sentbuf[1]!=4||sentbuf[2]!=7||sentbuf[3]!=0||sentbuf[4]!=(0xC5^4^7))return 58;
 for(i=0;i<8;++i)if(sentbuf[5+i*64]!=0x33)return 59;
 if(sentbuf[517]!=0)return 60;
 /* The host says it failed the write (XOR + 1): $27. */
 quiet();feed[4]=1;arm_pos=0;arm_end=5;arm_at=518;
 unit=0x90;if(!io_error(2))return 61;
 quiet();
 ACIA_STATUS=0;                                                 /* CTS high: TDRE never */
 unit=0x10;if(!io_error(1))return 7;
 unit=0x90;if(!io_error(2))return 8;
 ACIA_STATUS=0x10;hook_at=100;patch_ld();                       /* dies mid-block */
 unit=0x10;if(!io_error(2))return 9;
 if(ACIA_STATUS)return 10;
 ACIA_STATUS=0x10;                                              /* sends, nothing comes back */
 unit=0x90;if(!io_error(1))return 11;
 unit=0x20;if(drv(1)!=0x28||!(res_p&1))return 12;               /* not our unit */
 cmd_at_dealloc=0xFF;
 vsdrive_uninstall();
 if(DEVADR[1]!=0x1111||DEVADR[9]!=0x2222)return 13;
 if(PEEK(0xBF31)!=0||PEEK(0xBF32)!=0x60)return 14;
 if(mli_cmds!=2)return 15;
 if(cmd_at_dealloc!=0x0A)return 16;      /* DTR was down before the handler went */
 for(i=0;i<4;++i)if(PEEK(0xC098+i)!=0xA0+i)return 23;   /* the printer, untouched */
 return 0;
}
'''
# The cycle budget of the receive loop: n blocks of 512 bytes with RDRF
# held up (the fast path), or one receive that times out (polls).
CYCLES_ASM=r'''
.import rd_buf
.export _rdloop, _rdwait, _mli
.bss
buf: .res 512
.code
; The MLI at $BF00: skips the three inline bytes, hands out interrupt
; number 1 (vs_int, $03C6), carry clear.
_mli:
 pla
 clc
 adc #3
 tay
 pla
 adc #0
 pha
 tya
 pha
 lda #1
 sta $03C6
 lda #0
 clc
 rts
setup:
 lda #<buf
 sta $44
 lda #>buf
 sta $45
 lda #2
 sta $03C4         ; vs_pg
 lda #0
 sta $03B9         ; vs_chk
 sta $03BE         ; vs_to
 lda #$C0
 sta $03BF         ; vs_to+1
 ldx $03B8         ; vs_acia
 ldy #0
 rts
_rdloop:           ; A = n
 sta count
: lda count
 beq done
 dec count
 jsr setup
 lda #$08
 sta $C0A9
 jsr rd_buf
 jmp :-
done:
 rts
_rdwait:
 jsr setup
 lda #0
 sta $C0A9
 jmp rd_buf
count: .res 1
'''
CYCLES_C=r'''
#include <stdlib.h>
void __fastcall__ rdloop(unsigned char n);
void rdwait(void);
void mli(void);
unsigned char vsdrive_install(void);
#define PEEK(a) (*(unsigned char*)(a))
int main(int argc,char**argv){
 PEEK(0xC205)=0x38;PEEK(0xC207)=0x18;PEEK(0xC20B)=0x01;PEEK(0xC20C)=0x31;PEEK(0xC0A1)=0xFC;
 PEEK(0xBF00)=0x4C;*(unsigned int*)0xBF01=(unsigned int)mli;
 PEEK(0xBF31)=0;PEEK(0xBF32)=0x60;
 if(vsdrive_install()!=0x21)return 1;
 if(argv[1][0]=='W')rdwait();else rdloop(atoi(argv[1]));
 return 0;
}
'''
def prepare(tmp,host):
 """The source as the harness needs it: install's DTR check bypassed and,
 with the host model, the two data-register instructions redirected."""
 src=(ROOT/'src/vsdrive.s').read_text()
 assert src.count('bcc     ins_acia')==1
 src=src.replace('bcc     ins_acia','jmp     ins_acia')
 if host:
  assert src.count('lda     ACIA_DATA,x')==3 and src.count('sta     ACIA_DATA,x')==1, 'the harness replaces every data-register access'
  src=src.replace('lda     ACIA_DATA,x','jsr     feed_rd').replace('sta     ACIA_DATA,x','jsr     feed_wr')
  src+='\n        .export ld_buf\n        .import feed_rd, feed_wr\n'
 else:
  src+='\n        .export rd_buf\n'
 (tmp/'vsdrive.s').write_text(src)
 target=Path(subprocess.check_output([shutil.which('cl65'),'--print-target-path'],text=True).strip())
 cfg=(target.parent/'cfg/sim6502.cfg').read_text().replace('start = $0200, size = $FDF0','start = $4000, size = $7000')
 cfg=cfg.replace('    CODE:     load = MAIN,   type = ro;','    CODE:     load = MAIN,   type = ro;\n    LC:       load = MAIN,   type = ro;')
 (tmp/'test.cfg').write_text(cfg)
def build(tmp,tgt,cpu,*sources):
 subprocess.run([shutil.which('cl65'),'-t',tgt,'--cpu',cpu,'-C',str(tmp/'test.cfg'),'-O','-o',str(tmp/'test')]+[str(tmp/s) for s in sources]+[str(tmp/'vsdrive.s')],check=True)
def cycles(tmp,*args):
 r=subprocess.run([shutil.which('sim65'),'-c',str(tmp/'test')]+list(args),capture_output=True,text=True,timeout=60)
 assert r.returncode==0,(r.returncode,r.stdout,r.stderr)
 return int(re.search(r'(\d+) cycles',r.stdout+r.stderr).group(1))
CPUS=(('sim6502','6502'),('sim65c02','65c02'))
class VDrive(unittest.TestCase):
 def test_driver_with_a_host_install_failures_and_destructor(self):
  with tempfile.TemporaryDirectory(prefix='a2fc-vdrive-') as tmp:
   p=Path(tmp);(p/'host.s').write_text(HOST);(p/'test.c').write_text(C);prepare(p,host=True)
   for tgt,cpu in CPUS:
    with self.subTest(cpu=cpu):
     build(p,tgt,cpu,'test.c','host.s')
     r=subprocess.run([shutil.which('sim65'),str(p/'test')],timeout=60)
     self.assertEqual(r.returncode,0)
 def test_receive_loop_fits_a_byte_time_at_115200(self):
  with tempfile.TemporaryDirectory(prefix='a2fc-vdrive-') as tmp:
   p=Path(tmp);(p/'cychost.s').write_text(CYCLES_ASM);(p/'cyc.c').write_text(CYCLES_C);prepare(p,host=False)
   for tgt,cpu in CPUS:
    with self.subTest(cpu=cpu):
     build(p,tgt,cpu,'cyc.c','cychost.s')
     base=cycles(p,'0')
     fast=(cycles(p,'10')-base)/(10*512)
     poll=(cycles(p,'W')-base)/16384
     print(f'\nVDrive receive loop, {cpu}: {fast:.1f} cycles a byte, {poll:.1f} a poll; '
           f'budget {BUDGET} (a byte every {BYTE_CYCLES:.1f})')
     self.assertLess(fast+poll,BUDGET)
     self.assertGreater(poll,10)            # the poll really waited (the countdown ran)
if __name__=='__main__':unittest.main()
