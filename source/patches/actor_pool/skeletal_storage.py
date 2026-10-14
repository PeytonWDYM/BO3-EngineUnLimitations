"""Give both native skeletal contexts separate backing without changing their layout or reservation rules."""
import struct
from captured_code import CapturedCode, CodeGuard, Rewrite, EXECUTABLE_SHA256
from x64_table import rel32

BANK_OFFSET = 0x3000000
BANK_BYTES = 3072*384*32*2
TOTAL_BYTES = 2*BANK_BYTES
ARENA_END = BANK_OFFSET+TOTAL_BYTES
USABLE_BYTES = BANK_BYTES-16
PREALLOCATION_GLOBALS = ((0x535D188,8),)
LEAF_UNWIND = bytes.fromhex('01000000')
# The physical pool bounds one complete concurrent set. Repeated replacement can still reach native NULL refusal.
OWNER_GUARDS = (
    CodeGuard(0x13c3ba0,18932,'a0b2ab3d56978ac3000c6cbc059b610ca6cd4d4a0509e7f9cdd4427bb3cad6a0'),
    CodeGuard(0x13c8690,6320,'19cf879c884980ff990d70c0c49b9a524fee5636f9d6aa12ae5243940f92d521'),
    CodeGuard(0x135af70,6432,'68a3ca86a031f7d5e187acdfa33da313478b7288d0b516e57619902bb2657169'),
    CodeGuard(0x13c85a0,230,'340f224e759e9443d1868374def17f4ff585fcaa825f0c3237899e4743f5b1ee'),
    CodeGuard(0x1320470,230,'d5db0e8b860666fc1512d063ebebd6bd7ba753971431eb60eb0ee71afeccf5ab'),
    CodeGuard(0x22c48f0,13,'5fa85c5d10db14977ef4edae2eec049bb3e6cf835a8ad7ed04d2f95530b73289'),
    CodeGuard(0x22c4840,12,'932c904734c039ff32e820cb727254cabd3142702713a3ac2847ba67db186054'),
    CodeGuard(0x22c4830,5,'e3792235e13f88c92217aa0ee1a6372724453d3dec5cc2f2a02c0fe365852199'),
    CodeGuard(0x22c5a80,50,'020e9ac6c5718e0e67043b9c0c707078f8f4c4c87eef354f4ef38bdc8915eaf3'),
    CodeGuard(0x22bd550,1395,'f719a9c0a0cb0ad08006d3bcf1ccc4584fc74811670ddf1771c11778441eef16'),
    CodeGuard(0x20f5d80,326,'d781505c8f8d992bf3760e8a39a9c3f6d1ea3d6d1f82a0cbad27b6e8e51bd763'),
    CodeGuard(0x22bd440,270,'ecbb929baa7951dec75172ac40e4226acd89ee9e7f68771b137afca27f8ce5d0'),
    CodeGuard(0x22bdb80,259,'d579693fbd11b6c6dcfe114aca4e3565dd4c69a25ca3f9cd11fbe07047a18bf6'),
    CodeGuard(0x20f5f70,375,'aa7ea97629241b0558ed12b983f49483a57f03c31953823770057f4e843de6b9'),
    CodeGuard(0x1cde1f0,7,'a0d2c1a883dfbe999666bb02d28351b991a98d6ee6a8e7467b7035344bee1f8d'),
    CodeGuard(0x22be6f0,16,'2d71cd782371ec49b4d14d4081ed8ebf45dd07acc4644824a60d1ee0cb7af152'),
    CodeGuard(0x20f5f00,99,'0e1aea8c254c4ae8d60337e77834d9f0748c4894ff97e6a04fbf1b2649a8daa0'),
    CodeGuard(0x22c5a50,48,'c00756dad799ba29b4abdd717088c3e622ea0c946cce815638f4d1b7d8843d9c'),
    CodeGuard(0x22be990,43,'26b285d7502ff37f38d5dd7825d88f9ee91c450fcdbc51935c7cc14ce300a383'),
    CodeGuard(0x2bc53b0,266,'baf5a61cf2523bd8cb2344c295fc4d67b0d26db33222cbf725aff6c18988e55e'),
    CodeGuard(0x312c8d8,20,'b881660bef7d22e787c8bc4bf5f8bd10f894ab61198d1fdd7a6f6cec6eeba757'),
    CodeGuard(0x312c8ec,20,'b922a91a74ae1329a851e6f13d50382f02b8bcce072e231a5d73324aaca0ed68'),
    CodeGuard(0x312c900,16,'147553f1b509e4938f34932179cdff28f2c67caf68e33374df66caa7d2ff9ae2'),
    CodeGuard(0x312ec74,20,'07e19ccc61f47f28d70efdc0d8ef7f13410ae105172d95ab805dcde196a7daa3'),
    CodeGuard(0x3130198,24,'e499000ecc5e7fe9a406be676dc5ade384b8ee89e0e2eacdeea7534a0c30204d'),
    CodeGuard(0x31301b0,8,'695b6786ba263d1459079f96a26829169a6e8cd96fbb0ddde37255f5a1fe7918'),
    CodeGuard(0x31301b8,20,'b881660bef7d22e787c8bc4bf5f8bd10f894ab61198d1fdd7a6f6cec6eeba757'),
    CodeGuard(0x31301cc,20,'5a229af148169eb7dcaef65e883ce679ac6e7060e1181a958f5476cb8b1bc8ab'),
    CodeGuard(0x31301e0,16,'52e2c024a983d4820319dc1d564c6d304be63c0731f5e346127853f08d0fec74'),
    CodeGuard(0x31afee8,8,'2d8867f028f39ef522d70e56d169d2fbb9046163869f9360ec470bdd2040cd24'),
    CodeGuard(0x31aff0c,24,'5c073c4d3111efe74bedb64c38f8228a1b40f6ce6459739dc42411313655321f'),
    CodeGuard(0x31b0014,20,'8899cc2d12670b17c2dd230fddb92ee4d2cab4a950955f5855227395ddb54649'),
    CodeGuard(0x31c2244,24,'780cbbac1b8df5d91e9d421abc3303b30637edabdc69b366a8c6ec4c57dbb372'),
    CodeGuard(0x31c2398,12,'2a344160e2bc63111e571f2759717917973ffd9e7b8bba968fb4969796f44d66'),
    CodeGuard(0x31c23a4,20,'4c66150ab0372048fe6cae721b36b23b7ac9de42573a867633672c991f8be4e6'),
    CodeGuard(0x31c23b8,20,'359030290f9415573c952342fd502316cba3c1fc9ab144ea10343c6b27c416ce'),
    CodeGuard(0x31c23cc,16,'76d59f7c6c0c8155e16493b2e8d541bc4c93577baf670ec32a876c2fdcf64834'),
    CodeGuard(0x31c23dc,16,'8558c07b6a7fc8f395ee71f726799f73319936a073d28d025a90eaa221b65d04'),
    CodeGuard(0x31c263c,36,'291595b54c93b2741b77492012c2b039c81f7362e17378532fa49e7a78e39c51'),
    CodeGuard(0x31c2a08,8,'2d8867f028f39ef522d70e56d169d2fbb9046163869f9360ec470bdd2040cd24'),
    CodeGuard(0x3243198,4,'67abdd721024f0ff4e0b3f4c2fc13bc5bad42d0b7851d456d88d203d15aaa450'),
    CodeGuard(0x99d930,270,'147d6ea0f2226cb28bab3fe12ee918f0d01dc2c0cdc84570de88942f941d3829'),
    CodeGuard(0x3117888,20,'66ce41c75ec3c1618568dd1a6bb42d24cefdc1d48f5efa021fb71f9a266984f7'),
    CodeGuard(0x22c5310,59,'56137c6d74b2d1b537c6bd5f6b5bdcbaff1a6d1d609d0e8d1e64e248df240568'),
    CodeGuard(0x31c2aac,12,'39455c244cd3d4de53471a0adec96067c74300ddc0ba6db9733fe8f8e3a9ffc4'),
    CodeGuard(0x22c5b20,11,'b9a9a498cb834a138d98b12e5fc4188aba65a30daacc351bc84c40ab55fef96d'),
)


