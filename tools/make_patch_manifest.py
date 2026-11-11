#!/usr/bin/env python3
"""Pack only the byte changes between the verified GOG executable and patch."""

import argparse
import hashlib
import struct
from pathlib import Path

from sys import path as import_path

import_path.insert(0, str(Path(__file__).resolve().parents[1]))
from patch import ORIGINAL_SHA256

MAGIC = b"EDENPATCH2"


def changes(original, patched):
    if len(original) > len(patched):
        raise ValueError("the patched executable cannot be shorter than the source")
    result = []
    index = 0
    while index < len(original):
        if original[index] == patched[index]:
            index += 1
            continue
        start = index
        while index < len(original) and original[index] != patched[index]:
            index += 1
        result.append((start, original[start:index], patched[start:index]))
    if len(patched) > len(original):
        result.append((len(original), b"", patched[len(original):]))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--patched", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    original = args.source.read_bytes()
    patched = args.patched.read_bytes()
    source_hash = hashlib.sha256(original).digest()
    if source_hash.hex() != ORIGINAL_SHA256:
        parser.error("source does not match the supported GOG executable")
    edits = changes(original, patched)
    if not edits:
        parser.error("patched executable has no changed bytes")

    manifest = bytearray(MAGIC)
    manifest.extend(source_hash)
    manifest.extend(hashlib.sha256(patched).digest())
    manifest.extend(struct.pack("<III", len(original), len(patched), len(edits)))
    for offset, expected, replacement in edits:
        manifest.extend(struct.pack("<III", offset, len(expected), len(replacement)))
        manifest.extend(expected)
        manifest.extend(replacement)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(manifest)
    print(f"manifest: {args.output} ({len(edits)} changed ranges, "
          f"{len(manifest)} bytes)")


if __name__ == "__main__":
    main()
