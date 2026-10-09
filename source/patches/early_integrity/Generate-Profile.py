"""Generate typed admission metadata from the public exact-build profile."""
import argparse
import hashlib
import json
import re
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
home=Path(__file__).parent
raw=(home/'exact_build_profile.json').read_bytes()
p=json.loads(raw)
identity=(home/'Identity.h').read_text()
expected=re.search(r'kProfileId\[\]="([0-9a-f]{64})"',identity).group(1)
def require(condition,message):
    if not condition:raise ValueError(message)
require(hashlib.sha256(raw).hexdigest()==expected,'Exact profile digest differs')
require(not args.output.exists(),'Use a new generated profile path')
require(p['executableSha256']=='0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0','Executable identity differs')
require(p['timestamp']==0x693d731e and p['imageSize']==0x1d74b000,'Image identity differs')
require(len(p['guards'])==14683 and sum(len(g['pointers']) for g in p['guards'])==7950,'Guard inventory differs')
require(p['siteCount']==len(p['sites'])==1069,'Checksum inventory differs')
require(p['publicationCount']==1079 and p['arenaSize']==36864 and p['relayStride']==32,'Publication geometry differs')
def array(b):return '{'+','.join(f'0x{x:02x}' for x in b)+'}'
lines=['#pragma once','#include "ProfileTypes.h"','namespace bo3::early_integrity {',
       f'inline constexpr std::array<Region,{len(p["regions"])}> kRegions{{{{']
lines += [f'Region{{{r["rva"]}u,{r["size"]}u}},' for r in p['regions']]
lines += ['}};',f'inline constexpr std::array<Site,{len(p["sites"])}> kSites{{{{']
for s in p['sites']:
    keys=['leaRva','storeRva','expectedRva','chainDestinationRva','computedReadRva','endpointRva',
          'computedLocalSlot','computedTableSlot','expectedTableSlot','indexSlot']
    lines.append('Site{'+','.join(str(s[k])+'u' for k in keys)+','+('true' if s['installerKind']=='split' else 'false')+'},')
lines+=['}};']
pointers=[v for g in p['guards'] for v in g['pointers']]
lines+=[f'inline constexpr std::array<ImagePointer,{len(pointers)}> kImagePointers{{{{']
lines += [f'ImagePointer{{{v["offset"]}u,{v["targetRva"]}u}},' for v in pointers]
lines+=['}};',f'inline constexpr std::array<Guard,{len(p["guards"])}> kGuards{{{{']
cursor=0
for g in p['guards']:
    lines.append(f'Guard{{{g["rva"]}u,{g["size"]}u,{cursor}u,{len(g["pointers"])}u,{array(bytes.fromhex(g["sha256"]))}}},')
    cursor+=len(g['pointers'])
lines+=['}};','}']
args.output.write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(hashlib.sha256(raw).hexdigest())
