"""Read-only SMALLDOS oracle, based on pom2games/wilderness/tools/smalldos.py.

Input is a raw 35-track DOS-order or ProDOS-order image. Files contain all
allocated sectors; neither byte EOF nor binary load address is recorded.
"""
DOS_L2P = [0,13,11,9,7,5,3,1,14,12,10,8,6,4,2,15]
PO_L2P = [0,2,4,6,8,10,12,14,1,3,5,7,9,11,13,15]
SIZE = 35*16*256


def offset(t, s, flip, order):
    physical = DOS_L2P[15-s]
    slot = (DOS_L2P if order == 'dos' else PO_L2P).index(physical)
    return ((34-t if flip else t)*16+slot)*256


def volume(data, order='dos'):
    if len(data) != SIZE:
        raise ValueError('image length')
    flip = None
    for candidate in (False, True):
        off = offset(0, 0, candidate, order)
        if data[off:off+4] == b'\x06\0\0\0':
            flip = candidate
            break
    if flip is None:
        raise ValueError('no catalogue')
    files = []
    for cs in range(4):
        off = offset(0, cs, flip, order)
        for pos in range(off+96, off+256, 32):
            e = data[pos:pos+32]
            if e[0] not in (0xC1, 0xC2):
                continue
            typ, n, t, s, reserved = e[:5]
            raw = bytes(c & 127 for c in e[5:])
            if not n or t >= 35 or s >= 16 or reserved or t*16+s+n > 560:
                raise ValueError('extent')
            if any(c < 32 or c > 126 for c in raw) or not raw.rstrip(b' '):
                raise ValueError('name')
            name = raw.decode('ascii').rstrip(' ')
            output = ''
            for c in name.upper()[:15]:
                c = c if c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.' else '.'
                if not output and c not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
                    c = 'X'
                output += c
            payload = b''.join(data[offset((t*16+s+i)//16,(t*16+s+i)%16,flip,order):
                                        offset((t*16+s+i)//16,(t*16+s+i)%16,flip,order)+256]
                               for i in range(n))
            files.append(dict(name=name, output=output, type=typ, data=payload))
    return dict(flip=flip, files=files)


def make(files, flip=True, order='dos'):
    """Disposable fixture: [(name, 'A'/'B', bytes)], sequential from track 1."""
    data = bytearray(SIZE)
    off = offset(0,0,flip,order)
    data[off:off+4] = b'\x06\0\0\0'
    start = 16
    for i,(name,typ,body) in enumerate(files):
        n = max(1,(len(body)+255)//256)
        if i >= 20 or n > 255 or start+n > 560:
            raise ValueError('fixture full')
        raw = name.encode('ascii')
        if not 0 < len(raw) <= 27:
            raise ValueError('fixture name')
        off = offset(0,i//5,flip,order)+96+(i%5)*32
        data[off:off+32] = bytes([ord(typ)|128,n,start//16,start%16,0])+bytes(c|128 for c in raw.ljust(27,b' '))
        padded = body.ljust(n*256,b'\0')
        for j in range(n):
            off = offset((start+j)//16,(start+j)%16,flip,order)
            data[off:off+256] = padded[j*256:(j+1)*256]
        start += n
    return bytes(data)


def convert(data, source, destination):
    result = bytearray(SIZE)
    src = DOS_L2P if source == 'dos' else PO_L2P
    dst = DOS_L2P if destination == 'dos' else PO_L2P
    for t in range(35):
        for physical in range(16):
            a = (t*16+src.index(physical))*256
            b = (t*16+dst.index(physical))*256
            result[b:b+256] = data[a:a+256]
    return bytes(result)
