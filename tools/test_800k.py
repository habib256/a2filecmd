"""800K policy and byte-for-byte checks of the generated disposable image."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import distribution as dist
from check_800k import check,MIN_FREE
from prodos_read import Image


class Selection(unittest.TestCase):
    def test_practical_selection_and_routing_dependencies(self):
        selected=dist.floppy_inventory()
        self.assertTrue({'COPY','MOVE','MOVECOPY','FIND','SYNC','TREE','GOTO','FAVRUN',
                         'FORMAT','FIXIT','REPAIR','RESCUE','UNDELETE','DISKCMP','SMALLDOS',
                         'DOSIMAGE','DOSPUT','MCSIMPORT','MCSPLAY','IDREAD','IDFORMATS','IDV1',
                         'UNWRAP','SCIIBIN','UNSQ','PASCAL','CPM',
                         'DOSBAS','DOSINT','VISICALC','PT3','APPLEWR','AWDATA'} <= selected)
        self.assertTrue(selected < dist.inventories()[1])
        self.assertTrue({'LISAV4','PAINT816','NRCLIP','DOCVIEW','WORDPERF'}.isdisjoint(selected))

    def test_unknown_and_duplicate_selections_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'config').mkdir()
            for names in ('smalldos smalldos','unknown_overlay'):
                (root/'config/800k.mk').write_text('PLUGINS800 = $(PLUGINS)\nXPLUGINS800 = '+names+'\n')
                with patch.object(dist,'ROOT',root),patch.object(dist,'inventories',return_value=(set(),{'SMALLDOS'})):
                    with self.assertRaises(ValueError):dist.floppy_inventory()


class BuiltImage(unittest.TestCase):
    def setUp(self):
        self.path=dist.ROOT/'dist'/dist.image_name('800K')
        self.build=dist.ROOT/'build-6502'
        if not self.path.exists():self.skipTest('build the 800K image first')
        self.original=self.path.read_bytes()

    def test_generated_inventory_helpers_bytes_and_capacity(self):
        count,free=check(self.path,self.build)
        self.assertEqual(count,len(dist.floppy_inventory()))
        self.assertGreaterEqual(free,MIN_FREE)

    def changed_entry(self,name,change,root=False):
        data=bytearray(self.original);image=Image(data)
        folder=next(e for e in image.entries(2) if e[0]>>4==13 and e[1:1+(e[0]&15)]==b'A2FILE')
        block=2 if root else int.from_bytes(folder[17:19],'little')
        while block:
            for k in range(13):
                off=block*512+4+k*39
                e=data[off:off+39]
                if e[0]>>4 and e[1:1+(e[0]&15)]==name.encode():
                    change(data,off);return bytes(data)
            block=int.from_bytes(data[block*512+2:block*512+4],'little')
        self.fail('missing test file '+name)

    def refused(self,data):
        with tempfile.TemporaryDirectory(prefix='800k-audit-') as directory:
            image=Path(directory)/'case.po';image.write_bytes(data)
            with self.assertRaises(ValueError):check(image,self.build)
            self.assertEqual(image.read_bytes(),data)
        self.assertEqual(self.path.read_bytes(),self.original)

    def test_missing_overlay_or_playback_helper_is_refused(self):
        for name in ('SMALLDOS.PLG','MOVECOPY.PLG','PPT3.BIN','VISICALC.BIN'):
            with self.subTest(name=name):
                self.refused(self.changed_entry(name,lambda data,off:data.__setitem__(off,0)))

    def test_mismatched_overlay_bytes_are_refused(self):
        def damage(data,off):
            key=int.from_bytes(data[off+17:off+19],'little')
            storage=data[off]>>4
            if storage==2:key=data[key*512]|data[key*512+256]<<8
            self.assertIn(storage,(1,2))
            data[key*512]^=1
        self.refused(self.changed_entry('SMALLDOS.PLG',damage))

    def test_allocated_blocks_marked_free_are_refused_without_changing_bytes(self):
        image=Image(self.original)
        folder=next(e for e in image.entries(2) if e[0]>>4==13 and e[1:1+(e[0]&15)]==b'A2FILE')
        directory=int.from_bytes(folder[17:19],'little')
        plugin=next(e for e in image.entries(directory) if e[1:1+(e[0]&15)]==b'SMALLDOS.PLG')
        index=int.from_bytes(plugin[17:19],'little')
        data_block=self.original[index*512]|self.original[index*512+256]<<8
        bitmap=image.header()['bitmap']*512
        for block in (0,directory,index,data_block):
            with self.subTest(block=block):
                damaged=bytearray(self.original)
                damaged[bitmap+(block>>3)]|=1<<(7-(block&7))
                self.assertEqual(Image(damaged).read(plugin),image.read(plugin))
                self.refused(bytes(damaged))

    def test_wrong_type_load_address_or_read_access_is_refused(self):
        for name,root in (('A2FILE.SYSTEM',True),('BASIC.SYSTEM',True),
                          ('SMALLDOS.PLG',False),('PPT3.BIN',False),
                          ('VISICALC.BIN',False),('FANTA.SYSTEM',False),
                          ('A2FILE.HELP',False)):
            for field in (0x10,0x1F,0x1E):
                with self.subTest(name=name,field=field):
                    damaged=self.changed_entry(name,
                        lambda data,off:data.__setitem__(off+field,data[off+field]^1),root=root)
                    self.refused(damaged)

    def test_read_only_protected_overlay_remains_acceptable(self):
        data=self.changed_entry('SMALLDOS.PLG',
            lambda data,off:data.__setitem__(off+0x1E,data[off+0x1E]&~2))
        with tempfile.TemporaryDirectory(prefix='800k-readonly-') as directory:
            image=Path(directory)/'case.po';image.write_bytes(data)
            self.assertEqual(check(image,self.build),check(self.path,self.build))
            self.assertEqual(image.read_bytes(),data)
        self.assertEqual(self.path.read_bytes(),self.original)


if __name__=='__main__':unittest.main()
