"""Compatibility entry point for the production DOS stream tests."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"tools"))
import test_dos_stream
if __name__ == "__main__":
    unittest.main(module=test_dos_stream)
