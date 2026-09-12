"""Execute the complete PT3 assembly decoder on both CPUs, with/without scaling.

Only the module address is relocated for sim65. pt_write is instrumented at
the data write to capture the bytes handed to the VIA; its real body still executes.
Expected amplitudes come from the archived reference tables, not the generator.
No user files, Apple II disks or auxiliary RAM are written.
"""
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGINS = ROOT / 'src/plugins'

HARNESS = r'''
#include <stdio.h>
#include <string.h>
extern unsigned char pt_regs[], notes[], emitted[];
extern unsigned pt_end;
void __fastcall__ pt_tables(unsigned char*);
void __fastcall__ pt_hw_start(unsigned char);
unsigned char pt_init(void), pt_frame(void);
void pt_output(void);
unsigned char tables[512], original[320], pt_pages[256];
unsigned char __fastcall__ pt_page(unsigned char page) {(void)page; return 0;}
#define song ((unsigned char*)0x8000)
static void word(unsigned p, unsigned v) { song[p]=v; song[p+1]=v>>8; }
static unsigned char vols[3];
static void fixture(unsigned char version, unsigned char volume,
                    unsigned char amplitude, unsigned char mode) {
    unsigned i, p;
    memset(song,0,320);
    song[13]=version; song[99]=1; song[100]=1; song[101]=1; song[202]=255;
    word(103,203); word(107,220); word(169,230);
    song[221]=1; song[222]=1;
    if(mode==1) song[222]=0;
    if(mode==2) song[222]=0xc1;
    if(mode==3) song[222]=0x81;
    song[223]=amplitude; song[231]=1;
    for(i=0;i<3;++i) {
        p=240+20*i; word(203+2*i,p);
        vols[i]=(volume+i*5)%15+1;
        if(volume!=255) song[p++]=0xc0|vols[i];
        else vols[i]=15;
        if(mode==1) { song[p++]=0xb9; song[p++]=0; song[p++]=37; }
        song[p++]=0x60;
        if(i==0 && volume!=255) song[p++]=0xc0|(vols[i]%15+1);
        song[p++]=0xd0; /* change A only; hold B/C with their previous volume */
        song[p++]=0xc0; /* rest, not a volume-zero command */
        song[p++]=0x60; /* new note retains volume, resets amplitude sliding */
    }
    memcpy(original,song,320);
    pt_end=320;
    memset(pt_pages,0,sizeof pt_pages);pt_pages[0]=0x80;pt_pages[1]=0x81;
    memset(tables,0xa5,sizeof tables); /* shared copy_buf is not zeroed */
    pt_tables(tables);
}
static int run(unsigned char version,unsigned char v,unsigned char amp,unsigned char mode) {
    unsigned i,j,index;
    unsigned char got,want,a;
    if(pt_init()) { puts("init failed"); return 1; }
    for(i=0;i<3;++i) if(notes[40*i]!=15) { puts("initial volume not 15"); return 2; }
    /* Row zero is unused: PT3 C0 disables the note, C1..CF set volume. */
    for(index=16;index<256;++index)
        if(tables[192+index]!=reference[version<'5'?0:1][index]) {
            printf("table %c index %u: %u\n",version,index,tables[192+index]); return 3;
        }
    for(j=0;j<4;++j) {
        if(pt_frame()) { puts("frame failed"); return 4; }
        pt_output();
        if(j==1 && v!=255) vols[0]=vols[0]%15+1;
        for(i=0;i<3;++i) {
            a=amp;
            index=j==3?1:j+1;
            if(mode==2) a=(amp+index>15)?15:amp+index;
            if(mode==3) a=(amp<index)?0:amp-index;
            want=j==2?0:reference[version<'5'?0:1][16*vols[i]+a];
            if(mode==1 && j!=2) want|=16;
            got=pt_regs[8+i];
            if(got!=want || emitted[8+i]!=want || notes[40*i]!=vols[i]) {
                printf("version %c volume %u amp %u mode %u frame %u channel %u: reg %u bus %u want %u state %u\n",
                       version,v,amp,mode,j,i,got,emitted[8+i],want,notes[40*i]); printf("slide %u enabled %u samplepos %u\n",notes[40*i+29],notes[40*i+3],notes[40*i+26]); return 5;
            }
        }
    }
    if(memcmp(original,song,320)) { puts("module changed"); return 6; }
    for(i=448;i<512;++i) if(tables[i]!=0xa5) { puts("table overrun"); return 7; }
    return 0;
}
int main(void) {
    unsigned char version,v,amp,mode;
    int r;
    pt_hw_start(4); /* sim65 RAM at C400 stands in for the VIA */
    for(version='3';version<='7';++version) {
        for(v=0;v<15;++v) for(amp=0;amp<16;++amp) for(mode=0;mode<4;++mode) {
            fixture(version,v,amp,mode);
            r=run(version,v,amp,mode); if(r) return r;
        }
        fixture(version,255,15,0);
        r=run(version,255,15,0); if(r) return r;
    }
    puts("ok: 4805 songs, independent A/B/C volumes, tables, slides, envelope, holds, rests, restart and VIA bytes");
    return 0;
}
'''


def reference_tables():
    text = (PLUGINS / 'pt3lib/init.inc').read_text()
    result = []
    for name in ('33_34', '35'):
        block = text.split(';PT3VolumeTable_' + name + ':', 1)[1].splitlines()[1:17]
        values = [int(v, 16) for row in block for v in re.findall(r'\$([0-9A-F]+)', row)]
        assert len(values) == 256
        result.append('{' + ','.join(map(str, values)) + '}')
    return 'static const unsigned char reference[2][256]={' + ','.join(result) + '};\n'


@unittest.skipUnless(shutil.which('cl65') and shutil.which('sim65'), 'needs cl65 and sim65')
class ChannelVolumes(unittest.TestCase):
    def test_full_decoder_and_output_on_both_cpus(self):
        with tempfile.TemporaryDirectory(prefix='pt3-volume-') as directory:
            t = Path(directory)
            (t / 'main.c').write_text(reference_tables() + HARNESS)
            for cpu in ('sim6502', 'sim65c02'):
                for converted in (False, True):
                    with self.subTest(cpu=cpu, converted=converted):
                        source = (PLUGINS / 'pt3.s').read_text().replace('PT3_LOC=$3300', 'PT3_LOC=$8000')
                        if not converted:
                            source = 'PT3_DISABLE_FREQ_CONVERSION=1\nPT3_DISABLE_ENABLE_FREQ_CONVERSION=1\n' + source
                        source = source.replace(' pla\n iny\n sta (ptr1),y\n', ' pla\n iny\n sta _emitted,x\n sta (ptr1),y\n')
                        source += '\n.export _notes, _emitted\n_notes=note_a\n.segment "BSS"\n_emitted: .res 14\n'
                        (t / 'pt3.s').write_text(source)
                        build = subprocess.run(['cl65', '-t', cpu, '-O', '--asm-include-dir', str(PLUGINS),
                                                '-o', str(t / 'prog'), str(t / 'main.c'), str(t / 'pt3.s')],
                                               capture_output=True, text=True)
                        self.assertEqual(build.returncode, 0, build.stdout + build.stderr)
                        run = subprocess.run(['sim65', str(t / 'prog')], capture_output=True, text=True, timeout=120)
                        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                        self.assertIn('ok: 4805 songs', run.stdout)


if __name__ == '__main__':
    unittest.main()
