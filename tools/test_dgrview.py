"""Run DGRVIEW's actual code: where each lo-res pixel lands in the text page.

Double lo-res is the mode whose memory is the text page, split between two
banks and two nibbles per byte, so the whole of this overlay is address
arithmetic. These tests pin that arithmetic against the Apple II layout: the
three thirds of eight rows $80 apart, the even columns in the auxiliary
bank, the low nibble above the high one.
"""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_six_plugins import PREFIX, ROOT

HARNESS = PREFIX + r'''
unsigned char host_main[1024], host_aux[1024], host_stage[3841];
unsigned char host_bank, host_shown, host_text, host_alt, host_altchar;
static unsigned char fault;
static int mock_error(FILE* f){return fault==2 || fault==4 || ferror(f);}
#define ferror mock_error
#include "src/plugins/dgrview.c"
#undef ferror
static FILE* mock_open(const char* p,const char* m){if(strcmp(m,"rb"))abort();return fault==1?NULL:fopen(p,m);}
static size_t mock_read(void* p,size_t z,size_t n,FILE* f){size_t got=fread(p,z,n,f);return fault==4?got/2:got;}
static int mock_close(FILE* f){return fclose(f) || fault==3?EOF:0;}

static char host_input[17];
static char host_note[80], host_reselect[17];
static struct Entry host_sel;
static unsigned char prompt_ok = 1;

static unsigned char mock_prompt(const char* label, const char* init, unsigned char hex)
{ (void)label; (void)init; (void)hex; return prompt_ok; }
/* The keys the viewer reads, then Escape; media_key ends on Escape only
 * (no neighbour in these tests). */
static const char* keys = "";
static unsigned int key_reads;
static char mock_cgetc(void) { ++key_reads; return *keys ? *keys++ : KEY_ESC; }
static unsigned char mock_media_key(unsigned char k) { return (k & 127) == KEY_ESC; }

int main(int argc, char** argv)
{
    static struct A2fcApi api;
    int i;
    /* argv: file type width_or_dash */
    strcpy(host_sel.name, "PIC");
    host_sel.type = (unsigned char)atoi(argv[2]);
    if (argv[3][0] == '-') prompt_ok = 0; else strcpy(host_input, argv[3]);
    if (argc > 4) host_sel.aux = (unsigned int)strtoul(argv[4], 0, 10);
    host_note[0] = 0;
    memset(host_stage, 0xA5, sizeof(host_stage)); /* stale previous file */
    if (argc > 6) keys = argv[6];
    if (argc > 7) fault=atoi(argv[7]);
    host_altchar = 0x80;                     /* the panels' alternate set */
    if (argc > 5 && atoi(argv[5])) {
        for (i = 0; i < 1024; ++i) {
            host_aux[i] = (unsigned char)(i * 3 + 1);
            host_main[i] = (unsigned char)(i * 5 + 2);
        }
    }

    api.selected = &host_sel;
    api.full = argv[1];
    api.note = host_note; api.reselect = host_reselect; api.input = host_input;
    api.fopen = mock_open; api.fread = mock_read; api.fclose = mock_close;
    api.strcpy = strcpy; api.sprintf = sprintf;
    api.version=4;api.media_wait=mock_cgetc;api.prompt = mock_prompt; api.cgetc = mock_cgetc;
    api.media_key = mock_media_key;

    plugin_entry(&api);
    printf("%u|%u|%u|%u|%u|%u|%s\n", host_shown, wide, host_text, host_alt, host_altchar,
           key_reads, host_note);
    for (i = 0; i < 1024; ++i) fputc(host_aux[i], stderr);
    for (i = 0; i < 1024; ++i) fputc(host_main[i], stderr);
    return 0;
}
'''


def row_of(r):
    """The Apple II text-page offset of byte row r, 0..23."""
    return (r & 7) * 128 + (r >> 3) * 40


HOLES = [o for o in range(1024) if o % 128 >= 120]   # the 64 screen-hole bytes


def visible(page, n=1024):
    """The visible bytes of a page among its first n, in page order."""
    return bytes(page[o] for o in range(min(n, len(page), 1024)) if o % 128 < 120)


SEED_AUX = bytes((i * 3 + 1) & 255 for i in range(1024))     # the harness's seeded banks
SEED_MAIN = bytes((i * 5 + 2) & 255 for i in range(1024))


