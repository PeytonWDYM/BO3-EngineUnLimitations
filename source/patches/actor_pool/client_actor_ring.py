"""Prepare complete native actor-ring storage with sixteen expanded snapshots of history."""
import struct

from captured_code import CapturedCode,CodeGuard,Rewrite
from shape import ActorShape

RING_RECORDS=8192
OWNER_GUARDS=(
    CodeGuard(0x13484E0,13340,'bfd45ac623d236578b003e480c9f8778af5ec55799c460f073107753f237b6af'),
    CodeGuard(0x312EF28,12,'33b509f8f3c1bada7d4ab58f43925faa47b3f6d2ea47fb52b84dcbbcb445297e'),
    CodeGuard(0x312EF34,36,'beb08f5e28f35bace3248186fcc52ce6ecc683f87aac16e6a454611913ca608d'),
    CodeGuard(0x312EF58,20,'c2a85f6f7387b03144843406b242337439474eceddff5b301547baf2e3b5e715'),
    CodeGuard(0x312EF6C,16,'6a625425d1432d741c8df68f7b970c5d731e0b7953719f04690201eed103401b'),
    CodeGuard(0x312EF7C,16,'af71a4da8cf420fd33236f00f374ba8ae6b96a06a9ac51e6bafcb900757ca2ca'),
    CodeGuard(0x312EF8C,36,'306e77c4ba74f86aaad6d9b46f38f967c9e4b9671b9cec76393564b0eca4089d'),
    CodeGuard(0x312EFB0,40,'764c6e07a521fc4e5795d48cf27e351ac8e8fb70f1aa10226a5c123798b1c7a1'),
    CodeGuard(0x14D4720,266,'d516b01e7860542c095f77b3af28e2efb89c9edd648fa8f5b5f906e93bdfb0ab'),
    CodeGuard(0x31442D0,20,'bb13e6c6a983c02cdabcec0406ca34d45ce7d54834c1237440984006a1b7ffe2'),
    CodeGuard(0x13655C0,942,'669a91c5d84aba1ac5aa753fac4ee46085448a009f03119c9ea027bbb03fd50c'),
    CodeGuard(0x3130048,24,'00b221af918f6a911ce707c5c368a9dbe92e27e36d8c16551d0af428cd7e61fc'),
    CodeGuard(0x3130064,20,'786fac421a7897ef733cae21840b89c3879ac657dc0bef3c8efe0525807812ae'),
    CodeGuard(0x3130078,20,'61796de6af67876f128a67d653b7dc4982609d54c949fd2812bf333b0cdd1f33'),
    CodeGuard(0x313008C,16,'b2a4706f17ed28c2a0c65eb54e73f73dc5f36b44616472e1892be8c00a725485'),
    CodeGuard(0x313009C,16,'cab877f85d47000f368fa8665c002171b7d23cca4aeb4f68b3bb62032495ddeb'),
)


def prepare_client_actor_ring(code: CapturedCode,shape: ActorShape) -> tuple[Rewrite,...]:
    """Change both native hunk passes through their shared instruction. Keep native modulo consumers and frames intact."""
    for guard in OWNER_GUARDS:code.guarded(guard)
    if RING_RECORDS<16*shape.actors:
        raise ValueError('The actor ring cannot retain sixteen complete expanded snapshots.')
    edits=[]
    for name,rva,expected,offset,value in (
        ('client_actor_ring_allocation',0x1349EB6,'ba00400100',1,RING_RECORDS*80),
        ('client_actor_ring_capacity',0x134B7B8,'c7415800040000',3,RING_RECORDS),
    ):
        original=bytes.fromhex(expected)
        if code.read(rva,len(original))!=original:
            raise ValueError('The native actor ring allocation or capacity instruction differs.')
        edits.append(Rewrite(name,code.guard(rva,len(original)),original[:offset]+struct.pack('<I',value)))
    return tuple(edits)
