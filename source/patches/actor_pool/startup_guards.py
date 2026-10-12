"""Recover exact stock preimages from the pinned AAE crash capture during offline preparation."""

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
