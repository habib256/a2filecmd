"""Independent, disposable DOS 3.3 fixtures and byte-level file reader."""
import struct
SIZE=143360

def offset(t,s):
    assert 0<=t<35 and 0<=s<16
    return (t*16+s)*256

def make_disk(files):
    disk=bytearray(SIZE)
    free=[(t,s) for t in range(3,35) if t!=17 for s in range(16)]
    assert len(files)<=105
    def alloc(): return free.pop(0)
    def put(ts,data):
        assert len(data)<=256
        o=offset(*ts); disk[o:o+len(data)]=data
    for index,(name,kind,data) in enumerate(files):
        n=(len(data)+255)//256
        lists=[alloc() for _ in range(max(1,(n+121)//122))]
        blocks=[alloc() for _ in range(n)]
        for i,ts in enumerate(blocks): put(ts,data[i*256:(i+1)*256])
        for i,ts in enumerate(lists):
            table=bytearray(256)
            if i+1<len(lists): table[1:3]=bytes(lists[i+1])
            struct.pack_into('<H',table,5,i*122)
            for j,pair in enumerate(blocks[i*122:(i+1)*122]): table[12+j*2:14+j*2]=bytes(pair)
            put(ts,table)
        entry=bytearray(35); entry[:2]=bytes(lists[0]); entry[2]=kind
        entry[3:33]=bytes(c|128 for c in name.encode('ascii').ljust(30))
        assert len(entry)==35
        struct.pack_into('<H',entry,33,n+len(lists))
        o=offset(17,15-index//7)+11+(index%7)*35
        disk[o:o+35]=entry
    for s in range(15,1,-1):
        o=offset(17,s); disk[o+1:o+3]=bytes([17,s-1])
    v=bytearray(256); v[1:4]=bytes([17,15,3]); v[6]=254; v[0x27]=122
    v[0x34:0x38]=bytes([35,16,0,1])
    for t,s in free: v[0x38+t*4+(s<8)]|=1<<(s&7)
    put((17,0),v)
    return bytes(disk)

def read_files(disk):
    files={}; used={(17,0)}; chain=set()
    t,s=disk[offset(17,0)+1:offset(17,0)+3]
    while t:
        assert (t,s) not in chain; chain.add((t,s)); used.add((t,s))
        cat=disk[offset(t,s):offset(t,s)+256]
        for i in range(7):
            e=cat[11+i*35:46+i*35]
            if e[0] in (0,255): continue
            name=bytes(c&127 for c in e[3:33]).decode('ascii').rstrip()
            assert name not in files
            ft,fs=e[:2]; data=bytearray(); blocks=[]; lists=[]
            while ft:
                assert (ft,fs) not in used; used.add((ft,fs)); lists.append((ft,fs))
                ts=disk[offset(ft,fs):offset(ft,fs)+256]
                assert struct.unpack_from('<H',ts,5)[0]==len(data)//256
                for j in range(122):
                    dt,ds=ts[12+j*2:14+j*2]
                    if not dt and not ds: break
                    assert (dt,ds) not in used; used.add((dt,ds)); blocks.append((dt,ds))
                    data+=disk[offset(dt,ds):offset(dt,ds)+256]
                ft,fs=ts[1:3]
            assert len(blocks)+len(lists)==struct.unpack_from('<H',e,33)[0]
            files[name]={'type':e[2],'data':bytes(data),'blocks':blocks,'lists':lists,'entry':bytes(e)}
        t,s=cat[1:3]
    for t,s in used:
        assert not disk[offset(17,0)+0x38+t*4+(s<8)]&(1<<(s&7))
    return files
