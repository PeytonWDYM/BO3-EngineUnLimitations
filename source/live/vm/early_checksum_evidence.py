"""Read-only evidence for the fixed early checksum publication. No code is executed."""
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import struct

from profile import integer

METHOD='late-crt-job-freeze-early-checksum'
GAME_SHA256='0b874dcc250848b7313ec13a0c76468dacc2009b5efa2bff4c587e169a9f77e0'
PROFILE_SHA256='b79d9e3e8d257fa2df8198c11cd8fc65b6f7cff428bef7e4a7dcb3d6c3ed8093'
ARENA_BYTES=36864

@dataclass(frozen=True)
class Site:
    rva:int
    destination:int
    expected_slot:int
    local_slot:int

    @property
    def original(self)->bytes:
        return b'\x48\x8d\x15'+struct.pack('<i',self.destination-self.rva-7)

@dataclass(frozen=True)
class EarlyChecksum:
    digest:str
    sites:tuple[Site,...]
    arena:int

    def verify(self,process)->bytes:
        base=process.module.baseaddress
        arena=bytearray(b'\xcc'*ARENA_BYTES)
        signature=hashlib.sha256()
        for index,site in enumerate(self.sites):
            address=self.arena+index*32
            expected=b'\xe9'+struct.pack('<i',address-base-site.rva-5)+b'\x90\x90'
            source=process.read(base+site.rva,7)
            if source!=expected:raise ValueError('An early checksum source hook differs.')
            relay=bytes((0x48,0x8b,0x55,site.expected_slot,0x8b,0x02,0x89,0x45,site.local_slot,0x48,0x8d,0x15))
            relay+=struct.pack('<i',base+site.destination-address-16)+b'\xe9'+struct.pack('<i',base+site.rva+7-address-21)
            arena[index*32:index*32+21]=relay
            signature.update(source)
        actual=process.read(self.arena,ARENA_BYTES)
        if actual!=arena:raise ValueError('The complete early checksum relay arena differs.')
        signature.update(actual)
        return signature.digest()

    def normalize(self,code:bytearray,start:int)->None:
        # authorize() verifies every complete source JMP before these partial range substitutions.
        for site in self.sites:
            low,high=max(start,site.rva),min(start+len(code),site.rva+7)
            if low<high:code[low-start:high-start]=site.original[low-site.rva:high-site.rva]

def load_early_checksum(process,profile:dict,session:dict,supplied:Path|None=None)->EarlyChecksum:
    if supplied is not None:
        if profile['status']!='fixture-only' or process.path.name.casefold()=='blackops3.exe' or process.sha256.casefold()==GAME_SHA256:
            raise ValueError('Early checksum overrides are limited to owned fixtures.')
        path=supplied;expected=profile['earlyChecksumFixtureSha256']
    else:
        path=Path(__file__).resolve().parents[2]/'patches/early_integrity/exact_build_profile.json';expected=PROFILE_SHA256
        if process.sha256.casefold()!=GAME_SHA256:raise ValueError('Unsupported early checksum game build.')
    raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
    if digest!=expected:raise ValueError('The fixed early checksum inventory changed.')
    data=json.loads(raw)
    if (data['executableSha256'].casefold()!=process.sha256.casefold() or data['timestamp']!=process.module.timestamp
            or data['imageSize']!=process.module.size or data['siteCount']!=1069 or len(data['sites'])!=1069
            or data['publicationCount']!=1079 or data['arenaSize']!=ARENA_BYTES or data['relayStride']!=32):
        raise ValueError('The early checksum inventory identity or geometry differs.')
    arena=integer(session['checksumArena'],'checksum arena',1,(1<<64)-ARENA_BYTES)
    sites=[];prior_end=0
    for row in data['sites']:
        rva=integer(row['leaRva'],'early checksum source',prior_end,process.module.size-7)
        destination=integer(row['chainDestinationRva'],'checksum chain',0,process.module.size-4)
        expected_slot=integer(row['expectedTableSlot'],'expected frame slot',0,127)
        local_slot=integer(row['computedLocalSlot'],'computed frame slot',0,127)
        sites.append(Site(rva,destination,expected_slot,local_slot));prior_end=rva+7
    return EarlyChecksum(digest,tuple(sites),arena)
