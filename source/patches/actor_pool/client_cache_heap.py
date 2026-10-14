"""Relocate the native fixed cache heap before its constructor publishes the root."""
import struct
from captured_code import CapturedCode, CodeGuard, Rewrite, EXECUTABLE_SHA256
from client_allocator import DISPATCH_TARGETS
from x64_table import rel32

HEAP_OFFSET = 0x2D00000
HEAP_BYTES = 0x200000
MAX_CENTITY_OWNERS = 2*0x700
# Startup must refuse a nonzero root before publishing these constructor edits.
# The native constructor later publishes the relocated heap through this root.
PREALLOCATION_GLOBALS = ((0x421F650, 8),)
OWNER_GUARDS = (
    CodeGuard(0xD3000,83,'cc82788a317d366137ff4f35b2764badb0584824009d7e59bc10340af5d8b030'),
    CodeGuard(0x3101D50,12,'39455c244cd3d4de53471a0adec96067c74300ddc0ba6db9733fe8f8e3a9ffc4'),
    CodeGuard(0x1CCA10,191,'4e9885ebcab2e0fe2ca07e291504a317727987fded294a543443e36d655240c9'),
    CodeGuard(0x31086C8,12,'39455c244cd3d4de53471a0adec96067c74300ddc0ba6db9733fe8f8e3a9ffc4'),
    CodeGuard(0x1D6130,74,'d916d56d68c09be94d55ff0183511e53d0836f700589aeabce12402c4e0527a2'),
    CodeGuard(0x3108488,8,'d96cb7a0d04bf5d2509d3676f472b175e1d7f107531c4264997ac82e084b19fd'),
    CodeGuard(0xFEEDF0,1203,'c12faed7c55d0be5dc79658260c820360360e451b7eb213bfe146a95565e7d30'),
    CodeGuard(0x31207B4,32,'3d05cd8e290947b0681bebfc7e55e5c7e1a551d63353d0885b6589235720f255'),
    CodeGuard(0x2275AD0,530,'4b66f2a2011e29ebffecb0ed617e739a149ffd45291dfb9154406f42a7a42f22'),
    CodeGuard(0x31BF8C0,32,'03935b26dc125638839ff027abfb7a2090c4f9ab81d1cc82cd42843d46ae7be4'),
    CodeGuard(0x2275D20,401,'90e7f8abcdada043a18b6c95fa3e43ae759c7cdfeeddad2b5989c2a2670414f9'),
    CodeGuard(0x31BF900,28,'21f84ac13ac05cba85a78d693ab91eb97d51d34572981f7cc1173c2a178dc06a'),
    CodeGuard(0x2275EC0,141,'6b116678dba5b5d63f4c4ec2598aaad61e8bccc30eadf84e692ee64b91bee480'),
    CodeGuard(0x31BF8B0,16,'63cfd0d40a89a36756c950e5d7bd3fe1d0bdb088a5df99eef68233f889ff7d28'),
    CodeGuard(0x2275F50,40,'1ff4a1aeae34ac0fc0ab223aaecb4379a6cec5e817f391788ef71cf124cd6dcb'),
    CodeGuard(0x22773A0,18,'88a681a92fb350e296bc388fecd30d426bd2cb71d8cbbe6bed5170a50978c911'),
    CodeGuard(0x2277460,22,'f7f24df97c1df44f84e8cf1d4ae7836e00641795b170155f120aaf1fa20f4695'),
    CodeGuard(0x22774E0,18,'8656ec5c4bf447bf212407ee1619ae3bcc723f2550cce9ee7b78e5453b25ab58'),
    CodeGuard(0x2277500,18,'c819673ec31c740c47c6f2f1c24c6316dbfd84cf339d4f344e2b5f48f6ceb146'),
    CodeGuard(0x2BC53B0,266,'baf5a61cf2523bd8cb2344c295fc4d67b0d26db33222cbf725aff6c18988e55e'),
    CodeGuard(0x3243198,4,'67abdd721024f0ff4e0b3f4c2fc13bc5bad42d0b7851d456d88d203d15aaa450'),
    CodeGuard(0x33C28F0,200,'f25de316725c60beb15622b0b700b79c54fe2facba800219dfd91b3ecdab3bad'),
    CodeGuard(0x2F25010,9,'b7f5f645376b825e22b51d21e97e1ba04c904daea5c05e93b3cc3cbf542f5765'),
)


def prepare_client_cache_heap(code: CapturedCode, arena: int) -> tuple[Rewrite, ...]:
    """Keep native allocation, cache rows, release, and frames. Change only size and backing operands."""
    if code.executable_sha256 != EXECUTABLE_SHA256:
        raise ValueError('The client cache heap requires the exact admitted executable.')
    if arena&0xFFFF or arena < code.base+code.meta['imageSize'] or arena+HEAP_OFFSET+HEAP_BYTES > code.base+0x7FFFFFFF:
        raise ValueError('The client cache heap requires complete aligned actor storage within relative reach.')
    for guard in OWNER_GUARDS:
        code.guarded(guard)
    actual = struct.unpack('<25Q',code.read(0x33C28F0,200))
    if actual != tuple(code.base+target for row in DISPATCH_TARGETS for target in row):
        raise ValueError('The native heap dispatch bindings differ.')
    return (
        Rewrite('client_cache_heap_capacity',code.guard(0x1D6147,5),b'\xBA'+struct.pack('<I',HEAP_BYTES)),
        Rewrite('client_cache_heap_backing',code.guard(0x1D6162,7),b'\x48\x8D\x0D'+rel32(code.base+0x1D6169,arena+HEAP_OFFSET)),
    )
