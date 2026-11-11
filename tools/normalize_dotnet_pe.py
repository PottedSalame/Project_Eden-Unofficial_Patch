#!/usr/bin/env python3
"""Make the legacy C# compiler's PE timestamp and module ID reproducible."""

import argparse
import hashlib
import struct
from pathlib import Path


def number(data, offset, size):
    if offset < 0 or offset + size > len(data):
        raise ValueError("truncated .NET executable")
    return int.from_bytes(data[offset:offset + size], "little")


def normalize(path):
    data = bytearray(path.read_bytes())
    if data[:2] != b"MZ":
        raise ValueError("not a PE executable")
    pe = number(data, 0x3C, 4)
    if data[pe:pe + 4] != b"PE\0\0":
        raise ValueError("missing PE signature")
    coff = pe + 4
    optional = coff + 20
    if number(data, optional, 2) != 0x10B:
        raise ValueError("expected a 32-bit PE executable")
    if number(data, optional + 92, 4) <= 14:
        raise ValueError("missing .NET data directory")

    sections = []
    table = optional + number(data, coff + 16, 2)
    for index in range(number(data, coff + 2, 2)):
        entry = table + index * 40
        sections.append(tuple(number(data, entry + offset, 4)
                              for offset in (12, 8, 20, 16)))

    def file_offset(rva, size):
        for section_rva, virtual_size, raw_offset, raw_size in sections:
            delta = rva - section_rva
            if 0 <= delta and delta + size <= raw_size and delta < virtual_size:
                offset = raw_offset + delta
                number(data, offset, size)
                return offset
        raise ValueError(".NET metadata is outside file-backed sections")

    cli_rva = number(data, optional + 208, 4)
    if cli_rva == 0:
        raise ValueError("not a .NET executable")
    cli = file_offset(cli_rva, 24)
    if number(data, cli + 16, 4) & 0x8:
        raise ValueError("cannot normalize a strong-name signed executable")
    metadata = file_offset(number(data, cli + 8, 4), 20)
    if data[metadata:metadata + 4] != b"BSJB":
        raise ValueError("missing .NET metadata root")
    version_length = number(data, metadata + 12, 4)
    header = metadata + 16 + ((version_length + 3) & ~3)
    streams = number(data, header + 2, 2)
    cursor = header + 4
    heaps = {}
    for _ in range(streams):
        offset = number(data, cursor, 4)
        size = number(data, cursor + 4, 4)
        end = data.find(b"\0", cursor + 8, cursor + 40)
        if end < 0:
            raise ValueError("invalid .NET metadata stream")
        name = bytes(data[cursor + 8:end]).decode("ascii")
        start = metadata + offset
        number(data, start, size)
        heaps[name] = (start, size)
        cursor += 8 + ((end - (cursor + 8) + 4) & ~3)

    if "#GUID" not in heaps or not ({"#~", "#-"} & heaps.keys()):
        raise ValueError("missing .NET module metadata")
    tables = heaps.get("#~", heaps.get("#-"))[0]
    valid = number(data, tables + 8, 8)
    if not valid & 1:
        raise ValueError("missing .NET Module table")
    rows = tables + 24
    if number(data, rows, 4) != 1:
        raise ValueError("expected one .NET Module row")
    first_row = rows + 4 * bin(valid).count("1")
    heap_sizes = number(data, tables + 6, 1)
    string_index_size = 4 if heap_sizes & 1 else 2
    guid_index_size = 4 if heap_sizes & 2 else 2
    mvid_index = number(data, first_row + 2 + string_index_size,
                        guid_index_size)
    guid_start, guid_size = heaps["#GUID"]
    if mvid_index == 0 or mvid_index * 16 > guid_size:
        raise ValueError("invalid .NET module ID index")
    mvid = guid_start + (mvid_index - 1) * 16

    data[coff + 4:coff + 8] = b"\0" * 4
    data[mvid:mvid + 16] = b"\0" * 16
    data[mvid:mvid + 16] = hashlib.sha256(data).digest()[:16]
    path.write_bytes(data)
    print("Normalized .NET executable SHA-256:", hashlib.sha256(data).hexdigest())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    args = parser.parse_args()
    try:
        normalize(args.executable)
    except (OSError, ValueError) as error:
        parser.exit(1, f"normalization failed: {error}\n")


if __name__ == "__main__":
    main()
