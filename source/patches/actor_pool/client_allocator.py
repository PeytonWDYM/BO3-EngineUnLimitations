"""Append actor banks to native client allocations while preserving the original pointer lifetime."""
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
)


def prepare_client_allocation(code: CapturedCode,helper_address: int) -> Rewrite:
    """Extend valid one/two-client allocations. Keep the native count and original allocation CALL untouched."""
    for guard in OWNER_GUARDS:code.guarded(guard)
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
