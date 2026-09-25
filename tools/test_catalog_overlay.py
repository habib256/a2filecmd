"""A DOS 3.3 catalog or disk-image directory read must never reload the
overlay window while another overlay's code is still on the return stack:
the read is deferred and the main loop settles it."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_file_safety import SOURCE, section

HARNESS = r'''
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
struct Entry {char name[17];};
struct Panel {unsigned char count,more,tags[18];struct Entry*e;};
static struct Panel panels[2];
#define pan_at(p) (&panels[p])   /* the resident helper: the same address */
static unsigned char in_overlay,panel_stale,reselect_panel,load_ok=1,read_ok=1;
static char reselect[17];static unsigned selects;
static void select_name(struct Panel* p,const char* n){++selects;}
static unsigned loads,reads,draws[2],status,info,panel_reads[2];
static const char* loaded;
static unsigned char load_overlay(const char* n,unsigned char any){++loads;loaded=n;if(load_ok)in_overlay=1;return load_ok;}
#define overlay(name) load_overlay(name, 0)
/* The overlay is in place while its reader runs: in_overlay must be set. */
static unsigned char read_dos33_panel(struct Panel* p){++reads;if(!in_overlay)return 99;p->count=7;return read_ok;}
static unsigned char read_image_dir(struct Panel* p){++reads;if(!in_overlay)return 99;p->count=6;return read_ok;}
''' + section('static unsigned char defer_panel(struct Panel* pan)\n{', 'static struct A2fcApi api;') + r'''
static unsigned char read_panel(unsigned char p){++panel_reads[p];panels[p].count=5;return 1;}
static void draw_panel(unsigned char p){++draws[p];}
static void draw_status(void){++status;}
static void draw_info(void){++info;}
''' + section('static void settle_panels(void)\n{', '/* Reads a directory into pool[base..]') + r'''
int main(int argc,char**argv){
 int scenario=atoi(argv[1]);
 panels[0].count=3;panels[1].count=4;panels[1].more=1;memset(panels[1].tags,0xFF,18);
 if(scenario==1){ /* overlay code on the stack: no load, an empty marked panel, reread once settled */
  in_overlay=1;
  if(read_dos33_overlay(&panels[1])!=1||loads||reads||panel_stale!=2||panels[1].count||panels[1].more||panels[1].tags[0]||panels[1].tags[17])return 1;
  if(!in_overlay||panels[0].count!=3)return 2;
  strcpy(reselect,"NAME");reselect_panel=0;   /* a name wanted in the OTHER panel is not applied here */
  settle_panels();
  if(in_overlay||panel_stale||panel_reads[0]||panel_reads[1]!=1||draws[0]||draws[1]!=1||status!=1||info!=1||selects||strcmp(reselect,"NAME"))return 3;
  reselect_panel=1;in_overlay=1;read_dos33_overlay(&panels[1]);settle_panels();
  if(selects!=1||reselect[0])return 4;   /* NAV's name lands in the settled panel, once */
  return 0;
 }
 if(scenario==2){ /* free window: CATALOG loaded, catalog read, context released; nothing to settle */
  if(read_dos33_overlay(&panels[0])!=1||loads!=1||strcmp(loaded,"CATALOG")||reads!=1||panels[0].count!=7||in_overlay||panel_stale)return 1;
  settle_panels();
  if(panel_reads[0]||panel_reads[1]||draws[0]||draws[1]||status||info)return 2;
  return 0;
 }
 if(scenario==3){ /* overlay missing or stale: no catalog read, failure, context released */
  load_ok=0;
  if(read_dos33_overlay(&panels[0])||reads||in_overlay||panel_stale)return 1;
  return 0;
 }
 if(scenario==4){ /* not a DOS 3.3 volume: failure reported, context released */
  read_ok=0;
  if(read_dos33_overlay(&panels[0])||reads!=1||in_overlay||panel_stale)return 1;
  return 0;
 }
 if(scenario==5){ /* image directory, overlay code on the stack: deferred like a DOS catalog */
  in_overlay=1;
  if(read_image_dir_overlay(&panels[0])!=1||loads||reads||panel_stale!=1||panels[0].count||!in_overlay)return 1;
  settle_panels();
  if(in_overlay||panel_stale||panel_reads[0]!=1||panel_reads[1]||draws[0]!=1||draws[1])return 2;
  return 0;
 }
 if(scenario==6){ /* image directory, free window: CATALOG loaded, walked, context released */
  if(read_image_dir_overlay(&panels[1])!=1||loads!=1||strcmp(loaded,"CATALOG")||reads!=1||panels[1].count!=6||in_overlay||panel_stale)return 1;
  return 0;
 }
 if(scenario==7){ /* image directory: a refused load reads nothing; "not a directory" (2) passes through */
  load_ok=0;
  if(read_image_dir_overlay(&panels[0])||reads||in_overlay)return 1;
  load_ok=1;read_ok=2;
  if(read_image_dir_overlay(&panels[0])!=2||reads!=1||in_overlay||panel_stale)return 2;
  return 0;
 }
 return 9;
}
'''


class CatalogOverlay(unittest.TestCase):
    def test_deferred_and_direct_reads(self):
        with tempfile.TemporaryDirectory(prefix='catalog-overlay-') as d:
            p = Path(d)
            (p / 'test.c').write_text(HARNESS)
            subprocess.run(['cc', '-std=c99', '-fsanitize=address,undefined', str(p / 'test.c'), '-o', str(p / 'test')], check=True, capture_output=True)
            for scenario in '1234567':
                self.assertEqual(subprocess.run([str(p / 'test'), scenario]).returncode, 0, 'scenario ' + scenario)


if __name__ == '__main__':
    unittest.main()
