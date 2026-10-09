"""Export exact, checked migration hook inputs from the hash-verified capture."""
import argparse
import hashlib
import json
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--manifest', type=Path, required=True)
p.add_argument('--output', type=Path, required=True)
args = p.parse_args()
meta = json.loads(args.manifest.read_text())
image = bytearray(meta['imageSize'])
for part in meta['ranges']:
    data = (args.manifest.parent/part['file']).read_bytes()
    assert hashlib.sha256(data).hexdigest() == part['sha256']
    start = int(part['moduleOffset'], 0)
    image[start:start+len(data)] = data

def checked(rva, expected):
    original = bytes.fromhex(expected)
    assert image[rva:rva+len(original)] == original, f'Unexpected instruction at {rva:x}'
    return {'rva':rva, 'original':original.hex()}

entries = []
for rva, expected, wrapper, reentry, continuation in (
    (0x13619e0,'4889742410','ReceiveMigrationHeader','MigrationHeaderReentry',0x13619e5),
    (0x13617f0,'4053554156','ReceiveMigrationData','MigrationDataReentry',0x13617f5),
    (0x21f9aa0,'3b0d02d555157521','ReceiveMigrationHeaderAck','MigrationHeaderAckReentry',0x21f9aa8),
    (0x21fa750,'48895c2410','SendMigrationHeader','MigrationSendHeaderReentry',0x21fa755),
    (0x12e1c0,'48895c2408','LoadMigrationState','MigrationLoadReentry',0x12e1c5),
    (0x2277a60,'40574883ec20','FlushMigrationState','MigrationFlushReentry',0x2277a66)):
    entries.append(checked(rva,expected)|{'wrapper':wrapper,'reentry':reentry,'continuationRva':continuation})
guards=[]
for rva,size in ((0xb24c0,0x165),(0x13619e0,0x85),(0x13617f0,0x126),(0x21f9aa0,0x2b),
                 (0x21fa750,0xdc),(0x12e1c0,0x133),(0x1362330,0x130),
                 (0x20fc7a0,8),(0x20fc7b0,7),(0x20fc7c0,8),(0x20fc7d0,8),
                 (0x20fc7e0,0x20),(0x20fd0b0,0xc1),(0x20feb30,0x9b),(0x20fe510,0xb0),
                 (0x2277a60,0x114),(0x21fa38d,0x6c),(0x22587a0,0xe),(0x6b40,0x16),
                 (0x6b60,0x5a),(0x6bc0,0xf7),(0x61f0,0x8ce)):
    guards.append({'rva':rva,'size':size,'sha256':hashlib.sha256(image[rva:rva+size]).hexdigest()})
call = checked(0x1361a50,'e8db080000')|{'wrapper':'SendHeaderAck','originalTargetRva':0x1362330}
version = checked(0x12e226,'83f803741f')|{'wrapper':'MigrationVersionGate','acceptedRva':0x12e24a,'rejectedRva':0x12e22b}
count = checked(0xb253f,'bf00002800')|{'immediateOffset':1,'stockValue':0x280000,'replacementValue':32*1024*1024}
senderVersion = checked(0x21fa7ae,'c744245c03000000')|{'immediateOffset':4,'stockValue':3,'replacement':'configured wireVersion'}
record = {
    'status':'Checked integration inputs. No actual game, whole-state compressed roundtrip, deadline, or matching-peer game validation.',
    'executableSha256':'0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0',
    'imageSize':meta['imageSize'], 'enhancedModeValue':0,
    'bufferBytes':32*1024*1024,'maxProtocolBytes':32768*1200,
    'wireVersionEncoding':'0xc6000000 | (clientRootCount << 20) | serverTotal',
    'defaultServerTotal':500001,'clientRootCount':18,'legacyVersion':3,'legacyClientRootCount':8,
    'entryHooks':entries,'callHooks':[call],'branchHooks':[version], 'immediateEdits':[count,senderVersion],
    'nativeGetters':{'nativeHeader':0x20fc7d0,'nativeWriteState':0x20fc7c0},
    'selectedPeerGlobalRva':0x17756fa8,'headerAckRejectedRva':0x21f9ac9,
    'unallocatedPointerRvas':[0x3ec4ed8,0x3ec4ee0,0x3ec4ee8,0x3ec4ef0,0x16dbb638],
    'unallocatedCapacityRvas':[0x3ec4ef8,0x3ec4efc,0x16dbb640],
    'bindingRecords':{
        'Bo3MigrationBindings':{'bytes':64,'fields':{'wireVersion':0,'bufferBytes':4,'originalHeader':8,'originalData':16,'originalHeaderAck':24,'originalSendHeader':32,'originalAckSend':40,'nativeHeader':48,'nativeWriteState':56}},
        'Bo3MigrationVersionBranches':{'bytes':16,'fields':{'accepted':0,'rejected':8}},
        'Bo3MigrationLoadBindings':{'bytes':16,'fields':{'original':0,'error':8}},
        'Bo3MigrationReentries':{'bytes':56,'fields':{'header':0,'data':8,'headerAckAccepted':16,'selectedPeer':24,'sendHeader':32,'load':40,'headerAckRejected':48}},
        'Bo3MigrationFlushBindings':{'bytes':16,'fields':{'original':0,'continuation':8}}},
    'codeGuards':guards}
assert not args.output.exists()
args.output.write_text(json.dumps(record,indent=2)+'\n')
print(json.dumps({'entries':len(entries),'codeGuards':len(guards),'inventory':str(args.output)}))
