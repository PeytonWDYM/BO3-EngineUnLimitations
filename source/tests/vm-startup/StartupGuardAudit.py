"""Compare the stock startup function guard with a mature mod-loaded capture."""
import argparse
from bisect import bisect_right
import hashlib
import json
from pathlib import Path
import struct
import sys

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--startup', type=Path, action='append', required=True)
p.add_argument('--mature', type=Path, required=True)
p.add_argument('--inventory', type=Path, required=True)
p.add_argument('--dependencies', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
p.add_argument('--verify-corrected', action='store_true')
args = p.parse_args()
assert len(args.startup) == 2, 'Supply two independent startup snapshots.'
sys.path.insert(0, str(args.dependencies))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'reverse'))
import capstone
import pefile
from dump_memory import DumpMemory, verify_identity

RVA, SIZE = 0x12dba10, 195
STOCK = 'dae070c185bbc5e5132b0c82d7701c2cc515b9a9650ed32cae8f084e4c4c8a8d'
MATURE = '32f9310c16ed760d59d917c7f6a60a35d42a8c757e7bfd9bb8e3f44c1f3e7aca'
PROFILE = dict(module='BlackOps3.exe', sha256='0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0',
               imageSize=494186496, timestamp=1765634846)
inventory = json.loads(args.inventory.read_text(encoding='utf-8-sig'))
assert inventory['executableSha256'] == PROFILE['sha256']
guard, = [r for r in inventory['codeGuards'] if r['rva'] == RVA]
assert guard['ownerRva'] == RVA and guard['size'] == SIZE
output = args.output.resolve()
assert not output.is_relative_to(Path(__file__).resolve().parents[3])
output.mkdir(parents=True, exist_ok=False)
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()

def unwind(memory, module):
    pe = pefile.PE(data=memory.read(module.baseaddress,0x1000), fast_load=True)
    directory = pe.OPTIONAL_HEADER.DATA_DIRECTORY[3]
    pdata = memory.read(module.baseaddress + directory.VirtualAddress, directory.Size)
    rows = list(struct.iter_unpack('<III', pdata))
    index = bisect_right([r[0] for r in rows], RVA)-1
    row = rows[index]
    assert row[0] == RVA and row[1] == RVA+SIZE
    header = memory.read(module.baseaddress+row[2],4)
    count = header[2]
    assert header[0]&7 == 1 and not (header[0]>>3)&4
    length = 4+((count+1)&~1)*2
    record = memory.read(module.baseaddress+row[2],length+(4 if (header[0]>>3)&3 else 0))
    operations = []
    codes = record[4:4+count*2]
    slot = 0
    while slot < count:
        offset, operation = codes[slot*2:slot*2+2]
        if operation&15 == 1 and operation>>4 == 0:
            amount, = struct.unpack_from('<H',codes,slot*2+2)
            operations.append(dict(offset=offset,operation='allocate',bytes=amount*8)); slot += 2
        elif operation&15 == 0:
            operations.append(dict(offset=offset,operation='push',register=operation>>4)); slot += 1
        else:
            raise ValueError('Unexpected native prologue unwind operation.')
    assert operations == [dict(offset=19,operation='allocate',bytes=0x41f0),
        dict(offset=6,operation='push',register=15),dict(offset=4,operation='push',register=13),
        dict(offset=2,operation='push',register=3)]
    assert 6 <= header[1] < SIZE
    handler = struct.unpack_from('<I',record,length)[0] if (header[0]>>3)&3 else None
    assert handler is not None and handler < module.size
    return dict(beginRva=row[0],endRva=row[1],unwindRva=row[2],version=header[0]&7,
                flags=header[0]>>3,prologueBytes=header[1],codeCount=count,frame=header[3],
                handlerRva=handler,operations=operations,bytes=record.hex(),sha256=hashlib.sha256(record).hexdigest())

