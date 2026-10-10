#!/usr/bin/env python3
"""Bounded, read-only census of the separately downloaded public PFS corpus.
Only the requested JSON output is written. Native readers are not invoked;
these metadata/header counts are not full viewer validation results.
"""
import argparse,hashlib,json,os
from collections import Counter
from pathlib import Path
from corpus_read import images,files

def census(root):
    sources=[];documents=[];errors=[];seen=set();parsed=0;duplicates=0
    for p in sorted((root/'images').rglob('*')):
        if not p.is_file():continue
        data=p.read_bytes();sources.append({'path':str(p.relative_to(root)),'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()})
        if p.suffix.lower() not in ('.dsk','.po','.zip'):continue
        for member,data in images(p):
            digest=hashlib.sha256(data).hexdigest()
            if digest in seen:duplicates+=1;continue
            seen.add(digest)
            try:fs,entries=files(data)
            except ValueError as exc:
                errors.append({'source':str(p.relative_to(root)),'member':member,'reason':str(exc)});continue
            parsed+=1
            for n,t,a,d in entries:
                if t!=22 or a not in (1,2,4):continue
                documents.append({'source':str(p.relative_to(root)),'member':member,'filesystem':fs,'name':n,'type':t,'aux':a,'length':len(d),'sha256':hashlib.sha256(d).hexdigest(),'header16':d[:16].hex()})
    by_aux={str(a):{'occurrences':sum(d['aux']==a for d in documents),'unique_contents':len({d['sha256'] for d in documents if d['aux']==a})} for a in (1,2,4)}
    return {'date':'2026-10-10','scope':'Separate downloaded PFS corpus; excluded from the fixed 1907-source general census. Metadata candidates only, not full validation.','sources':sources,'parsed_unique_images':parsed,'duplicate_images':duplicates,'errors':errors,'by_aux':by_aux,'documents':documents}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--corpus',type=Path,default=Path(os.environ.get('A2FC_PFS_CORPUS','/tmp/a2fc-pfs-corpus')));ap.add_argument('--output',type=Path,required=True);args=ap.parse_args()
    result=census(args.corpus);args.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k not in ('sources','documents','errors')},indent=2));print(len(result['sources']),'sources;',len(result['errors']),'unreadable images')
if __name__=='__main__':main()
