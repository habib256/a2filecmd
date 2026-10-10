"""Bounded read-only corpus access. Reject malformed chains; no source writes."""
import gzip
import io
import zipfile
from pathlib import Path
from prodos_read import Image
from legacy_corpus import dos_files
from po2dsk import SECTORS
MAX_IMAGE=32*1024*1024

class CheckedImage(Image):
    def block(self,n):
        if n<0 or (n+1)*512>len(self.d):raise ValueError('block outside image')
        return super().block(n)
    def entries(self,key,skip_header=True):
        result=[];seen=set();first=True;previous=0
        while key:
            if key in seen:raise ValueError('cyclic directory')
            seen.add(key);b=self.block(key)
            if int.from_bytes(b[:2],'little')!=previous:raise ValueError('directory backlink')
            for i in range(13):
                if first and not i and skip_header:continue
                e=b[4+i*39:43+i*39]
                if e[0]>>4:
                    if not e[0]&15:raise ValueError('empty live name')
                    result.append(e)
            first=False;previous=key;key=int.from_bytes(b[2:4],'little')
        return result
    def read(self,e):
        kind=e[0]>>4;length=int.from_bytes(e[21:24],'little')
        if kind==1 and length>512:raise ValueError('oversized seedling')
        if kind==2 and length>131072:raise ValueError('oversized sapling')
        data=super().read(e)
        if len(data)!=length:raise ValueError('short data')
        return data
    def files(self,key=2,prefix='',seen=None):
        if seen is None:seen=set()
        if key in seen:raise ValueError('directory alias/cycle')
        seen.add(key)
        for e in self.entries(key):
            name=prefix+'/'+e[1:1+(e[0]&15)].decode('ascii')
            if e[0]>>4==13:
                yield from self.files(int.from_bytes(e[17:19],'little'),name,seen)
            else:yield name,e[16],int.from_bytes(e[31:33],'little'),self.read(e)


def images(path):
    data=path.read_bytes()
    if len(data)>MAX_IMAGE*8:raise ValueError('source expansion limit')
    if path.suffix.lower()=='.zip':
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            total=0
            for e in z.infolist():
                if e.is_dir():continue
                if Path(e.filename).suffix.lower() not in ('.dsk','.do','.po','.2mg','.2img','.hdv','.img'):continue
                total+=e.file_size
                if e.file_size>MAX_IMAGE or total>MAX_IMAGE*8:raise ValueError('ZIP expansion limit')
                yield e.filename,z.read(e)
    elif path.suffix.lower()=='.gz':
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as z:data=z.read(MAX_IMAGE+1)
        if len(data)>MAX_IMAGE:raise ValueError('gzip expansion limit')
        yield path.stem,data
    else:yield path.name,data


def files(data):
    if data[:4]==b'2IMG':
        if len(data)<64:raise ValueError('short 2IMG')
        order=int.from_bytes(data[12:16],'little');off=int.from_bytes(data[24:28],'little');n=int.from_bytes(data[28:32],'little')
        if off<64 or not n or off+n>len(data) or order not in (0,1):raise ValueError('invalid/unsupported 2IMG')
        data=data[off:off+n]
    if not data or len(data)>MAX_IMAGE:raise ValueError('image size limit')
    variants=[data]
    if len(data)==143360:
        variants.append(b''.join(data[(b//8*16+s)*256:(b//8*16+s+1)*256] for b in range(280) for s in SECTORS[b%8]))
    for v in variants:
        if len(v)>=1536 and v[1028]>>4==15 and v[1059:1061]==bytes([39,13]):
            disk=CheckedImage(v);header=disk.header()
            if header['blocks']*512>len(v) or not header['blocks']:raise ValueError('volume length')
            return 'prodos',list(disk.files())
    if len(data)==143360 and data[69632+0x34:69632+0x38]==bytes([35,16,0,1]):
        return 'dos',list(dos_files(data))
    raise ValueError('unsupported filesystem/container')