def capture(path, label, startup):
    identity_path = path.parent/'process.json'
    identity = json.loads(identity_path.read_text(encoding='utf-8-sig'))
    memory = DumpMemory(path)
    try:
        module = verify_identity(memory,PROFILE,identity)
        code = memory.read(module.baseaddress+RVA,SIZE)
        decoded = list(md.disasm(code,module.baseaddress+RVA))
        assert sum(i.size for i in decoded) == SIZE
        assert decoded[0].mnemonic == ('push' if startup else 'ret')
        if startup: assert decoded[0].op_str == 'rbx' and decoded[0].size == 2
        code_hash = hashlib.sha256(code).hexdigest()
        assert code_hash == (STOCK if startup else MATURE)
        assert code[0] == (0x40 if startup else 0xc3)
        pool, table = (memory.number(module.baseaddress+rva,'Q') for rva in (0x5124580,0x5124500))
        if startup: assert pool == table == 0
        record = dict(label=label,dump=str(path),dumpSha256=digest(path),identity=str(identity_path),
            identitySha256=digest(identity_path),pid=identity['pid'],startedUtc=identity['startedUtc'],
            executableSha256=identity['sha256'],moduleBase=hex(module.baseaddress),codeBytes=code.hex(),
            codeSha256=code_hash,poolPointer=hex(pool),hashPointer=hex(table),unwind=unwind(memory,module),
            guards=[dict(rva=r['rva'],size=r['size'],matches=hashlib.sha256(memory.read(module.baseaddress+r['rva'],r['size'])).hexdigest()==r['sha256'])
                    for r in inventory['codeGuards']],
            counts=[dict(rva=r['rva'],matches=memory.read(module.baseaddress+r['rva'],len(bytes.fromhex(r['bytes'])))==bytes.fromhex(r['bytes']))
                    for r in inventory['serverCountInstructions']])
        lines=[f'{i.address-module.baseaddress:08x} {i.bytes.hex()} {i.mnemonic} {i.op_str}' for i in decoded]
        (output/f'{label}.asm').write_text('\n'.join(lines)+'\n')
        (output/f'{label}.bin').write_bytes(code)
        return record
    finally:
        memory.close()

captures=[capture(path,f'startup-{i+1}',True) for i,path in enumerate(args.startup)]
captures.append(capture(args.mature,'mature',False))
assert (captures[0]['pid'],captures[0]['startedUtc']) != (captures[1]['pid'],captures[1]['startedUtc'])
assert captures[0]['codeBytes'] == captures[1]['codeBytes']
for row in captures:
    assert row['unwind'] == captures[0]['unwind']
    assert all(r['matches'] for r in row['counts'])
old, new = bytes.fromhex(captures[2]['codeBytes']),bytes.fromhex(captures[0]['codeBytes'])
changed = [i for i,(a,b) in enumerate(zip(old,new)) if a!=b]
assert changed == [0]
for row in captures[:2]:
    assert all(r['matches'] for r in row['guards'] if r['rva'] != RVA)
if args.verify_corrected:
    assert guard['sha256'] == STOCK
    assert all(r['matches'] for row in captures[:2] for r in row['guards'])
    # The mature capture also has the already documented AAE Com_Error detour.
    assert [r['rva'] for r in captures[2]['guards'] if not r['matches']] == [RVA,0x20ec0b0]
result=dict(passed=True,rva=RVA,size=SIZE,changedOffsets=changed,recommendedStockSha256=STOCK,
            inventorySha256=digest(args.inventory),inventoryGuardSha256=guard['sha256'],
            inventoryMatchesStock=guard['sha256']==STOCK,correctedGuardVerified=args.verify_corrected,
            matureGuardRejected=not next(r['matches'] for r in captures[2]['guards'] if r['rva']==RVA),captures=captures,
            harnessSha256=digest(Path(__file__)),
            provenance='Two independent pre-allocation captures prove the stock 40 prefix. The mature C3 is a runtime modification. This audit does not identify its writer.',
            scope='Read-only captured bytes and native instruction/unwind metadata. No live reads, game launch, deployment, guard bypass or alternate accepted hash.')
(output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({k:result[k] for k in ('passed','changedOffsets','recommendedStockSha256','inventoryMatchesStock')}))
