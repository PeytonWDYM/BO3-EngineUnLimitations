"""Bind the native one-based field getter to the complete expanded sentient pool."""
import struct

from captured_code import CapturedCode,CodeGuard,Rewrite
from shape import ActorShape,SENTIENT_BYTES

OWNER_GUARDS=(
    CodeGuard(0x1B14AC0,420,'6e26dbf40b709c4b6b624706692b8dab059e02cbecbc8f864183c8b49366b8da'),
    CodeGuard(0x3160F08,8,'d96cb7a0d04bf5d2509d3676f472b175e1d7f107531c4264997ac82e084b19fd'),
    CodeGuard(0x159A2B0,208,'271396a001efb09777b743e25a37cb69ea704f031cb1c1565d6bec293de46907'),
    CodeGuard(0x314872C,20,'35e41fcc6b8100dd284d13835e6d72cd48d074c71457aaf53548eb6627b5e251'),
    CodeGuard(0x33FFB20,32,'66687aadf862bd776c8fc18b8e9f8e20089714856ee233b3902a591d0d5f2925'),
    CodeGuard(0x2EE25F0,28801,'3b4cedc2d079abb49634d308f44477b3be79302630fa5ce9d87fd6469955b9d1'),
    CodeGuard(0x31D3DD4,24,'0cea504bb5b4f565bb7279d925cb4c75eed12d14edda826611e6977660bb9524'),
    CodeGuard(0x2FED858,14,'6ba1fd380c6dc0e002a29d0f94ddd8bb87c972b42dc28348bc114dc149b0b2fe'),
    CodeGuard(0x2F11F20,8,'f884f13a579081e741ee90abcf74d8eb4ce8bc0228525f19edfdbc85a7750828'),
)


def prepare_folded_sentient_storage(code: CapturedCode,native_pool: int) -> Rewrite:
    """Retain the type-11 zero branch and native frame. Only change the indexed load displacement."""
    extent=ActorShape(500).sentient_bytes
    displacement=native_pool-code.base-SENTIENT_BYTES
    if (native_pool<=0 or native_pool&15 or native_pool+extent>0x800000000000
            or native_pool<code.base+code.meta['imageSize'] and code.base<native_pool+extent
            or not -(1<<31)<=displacement<(1<<31)):
        raise ValueError('The complete sentient pool requires a separate aligned interval and signed native displacement.')
    for guard in OWNER_GUARDS:code.guarded(guard)
    # Native handles are one-based. The existing multiply therefore indexes a base biased by one record.
    original=code.read(0x1B14BC0,8)
    return Rewrite('sentient_folded_handle_storage',code.guard(0x1B14BC0,8),
                   original[:4]+struct.pack('<i',displacement),
                   image_relative_operands=((4,native_pool-SENTIENT_BYTES),))
