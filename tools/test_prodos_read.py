"""Check sparse ProDOS reads without using the volume writer as an oracle."""
import unittest

from prodos_read import BLOCK, Image


class SparseReads(unittest.TestCase):
    def setUp(self):
        self.data = bytearray(8 * BLOCK)
        # A hole must never leak boot bytes (or interpret them as pointers).
        self.data[:BLOCK] = b'\xff' * BLOCK
        self.data[6 * BLOCK:7 * BLOCK] = b'A' * BLOCK
        self.data[7 * BLOCK:8 * BLOCK] = b'B' * BLOCK

    def pointer(self, block, slot, target):
        self.data[block * BLOCK + slot] = target & 255
        self.data[block * BLOCK + 256 + slot] = target >> 8

    def read(self, storage, key, size):
        entry = bytearray(39)
        entry[0] = storage << 4
        entry[0x11:0x13] = key.to_bytes(2, 'little')
        entry[0x15:0x18] = size.to_bytes(3, 'little')
        return Image(self.data).read(entry)

    def test_sapling_holes_and_partial_tail(self):
        self.pointer(3, 1, 6)
        self.pointer(3, 3, 7)
        for size in (BLOCK * 2 + 17, BLOCK * 4):
            with self.subTest(size=size):
                expected = bytes(BLOCK) + b'A' * BLOCK + bytes(BLOCK) + b'B' * BLOCK
                self.assertEqual(self.read(2, 3, size), expected[:size])

    def test_tree_data_hole(self):
        self.pointer(3, 0, 4)
        self.pointer(4, 0, 6)
        self.pointer(4, 2, 7)
        self.assertEqual(self.read(3, 3, BLOCK * 2 + 17),
                         b'A' * BLOCK + bytes(BLOCK) + b'B' * 17)

    def test_missing_tree_index_followed_by_data(self):
        self.pointer(3, 1, 4)
        self.pointer(4, 0, 7)
        self.assertEqual(self.read(3, 3, BLOCK * 256 + 17),
                         bytes(BLOCK * 256) + b'B' * 17)

    def test_missing_tree_index_at_partial_eof(self):
        self.pointer(3, 0, 4)
        self.pointer(4, 255, 6)
        self.assertEqual(self.read(3, 3, BLOCK * 256 + 17),
                         bytes(BLOCK * 255) + b'A' * BLOCK + bytes(17))


if __name__ == '__main__':
    unittest.main()
