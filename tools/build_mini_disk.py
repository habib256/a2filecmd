#!/usr/bin/env python3
"""Rebuild the generated Mini artifact, preserving its predecessor on failure.

The DOS master is read-only. mkmini33's exclusive-output CLI stays unchanged;
this build wrapper publishes a verified temporary in the output directory.
"""
import argparse
import os
import tempfile
from pathlib import Path
from mkmini33 import SIZE, build


def from_template(data):
    if len(data) != 3 * 4096:
        raise ValueError('expected exactly three DOS 3.3 boot tracks')
    master = bytearray(SIZE)
    master[:len(data)] = data
    master[17 * 4096 + 3] = 3
    master[17 * 4096 + 0x34:17 * 4096 + 0x38] = bytes([35, 16, 0, 1])
    return master


def publish(output, data):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=output.parent, prefix='.mini-', delete=False) as f:
            temporary = Path(f.name)
            if f.write(data) != len(data):
                raise OSError('short Mini image write')
            f.flush()
            os.fsync(f.fileno())
        if temporary.read_bytes() != data:
            raise OSError('Mini image verification failed')
        os.replace(temporary, output)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--master', type=Path)
    source.add_argument('--boot-template', type=Path)
    parser.add_argument('--binary', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    for input_path in (a.master or a.boot_template, a.binary):
        if a.output.resolve() == input_path.resolve() or (a.output.exists() and a.output.samefile(input_path)):
            raise ValueError('output must not replace an input')
    master = a.master.read_bytes() if a.master else from_template(a.boot_template.read_bytes())
    data = build(master, a.binary.read_bytes())
    publish(a.output, data)
    print(f'{a.output}: {len(data)} bytes, verified DOS 3.3 boot disk')


if __name__ == '__main__':
    main()
