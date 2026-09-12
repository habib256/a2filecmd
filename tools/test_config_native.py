"""Run the actual fixed-address preference parser as optimized 6502 code.

Host C cannot catch cc65's incorrect pointer-low-byte elimination on indexed
fields of an absolute struct. Exercise the parser with its native layout.
"""
import os,shutil,subprocess,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
class NativeConfig(unittest.TestCase):
 def test_fixed_address_parser(self):
  source=(ROOT/'src/config.h').read_text()
  struct=source[source.index('struct ConfigState'):source.index('static const char cfg_format')]
  parser=source[source.index('static unsigned char cfg_parse'):source.index('static unsigned char cfg_verify')]
  code='''#include <string.h>
#define PATH_LEN 64
#define SORT_MODES 3
#define CONFIG_STATE ((struct ConfigState*)0x6000)
static struct {char path[64];} panels[2];
static unsigned char active,sort_mode;
'''+struct+parser+'''
int main(void){
 const char* good="/LEFT\\r/RIGHT\\rS2A1\\r";
 unsigned int i;
 strcpy(CF->read,good);CF->size=strlen(good);
 if(!cfg_parse(1)||strcmp(panels[0].path,"/LEFT")||strcmp(panels[1].path,"/RIGHT")||sort_mode!=2||active!=1)return 1;
 for(i=0;i<strlen(good);++i){strcpy(CF->read,good);CF->size=i;if(cfg_parse(1))return 2;}
 if(strcmp(panels[0].path,"/LEFT")||strcmp(panels[1].path,"/RIGHT"))return 3;
 strcpy(CF->read,"\\r\\rS0A0\\r");CF->size=7;if(!cfg_parse(1)||panels[0].path[0]||panels[1].path[0])return 4;
 return 0;
}
'''
  compilers=[(shutil.which('cl65'),{})]
  head=Path.home()/'opt/cc65-head'
  if (head/'bin/cl65').exists():compilers.append((str(head/'bin/cl65'),{'CC65_HOME':str(head/'share/cc65')}))
  with tempfile.TemporaryDirectory(prefix='cfg-sim-') as t:
   t=Path(t);p=t/'test.c';p.write_text(code)
   for compiler,env in compilers:
    with self.subTest(compiler=compiler):
     subprocess.run([compiler,'-t','sim6502','-O','-Oirs','-Cl','--codesize','100','-o',str(t/'test'),str(p)],check=True,capture_output=True,env={**os.environ,**env})
     subprocess.run([shutil.which('sim65'),str(t/'test')],check=True,timeout=10)
if __name__=='__main__':unittest.main()
