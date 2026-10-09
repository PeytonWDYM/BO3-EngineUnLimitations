"""Compile two exact runtime CRT guards; owned builds use their plain native image."""
import argparse
import json
from pathlib import Path
import pefile

parser = argparse.ArgumentParser()
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--fixture', type=Path)
args = parser.parse_args()
if args.fixture:
    pe = pefile.PE(str(args.fixture))
    exports = {row.name.decode(): row.address for row in pe.DIRECTORY_ENTRY_EXPORT.symbols if row.name}
    directory = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
    guards = []
    for name in ('OwnedCaller', 'OwnedCrtCaller'):
        function = next(row for row in pe.DIRECTORY_ENTRY_EXCEPTION if row.struct.BeginAddress == exports[name])
        row = function.struct
        info = pe.get_data(row.UnwindData, 4)
        size = 4 + ((info[2] + 1) & ~1) * 2
        assert info[0] == 1
        guards.append(dict(tableRva=directory.VirtualAddress + pe.DIRECTORY_ENTRY_EXCEPTION.index(function) * 12,
                           begin=row.BeginAddress, end=row.EndAddress, unwindRva=row.UnwindData,
                           info=pe.get_data(row.UnwindData, size).hex(), code=pe.get_data(row.BeginAddress, 7 if name == 'OwnedCaller' else 4).hex()))
    profile = dict(timestamp=pe.FILE_HEADER.TimeDateStamp, imageSize=pe.OPTIONAL_HEADER.SizeOfImage, guards=guards)
else:
    profile = json.loads(Path(__file__).with_name('RuntimeUnwind.json').read_text())
    assert profile['imageSha256'] == '0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0'
assert len(profile['guards']) == 2
text = '#pragma once\nstruct RuntimeGuard {DWORD tableRva;RUNTIME_FUNCTION function;unsigned int infoSize,codeSize;unsigned char info[32],code[44];};\n'
text += f"constexpr DWORD kRuntimeTimestamp={profile['timestamp']}u,kRuntimeImageSize={profile['imageSize']}u;\n"
text += 'constexpr RuntimeGuard kRuntimeUnwind[]={\n'
for guard in profile['guards']:
    info, code = bytes.fromhex(guard['info']), bytes.fromhex(guard['code'])
    assert len(info) <= 32 and len(code) <= 44 and guard['begin'] < guard['end'] < profile['imageSize']
    text += '{'+str(guard['tableRva'])+'u,{'+','.join(str(guard[key])+'u' for key in ('begin','end','unwindRva'))+'},'
    text += f'{len(info)}u,{len(code)}u,'+'{'+','.join(map(str, info))+'},{'+','.join(map(str, code))+'}},\n'
text += '};\n'
args.output.write_text(text)
