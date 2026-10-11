"""Replay the captured cookie handler to test native-frame translation in temporary stack phases."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

PATCHES = Path(__file__).resolve().parents[2] / 'patches/actor_pool'
sys.path.insert(0, str(PATCHES))
from captured_code import CapturedCode, CodeGuard

HANDLER = CodeGuard(0x2BC3A04, 29, '53989c4a3df823fa742c0bebda04d4729c810916a7f81899cc2b885ae9c8997c')
COMMON = CodeGuard(0x2BC3A24, 99, 'b17460e875c3ee6c6e0ea3ad52fa5c3b2d83c39f2a7a3547dcb87eb185dd1b0d')


def run(module: Path, executable: Path, dependencies: Path, output: Path) -> dict:
    sys.path.insert(0, str(dependencies))
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_64, UC_HOOK_CODE
    import unicorn.x86_const as x64
    output = output.resolve()
    if (Path.home() / '.codex/labs/bo3-engine').resolve() not in output.parents or output.exists():
        raise ValueError('Use a new result file inside the private BO3 lab.')
    code = CapturedCode(module, executable)
    captured = [(code.base + guard.rva, code.guarded(guard)) for guard in (HANDLER, COMMON)]
    security_check = code.base + 0x2BC3AA0
    dispatcher, function, handler_data, image = 0x49000000, 0x49100000, 0x49200000, 0x30000000
    stack, native_frame, stop = 0x50000000, 0x50001000, 0x51000000
    cookie = 0x123456789ABCDEF0
    cases = []
    for offset in (0xE0, 0x2C0, 0x680, 0x1D90, 0x3D20, 0x5430):
        for depth in (0, 8, 16, 24, 32, 40):
            for mode in ('untranslated', 'offset-only', 'translated-frame'):
                machine = Uc(UC_ARCH_X86, UC_MODE_64)
                regions = [(dispatcher, 4096), (function, 4096), (handler_data, 4096), (image, 4096),
                           (stack, 0x10000), (stop, 4096), (security_check, 1)]
                pages = set()
                for address, size in regions + [(address, len(raw)) for address, raw in captured]:
                    pages.update(range(address & ~4095, (address + size + 4095) & ~4095, 4096))
                for page in sorted(pages):
                    machine.mem_map(page, 4096)
                for address, raw in captured:
                    machine.mem_write(address, raw)
                machine.mem_write(security_check, b'\xc3')
                machine.mem_write(stack, b'\xcc' * 0x10000)
                # The dispatcher and frame header are authored. All guarded native frames in this scope have no frame register.
                machine.mem_write(dispatcher + 8, struct.pack('<Q', image))
                machine.mem_write(dispatcher + 0x10, struct.pack('<Q', function))
                machine.mem_write(dispatcher + 0x38, struct.pack('<Q', handler_data))
                machine.mem_write(function, struct.pack('<III', 0, 1, 0x100))
                machine.mem_write(image + 0x100, bytes((1, 0, 0, 0)))
                temporary_frame = native_frame - depth
                cookie_offset = offset + depth if mode == 'offset-only' else offset
                machine.mem_write(handler_data, struct.pack('<I', cookie_offset))
                machine.mem_write(native_frame + offset, struct.pack('<Q', cookie ^ native_frame))
                initial_rsp = stack + 0xF008
                machine.mem_write(initial_rsp, struct.pack('<Q', stop))
                saved = {getattr(x64, 'UC_X86_REG_' + name): 0x100000000 + index
                         for index, name in enumerate(('RBX', 'RBP', 'RSI', 'RDI', 'R12', 'R13', 'R14', 'R15'))}
                saved.update({getattr(x64, 'UC_X86_REG_XMM' + str(index)): (index << 120) | 0x112233445566778899
                              for index in range(6, 16)})
                for register, value in saved.items():
                    machine.reg_write(register, value)
                machine.reg_write(x64.UC_X86_REG_RSP, initial_rsp)
                machine.reg_write(x64.UC_X86_REG_RCX, 0)
                machine.reg_write(x64.UC_X86_REG_RDX, native_frame if mode == 'translated-frame' else temporary_frame)
                machine.reg_write(x64.UC_X86_REG_R8, 0)
                machine.reg_write(x64.UC_X86_REG_R9, dispatcher)
                decoded = []

                def check(engine, address, size, unused):
                    decoded.append(engine.reg_read(x64.UC_X86_REG_RCX))
                    rsp = engine.reg_read(x64.UC_X86_REG_RSP)
                    engine.reg_write(x64.UC_X86_REG_RIP, struct.unpack('<Q', engine.mem_read(rsp, 8))[0])
                    engine.reg_write(x64.UC_X86_REG_RSP, rsp + 8)

                machine.hook_add(UC_HOOK_CODE, check, begin=security_check, end=security_check)
                machine.emu_start(code.base + HANDLER.rva, stop, count=1000)
                assert machine.reg_read(x64.UC_X86_REG_RIP) == stop
                assert machine.reg_read(x64.UC_X86_REG_RSP) == initial_rsp + 8
                assert all(machine.reg_read(register) == value for register, value in saved.items())
                assert machine.reg_read(x64.UC_X86_REG_RAX) == 1
                valid = decoded == [cookie]
                assert valid == (depth == 0 or mode == 'translated-frame')
                if mode == 'offset-only':
                    assert decoded == [cookie ^ native_frame ^ temporary_frame]
                cases.append({'cookieOffset': offset, 'temporaryStackBytes': depth, 'mode': mode,
                              'cookieMatches': valid, 'rejectedCandidate': not valid})
    result = {'passed': True, 'cases': cases, 'refusals': sum(case['rejectedCandidate'] for case in cases),
              'scope': 'Direct captured handler and common-helper replay. Dispatcher, frame header and final cookie check are authored. Frame translation is supplied as an argument, not implemented as a runtime bridge.',
              'sourceSha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'nativeGuards': [{'rva': hex(guard.rva), 'bytes': guard.size, 'sha256': guard.sha256} for guard in (HANDLER, COMMON)],
              'gameWrites': 0, 'activationAllowed': False, 'windowsExceptionDispatchVerified': False,
              'runtimeHandlerBridgeImplemented': False, 'cppCleanupVerified': False}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n')
    return {'passed': True, 'cases': len(cases), 'refusals': result['refusals'], 'output': str(output)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('module', 'executable', 'dependencies', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.module, args.executable, args.dependencies, args.output), indent=2))
