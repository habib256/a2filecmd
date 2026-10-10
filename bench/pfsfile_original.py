import os,sys,tempfile,time,subprocess,hashlib,json
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1]/'tools')]
from pom2 import Pom2,ROOT
from test_pfsfile import PfsFile,real_files
root=Path(os.environ.get('A2FC_PFS_CORPUS','/tmp/a2fc-pfs-corpus'))
expected=['Expense Category: Utilities','Date: 86/12/13','Item: Utilities','Amount: $75.00','Check #: 1821','Charge to: Marketing Expenses','Pay to: West Coast Gas and Electric','44189 S. Main St.','San Jose, CA 95126']
originals=dict(real_files());PfsFile.setUpClass()
try: rows,_,_=PfsFile().run_file(originals['/COSTFILE.PFS'])
finally:PfsFile.tearDownClass()
from corpus_read import files
with tempfile.TemporaryDirectory(prefix='pfsfile-original-') as td:
 td=Path(td);stage=td/'stage';stage.mkdir()
 _,entries=files((root/'images/productivity/integrated/pfs/PFS_FILE_PRODOS_hr.dsk').read_bytes())
 for n,t,a,d in entries:(stage/(n[1:]+'#%02X%04X'%(t,a))).write_bytes(d)
 for n in ('STAFF.PFS','COSTFILE.PFS'):(stage/(n+'#160001')).write_bytes(originals['/'+n])
 hd=td/'pfs.hdv';subprocess.run([sys.executable,str(ROOT/'tools/mkvolume.py'),str(stage),str(hd),'--volume','PFSFILE','--boot',str(ROOT/'data/prodos_boot.tmpl'),'--blocks','1600'],check=True,capture_output=True)
 with Pom2(hd,port=6948+int(os.environ.get('A2FC_PORT_OFFSET','0')),boot=5) as p:
  time.sleep(5);print('BOOT\n'+'\n'.join(p.screen()),flush=True)
  for keys in (b'7\r',b'COSTFILE.PFS\r',b'4\r'):
   p.raw(keys);time.sleep(2);print('KEY '+repr(keys)+'\n'+'\n'.join(p.screen()),flush=True)
  memory=p.peek(0x1000,0xb000);patches=[]
  for pattern in (b'\xad\x61\xc0',b'\x2c\x61\xc0'):
   start=0
   while True:
    at=memory.find(pattern,start)
    if at<0:break
    patches.append((0x1000+at,pattern));start=at+3
  # POM2's keyboard endpoint has no Open-Apple modifier. Adapt its sole
  # button-0 read in MAIN for one Return, then restore the instruction.
  # All rendering, record decoding and file bytes remain original.
  assert len(patches)==1,patches
  print('Apple input adapter',[(hex(a),v.hex()) for a,v in patches],flush=True)
  p.poke(0x0200,b'\x80')
  for a,v in patches:p.poke(a+1,b'\x00\x02')
  p.raw(b'\r');time.sleep(2)
  for a,v in patches:p.poke(a,v)
  print('FOUND\n'+'\n'.join(p.screen()),flush=True)
  screen='\n'.join(p.screen())
  for label in expected:
   assert label in screen and any(label in row for row in rows),label
  p.sync_disks();_,after=files(hd.read_bytes())
  for n,t,a,d in after:
   if n in originals:assert d==originals[n],n
  result={'date':'2026-10-10','scope':'Nine literal values/labels from first COSTFILE record only; no full typography or all-record comparison. Input adapter redirects one MAIN Open-Apple read for one Return, then restores it.','labels_compared':len(expected),'document_sha256':hashlib.sha256(originals['/COSTFILE.PFS']).hexdigest(),'source_documents_preserved':True}
  out=Path('/tmp/a2fc-pfsfile-oracle');out.mkdir(exist_ok=True);(out/'first-record.json').write_text(json.dumps(result,indent=2)+'\n')
  print('9/9 original/C labels, document bytes unchanged',flush=True)
