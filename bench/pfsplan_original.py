#!/usr/bin/env python3
"""Compare COSTS visible numeric cells with the original PFS:Plan program.
Disposable disk only, normal keyboard input, source sheets byte-preserved.
Scope: seven visible rows and six columns, not all sheets or typography.
"""
import sys,os,tempfile,time,subprocess,json,re,hashlib
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1]/'tools')]
from pom2 import Pom2,ROOT
from corpus_read import files
from test_pfsplan import PfsPlan,originals
root=Path(os.environ.get('A2FC_PFS_CORPUS','/tmp/a2fc-pfs-corpus'))
docs=dict(originals());PfsPlan.setUpClass()
try:rows,_,_=PfsPlan().run_file(docs['/COSTS.PFS'])
finally:PfsPlan.tearDownClass()
with tempfile.TemporaryDirectory(prefix='pfsplan-original-') as tmp:
 tmp=Path(tmp);stage=tmp/'stage';stage.mkdir()
 for n,t,a,d in files((root/'images/productivity/integrated/pfs/PFS Plan.po').read_bytes())[1]:(stage/(n[1:]+'#%02X%04X'%(t,a))).write_bytes(d)
 hd=tmp/'plan.hdv';subprocess.run([sys.executable,str(ROOT/'tools/mkvolume.py'),str(stage),str(hd),'--volume','PFSPLAN','--boot',str(ROOT/'data/prodos_boot.tmpl'),'--blocks','1600'],check=True,capture_output=True)
 with Pom2(hd,port=6955+int(os.environ.get('A2FC_PORT_OFFSET','0')),boot=5) as p:
  time.sleep(5)
  for keys in (b'2\r',b'1\r',b'COSTS.PFS\r',b'\x1b',b'1\r'):p.raw(keys);time.sleep(2)
  screen=p.screen();print('\n'.join(screen),flush=True)
  source_row=0;compared=0
  for row in rows:
   if row.startswith('R') and 'formula:' not in row:
    m=re.match(r'R(\d+) (.*)',row)
    if not m:continue
    source_row=int(m[1]);label=m[2]
    if 2<=source_row<=8:assert label in screen[source_row+1],(source_row,label)
   elif row.startswith(' C') and 2<=source_row<=8:
    m=re.match(r' C(\d+) (\w+) = (\S+)',row)
    if not m:continue
    col=int(m[1])
    if col>6:continue
    pieces=screen[source_row+1].split('|');literal=pieces[col-1].strip()
    if col==1:literal=literal.split()[-1]
    assert literal.replace(',','')==m[3],(source_row,col,literal,m[3])
    assert m[2] in screen[0],m[2]
    compared+=1
  assert compared==42,compared
  p.sync_disks();after={n:d for n,t,a,d in files(hd.read_bytes())[1] if t==22 and a==4};assert after==docs
  result={'date':'2026-10-10','scope':'COSTS rows 2 through 8, columns 1 through 6; 42 literal stored numeric values and visible labels. No all-sheet or typography comparison. Normal original keyboard input, no code adapter.','numeric_cells_compared':compared,'all_six_source_sheets_preserved':True,'document_sha256':hashlib.sha256(docs['/COSTS.PFS']).hexdigest()}
  out=Path('/tmp/a2fc-pfsplan-oracle');out.mkdir(exist_ok=True);(out/'costs.json').write_text(json.dumps(result,indent=2)+'\n');print('42/42 original/C values; six source sheets preserved',flush=True)