def prepare_skeletal_storage(code: CapturedCode, bank: int, address: int) -> tuple[Rewrite, ...]:
    """Select the local bank at native reset. Keep atomic reservation, generation, cache reuse, and finite refusal."""
    if code.executable_sha256 != EXECUTABLE_SHA256:
        raise ValueError('Skeletal storage requires the exact admitted executable.')
    end=bank+TOTAL_BYTES
    if bank&0xFFFF or bank<code.base+code.meta['imageSize'] or end>code.base+0x7FFFFFFF:
        raise ValueError('Skeletal storage requires two complete aligned banks outside the native image.')
    if address&15 or address<code.base+code.meta['imageSize'] or address+27>code.base+0x7FFFFFFF or address<end and address+27>bank:
        raise ValueError('The skeletal selector must be aligned, reachable, and separate from both banks.')
    for guard in OWNER_GUARDS:
        code.guarded(guard)
    if code.read(0x135C82C,11)!=bytes.fromhex('488d83ebb800004883e0f0') or code.read(0x13C84BF,6)!=bytes.fromhex('81fff0ff0f00'):
        raise ValueError('The native skeletal backing and end operands differ.')
    # RBX equals the decoded context root for client zero. Client one adds the unchanged native context stride.
    # The leaf writes only RAX. The original AND restores the promised flags after its comparison.
    leaf=bytes.fromhex('483b5d1848b8')+struct.pack('<Q',bank)+bytes.fromhex('740a48b8')+struct.pack('<Q',bank+BANK_BYTES)+b'\xC3'
    reset=b'\xE8'+rel32(code.base+0x135C831,address)+bytes.fromhex('4883e0f09090')
    return (
        Rewrite('skeletal_reset_backing',code.guard(0x135C82C,11),reset,address,leaf),
        Rewrite('skeletal_reservation_limit',code.guard(0x13C84BF,6),b'\x81\xFF'+struct.pack('<I',USABLE_BYTES)),
    )
