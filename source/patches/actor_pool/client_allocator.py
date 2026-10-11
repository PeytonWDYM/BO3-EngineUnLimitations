"""Append actor banks to native client allocations while preserving the original pointer lifetime."""
import struct
from captured_code import CapturedCode,CodeGuard,Rewrite
from client_actors import NATIVE_CLIENT_STRIDE as CLIENT_STRIDE,ACTOR_BANK_OFFSET as BANK_OFFSET
from x64_table import Emitter,rel32

OWNER_GUARDS=(
    CodeGuard(0x8408F0,13024,'afd659eb40367f31d01072232d9d6c66ecdc6bf003f0b62c2e9e8136673850ac'),
    CodeGuard(0x853D90,12812,'f62fea999d25b7887842964bbd018a396096a009a516a95727f6a4dd0b51ea89'),
    CodeGuard(0x8ED490,24328,'6a067e7a03998c4108abe707c5b7e2d83b73681747d537c2f5d5f7c7081205d8'),
    CodeGuard(0x3115684,24,'c797af2088b42a8ffc02d1a93a84d8757514fd09698e6008571de084cffa20ca'),
    CodeGuard(0x311569C,20,'2e7a84f31f588eacf1df34c8ef8cad70138264bae45bdd60f3fc8454a5228a64'),
    CodeGuard(0x31156B0,16,'0d008ec3f65e1a05fbe5e56248bf2f67e7a08776b2ab2b6cf1b9f546a97ae102'),
    CodeGuard(0x31156C0,20,'788454326c163f7e35845a89b0a6007469e85a981405c0afdb8b14eb96da5bb0'),
    CodeGuard(0x31164A8,36,'86479059d86938cd804d557a37a3c51e80f395e12248c9aaf632f421ab2660a6'),
    CodeGuard(0x135D330,418,'e1deed9977e48ab6b7d3be017fc127962b6f7637715a5db2ce86fccf5a4de1c9'),
    CodeGuard(0x85B990,6520,'30025f0cd588e2af61499b67e6882d7789d038586e5ed9be0951a0f817b856e9'),
    CodeGuard(0x2276D50,867,'e2b4766a82b0c52b76b73f8389038e161e62eed3fd32827883dc34110c8b7dbc'),
    CodeGuard(0x2277190,131,'c25af886cecaf390fec88200ab6f2ae0edd143483e5da4225b6d87dcbf6b5767'),
    CodeGuard(0x22773A0,18,'88a681a92fb350e296bc388fecd30d426bd2cb71d8cbbe6bed5170a50978c911'),
    CodeGuard(0x2277460,22,'f7f24df97c1df44f84e8cf1d4ae7836e00641795b170155f120aaf1fa20f4695'),
    CodeGuard(0x2277480,51,'14cc8774f59a7001497f1f389c1a004d4a0348f3d983d6e29ba59a39367bd655'),
    CodeGuard(0x22774E0,18,'8656ec5c4bf447bf212407ee1619ae3bcc723f2550cce9ee7b78e5453b25ab58'),
    CodeGuard(0x2277500,18,'c819673ec31c740c47c6f2f1c24c6316dbfd84cf339d4f344e2b5f48f6ceb146'),
    CodeGuard(0x3115C04,16,'6996b18d76fc8bd8369a82fb4e96ae3ba048369b76ed7219a2579bbc58fc040a'),
    CodeGuard(0x3115C14,32,'f574b73ba7bf8b6d458297cbe1ecebd81f04f67872305a761d7d82add13553cd'),
    CodeGuard(0x3115C34,16,'a06226aa71948b849cc30e84839fb6617d7ad985442fd515710b489a8cc40961'),
    CodeGuard(0x3115C44,32,'26eeee94bff3a65449457cf8afd98aee23d4b64a28204551b04b51dcf44e47a1'),
    CodeGuard(0x312F7A0,24,'a1061acab3642546e7b17e9f8f3c3bbedb0008594c20b21c81bb750e45318cae'),
    CodeGuard(0x31BFAB8,20,'bb13e6c6a983c02cdabcec0406ca34d45ce7d54834c1237440984006a1b7ffe2'),
    CodeGuard(0x31BFACC,8,'a7f7bf8f80627894f2b1c77ccea1666d562cd20304131c967ac639d96cbf6b37'),
    CodeGuard(0x31BFAD4,20,'b98c6e8492424e27119a504e3658b961e0e194ca3fb5f85523158b26dd512211'),
    CodeGuard(0x31BFAE8,20,'e21da9792801951a69cf1e9171182df8444126d5da7d18d631fc0fe44cf639f3'),
    CodeGuard(0x31BFAFC,16,'cedcba2873b9f917e50d46dc35f3eec935186b57f9668b45c46601bf3254d6a3'),
    CodeGuard(0x31BFB0C,16,'a79d086671265488d10ec679bb754e679815a9ef2e664cc3f3484770a8e27e8e'),
    CodeGuard(0x31BFB1C,8,'a7f7bf8f80627894f2b1c77ccea1666d562cd20304131c967ac639d96cbf6b37'),
    CodeGuard(0x31BFB24,20,'04014369a277c48156d1227078b3b97a6f800c8e500088bb097868edcd09f2bb'),
    CodeGuard(0x31BFB38,16,'6d442f0c9cb7a633707d6faf6798d3cb19e118eb3773913b5d4bf1fcaa50abf4'),
    CodeGuard(0x31BFB48,12,'dcdef798215bc4697ca983b28a079e09eb3ce8d99b1dfb5dc32254f859abd184'),
    CodeGuard(0x31BFB54,36,'1e3113d166fde39e67453caa3bb3a30a957eb5c484cc6f395ae4b30675b21b57'),
    CodeGuard(0x31BFB78,16,'8da49b00487eaea964ea5b09c1f677a06f015fd1e4a5cbfb6e0b10039e7464af'),
    CodeGuard(0x31BFAA0,8,'d96cb7a0d04bf5d2509d3676f472b175e1d7f107531c4264997ac82e084b19fd'),
)
# Five forty-byte records: create, reset, clear, allocate, release. Absolute pointers follow ASLR.
DISPATCH_TARGETS=(
    (0x2276D50,0x2276DE0,0x2276ED0,0x2276F20,0x22770B0),
    (0x22770C0,0x2277150,0x2277160,0x2277170,0x2277180),
    (0x2275EC0,0x2275F50,0x2275CF0,0x2275AD0,0x2275D20),
    (0x2276090,0x2276120,0x2276010,0x2275F80,0x2276030),
    (0x2277190,0x22771C0,0x22771D0,0x22771E0,0x2277210),
)


