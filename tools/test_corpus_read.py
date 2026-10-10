"""Malformed corpus inputs must be bounded and must preserve source bytes."""
import io
import sys
import unittest
import zipfile
from pathlib import Path
from corpus_read import CheckedImage,files
from test_volinfo import fixture
from mkdos33 import build

class CorpusRead(unittest.TestCase):
    def test_multiplan_R_preserves_header_and_zero_allocated_sectors(self):
        from legacy_corpus import dos_files
        payload=bytes.fromhex('08E70000D6100100')+bytes(760)
        disk=build([('SHEET',64,payload)])
        before=bytes(disk);entry=list(dos_files(before))[0]
        self.assertEqual(entry,('SHEET',244,0,payload));self.assertEqual(bytes(disk),before)

    def test_bank_street_geometry_requires_explicit_read_only_opt_in(self):
        from legacy_corpus import dos_files
        disk=bytearray(build([('DATA',4,b'\x00\x40\x01\x00X')]))
        disk[17*4096+54:17*4096+56]=b'\x01\x00';before=bytes(disk)
        with self.assertRaises(ValueError):list(dos_files(before))
        self.assertEqual(list(dos_files(before,bank_street_geometry=True))[0][3],b'X')
        self.assertEqual(bytes(disk),before)

    def test_dos_not_mistaken_for_prodos_opcode(self):
        disk=bytearray(build([('LETTER',0,b'HELLO\r\0')]))
        disk[1028:1030]=b'\xff\xe6'
        before=bytes(disk);fs,entries=files(before)
        self.assertEqual(fs,'dos');self.assertEqual(entries[0][3],b'HELLO\r')
        self.assertEqual(bytes(disk),before)

    def test_block_and_directory_bounds(self):
        disk=bytearray(4096)
        img=CheckedImage(bytes(disk))
        for n in (-1,8,65535):
            with self.assertRaises(ValueError):img.block(n)
        disk[1026:1028]=(2).to_bytes(2,'little')
        with self.assertRaises(ValueError):CheckedImage(bytes(disk)).entries(2)
        disk[1026:1028]=(65535).to_bytes(2,'little')
        with self.assertRaises(ValueError):CheckedImage(bytes(disk)).entries(2)

    def test_sparse_and_oversized_seedling(self):
        e=bytearray(39);e[0]=0x11;e[17:19]=(7).to_bytes(2,'little');e[21:24]=(513).to_bytes(3,'little')
        with self.assertRaises(ValueError):CheckedImage(bytes(4096)).read(e)
        e[0]=0x21;e[17:19]=(7).to_bytes(2,'little');e[21:24]=(1024).to_bytes(3,'little')
        self.assertEqual(CheckedImage(bytes(4096)).read(e),bytes(1024))

    def test_bad_2img_offsets(self):
        for offset,length,order in ((0,10,1),(64,1000,1),(64,10,2)):
            d=bytearray(100);d[:4]=b'2IMG';d[12:16]=order.to_bytes(4,'little');d[24:28]=offset.to_bytes(4,'little');d[28:32]=length.to_bytes(4,'little')
            with self.assertRaises(ValueError):files(bytes(d))

if __name__=='__main__':unittest.main()
