"""Extend actor entity allocation through the guarded native normal-entity path."""
import struct
from captured_code import CodeGuard, Rewrite
from x64_table import Emitter, continuation_jump

# The miss is inside a live native frame: RBX saved at RSP+32, allocation 40.
# Publish this metadata for the complete stub, including the G_Spawn return PC.
ENTITY_ALLOCATOR_UNWIND = bytes.fromhex('010003000034040000420000')
ENTITY_ALLOCATOR_OWNER = (0x1B751E0, 0x1B75265, 0x31631D8)
MISS = CodeGuard(0x1B75227, 9, 'bb08b2ec794c05b71ef3ed21aaf6d9bd57765e877d48a40cc84b0da98bdbf468')
GUARDS = (
    CodeGuard(0x1B751E0,133,'9394b01b5e5033e8fb232f4586be4bbf521f740966e3334c2a817a7358562b74'),
    CodeGuard(0x1A865450,12,'57abacf60daf1bdc00966d55c71beefb10c072baaa65cd0332f2c27db693bae5'),
    CodeGuard(0x31631D8,12,'2fefb7eccf3d2523f1b82dd9f0437a1d05c7d076a929e5c78184566fb30f9438'),
    CodeGuard(0x1B75050,283,'c3b0cedbbbed8c29b1b759c1c5e9a58f36a4e80f418442a93ea858aafd0caa67'),
    CodeGuard(0x3162E90,8,'36061d653c465cef14e591e1b25fa110d6689baafda9d2fb58930b053eb510e2'),
    CodeGuard(0x1B6D850,6900,'62ec02cc1d0fba289139215721b0e8d42e78e391e9dfa35728bbd5225d37e100'),
    CodeGuard(0x21F33F0,60,'40bc92f206b63092e46d09296c5415ed2857970d30d2157c48027c6760730e7f'),
    CodeGuard(0x1B6B580,949,'13db53bf7cc881a516734f58945d9d30cd7ea5abb5b127f8571f397e219d63c9'),
    CodeGuard(0x24B6480,949,'b58ce0348843a34eeafd26abd1ffff1862bc388b326e5aa40edcb2f13d832054'),
    CodeGuard(0x24EF7F0,499,'8921ddf5f7903ee02cabf8b4bf2b6c7236e92ba377651a6d35785b008fc064d3'),
    CodeGuard(0x24B9D10,1061,'fd52d283dd94dc8213f9ca186baba5ef18897de6c485ed296010e55086b33d0a'),
    CodeGuard(0x24B2520,1061,'48bc505ebb193efa19e83244b2e0d67d99ba2bb679fe5eeed4340d28fa7ca41c'),
    CodeGuard(0x24AE5E0,295,'2bd295d4c09c88bab89bb1d878720a72aa843b4e2fa02bff8cd6d562e5b64fe5'),
    CodeGuard(0x24AE707,147,'68311ec4af383408fa4f6da9b16483c2a8e6cd7b0c6d43673ae672ab9a4c8220'),
    CodeGuard(0x24B5EB0,48,'9e5638fdf2a0c1459172d4d0c281d6f2e0398415baf6bd7c7de29078b15dd6b8'),
    CodeGuard(0x24B5EE0,35,'4f90f86f31cfdde4e18d9a78866de384a025ad1cc5cb4e055c90912ebee569a8'),
    CodeGuard(0x1B75170,109,'ca539d579fc079e5855c37b03f2d3eb4c096fe10e300ef2feadaa7ab691e2063'),
)


def prepare_entity_allocator(code, address: int) -> Rewrite:
    """Keep the 64 dedicated IDs, then use G_Spawn only when it can succeed.

    The native server thread owns the pool and its valid free chain. G_Spawn
    keeps its 500 ms reuse policy and generation update. Exhaustion returns
    null through the original epilogue, so native callers retain their retry.
    """
    for guard in GUARDS:
        code.guarded(guard)
    original = code.guarded(MISS)
    e = Emitter(address)
    available = address+48
    e.rip(b'\x48\x8b\x05', code.base+0xA1B0748)
    e.put(b'\x48\x85\xc0')
    e.rip(b'\x0f\x85', available)
    e.rip(b'\x8b\x05', code.base+0xA1B0744)
    e.put(b'\x3d\xfe\x03\x00\x00')
    e.rip(b'\x0f\x8c', available)
    # Retain the original miss diagnostics before the native null return.
    e.put(original[:2])
    target = code.base+MISS.rva+MISS.size+struct.unpack('<i', original[5:])[0]
    e.rip(original[2:5], target)
    e.put(continuation_jump(address+len(e.code), code.base+0x1B75230, 6))
    e.rip(b'\xe8', code.base+0x1B75050)
    e.put(continuation_jump(address+len(e.code), code.base+0x1B75246, 6))
    return Rewrite('actor_entity_allocator', MISS,
                   continuation_jump(code.base+MISS.rva, address, MISS.size),
                   address, bytes(e.code))
