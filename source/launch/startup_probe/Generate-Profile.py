"""Build-pinned caller/observation offsets. Never accepts runtime profile overrides."""
import argparse,hashlib,json
from pathlib import Path
import pefile
parser=argparse.ArgumentParser()
parser.add_argument('--output',type=Path,required=True)
source=parser.add_mutually_exclusive_group(required=True)
source.add_argument('--capture',type=Path)
source.add_argument('--fixture',type=Path)
parser.add_argument('--refuse-fixture-identity',action='store_true')
a=parser.parse_args()
size,timestamp,caller,return_rva,allocator=494186496,1765634846,0x2be2020,0x2be2032,0x12df230
crt_return=0x2bd4124
pools=[0x5124580,0x5124500,0x5124680,0x5124600]
pointers=[0x3ec4ed8,0x3ec4ee0,0x3ec4ee8,0x3ec4ef0,0x16dbb638]
sizes=[0x3ec4ef8,0x3ec4efc,0x16dbb640]
if a.capture:
    assert not a.refuse_fixture_identity
    j=json.loads(a.capture.read_text(encoding='utf-8-sig'))
    proof=j['crtCallerProof']
    assert proof['callRva']==0x2bd411f and proof['returnRva']==crt_return and proof['wrapperRva']==caller
    encoded=bytes.fromhex(proof['callBytes'])
    assert len(encoded)==5 and encoded[0]==0xe8
    assert crt_return+int.from_bytes(encoded[1:],'little',signed=True)==caller
    raw=bytes.fromhex(j['earlyCallerBytes'])
    assert hashlib.sha256(raw).hexdigest()=='6154a242bdbf2f8efd1081690861ff1cd976cd3b3e4b5f58e3be780958b8c96f'
else:
    assert a.fixture.name=='VmStartupControlTarget.exe'
    pe=pefile.PE(str(a.fixture)); e={x.name.decode():x.address for x in pe.DIRECTORY_ENTRY_EXPORT.symbols if x.name}
    size,timestamp=pe.OPTIONAL_HEADER.SizeOfImage,pe.FILE_HEADER.TimeDateStamp
    if a.refuse_fixture_identity:timestamp^=1
    caller,return_rva,allocator=e['OwnedCaller'],e['OwnedReturn'],e['OwnedCaller']
    crt_return=e['OwnedCrtReturn']
    raw=pe.get_data(caller,44)
    assert raw[:7]==bytes.fromhex('4881ec98000000') and raw[28:33]==bytes.fromhex('b80a000000')
    assert return_rva==caller+18
    storage=e['ProbeStorage']
    pools=[e['ControlPool'],e['ControlHash'],storage+16,storage+24]
    pointers=[storage+32+i*8 for i in range(5)]
    sizes=[storage+80+i*4 for i in range(3)]
assert len(raw)==44 and caller<=return_rva<caller+44
checks=[(caller,44),(allocator,16)]+[(r,8) for r in pools+pointers]+[(r,4) for r in sizes]
assert all(0<=r and r+n<=size for r,n in checks)
text='#pragma once\n'
for name,value in [('ImageSize',size),('Timestamp',timestamp),('CallerRva',caller),('ReturnRva',return_rva),('AllocatorRva',allocator),('CrtReturnRva',crt_return),('WrapperCallerDelta',0xa0)]:text+=f'constexpr DWORD k{name}={value}u;\n'
for name,values in [('PoolRvas',pools),('MigrationPointerRvas',pointers),('MigrationSizeRvas',sizes)]:text+=f'constexpr DWORD k{name}[]={{'+','.join(str(r)+'u' for r in values)+'};\n'
text+='constexpr unsigned char kCallerBytes[]={'+','.join(str(v) for v in raw)+'};\n'
a.output.write_text(text)
(a.output.parent/'caller-profile-receipt.json').write_text(json.dumps({'source':str(a.capture or a.fixture),'sourceSha256':hashlib.sha256((a.capture or a.fixture).read_bytes()).hexdigest(),'callerSha256':hashlib.sha256(raw).hexdigest(),'imageSize':size,'timestamp':timestamp,'callerRva':caller,'returnRva':return_rva,'readRanges':checks},indent=2))
