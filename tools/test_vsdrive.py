"""Run the real VDrive driver (src/vsdrive.s) under sim65: install over two
distinct DEVADR drivers, the interrupt handler's CLD, STATUS's block count,
a 6551 whose transmitter never empties (CTS high) or dies mid-block, a silent
host, and the destructor giving each drive its own driver back.

sim65 memory is plain RAM: the slot ROM signature and the 6551 registers are
bytes the test writes. Only the software-reset check of install (DTR must
drop, which RAM cannot do) is bypassed."""
import shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
ASM=r'''
.importzp ptr3, ptr4
.import ld_buf
.export _drv, _unit, _res_a, _res_x, _res_y, _res_p, _s_before, _s_after
.export _mli, _mli_cmds, _irq_handler, _hook_at, _patch_ld
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
buf: .res 512
.code
; unsigned char __fastcall__ drv(unsigned char cmd): one call through the
; page-3 thunk, as ProDOS makes it, interrupts enabled.
_drv:
 sta $42
 lda _unit
 sta $43
 lda #<buf
 sta $44
 lda #>buf
 sta $45
 lda #0
 sta $46
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
; returns interrupt number 1; DEALLOC_INTERRUPT ($41) succeeds.
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
 cmp #$40
 bne ret
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
; The page-3 block reader, replaced: at byte hook_at the 6551 status drops
; to 0 -- the transmitter stops emptying in the middle of a written block.
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
extern unsigned char unit,res_a,res_x,res_y,res_p,s_before,s_after,mli_cmds,hook_at;
extern unsigned int irq_handler;
extern void mli(void);
void patch_ld(void);
unsigned char __fastcall__ drv(unsigned char cmd);
unsigned char vsdrive_install(void);
void vsdrive_uninstall(void);
#define DEVADR ((unsigned int*)0xBF10)
#define PEEK(a) (*(unsigned char*)(a))
#define ACIA_STATUS PEEK(0xC0A9)          /* slot 2 */
/* carry set, A = $27, the 6502 stack and the interrupt flag as before */
static unsigned char io_error(unsigned char cmd){
 return drv(cmd)==0x27 && (res_p&1) && s_after==s_before && !(res_p&4);
}
int main(void){
 unsigned char* h;
 PEEK(0xBF00)=0x4C;*(unsigned int*)0xBF01=(unsigned int)mli;
 PEEK(0xC205)=0x38;PEEK(0xC207)=0x18;PEEK(0xC20B)=0x01;PEEK(0xC20C)=0x31;
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
 ACIA_STATUS=0;                                                 /* CTS high: TDRE never */
 unit=0x10;if(!io_error(1))return 7;
 unit=0x90;if(!io_error(2))return 8;
 ACIA_STATUS=0x10;hook_at=100;patch_ld();                       /* dies mid-block */
 unit=0x10;if(!io_error(2))return 9;
 if(ACIA_STATUS)return 10;
 ACIA_STATUS=0x10;                                              /* sends, nothing comes back */
 unit=0x90;if(!io_error(1))return 11;
 unit=0x20;if(drv(1)!=0x28||!(res_p&1))return 12;               /* not our unit */
 vsdrive_uninstall();
 if(DEVADR[1]!=0x1111||DEVADR[9]!=0x2222)return 13;
 if(PEEK(0xBF31)!=0||PEEK(0xBF32)!=0x60)return 14;
 if(mli_cmds!=2)return 15;
 return 0;
}
'''
class VDrive(unittest.TestCase):
 def test_driver_install_timeouts_status_and_destructor(self):
  src=(ROOT/'src/vsdrive.s').read_text()
  self.assertEqual(src.count('bcc     ins_acia'),1)
  src=src.replace('bcc     ins_acia','jmp     ins_acia')+'\n        .export ld_buf\n'
  with tempfile.TemporaryDirectory(prefix='a2fc-vdrive-') as tmp:
   p=Path(tmp);(p/'host.s').write_text(ASM);(p/'test.c').write_text(C);(p/'vsdrive.s').write_text(src)
   target=Path(subprocess.check_output([shutil.which('cl65'),'--print-target-path'],text=True).strip())
   cfg=(target.parent/'cfg/sim6502.cfg').read_text().replace('start = $0200, size = $FDF0','start = $4000, size = $7000')
   cfg=cfg.replace('    CODE:     load = MAIN,   type = ro;','    CODE:     load = MAIN,   type = ro;\n    LC:       load = MAIN,   type = ro;')
   (p/'test.cfg').write_text(cfg)
   for tgt,cpu in (('sim6502','6502'),('sim65c02','65c02')):
    with self.subTest(cpu=cpu):
     subprocess.run([shutil.which('cl65'),'-t',tgt,'--cpu',cpu,'-C',str(p/'test.cfg'),'-O','-o',str(p/'test'),str(p/'test.c'),str(p/'host.s'),str(p/'vsdrive.s')],check=True)
     r=subprocess.run([shutil.which('sim65'),str(p/'test')],timeout=20)
     self.assertEqual(r.returncode,0)
if __name__=='__main__':unittest.main()
