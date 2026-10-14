"""Replay native cache heap creation, lookup, exhaustion, release, and reuse."""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import sys

PATCHES = Path(__file__).resolve().parents[2]/'patches/actor_pool'
sys.path.insert(0, str(PATCHES))
from captured_code import CapturedCode


def run(module: Path, executable: Path, native_replay: Path, lifecycle_replay: Path, output: Path) -> dict:
    output = output.resolve()
    lab = (Path.home()/'.codex/labs/bo3-engine').resolve()
    if output.exists() or lab not in output.parents or any(lab not in path.resolve().parents for path in (native_replay, lifecycle_replay)):
        raise ValueError('Use private native inputs and a new result folder in the BO3 lab.')
    from client_cache_heap import prepare_client_cache_heap, OWNER_GUARDS, HEAP_BYTES, HEAP_OFFSET, PREALLOCATION_GLOBALS
    code = CapturedCode(module, executable)
    arena = code.base+0x20000000
    edits = prepare_client_cache_heap(code, arena)
    assert len(edits) == 2 and all(not edit.stub and len(edit.replacement) == edit.guard.size for edit in edits)
    assert edits[0].guard.rva == 0x1D6147 and edits[0].replacement.hex() == 'ba00002000'
    assert edits[1].guard.rva == 0x1D6162 and HEAP_OFFSET == 0x2D00000
    assert PREALLOCATION_GLOBALS == ((0x421F650, 8),)
    assert HEAP_BYTES == 0x200000 and HEAP_OFFSET+HEAP_BYTES == 0x2F00000
    refusals = []
    class ChangedCode(CapturedCode):
        def read(self, rva, size):
            raw = bytearray(super().read(rva,size))
            if rva <= self.mutation < rva+size:
                raw[self.mutation-rva] ^= 1
            return bytes(raw)
    changed = object.__new__(ChangedCode)
    changed.__dict__.update(code.__dict__)
    for guard in OWNER_GUARDS:
        changed.mutation = guard.rva+guard.size//2
        try:
            prepare_client_cache_heap(changed, arena)
        except ValueError:
            refusals.append(hex(changed.mutation))
        else:
            raise AssertionError('An altered native cache contract escaped refusal.')
    for invalid in (arena+1, code.base, code.base+code.meta['imageSize']-0x10000, code.base+0x80000000, -0x10000):
        try:
            prepare_client_cache_heap(code, invalid)
        except ValueError:
            pass
        else:
            raise AssertionError('An invalid backing span escaped refusal.')
    sys.path.insert(0, str(native_replay.resolve().parent))
    replay = runpy.run_path(str(native_replay))
    assert replay['code'].executable_sha256 == code.executable_sha256 and replay['code'].base == code.base
    replay['run']()
    peak = runpy.run_path(str(lifecycle_replay))
    native_heap = replay['NativeHeap']
    heaps = []
    def owned_heap(capacity):
        assert capacity == HEAP_BYTES
        heap = native_heap(capacity, edits=edits)
        assert heap.heap == arena+HEAP_OFFSET
        heaps.append(heap)
        return heap
    peak['run'].__globals__['NativeHeap'] = owned_heap
    lifecycle = peak['run']()
    assert lifecycle['peaks'] == [{'localClients':1,'centityOwners':1792,'usedBytes':802880}, {'localClients':2,'centityOwners':3584,'usedBytes':1605696}]
    assert lifecycle['nativeReleaseCoalescingResetReuse'] and lifecycle['livePayloadsPreserved']
    substituted = {0x2242380, 0x2242730, 0x1191E0, 0x119190}
    executed = set().union(*(heap.executed_native for heap in heaps))
    uncovered = [hex(rva) for rva in sorted(executed-substituted) if not any(guard.rva <= rva < guard.rva+guard.size for guard in OWNER_GUARDS)]
    assert not uncovered, uncovered
    output.mkdir(parents=True)
    result = {'passed':True, 'nativeLifecycle':lifecycle, 'sourceGuardRefusals':refusals, 'invalidSpanRefusals':5,
              'nativeExecutedAddresses':len(executed), 'nativeSubstitutions':[hex(value) for value in sorted(substituted)],
              'preallocationZeroSpans':PREALLOCATION_GLOBALS, 'runtimeIntegrated':False, 'gameWrites':0,
              'edits':[{'name':edit.name,'rva':hex(edit.guard.rva),'replacement':edit.replacement.hex()} for edit in edits],
              'files':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in (Path(__file__),PATCHES/'client_cache_heap.py',native_replay,lifecycle_replay)},
              'limit':'Private single-thread native lifecycle. Profiler and TLS tracking endpoints are substituted. Live game, concurrent contention, and exception dispatch remain unverified.'}
    (output/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'passed':True,'sourceGuardRefusals':len(refusals),'nativeMaxOwners':3584,'output':str(output)},indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--module',type=Path,required=True)
    parser.add_argument('--executable',type=Path,required=True)
    parser.add_argument('--native-replay',type=Path,required=True)
    parser.add_argument('--lifecycle-replay',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args = parser.parse_args()
    run(args.module,args.executable,args.native_replay,args.lifecycle_replay,args.output)
