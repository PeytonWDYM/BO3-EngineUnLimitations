"""Create an inert private MEM_IMAGE seed. Its entrypoint is zero."""
import argparse
import collections
import json
import struct
from pathlib import Path
import pefile

parser=argparse.ArgumentParser()
parser.add_argument('--profile',type=Path,required=True)
parser.add_argument('--guards',type=Path,required=True)
parser.add_argument('--captured-image',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
p=json.loads(args.profile.read_text())
guards=json.loads(args.guards.read_text())
capture=args.captured_image.read_bytes()
preferred=0x140000000
first=p['regions'][0]
last=p['regions'][-1]
first_size=(first['size']+p['regions'][1]['size']+4095)&~4095
sections=[(b'.ownedA',first['rva'],first_size,bytearray(first_size),0xe0000020),
          (b'.reloc',first['rva']+first_size,0x20000,bytearray(0x20000),0x42000040),
          (b'.gap',first['rva']+first_size+0x20000,last['rva']-(first['rva']+first_size+0x20000),bytearray(),0xc0000080),
          (b'.ownedB',last['rva'],last['size'],bytearray(last['size']),0xe0000020)]
def place(rva,raw):
    for _,start,size,data,_ in sections:
        if start<=rva and rva+len(raw)<=start+size:
            data[rva-start:rva-start+len(raw)]=raw
            return
    raise ValueError(f'Fixture seed leaves owned sections: {rva:x}')
for g in guards:
    place(g['rva'],bytes.fromhex(g['bytes']))
for site in p['sites']:
    for name in ['expectedRva','chainDestinationRva']:
        rva=site[name]
        place(rva,capture[rva:rva+4])
pointers={g['rva']+v['offset']:v['targetRva'] for g in p['guards'] for v in g['pointers']}
for rva,target in pointers.items():
    place(rva,struct.pack('<Q',preferred+target))
pages=collections.defaultdict(list)
for rva in sorted(pointers):pages[rva&~4095].append(0xa000|(rva&4095))
relocations=bytearray()
for page,entries in sorted(pages.items()):
    if len(entries)%2:entries.append(0)
    relocations+=struct.pack('<II',page,8+2*len(entries))+struct.pack('<'+'H'*len(entries),*entries)
assert len(relocations)<=sections[1][2]
sections[1][3][:len(relocations)]=relocations
header=bytearray(4096)
header[:2]=b'MZ'
struct.pack_into('<I',header,0x3c,0x80)
header[0x80:0x84]=b'PE\0\0'
struct.pack_into('<HHIIIHH',header,0x84,0x8664,len(sections),p['timestamp'],0,0,240,0x2022)
optional=0x98
struct.pack_into('<H',header,optional,0x20b)
struct.pack_into('<I',header,optional+16,0)
struct.pack_into('<Q',header,optional+24,preferred)
struct.pack_into('<II',header,optional+32,4096,512)
struct.pack_into('<HH',header,optional+40,6,0)
struct.pack_into('<HH',header,optional+48,6,0)
struct.pack_into('<II',header,optional+56,p['imageSize'],4096)
struct.pack_into('<HH',header,optional+68,3,0x160)
struct.pack_into('<QQQQ',header,optional+72,0x100000,4096,0x100000,4096)
struct.pack_into('<I',header,optional+108,16)
struct.pack_into('<II',header,optional+112,0x800,0x100)
struct.pack_into('<II',header,optional+112+5*8,sections[1][1],len(relocations))
# Ordinal one names an inert data byte in the read-only PE header.
struct.pack_into('<IIHHIIIIIII',header,0x800,0,p['timestamp'],0,0,0x880,1,1,1,0x850,0x854,0x858)
struct.pack_into('<I',header,0x850,0x900)
struct.pack_into('<I',header,0x854,0x8a0)
struct.pack_into('<H',header,0x858,0)
header[0x880:0x880+len(b'EarlyIntegrityOwnedImage.dll\0')]=b'EarlyIntegrityOwnedImage.dll\0'
header[0x8a0:0x8ab]=b'OwnedProof\0'
cursor=4096
for index,(name,rva,size,data,flags) in enumerate(sections):
    struct.pack_into('<8sIIIIIIHHI',header,0x188+index*40,name,size,rva,len(data),cursor if data else 0,0,0,0,0,flags)
    cursor+=len(data)
with args.output.open('wb') as stream:
    stream.write(header)
    for _,_,_,data,_ in sections:stream.write(data)
pe=pefile.PE(str(args.output))
assert pe.OPTIONAL_HEADER.AddressOfEntryPoint==0
assert pe.OPTIONAL_HEADER.SizeOfImage==p['imageSize']
assert len(pe.DIRECTORY_ENTRY_EXPORT.symbols)==1 and pe.DIRECTORY_ENTRY_EXPORT.symbols[0].ordinal==1
assert pe.DIRECTORY_ENTRY_EXPORT.symbols[0].address==0x900
print(json.dumps({'inertFixture':str(args.output),'bytes':args.output.stat().st_size,
                  'relocations':len(pointers),'entrypoint':0,'ordinal':1,'capturedCodeExecuted':False}))
