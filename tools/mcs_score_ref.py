"""Independent Apple II MCS editor-record model, derived from the original editor.
The main file has 256 state bytes then staff 0; .OBJ holds staff 1.
No commercial code, disk or song is distributed here.
"""
DUR=(2,4,8,16,32,2,4,8,16,32)
DOT=(3,6,12,24,48,3,6,12,24,48)
LADDER=(0,1,2,4,6,8,9,11,13,14,16,18,20,21,23,25,26,28,30,32,33,35,37,38,40,42,44,45,47,49,50,52,54,56,57,59,61,255)
def convert(records,staff,ts):
 rec=[tuple(records[i:i+4]) for i in range(0,len(records),4)][:-1]
 key=[0]*38;acc=[0]*38;dot=[0]*38;clef=7 if staff==0 else -13;tie=0;octave=permanent=0;out=[]
 for i,(kind,y,lo,hi) in enumerate(rec):
  x=lo+256*hi
  if kind==31:acc=[0]*38;dot=[0]*38;octave=0;continue
  if kind in (10,11,12):
   acc[y]=kind
   if x<80:
    chrom=LADDER[y+clef]%12
    for z in range(0 if staff==0 else 19,19 if staff==0 else 38):
     idx=z+clef
     if 0<=idx<37 and LADDER[idx]%12==chrom:key[z]=kind
   continue
  if kind==13:dot[y]=1;continue
  if kind==14:octave=1;permanent|=x<80;continue
  if kind==15:clef=7 if staff==0 else -13;continue
  if kind==16:clef=19 if staff==0 else -1;continue
  if kind in (17,26):tie=64;continue
  orig=kind
  if 21<=kind<=24:kind-=21
  if kind==25:kind=18
  if kind not in (*range(10),18,19):raise ValueError(kind)
  pitch=62
  if kind in (0,1,2,3,4,18) or 21<=orig<=25:
   idx=y+clef
   pitch=LADDER[idx]
   if octave or permanent:pitch=max(0,pitch-12)
   if acc[y]!=10:
    for modify in (acc[y],key[y]):
     if modify==11:pitch-=1
     if modify==12:pitch+=1
  d=(1 if kind in (18,19) else DOT[kind] if dot[y] else DUR[kind])
  if kind==9:d=(16,32,24,24)[ts]
  dot[y]=0
  following=rec[i+1] if i+1<len(rec) else (31,0,0,0)
  chord=following[2:]==(lo,hi) and (following[0] in (0,1,2,3,4,18) or 21<=following[0]<26)
  out.append((pitch*2,d|(tie if staff==0 else 0)|(128 if chord else 0)))
  if not chord:tie=0
 return bytes(v for pair in out for v in pair)


def score(main,obj):
    if len(main)<264 or len(main)%4 or len(obj)<8 or len(obj)%4:
        raise ValueError("score size")
    header=main[:256]
    if header[122:126]!=bytes((0,0,0x41,0x74)) or header[126]>3:
        raise ValueError("state header")
    for staff,records,base in ((0,main[256:],0x4100),(1,obj,0x7400)):
        end=header[118+staff]+256*header[120+staff]
        if end!=base+len(records)-4 or end>=base+0xb00:
            raise ValueError("end pointer")
    parts=[convert(main[256:],0,header[126]),convert(obj,1,header[126])]
    durations=[sum(p[i+1]&63 for i in range(0,len(p),2) if not p[i+1]&128) for p in parts]
    maximum=max(durations)
    if not maximum:raise ValueError("empty score")
    out=bytearray()
    for part,duration in zip(parts,durations):
        gap=maximum-duration
        while gap:
            n=min(gap,63);part+=bytes((124,n));gap-=n
        if len(part)>1150:raise ValueError("staff too long")
        out+=part+bytes(1152-len(part))
    return bytes(out)


def fixture(top=None,bottom=None,time=1):
    if top is None:top=[(31,10,16),(15,10,20),(1,10,96),(2,11,120),(31,10,200)]
    if bottom is None:bottom=[(31,10,16),(16,30,20),(1,30,96),(31,10,200)]
    def packed(records):return b"".join(bytes((k,y))+x.to_bytes(2,"little") for k,y,x in records)
    a,b=packed(top),packed(bottom);header=bytearray(256)
    header[122:126]=bytes((0,0,0x41,0x74));header[126]=time
    for s,data,base in ((0,a,0x4100),(1,b,0x7400)):
        end=base+len(data)-4;header[118+s]=end&255;header[120+s]=end>>8
    return bytes(header)+a,b


def original_export(main,obj,disk):
    """Execute the original conversion instructions in disposable 6502 RAM.

    The card-volume callback at $5027 is replaced with RTS; it does not
    participate in notation decoding. Main staff end terminates the editor,
    so the second stream can be a prefix of the complete imported staff.
    """
    from mos6502 import CPU
    from take1_ref import DosImage
    d=DosImage(disk);c=CPU()
    for name,base in ((b"A3",0xa00),(b"A4",0x4a00)):
        data=d.read_file(*d.find(name));c.m[base:base+len(data)]=data
    if len(main)<264 or len(main)>0xc00 or len(obj)>0xb00:raise ValueError("score")
    c.m[0x4000:0x4100]=main[:256]
    c.m[0x4100:0x4100+len(main)-256]=main[256:]
    c.m[0x7400:0x7400+len(obj)]=obj
    c.m[0x5027]=0x60;c.m[0xa56:0xa58]=b"\1\1"
    c.m[0xa58:0xa5c]=b"\xfc\x40\xfc\x73"
    c.m[0xa72:0xa78]=b"\xff"*6;c.m[0x7f54:0x7f56]=b"\0\6"
    c.call(0x91a5)
    for s,start,length in ((0,0x4100,len(main)-256),(1,0x7400,len(obj))):
        end=start+length-4
        c.m[0x4076+s]=end&255;c.m[0x4078+s]=end>>8
        c.m[0xc04+s]=c.m[0xc06+s]
    for _ in range(200000):
        if c.call(0x8a23)==0:break
    else:raise ValueError("original did not finish")
    return [bytes(c.m[base:int.from_bytes(c.m[0xf8+2*s:0xfa+2*s],"little")])
            for s,base in enumerate((0x1000,0x1480))]
