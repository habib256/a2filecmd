"""Audit the built 800K selection, helper dependencies and exact plugin bytes."""
import argparse
from pathlib import Path
import distribution as dist
from prodos_read import Image
from prodos_check import check as check_structure

MIN_FREE = 160  # 80 KiB for user files and future safety fixes


def check(path, build):
    data = Path(path).read_bytes()
    image = Image(data)
    if len(data) != 1600*512 or image.header()['blocks'] != 1600:
        raise ValueError('800K geometry')
    # Matching file bytes do not make allocation safe: a used block marked
    # free could be overwritten on the next user write. Validate the whole
    # read-only structure before following directories or trusting free space.
    structure = check_structure(data)
    if not structure.complete or structure.findings:
        raise ValueError('800K inconsistent ProDOS structure')
    entries = {}

    def walk(key=2, prefix=''):
        for e in image.entries(key):
            name = e[1:1+(e[0]&15)].decode('ascii')
            full = prefix+'/'+name
            if e[0]>>4 == 13:
                walk(int.from_bytes(e[17:19],'little'),full)
            else:
                entries[full] = e
    walk()
    selected = dist.floppy_inventory()
    actual = {p.split('/')[-1][:-4] for p in entries if p.startswith('/A2FILE/') and p.endswith('.PLG')}
    if actual != selected:
        raise ValueError('800K overlay inventory mismatch: '+str(sorted(actual^selected)))
    native = set(dist.MAKEFILE.split('PLUGINS = ',1)[1].splitlines()[0].split())
    sources = {'/A2FILE/A2FILE.CODE':Path(build)/'A2FILE.CODE.BIN',
               '/A2FILE.SYSTEM':Path(build)/'A2FILE.SYSTEM.SYS',
               '/A2FILE/PPT3.BIN':Path(build)/'PPT3.BIN',
               '/A2FILE/VISICALC.BIN':Path(build)/'visicalc.PLG.BIN',
               '/A2FILE/FANTA.SYSTEM':Path(build)/'FANTA.SYSTEM.SYS',
               '/A2FILE/TAKE1.SYSTEM':Path(build)/'TAKE1.SYSTEM.SYS'}
    sources.update({'/'+name:dist.ROOT/'data'/ (name+'.SYS') for name in ('PRODOS',*dist.RUNTIMES)})
    sources['/RECOVER'] = dist.ROOT/'data/RECOVER.TXT'
    sources['/A2FILE/A2FILE.HELP'] = dist.ROOT/'data/A2FILE.HELP.TXT'
    for name in selected:
        source = Path(build)/('A2FILE.CODE.BIN.'+name if name in native else name.lower()+'.PLG')
        sources['/A2FILE/'+name+'.PLG'] = source
    for name,source in sources.items():
        if name not in entries or image.read(entries[name]) != source.read_bytes():
            raise ValueError('800K missing or mismatched file: '+name)
        # These are the load contracts of the staged files, not merely
        # matching payloads. SYS interpreters need SYS type/read access;
        # overlays and helper binaries keep their declared load addresses.
        entry = entries[name]
        if name == '/PRODOS' or name.endswith('.SYSTEM'):
            file_type = 0xFF
        elif name in ('/RECOVER','/A2FILE/A2FILE.HELP'):
            file_type = 4
        else:
            file_type = 6
        aux = 0x1B00 if name.endswith('.PLG') else 0x0800 if name == '/A2FILE/PPT3.BIN' else 0
        if (entry[0]>>4 not in (1,2,3) or not entry[0x1E]&1 or
                entry[0x10] != file_type or int.from_bytes(entry[0x1F:0x21],'little') != aux):
            raise ValueError('800K invalid load metadata: '+name)
    free = image.free_blocks()
    if free < MIN_FREE:
        raise ValueError('800K needs at least %d free blocks, got %d' % (MIN_FREE,free))
    return len(selected),free


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image',type=Path);parser.add_argument('build',type=Path)
    args=parser.parse_args()
    count,free=check(args.image,args.build)
    print('800K: %d overlays verified, %d free blocks (%d KiB)' % (count,free,free//2))