class DgrView(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='dgrview-')
        cls.p = Path(cls.tmp.name)
        (cls.p / 'test.c').write_text(HARNESS)
        cls.exe = cls.p / 'test'
        subprocess.run(['cc', '-std=c99', '-Wno-unknown-pragmas', '-I', str(ROOT),
                        str(cls.p / 'test.c'), '-o', str(cls.exe)],
                       check=True, capture_output=True)
        cls.command=[str(cls.exe)]

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def view(self, data, ftype=6, width='--', aux=0, seeded=False, keys='', fault=0):
        """Runs the viewer on `data`; `keys` are read before Escape. The
        display state show() left (text, character set), the RDALTCHAR put
        back and the keys read land in self.state."""
        f = self.p / 'pic'
        f.write_bytes(data)
        r = subprocess.run(self.command+[str(f), str(ftype), width, str(aux), str(int(seeded)), keys,str(fault)],
                           capture_output=True, check=True)
        self.assertEqual(f.read_bytes(), data)
        self.assertEqual(len(r.stderr), 2048)
        shown, wide, text, alt, altchar, reads, note = r.stdout.decode().strip().split('|', 6)
        self.state = dict(text=int(text), alt=int(alt), altchar=int(altchar), reads=int(reads))
        return int(shown), int(wide), note, r.stderr[:1024], r.stderr[1024:2048]

    # -- whole screens ----------------------------------------------------
    def test_a_double_screen_fills_the_auxiliary_half_first(self):
        aux_half = bytes((i * 3) & 0xFF for i in range(1024))
        main_half = bytes((i * 5 + 1) & 0xFF for i in range(1024))
        shown, wide, note, aux, main = self.view(aux_half + main_half, seeded=True)
        self.assertEqual((shown, wide), (1, 1))
        self.assertIn('80 x 48', note)
        self.assertEqual(visible(aux), visible(aux_half))
        self.assertEqual(visible(main), visible(main_half))
        # The screen holes hold the cards' and the firmware's state, not the
        # file's leftovers: neither bank's is written.
        self.assertEqual([aux[o] for o in HOLES], [SEED_AUX[o] for o in HOLES])
        self.assertEqual([main[o] for o in HOLES], [SEED_MAIN[o] for o in HOLES])

    def test_a_single_screen_is_forty_columns_in_the_main_half(self):
        page = bytes((i * 7) & 0xFF for i in range(1024))
        shown, wide, note, aux, main = self.view(page, seeded=True)
        self.assertEqual((shown, wide), (1, 0))
        self.assertIn('40 x 48', note)
        self.assertEqual(visible(main), visible(page))
        self.assertEqual([main[o] for o in HOLES], [SEED_MAIN[o] for o in HOLES])
        self.assertEqual(aux, SEED_AUX)             # untouched: 80COL is off

    def test_too_big_is_refused(self):
        shown, _, note, _, _ = self.view(bytes(3841))
        self.assertEqual(shown, 0)
        self.assertIn('3840', note)

    def test_an_empty_file_is_refused(self):
        shown, _, note, _, _ = self.view(b'')
        self.assertEqual(shown, 0)
        self.assertIn('Empty', note)

    def test_a_directory_is_refused(self):
        shown, _, note, _, _ = self.view(bytes(1024), ftype=0x0F)
        self.assertEqual(shown, 0)
        self.assertIn('Select', note)

    # -- a2dgrx pixmaps ---------------------------------------------------
    def pixel(self, aux, main, x, y):
        """The colour of double lo-res pixel (x, y), read back out of the two
        halves the way the hardware would."""
        page = aux if not (x & 1) else main
        b = page[row_of(y >> 1) + (x >> 1)]
        return (b >> 4) if (y & 1) else (b & 0x0F)

    def test_a_pixmap_lands_where_its_mask_says(self):
        """4x2, the second row transparent. Its colour nibbles are NOT zero:
        a transparent pixel painted anyway would show, which is the whole
        point of the mask, and zeros would have hidden the mistake."""
        data = bytes([0xF1, 0xF2, 0xF3, 0xF4,
                      0x07, 0x08, 0x09, 0x0A])
        shown, wide, note, aux, main = self.view(data, width='04')
        self.assertEqual((shown, wide), (1, 1))
        self.assertIn('4 x 2', note)
        x0, y0 = (80 - 4) // 2, (48 - 2) // 2
        for i in range(4):
            self.assertEqual(self.pixel(aux, main, x0 + i, y0), i + 1)
            self.assertEqual(self.pixel(aux, main, x0 + i, y0 + 1), 0)  # masked out
        # and nothing else on the screen was painted
        lit = [(x, y) for y in range(48) for x in range(80)
               if self.pixel(aux, main, x, y)]
        self.assertEqual(lit, [(x0 + i, y0) for i in range(4)])

    def test_both_banks_and_both_nibbles_are_reached(self):
        """A 2x2 block proves the even/odd bank split and the low/high nibble
        split at once."""
        data = bytes([0xF5, 0xF6, 0xF7, 0xF8])
        shown, _, _, aux, main = self.view(data, width='02')
        x0, y0 = (80 - 2) // 2, (48 - 2) // 2
        self.assertEqual(self.pixel(aux, main, x0, y0), 5)
        self.assertEqual(self.pixel(aux, main, x0 + 1, y0), 6)
        self.assertEqual(self.pixel(aux, main, x0, y0 + 1), 7)
        self.assertEqual(self.pixel(aux, main, x0 + 1, y0 + 1), 8)
        self.assertNotEqual(x0 & 1, (x0 + 1) & 1)    # the two really differ in bank

    def test_zoom_pixels_masks_bounds_holes_and_reset(self):
        for w,h in ((4,2),(20,12),(21,12),(40,24),(41,24),(80,48),(1,1)):
            data=bytes((0xF0 if (x+y)%3 else 0)|((x+y)%15+1) for y in range(h) for x in range(w))
            for keys in ('','Z','ZZ','ZZZ','zzzz'):
                scale=1
                for key in keys:
                    nxt=scale*2;scale=nxt if nxt<=4 and w*nxt<=80 and h*nxt<=48 else 1
                shown,_,note,aux,main=self.view(data,width=f'{w:02X}',seeded=True,keys=keys)
                self.assertEqual(shown,1);self.assertIn(f'x{scale}. Z:',note)
                x0=(80-w*scale)//2;y0=(48-h*scale)//2
                for y in range(48):
                    for x in range(80):
                        want=0
                        if x0<=x<x0+w*scale and y0<=y<y0+h*scale:
                            b=data[((y-y0)//scale)*w+(x-x0)//scale];want=b&15 if b&0xF0 else 0
                        self.assertEqual(self.pixel(aux,main,x,y),want)
                self.assertEqual(bytes(aux[o] for o in HOLES),bytes(SEED_AUX[o] for o in HOLES))
                self.assertEqual(bytes(main[o] for o in HOLES),bytes(SEED_MAIN[o] for o in HOLES))
        # Z belongs to pixmaps; DGR headers and saved pages retain their modes.
        for data,meta in ((b'DGR\1\x28\x30\0\0'+bytes([0x55])*960,0),(bytes([0x55])*1024,0x400)):
            before=self.view(data,aux=meta,seeded=True)
            self.assertEqual(self.view(data,aux=meta,seeded=True,keys='ZZZ'),before)

    def test_checkerboard_transparency_black_zoom_toggle_and_holes(self):
        for w,h in ((1,1),(4,2),(20,12),(80,48)):
            data=bytes((0xF0 if (x+y)%3 else 0)|((x+3*y)%16) for y in range(h) for x in range(w))
            for keys in ('C','cZ','CZCZ','CZZ','CC','ZCCZ','CZZZC'):
                scale=1;check=False
                for key in keys.upper():
                    if key=='C':check=not check
                    else:
                        nxt=scale*2;scale=nxt if nxt<=4 and w*nxt<=80 and h*nxt<=48 else 1
                shown,_,note,aux,main=self.view(data,width=f'{w:02X}',seeded=True,keys=keys)
                self.assertEqual(shown,1);self.assertIn('C: grid',note)
                x0=(80-w*scale)//2;y0=(48-h*scale)//2
                for y in range(48):
                    for x in range(80):
                        want=(15 if ((x//4+y//4)%2) else 5) if check else 0
                        if x0<=x<x0+w*scale and y0<=y<y0+h*scale:
                            b=data[((y-y0)//scale)*w+(x-x0)//scale]
                            if b&0xF0:want=b&15
                        self.assertEqual(self.pixel(aux,main,x,y),want)
                for page,seed in ((aux,SEED_AUX),(main,SEED_MAIN)):
                    self.assertEqual(bytes(page[o] for o in HOLES),bytes(seed[o] for o in HOLES))
        for data,meta in ((b'DGR\1\x28\x30\0\0'+bytes([0x55])*960,0),(bytes([0x55])*1024,0x400)):
            self.assertEqual(self.view(data,aux=meta,seeded=True,keys='CZC'),self.view(data,aux=meta,seeded=True))

    def test_mask_preview_zoom_background_restoration_and_holes(self):
        for w,h in ((1,1),(4,2),(20,12),(80,48)):
            # Every high-nibble value is exercised; low nibbles include black.
            data=bytes(((i%16)<<4)|((i*7+3)%16) for i in range(w*h))
            for keys in ('M','mZ','CM','CMZZ','CMZZM','MCMM','MM','MZMC','MCMZZM'):
                scale=1;check=mask=False
                for key in keys.upper():
                    if key=='C':check=not check
                    elif key=='M':mask=not mask
                    else:
                        nxt=scale*2;scale=nxt if nxt<=4 and w*nxt<=80 and h*nxt<=48 else 1
                shown,_,note,aux,main=self.view(data,width=f'{w:02X}',seeded=True,keys=keys)
                self.assertEqual(shown,1);self.assertIn('M: mask',note)
                x0=(80-w*scale)//2;y0=(48-h*scale)//2
                for y in range(48):
                    for x in range(80):
                        want=(15 if (x//4+y//4)%2 else 5) if check and not mask else 0
                        if x0<=x<x0+w*scale and y0<=y<y0+h*scale:
                            b=data[((y-y0)//scale)*w+(x-x0)//scale]
                            if b&0xF0:want=15 if mask else b&15
                        self.assertEqual(self.pixel(aux,main,x,y),want)
                for page,seed in ((aux,SEED_AUX),(main,SEED_MAIN)):
                    self.assertEqual(bytes(page[o] for o in HOLES),bytes(seed[o] for o in HOLES))
        for data,meta in ((b'DGR\1\x28\x30\0\0'+bytes([0x55])*960,0),(bytes([0x55])*1024,0x400)):
            self.assertEqual(self.view(data,aux=meta,seeded=True,keys='MCZM'),self.view(data,aux=meta,seeded=True))

    def test_sprite_mirrors_colors_masks_zoom_holes_and_restore(self):
        for w,h in ((1,1),(5,3),(20,12),(80,48)):
            data=bytes(((i%16)<<4)|((i*7+3)%16) for i in range(w*h))
            for keys in ('H','v','HV','HHVV','HZ','VZZ','CHVMZ','CHVZZM','MHHCCVV','hvzmcHV'):
                scale=1;check=mask=hflip=vflip=False
                for key in keys.upper():
                    if key=='C':check=not check
                    elif key=='M':mask=not mask
                    elif key=='H':hflip=not hflip
                    elif key=='V':vflip=not vflip
                    else:
                        nxt=scale*2;scale=nxt if nxt<=4 and w*nxt<=80 and h*nxt<=48 else 1
                shown,_,note,aux,main=self.view(data,width=f'{w:02X}',seeded=True,keys=keys)
                self.assertEqual(shown,1);self.assertIn('H/V: flip',note)
                self.assertLess(len(note),80)
                x0=(80-w*scale)//2;y0=(48-h*scale)//2
                for y in range(48):
                    for x in range(80):
                        want=(15 if (x//4+y//4)%2 else 5) if check and not mask else 0
                        if x0<=x<x0+w*scale and y0<=y<y0+h*scale:
                            sx=(x-x0)//scale;sy=(y-y0)//scale
                            if hflip:sx=w-1-sx
                            if vflip:sy=h-1-sy
                            b=data[sy*w+sx]
                            if b&0xF0:want=15 if mask else b&15
                        self.assertEqual(self.pixel(aux,main,x,y),want)
                for page,seed in ((aux,SEED_AUX),(main,SEED_MAIN)):
                    self.assertEqual(bytes(page[o] for o in HOLES),bytes(seed[o] for o in HOLES))
        for data,meta in ((b'DGR\1\x28\x30\0\0'+bytes([0x55])*960,0),(bytes([0x55])*1024,0x400)):
            self.assertEqual(self.view(data,aux=meta,seeded=True,keys='HV'),self.view(data,aux=meta,seeded=True))

    def test_rotation_pixels_zoom_mirrors_masks_bounds_and_reset(self):
        for w,h in ((1,1),(5,3),(20,12),(40,24),(48,1),(49,1),(80,48)):
            data=bytes(((i%16)<<4)|((i*7+3)%16) for i in range(w*h))
            for keys in ('O','oo','OOO','OOOO','ZO','ZZO','OF','OZ','OH','HO',
                         'VO','OV','CHVMZO','OOHOVMZC','CHVMZOR','OOOOF'):
                rows=[list(data[y*w:(y+1)*w]) for y in range(h)]
                scale=1;check=mask=False
                for key in keys.upper():
                    dw,dh=len(rows[0]),len(rows)
                    if key=='O':
                        if dw>48:continue
                        rows=[list(row) for row in zip(*rows[::-1])]
                        while len(rows[0])*scale>80 or len(rows)*scale>48:scale//=2
                    elif key=='H':rows=[row[::-1] for row in rows]
                    elif key=='V':rows=rows[::-1]
                    elif key=='C':check=not check
                    elif key=='M':mask=not mask
                    elif key=='R':
                        rows=[list(data[y*w:(y+1)*w]) for y in range(h)]
                        scale=1;check=mask=False
                    elif key=='Z':
                        nxt=scale*2
                        scale=nxt if nxt<=4 and dw*nxt<=80 and dh*nxt<=48 else 1
                    elif key=='F':
                        scale=4
                        while dw*scale>80 or dh*scale>48:scale//=2
                dw,dh=len(rows[0]),len(rows)
                shown,_,note,aux,main=self.view(data,width=f'{w:02X}',seeded=True,keys=keys)
                self.assertEqual(shown,1);self.assertIn('O: turn',note)
                self.assertIn(f'{dw} x {dh} x{scale}. Z:',note);self.assertLess(len(note),80)
                x0=(80-dw*scale)//2;y0=(48-dh*scale)//2
                for y in range(48):
                    for x in range(80):
                        want=(15 if (x//4+y//4)%2 else 5) if check and not mask else 0
                        if x0<=x<x0+dw*scale and y0<=y<y0+dh*scale:
                            b=rows[(y-y0)//scale][(x-x0)//scale]
                            if b&0xF0:want=15 if mask else b&15
                        self.assertEqual(self.pixel(aux,main,x,y),want,(w,h,keys,x,y))
                for page,seed in ((aux,SEED_AUX),(main,SEED_MAIN)):
                    self.assertEqual(bytes(page[o] for o in HOLES),bytes(seed[o] for o in HOLES))

    def test_rotation_refusal_and_other_formats_preserve_display(self):
        for w,h in ((49,1),(80,48)):
            data=bytes((i*7+0xF0)&255 for i in range(w*h))
            for prefix in ('','F','CHVM'):
                self.assertEqual(self.view(data,width=f'{w:02X}',seeded=True,keys=prefix+'Oooo'),
                                 self.view(data,width=f'{w:02X}',seeded=True,keys=prefix))
        for data,meta in ((b'DGR\1\x28\x30\0\0'+bytes([0x55])*960,0),
                          (bytes([0x55])*1024,0x400),(self.text_page(),0x400)):
            self.assertEqual(self.view(data,aux=meta,seeded=True,keys='Oo'),self.view(data,aux=meta,seeded=True))

    def test_fit_selects_maximum_zoom_and_preserves_options(self):
        for w,h,steps in ((1,1,2),(20,12,2),(21,12,1),(20,13,1),(40,24,1),
                          (41,24,0),(40,25,0),(80,48,0)):
            data=bytes(((i%16)<<4)|((i*7+3)%16) for i in range(w*h))
            for prefix in ('','C','M','CHV','CHVM'):
                expected=self.view(data,width=f'{w:02X}',seeded=True,keys=prefix+'Z'*steps)
                for keys in (prefix+'F',prefix+'ff',prefix+'ZF',prefix+'ZZf'):
                    self.assertEqual(self.view(data,width=f'{w:02X}',seeded=True,keys=keys),expected)
                self.assertIn('F: fit',expected[2]);self.assertLess(len(expected[2]),80)
                # Z wraps to x1 after fit; R clears the retained options.
                self.assertEqual(self.view(data,width=f'{w:02X}',seeded=True,keys=prefix+'FZ'),
                                 self.view(data,width=f'{w:02X}',seeded=True,keys=prefix))
                self.assertEqual(self.view(data,width=f'{w:02X}',seeded=True,keys=prefix+'FR'),
                                 self.view(data,width=f'{w:02X}',seeded=True))
        for data,meta in ((b'DGR\1\x28\x30\0\0'+bytes([0x55])*960,0),
                          (bytes([0x55])*1024,0x400),(self.text_page(),0x400)):
            self.assertEqual(self.view(data,aux=meta,seeded=True,keys='Ff'),self.view(data,aux=meta,seeded=True))

    def test_reset_restores_original_pixels_and_options(self):
        for w,h in ((1,1),(5,3),(20,12),(80,48)):
            data=bytes(((i%16)<<4)|((i*7+3)%16) for i in range(w*h))
            original=self.view(data,width=f'{w:02X}',seeded=True)
            for keys in ('R','r','RR','ZCHVMR','ZZCHVMr','hvzmcrR'):
                self.assertEqual(self.view(data,width=f'{w:02X}',seeded=True,keys=keys),original)
                self.assertIn('R: reset',original[2])
                self.assertLess(len(original[2]),80)
            # Each option must start from its default after reset.
            for key in 'ZCMHV':
                self.assertEqual(self.view(data,width=f'{w:02X}',seeded=True,keys='ZZCHVMR'+key),
                                 self.view(data,width=f'{w:02X}',seeded=True,keys=key))
        for data,meta in ((b'DGR\1\x28\x30\0\0'+bytes([0x55])*960,0),
                          (bytes([0x55])*1024,0x400),(self.text_page(),0x400)):
            self.assertEqual(self.view(data,aux=meta,seeded=True,keys='Rr'),self.view(data,aux=meta,seeded=True))

    def test_the_widest_pixmap_reaches_both_edges(self):
        """A complete 80x48 pixmap reaches all four edges and both banks."""
        data = bytes([0xF9] * (80 * 48))
        shown, _, note, aux, main = self.view(data, width='50')     # $50 = 80
        self.assertEqual(shown, 1)
        self.assertIn('80 x 48', note)
        y0 = 0
        self.assertEqual(self.pixel(aux, main, 0, y0), 9)           # left, aux bank
        self.assertEqual(self.pixel(aux, main, 79, 47), 9)
        lit = sum(1 for y in range(48) for x in range(80) if self.pixel(aux, main, x, y))
        self.assertEqual(lit, 80 * 48)

    def test_a_pixmap_over_3840_bytes_is_refused(self):
        shown, _, note, aux, main = self.view(bytes([0xF1] * 3841), width='50',seeded=True)
        self.assertEqual(shown, 0)
        self.assertIn('3840', note);self.assertEqual((aux,main),(SEED_AUX,SEED_MAIN))

    def test_read_close_errors_and_oversized_saved_pages_preserve_banks(self):
        for data,meta in ((b'DGR\1\x50\x30\1\0'+bytes(1920),0),(bytes(2048),0x400),(bytes([0xF9])*3840,0)):
            for fault in (1,2,3,4):
                shown,_,note,aux,main=self.view(data,width='50',aux=meta,seeded=True,keys='OFZ',fault=fault)
                self.assertEqual(shown,0);self.assertTrue(note);self.assertEqual((aux,main),(SEED_AUX,SEED_MAIN))
        shown,_,note,aux,main=self.view(bytes(3000),aux=0x400,seeded=True)
        self.assertEqual(shown,0);self.assertIn('2048',note);self.assertEqual((aux,main),(SEED_AUX,SEED_MAIN))

    def test_a_width_that_does_not_divide_is_refused(self):
        shown, _, note, _, _ = self.view(bytes([0xF1] * 100), width='07')
        self.assertEqual(shown, 0)
        self.assertIn('Invalid sprite', note)

    def test_a_width_over_eighty_is_refused(self):
        shown, _, note, _, _ = self.view(bytes([0xF1] * 81), width='51')
        self.assertEqual(shown, 0)

    def test_a_pixmap_taller_than_the_screen_is_refused(self):
        shown, _, note, _, _ = self.view(bytes([0xF1] * (2 * 49)), width='02')
        self.assertEqual(shown, 0)
        self.assertIn('Invalid sprite', note)

    def test_declining_the_width_shows_nothing(self):
        shown, _, _, aux, main = self.view(bytes([0xF1] * 12), width='-')
        self.assertEqual(shown, 0)
        self.assertEqual(sum(aux) + sum(main), 0)

    def test_auxtype_0400_is_what_says_lo_res(self):
        """bmp2dhr writes .SLO at 962 bytes, not 1024: an equality test on the
        size would refuse the very files this is for."""
        page = bytes((i * 11 + 3) & 0xFF for i in range(962))
        shown, wide, note, aux, main = self.view(page, aux=0x0400, seeded=True)
        self.assertEqual((shown, wide), (1, 0))
        self.assertIn('40 x 48', note)
        self.assertEqual(visible(main, 962), visible(page))
        # the rest stays black, the holes as they were
        self.assertEqual(visible(main)[len(visible(page)):], bytes(960 - len(visible(page))))
        self.assertEqual([main[o] for o in HOLES], [SEED_MAIN[o] for o in HOLES])

    def test_a_double_file_of_an_odd_size_splits_in_two(self):
        """.DLO is 1,922 bytes: two halves of 961."""
        d = bytes((i * 13 + 7) & 0xFF for i in range(1922))
        shown, wide, note, aux, main = self.view(d, aux=0x0400)
        self.assertEqual((shown, wide), (1, 1))
        self.assertIn('80 x 48', note)
        self.assertEqual(visible(aux, 961), visible(d[:961]))
        self.assertEqual(visible(main, 961), visible(d[961:]))

    def test_the_proposed_header_says_what_the_file_is(self):
        """'DGR' 1, width, height, flags -- rows of forty bytes with no screen
        holes, so each row lands at its own address."""
        lines = 24
        auxhalf = bytes((i * 3 + 1) & 0xFF for i in range(40 * lines))
        mainhalf = bytes((i * 5 + 2) & 0xFF for i in range(40 * lines))
        hdr = bytes([ord('D'), ord('G'), ord('R'), 1, 80, 48, 1, 0])
        shown, wide, note, aux, main = self.view(hdr + auxhalf + mainhalf)
        self.assertEqual((shown, wide), (1, 1))
        self.assertIn('80 x 48', note)
        for r in range(lines):
            at = row_of(r)
            self.assertEqual(aux[at:at + 40], auxhalf[r * 40:(r + 1) * 40])
            self.assertEqual(main[at:at + 40], mainhalf[r * 40:(r + 1) * 40])
        # the screen holes are left alone, which is the point of the format:
        # rows 0, 8 and 16 fill offsets 0-119 and 120-127 is the first hole
        self.assertEqual(aux[120:128], bytes(8))
        self.assertEqual(main[120:128], bytes(8))

    def test_the_proposed_header_single_half(self):
        lines = 24
        onehalf = bytes((i * 7 + 4) & 0xFF for i in range(40 * lines))
        hdr = bytes([ord('D'), ord('G'), ord('R'), 1, 40, 48, 0, 0])
        shown, wide, note, aux, main = self.view(hdr + onehalf)
        self.assertEqual((shown, wide), (1, 0))
        self.assertIn('40 x 48', note)
        self.assertEqual(main[row_of(23):row_of(23) + 40], onehalf[23 * 40:24 * 40])
        self.assertEqual(aux, bytes(1024))

    def test_a_header_asking_for_more_than_the_screen_is_refused(self):
        hdr = bytes([ord('D'), ord('G'), ord('R'), 1, 200, 48, 1, 0])
        shown, _, note, _, _ = self.view(hdr + bytes(1920))
        self.assertEqual(shown, 0)
        self.assertIn('Invalid or truncated', note)

    def assert_seeded_banks(self, aux, main):
        self.assertEqual(aux, bytes((i * 3 + 1) & 255 for i in range(1024)))
        self.assertEqual(main, bytes((i * 5 + 2) & 255 for i in range(1024)))

    def test_sprite_height_boundary(self):
        shown, _, note, aux, main = self.view(bytes([0xF1]) * 48, width='01')
        self.assertEqual(shown, 1)
        self.assertIn('1 x 48', note)
        for y in range(48):
            self.assertEqual(self.pixel(aux, main, 39, y), 1)
        shown, _, note, aux, main = self.view(bytes([0xF1]) * 49,
                                             width='01', seeded=True)
        self.assertEqual(shown, 0)
        self.assert_seeded_banks(aux, main)

    def test_extra_payload_is_refused(self):
        data = b'DGR\x01\x28\x30\0\0' + bytes(961)
        shown, _, note, aux, main = self.view(data, seeded=True)
        self.assertEqual(shown, 0)
        self.assertIn('Invalid or truncated', note)
        self.assert_seeded_banks(aux, main)

    def test_truncated_header_and_payload_never_touch_screen_banks(self):
        data = b'DGR\x01\x50\x30\x01\0' + bytes([0x55]) * 1920
        for cut in (*range(3, 10), 255, 968, 1024, 1927):
            with self.subTest(cut=cut):
                shown, _, note, aux, main = self.view(data[:cut], width='01', seeded=True)
                self.assertEqual(shown, 0)
                self.assertIn('Invalid or truncated', note)
                self.assert_seeded_banks(aux, main)

    def test_invalid_header_fields_are_not_interpreted_as_sprites(self):
        data = bytearray(b'DGR\x01\x50\x30\x01\0' + bytes(1920))
        for at, value in ((3, 2), (4, 0), (4, 40), (5, 0), (5, 47), (6, 2), (7, 1)):
            with self.subTest(at=at, value=value):
                mutated = data.copy(); mutated[at] = value
                shown, _, note, aux, main = self.view(mutated, width='01', seeded=True)
                self.assertEqual(shown, 0)
                self.assert_seeded_banks(aux, main)

    def test_sprite_height_is_checked_before_narrowing_to_a_byte(self):
        for size, width in ((255, '01'), (256, '01'), (257, '01'), (304, '01'),
                            (305, '01'), (1536, '03')):
            with self.subTest(size=size):
                shown, _, note, aux, main = self.view(bytes([0xF1]) * size, width=width, seeded=True)
                self.assertEqual(shown, 0)
                self.assertIn('Invalid sprite', note)
                self.assert_seeded_banks(aux, main)

    # -- text screens (2026-10-04) ------------------------------------------
    def text_page(self, line=b'A TITLE SCREEN SAVED FROM $0400'):
        page = bytearray([0xA0]) * 1024
        page[row_of(2):row_of(2) + len(line)] = bytes(c | 0x80 for c in line)
        return bytes(page)

    def test_a_text_page_is_shown_as_text(self):
        shown, wide, note, aux, main = self.view(self.text_page(), aux=0x0400, seeded=True)
        self.assertEqual((shown, wide), (1, 0))
        self.assertEqual((self.state['text'], self.state['alt']), (1, 0))   # the II's primary set
        self.assertIn('Text screen, 40 columns', note)
        self.assertEqual(visible(main), visible(self.text_page()))
        self.assertEqual([main[o] for o in HOLES], [SEED_MAIN[o] for o in HOLES])
        self.assertEqual(self.state['altchar'], 0x80)      # the panels' set put back

    def test_eighty_columns_of_text_use_the_alternate_set(self):
        self.view(self.text_page() * 2, aux=0x0400)
        self.assertEqual((self.state['text'], self.state['alt']), (1, 1))

    def test_t_turns_the_guess_round_and_a_switches_the_set(self):
        _, _, note, _, _ = self.view(self.text_page(), aux=0x0400, keys='aT')
        self.assertEqual((self.state['text'], self.state['alt'], self.state['reads']), (0, 1, 3))
        self.assertIn('Lo-res screen', note)
        _, _, note, _, _ = self.view(bytes([0x55]) * 1024, keys='at')   # A means nothing in lo-res
        self.assertEqual((self.state['text'], self.state['alt']), (1, 0))
        self.assertIn('Text screen', note)

    def test_t_is_ignored_where_the_file_says_lo_res(self):
        hdr = b'DGR\x01\x28\x30\x00\x00' + bytes([0xA0]) * 960
        _, _, note, _, _ = self.view(hdr, keys='TA')
        self.assertEqual(self.state['text'], 0)
        self.assertIn('Lo-res screen, 40 x 48', note)

    def test_a_small_file_without_the_auxtype_is_still_a_pixmap(self):
        """The auxtype is what distinguishes a short screen from a sprite."""
        shown, _, note, _, _ = self.view(bytes([0xF1] * 12), width='04')
        self.assertEqual(shown, 1)
        self.assertIn('pixmap', note)

    def test_both_cpus_actual_reader(self):
        if not shutil.which('cl65') or not shutil.which('sim65'):self.skipTest('cc65 unavailable')
        path=Path(subprocess.check_output(['cl65','--print-target-path'],text=True).strip())
        for cpu,target in (('6502','sim6502'),('65c02','sim65c02')):
            cfg=self.p/(target+'.cfg');cfg.write_text((path.parent/'cfg'/(target+'.cfg')).read_text().replace('\n    CODE:','\n    OVLHDR: load = MAIN, type = ro;\n    CODE:',1))
            exe=self.p/target
            subprocess.run(['cl65','-t',target,'--cpu',cpu,'-Oirs','-Cl','-C',str(cfg),'-I',str(ROOT),str(self.p/'test.c'),'-o',str(exe)],check=True,capture_output=True)
            self.command=['sim65',str(exe)]
            try:
                for name in sorted(dir(self)):
                    if name.startswith('test_') and name!='test_both_cpus_actual_reader':getattr(self,name)()
            finally:self.command=[str(self.exe)]


if __name__ == '__main__':
    unittest.main()
