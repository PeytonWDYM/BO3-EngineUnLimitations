"""Create a private inert address image from one identity-checked stock startup dump."""
import argparse, hashlib, json, struct, sys
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--dump',type=Path,required=True)
p.add_argument('--inventory',type=Path,required=True)
p.add_argument('--dependencies',type=Path,required=True)
p.add_argument('--output',type=Path,required=True)
a=p.parse_args()
sys.path.insert(0,str(a.dependencies))
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'reverse'))
from dump_memory import DumpMemory, verify_identity
inventory=json.loads(a.inventory.read_text(encoding='utf-8-sig'))
assert len(inventory['codeGuards'])==82 and len(inventory['serverCountInstructions'])==19
identity_file=a.dump.parent/'process.json'
identity=json.loads(identity_file.read_text(encoding='utf-8-sig'))
profile=dict(module='BlackOps3.exe',sha256=inventory['executableSha256'],imageSize=inventory['imageSize'],timestamp=inventory['timestamp'])
memory=DumpMemory(a.dump)
try:
    module=verify_identity(memory,profile,identity)
    records=[(0,memory.read(module.baseaddress,4096))]
    for guard in inventory['codeGuards']:
        raw=memory.read(module.baseaddress+guard['rva'],guard['size'])
        assert hashlib.sha256(raw).hexdigest()==guard['sha256']
        records.append((guard['rva'],raw))
    for count in inventory['serverCountInstructions']:
        raw=memory.read(module.baseaddress+count['rva'],len(bytes.fromhex(count['bytes'])))
        assert raw==bytes.fromhex(count['bytes'])
        records.append((count['rva'],raw))
    for rva,size in [(r,8) for r in (0x5124580,0x5124500,0x5124680,0x5124600,0x3ec4ed8,0x3ec4ee0,0x3ec4ee8,0x3ec4ef0,0x16dbb638)]+[(r,4) for r in (0x3ec4ef8,0x3ec4efc,0x16dbb640)]:
        raw=memory.read(module.baseaddress+rva,size)
        assert raw==bytes(size),hex(rva)
        records.append((rva,raw))
finally:
    memory.close()
raw=struct.pack('<I',len(records))+b''.join(struct.pack('<II',rva,len(data))+data for rva,data in records)
with a.output.open('xb') as out: out.write(raw)
def digest(path):
    with path.open('rb') as file:return hashlib.file_digest(file,'sha256').hexdigest()
a.output.with_suffix('.json').write_text(json.dumps(dict(scope='Inert owned mapping. No native BO3 instructions execute.',dump=str(a.dump),dumpSha256=digest(a.dump),identity=str(identity_file),identitySha256=digest(identity_file),inventorySha256=digest(a.inventory),seedSha256=hashlib.sha256(raw).hexdigest(),records=len(records),guards=82,counts=19),indent=2))