def prepare_client_allocation(code: CapturedCode,helper_address: int) -> Rewrite:
    """Extend valid one/two-client allocations. Keep the native count and original allocation CALL untouched."""
    for guard in OWNER_GUARDS:code.guarded(guard)
    actual=struct.unpack('<25Q',code.read(0x33C28F0,200))
    if actual!=tuple(code.base+target for row in DISPATCH_TARGETS for target in row):
        raise ValueError('The normalized native hunk dispatch bindings differ.')
    if (helper_address<=0 or helper_address&15 or helper_address+512>0x800000000000
            or helper_address<code.base+code.meta['imageSize'] and code.base<helper_address+512):
        raise ValueError('The client allocation stub requires a complete aligned code interval outside the native image.')
    original=bytes.fromhex('4869d220273400')
    if code.read(0x840922,7)!=original:
        raise ValueError('The original native client allocation product differs.')
    helper=Emitter(helper_address)
    helper.put(bytes.fromhex('4883fa01'))
    helper.rip(bytes.fromhex('0f8c'),helper_address+24)
    helper.put(bytes.fromhex('4883fa02'))
    helper.rip(bytes.fromhex('0f8f'),helper_address+24)
    helper.put(bytes.fromhex('4883c202'))
    helper.put(original)
    helper.rip(b'\xe9',code.base+0x840929)
    replacement=b'\xe9'+rel32(code.base+0x840922+5,helper_address)+b'\x90\x90'
    return Rewrite('client_appended_actor_bank_allocation',code.guard(0x840922,7),replacement,
                   helper_address,bytes(helper.code))
