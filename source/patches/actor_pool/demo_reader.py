"""Prepare native demo playback and reset against the complete writer-owned prior-record storage."""
import struct

from captured_code import CapturedCode,CodeGuard,Rewrite
from demo_writer import DemoWriter
from x64_table import rel32

NATIVE_ACTOR_OFFSET=0x56757C
OWNER_GUARDS=(
    CodeGuard(0x25A4D40,1730,'fa97d693d2f02639b84cfe99718dd00852d90193920ed80c9a273c10f4eb102a'),
    CodeGuard(0x31DB6C0,36,'145d55c14b123be92e0433a7482a3a3b6bb5dbeffaf639192dbe04ae55f84423'),
    CodeGuard(0x25A9AB0,155,'553122ec598bb16cf17b95237f85dfcc12a4bb6e99cdaa6dd9e10c125840c598'),
    CodeGuard(0x31DABD4,8,'2d8867f028f39ef522d70e56d169d2fbb9046163869f9360ec470bdd2040cd24'),
)


def prepare_demo_reader(code: CapturedCode,storage: DemoWriter) -> tuple[Rewrite,...]:
    """Keep forty native record stores and both complete native frames. Their shared base carries the relocation."""
    for guard in OWNER_GUARDS:code.guarded(guard)
    if storage.base<code.base+code.meta['imageSize'] and code.base<storage.base+storage.bytes:
        raise ValueError('Demo prior-record storage overlaps the native image.')
    edits=[]
    for name,rva,expected,offset,replacement in (
        ('demo_reader_actor_bits',0x25A4E50,'ba06000000',1,struct.pack('<I',storage.shape.actors.bit_length())),
        ('demo_reader_prior_records',0x25A5055,'488d1524b0bb16',3,
         rel32(code.base+0x25A505C,storage.base-NATIVE_ACTOR_OFFSET)),
        ('demo_reset_prior_records',0x25A9AF2,'488d0d03db1117',3,rel32(code.base+0x25A9AF9,storage.base)),
        ('demo_reset_prior_bytes',0x25A9AF9,'41b800140000',2,struct.pack('<I',storage.bytes)),
    ):
        original=bytes.fromhex(expected)
        if code.read(rva,len(original))!=original:
            raise ValueError('A native demo playback or reset instruction differs.')
        edits.append(Rewrite(name,code.guard(rva,len(original)),original[:offset]+replacement))
    return tuple(edits)
