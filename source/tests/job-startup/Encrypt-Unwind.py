"""Owned fixture only: retain plain .pdata and replace two disk unwind bodies."""
import argparse
import json
from pathlib import Path
import pefile

parser = argparse.ArgumentParser()
parser.add_argument('target', type=Path)
parser.add_argument('receipt', type=Path)
args = parser.parse_args()
pe = pefile.PE(str(args.target))
exports = {row.name.decode(): row.address for row in pe.DIRECTORY_ENTRY_EXPORT.symbols if row.name}
data = bytearray(args.target.read_bytes())
rows = []
for name, expected in [('OwnedCaller', '0107020007011300'), ('OwnedCrtCaller', '0104010004420000')]:
    row = next(row.struct for row in pe.DIRECTORY_ENTRY_EXCEPTION if row.struct.BeginAddress == exports[name])
    offset = pe.get_offset_from_rva(row.UnwindData)
    assert data[offset:offset + 8].hex() == expected
    encrypted = bytes.fromhex('d6ad23595f327cd2')
    data[offset:offset + 8] = encrypted
    rows.append(dict(name=name, unwindRva=row.UnwindData, runtime=expected, disk=encrypted.hex()))
pe.close()
args.target.write_bytes(data)
args.receipt.write_text(json.dumps(dict(scope='Owned target only; restores exact runtime metadata before gate.', rows=rows), indent=2))
