"""Relocate the shared persistent animation-node pool within its complete 16-bit link domain."""
import json
from pathlib import Path
import struct

from captured_code import CapturedCode, CodeGuard, Rewrite, EXECUTABLE_SHA256

BANK_OFFSET=0xC000000
PHYSICAL_ROWS=1<<16
USABLE_ROWS=PHYSICAL_ROWS-1
RECORD_BYTES=0x58
BANK_BYTES=PHYSICAL_ROWS*RECORD_BYTES
ARENA_END=BANK_OFFSET+BANK_BYTES
NATIVE_POOL=0x17DF81E0
NATIVE_BYTES=6000*RECORD_BYTES
PREALLOCATION_GLOBALS=((NATIVE_POOL,NATIVE_BYTES),)
INITIALIZER_RVA=0x22C9BD0
INITIALIZER_BYTES=150
_INVENTORY=json.loads(Path(__file__).with_name('anim_info_inventory.json').read_text())
OWNER_GUARDS=tuple(CodeGuard(item['rva'],item['size'],item['sha256']) for item in (*_INVENTORY['codeGuards'],*_INVENTORY['metadataGuards']))


def _initializer(bank: int) -> bytes:
    """Build both circular free-list links. Keep node zero reserved and clear its native animation state."""
    body=bytearray(b'\x31\xC0\x49\xB8'+struct.pack('<Q',bank+0x40)+b'\xB9'+struct.pack('<I',PHYSICAL_ROWS)+b'\xBA'+struct.pack('<I',USABLE_ROWS)+b'\x45\x31\xC9')
    loop=len(body)
    body+=bytes.fromhex('4189104489caffc281e2ffff0000418950044489ca41ffc14983c058ffc9')
    body+=b'\x75'+struct.pack('<b',loop-(len(body)+2))
    body+=b'\x49\xB8'+struct.pack('<Q',bank)
    body+=bytes.fromhex('49894010498940184989402049894028c3')
    return bytes(body)+b'\x90'*(INITIALIZER_BYTES-len(body))


def prepare_anim_info_storage(code: CapturedCode, bank: int) -> tuple[Rewrite, ...]:
    """Prepare complete backing and initialization. Keep native allocation, release, codecs, and finite refusal."""
    if code.executable_sha256!=EXECUTABLE_SHA256:
        raise ValueError('Animation-node storage requires the exact admitted executable.')
    if bank&0xFFFF or bank<code.base+code.meta['imageSize'] or bank+BANK_BYTES>code.base+0x7FFFFFFF:
        raise ValueError('Animation-node storage requires a complete aligned bank outside the image within signed RIP reach.')
    for guard in OWNER_GUARDS:
        code.guarded(guard)
    edits=[]
    for operand in _INVENTORY['poolOperands']:
        rva=operand['rva']
        original=bytes.fromhex(operand['original'])
        if code.read(rva,len(original))!=original:
            raise ValueError(f'The native animation-node pool operand differs at RVA {rva:#x}.')
        replacement=bytearray(original)
        displacement=operand['displacementOffset']
        target=bank+operand['nativeTargetRva']-NATIVE_POOL
        replacement[displacement:displacement+4]=struct.pack('<i',target-(code.base+rva+len(original)))
        edits.append(Rewrite(f'anim_info_pool_{rva:x}',code.guard(rva,len(original)),bytes(replacement)))
    # The complete native leaf has no stack or nonvolatile-register use. Its location and metadata stay unchanged.
    edits.append(Rewrite('anim_info_initializer',code.guard(INITIALIZER_RVA,INITIALIZER_BYTES),_initializer(bank)))
    return tuple(edits)
