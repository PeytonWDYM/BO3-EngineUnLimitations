"""Recover exact preallocation bytes from the pinned initialized AAE capture."""

import hashlib

# Both complete stock owners match two saved admitted startup dumps and the passive startup image.
# These are offline source corrections. Runtime admission still hashes the complete native owners.
STOCK_PREIMAGES=(
    (0x19D15DC,bytes.fromhex('e881ea7680'),bytes.fromhex('e87ff57100')),
    (0x20EC0B0,bytes.fromhex('e99e4cf0fd'),bytes.fromhex('4c894c2420')),
)


def stock_preimages(read):
    """Require the exact researched capture hooks before returning their stock instructions."""
    for rva,captured,original in STOCK_PREIMAGES:
        if read(rva,len(captured))!=captured:
            raise ValueError(f'The pinned AAE source hook differs at RVA {rva:#x}.')
    return tuple((rva,original) for rva,_,original in STOCK_PREIMAGES)


def field_preimages(read):
    """Admit the captured initialized field, then model its observed cold startup state.

    The guarded CRT initializer constructs this descriptor after the launcher barrier.
    This correction changes offline source reads only. The launcher never writes the descriptor.
    """
    if hashlib.sha256(read(0x33FFB20,32)).hexdigest()!='64c0656b327ba05cceb3a028d1f6e1f3431937b956decf2d2dd8b0f0efb81753':
        raise ValueError('The captured initialized sentient field descriptor differs.')
    return ((0x33FFB20,bytes(32)),)
