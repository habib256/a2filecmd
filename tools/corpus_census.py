#!/usr/bin/env python3
"""Reproducible local census. Sources are read-only; outputs go to --output.
Metadata inventory and actual-C content candidates are counted separately.
No claim of full reader validation or file occurrence deduplication by name.
"""
import argparse
import ctypes
import hashlib
import json
import subprocess
import tempfile
import zipfile
from collections import Counter
from pathlib import Path
from corpus_read import images,files
ROOT=Path(__file__).resolve().parents[1]

C_SOURCE=r'''
#define __fastcall__
#define PLUGIN_HOST
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#undef memcpy
#undef memset
#undef strcpy
#undef sprintf
struct A2fcApi;
unsigned char host_id_sample[512];
#include "src/plugins/ident.c"
static struct A2fcApi ca;static struct Entry ce;static unsigned char sample[512];
const char* corpus_ident(const char* name,int typ,int aux,const unsigned char* bytes,unsigned long len,int dos,char* output){
 const char* label;static char result[256];
 memset(&ce,0,sizeof ce);strncpy(ce.name,name,NAME_LEN-1);ce.type=typ;ce.aux=aux;ce.size=len;
 memset(&ca,0,sizeof ca);ca.sprintf=sprintf;ca.fseek=fseek;ca.fread=fread;
 A=&ca;e=&ce;b=sample;sz.l=len;n=len<512?len:512;id_dos=dos;reader=NULL;io_failed=0;
 memset(sample,0,sizeof sample);memcpy(sample,bytes,n);
 /* identify() may seek or inspect complete Duet data. Only this disposable
  * temporary copy is written. Original disks and files stay read-only. */
 f=tmpfile();if(!f)return NULL;
 if(fwrite(bytes,1,len,f)!=len || fseek(f,0,SEEK_SET)){fclose(f);return NULL;}
 label=extra_v1();if(!label)label=extra();if(!label)label=identify();if(!reader)route(label);
 snprintf(result,sizeof result,"%s",label);ca.strcpy=strcpy;ca.input=output;ca.arg='O';id_finish(&ca,&ce,result,reader,dos);
 if(fclose(f)||io_failed)return NULL;
 return result;
}
'''

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--corpus',type=Path,default=Path.home()/'.cache/a2fc/asimov_corpus')
    ap.add_argument('--extra',type=Path,action='append',default=[])
    ap.add_argument('--output',type=Path,required=True)
    args=ap.parse_args();out=args.output;out.mkdir(parents=True,exist_ok=True)
    index=json.loads((args.corpus/'index.json').read_text());raw=sorted(p for p in (args.corpus/'raw').rglob('*') if p.is_file())
    inv={'raw_sources':len(raw),'indexed_containers':len(index['disks']),'indexed_file_occurrences':len(index['rows']),
         'indexed_errors':len(index['errors']),'indexed_filesystems':dict(Counter(x['fs'] for x in index['disks'])),
         'indexed_types':dict(Counter(x['fs']+':'+str(x['type']) for x in index['rows']))}
    manifest=[];failures=[];rows=[];seen_images=set();seen_files=set();duplicates=0;parsed=0
    for root in args.extra:raw.extend(sorted(p for p in root.rglob('*') if p.is_file()))
    with tempfile.TemporaryDirectory(prefix='a2fc-census-') as td:
        td=Path(td);(td/'ident.c').write_text(C_SOURCE)
        subprocess.run(['cc','-std=c99','-Wno-unknown-pragmas','-Wno-deprecated-declarations','-shared','-fPIC','-I',str(ROOT),str(td/'ident.c'),'-o',str(td/'ident.so')],check=True,capture_output=True)
        lib=ctypes.CDLL(str(td/'ident.so'));ident=lib.corpus_ident
        ident.argtypes=[ctypes.c_char_p,ctypes.c_int,ctypes.c_int,ctypes.c_void_p,ctypes.c_ulong,ctypes.c_int,ctypes.c_void_p];ident.restype=ctypes.c_char_p
        for no,path in enumerate(raw):
            if no%100==0:print(f'{no}/{len(raw)} sources, {parsed} images, {len(rows)} files',flush=True)
            digest=hashlib.sha256(path.read_bytes()).hexdigest();manifest.append({'path':str(path),'sha256':digest,'bytes':path.stat().st_size})
            try:
                count=0
                for member,data in images(path):
                    count+=1;dh=hashlib.sha256(data).hexdigest()
                    if dh in seen_images:duplicates+=1;continue
                    seen_images.add(dh)
                    try:fs,entries=files(data)
                    except (ValueError,IndexError,UnicodeError) as exc:
                        failures.append({'source':str(path),'member':member,'reason':str(exc)});continue
                    parsed+=1
                    for name,typ,aux,body in entries:
                        fh=hashlib.sha256(body).hexdigest();identity=(fh,typ,aux,fs);unique=identity not in seen_files;seen_files.add(identity)
                        view=ctypes.create_string_buffer(64);buf=ctypes.create_string_buffer(body)
                        label=ident(name.rsplit('/',1)[-1].upper().encode(),typ,aux,buf,len(body),fs=='dos',view)
                        if label is None:
                            failures.append({'source':str(path),'member':member,'file':name,'reason':'C identification I/O error'});continue
                        label=label.decode();reader=view.value.decode()
                        status='generic' if reader in ('HEX','TEXT','DOSVIEW') or label.startswith('Binary, maybe') else 'candidate'
                        rows.append({'source':str(path),'member':member,'fs':fs,'name':name,'type':typ,'aux':aux,'length':len(body),'sha256':fh,'unique_content_metadata':unique,'label':label,'reader':reader,'status':status})
                if not count:failures.append({'source':str(path),'reason':'no supported image in container'})
            except (ValueError,IndexError,UnicodeError,OSError,EOFError,zipfile.BadZipFile,NotImplementedError) as exc:failures.append({'source':str(path),'reason':str(exc)})
    inv.update(parsed_unique_images=parsed,duplicate_images=duplicates,classified_file_occurrences=len(rows),unique_content_metadata=len(seen_files),scan_failures=len(failures),scan_filesystems=dict(Counter(r['fs'] for r in rows)))
    groups=Counter((r['reader'],r['status']) for r in rows)
    inv['reader_candidates']=[{'reader':k[0],'status':k[1],'occurrences':v,'unique':sum(r['reader']==k[0] and r['status']==k[1] and r['unique_content_metadata'] for r in rows)} for k,v in groups.most_common()]
    for name,data in [('summary.json',inv),('manifest.json',manifest),('files.json',rows),('failures.json',failures)]:
        (out/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(inv,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
