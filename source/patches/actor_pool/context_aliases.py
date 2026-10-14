"""Relocate native actor members addressed through client and server TLS contexts."""
import struct

from captured_code import CapturedCode, CodeGuard, Rewrite, EXECUTABLE_SHA256
from client_actors import ClientActors

CLIENT_CONTEXT_OFFSET = 0x2E78B0
SERVER_CONTEXT_RVA = 0xA173A90

# Complete providers, native context bindings, the client reset, and their frame metadata.
GUARDS = (
    CodeGuard(0x188DF0, 12564, '7fff5f2a4328d7287bf152818e467daabb95857bb7b11f3e1abbdde4a07514a0'),
    CodeGuard(0x310735C, 16, '3efb60f9350fcd5bdafd41b719adf580b377ac1b2b9de6aaec4327464f683050'),
    CodeGuard(0x4746D0, 18912, '4592b93652e069bd3027c58c4999770ab8a48506bb9b895311c55ee86b41e58e'),
    CodeGuard(0x310E44C, 24, '4d7d7db0bb8833aead4167ea705ae26ede1a40e40c516e1df0f191300fcf8acc'),
    CodeGuard(0x497F40, 12756, '16a06f310aed6dde4659dd846bc429eeb1b4d940ce84b8825af255a570c2d4b0'),
    CodeGuard(0x310E3F8, 12, 'b1768b66ea6fe4d67ce401a4a52f87ca93e0695b351c81c3a627298bd5df4da8'),
    CodeGuard(0x310E404, 20, '9a51a97565d5e66d33a140c12eccfdea5e256d89e7b7e52bc9c22987a32eb115'),
    CodeGuard(0x310E418, 16, 'da521ac60b024e9a615f2eba399d1ed718d0dd6273feee6d420ba3ece16e1aa7'),
    CodeGuard(0x310E428, 20, 'c8eb44e1d77c2071647590131880a89c733f93d8fed655af9a0f8872b59e9b87'),
    CodeGuard(0x1B64780, 1093, '3a995ed36ca6e46731672a57d5c97f4d1427bd3bb0031a44aa17d17f915a72ad'),
    CodeGuard(0x3162A6C, 20, '753acad9fd6c52279607eb86e91b5df6acf845bbce2b46ec48e7b7126c4a8055'),
    CodeGuard(0x3162A80, 20, 'f5cdc3c5698058d1a691196a3abc3a79f4cacc8ea4fa60179fa6218fd54ecb67'),
    CodeGuard(0x3162A94, 36, 'a32d49c6c653820568ed989c00c83de886b7aa4721fc1b2e7bf967c2f92c4521'),
    CodeGuard(0x3162AB8, 24, '498d587b14d7d624205b4e1d81a0455e5ca01f81d0768d66df657d37a828a03d'),
    CodeGuard(0x3162AD0, 16, '9218773e466c4da33207d66f2d33ad2fffbabf46a8030b8621a7ab57d1c175d8'),
    CodeGuard(0x3162AE0, 16, '5840c01a81e2b61bf594a2997c59a19ab1e2c37f555e843a19633722023b8f68'),
    CodeGuard(0x24B2520, 1061, '48bc505ebb193efa19e83244b2e0d67d99ba2bb679fe5eeed4340d28fa7ca41c'),
    CodeGuard(0x31CF54C, 32, '4ab28e40429a30b223f535a7f41b8b3028d005de350fba8a7f4f91c45edcd528'),
    CodeGuard(0x8ED490, 24328, '6a067e7a03998c4108abe707c5b7e2d83b73681747d537c2f5d5f7c7081205d8'),
    CodeGuard(0x31164A8, 40, '00ed29ff885ce371f745f418519a43ec06989017210fc035110b47e280a957d0'),
    CodeGuard(0x19CA570, 93492, 'b07da6ea8a83315ad476cbdc65222d588eef13de575e424587cd71ad442bf3ee'),
    CodeGuard(0x3159648, 36, '1d319e56b89b079ebc7254b4c56902438ccd512b056e0d2aea582494dd849775'),
    CodeGuard(0x93E90, 334, 'eaa89ef724f67c5ae3f263b0fc47c7f2ec6d628eee7c41aa1e39b94c09a72c14'),
    CodeGuard(0x30FF5B0, 16, '63cfd0d40a89a36756c950e5d7bd3fe1d0bdb088a5df99eef68233f889ff7d28'),
    CodeGuard(0x1013020, 49612, 'c2f7daa9e6dd65adeb080ded5c21ec8b8efed2625b0a117a86e303bc894d5c8f'),
    CodeGuard(0x3120880, 24, 'ea31c76bf5017af04a5899443ab0553840d6302f22a870ef791eaff01b567e39'),
    CodeGuard(0x20F5ED0, 44, '0e99c51446805ed8fa9915efda2dd4b55c2c1a2953e7bfb3030ba65d1282f82a'),
)
CLIENT_SITES = (
    ('client_actor_context_state', 0x18BE3B, '4805e80c0100', 2, 0xB8),
    ('client_actor_context_record', 0x47778A, '4805300c0100', 2, 0),
    ('client_actor_context_state_pointer', 0x49B05F, '4883bc08f80c010000', 4, 0xC8),
)
SERVER_SITES = (
    ('server_actor_context_model_clear', 0x1B64993, '4c89a408b8160100'),
    ('server_actor_context_model_set', 0x24B25D2, '48898411b8160100'),
)


def prepare_context_aliases(code: CapturedCode, clients: ClientActors, secondary_actor_bank: int) -> tuple[Rewrite, ...]:
    """Keep native TLS lifetime, record strides, branches, and frames. Change only member displacements."""
    target = secondary_actor_bank + 0xA88
    server_displacement = target - (code.base + SERVER_CONTEXT_RVA)
    if code.executable_sha256 != EXECUTABLE_SHA256:
        raise ValueError('The context aliases require the exact admitted executable.')
    if (secondary_actor_bank <= 0 or secondary_actor_bank & 15
            or secondary_actor_bank + clients.shape.secondary_actor_bytes > 0x800000000000
            or secondary_actor_bank < code.base + code.meta['imageSize'] and code.base < secondary_actor_bank + clients.shape.secondary_actor_bytes
            or not -(1 << 31) <= server_displacement < 1 << 31):
        raise ValueError('The complete server actor bank requires a separate aligned interval and signed context displacement.')
    for guard in GUARDS:
        code.guarded(guard)
    edits = []
    for name, rva, expected, field, member in CLIENT_SITES:
        value = clients.actor_offset + member - CLIENT_CONTEXT_OFFSET
        if not -(1 << 31) <= value < 1 << 31:
            raise ValueError('A client context member exceeds its signed native displacement.')
        original = bytes.fromhex(expected)
        if code.read(rva, len(original)) != original:
            raise ValueError('A native client context instruction differs.')
        replacement = original[:field] + struct.pack('<i', value) + original[field + 4:]
        edits.append(Rewrite(name, code.guard(rva, len(original)), replacement))
    for name, rva, expected in SERVER_SITES:
        original = bytes.fromhex(expected)
        if code.read(rva, len(original)) != original:
            raise ValueError('A native server context instruction differs.')
        edits.append(Rewrite(name, code.guard(rva, len(original)), original[:4] + struct.pack('<i', server_displacement),
                             context_relative_operands=((4, target, SERVER_CONTEXT_RVA),)))
    return tuple(edits)
