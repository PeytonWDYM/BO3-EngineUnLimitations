"""Emit owned relocation stubs. No process memory or executable file is modified."""

from dataclasses import dataclass
import struct

from table_layout import TableLayout, NATIVE_SENTIENT_BYTES, NATIVE_TABLE_OFFSET

REGISTERS = ('rax', 'rcx', 'rdx', 'rbx', 'rsp', 'rbp', 'rsi', 'rdi',
             'r8', 'r9', 'r10', 'r11', 'r12', 'r13', 'r14', 'r15')


def rel32(source_end: int, destination: int) -> bytes:
    displacement = destination-source_end
    if not -(1 << 31) <= displacement < (1 << 31):
        raise ValueError('A relative code or data address exceeds the x64 displacement range.')
    return struct.pack('<i', displacement)


class Emitter:
    def __init__(self, address: int):
        self.address = address
        self.code = bytearray()

    def put(self, value: bytes) -> None:
        self.code.extend(value)

    def rip(self, opcode: bytes, destination: int) -> None:
        self.put(opcode+rel32(self.address+len(self.code)+len(opcode)+4, destination))

    def push(self, register: str) -> None:
        number = REGISTERS.index(register)
        self.put((b'\x41' if number >= 8 else b'')+bytes([0x50+(number & 7)]))

    def pop(self, register: str) -> None:
        number = REGISTERS.index(register)
        self.put((b'\x41' if number >= 8 else b'')+bytes([0x58+(number & 7)]))

    def mov(self, destination: str, source: str) -> None:
        dst, src = REGISTERS.index(destination), REGISTERS.index(source)
        self.put(bytes([0x48 | ((src >> 3) << 2) | (dst >> 3), 0x89, 0xC0 | ((src & 7) << 3) | (dst & 7)]))

    def subtract(self, destination: str, source: str) -> None:
        dst, src = REGISTERS.index(destination), REGISTERS.index(source)
        self.put(bytes([0x48 | ((src >> 3) << 2) | (dst >> 3), 0x29, 0xC0 | ((src & 7) << 3) | (dst & 7)]))

    def add(self, destination: str, source: str) -> None:
        dst, src = REGISTERS.index(destination), REGISTERS.index(source)
        self.put(bytes([0x48 | ((src >> 3) << 2) | (dst >> 3), 0x01, 0xC0 | ((src & 7) << 3) | (dst & 7)]))

    def row_address(self, owner_register: str, pool_pointer: int, layout: TableLayout) -> None:
        self.mov('rax', owner_register)
        self.rip(b'\x48\x2b\x05', pool_pointer)
        self.put(b'\x31\xd2\xb9'+struct.pack('<I', NATIVE_SENTIENT_BYTES)+b'\x48\xf7\xf1')
        self.put(b'\x48\x69\xc0'+struct.pack('<I', layout.row_bytes))
        self.put(b'\x48\xb9'+struct.pack('<Q', layout.external_table)+b'\x48\x01\xc8')


@dataclass(frozen=True)
class MemberInstruction:
    original: bytes
    owner_register: str
    base_register: str
    index_register: str | None
    scale: int
    displacement: int
    modrm_offset: int
    displacement_offset: int
    displacement_size: int
    rex: int
    registers_used: frozenset[str]
    index_bias: int = 0
    trailing_original: bytes = b''
    native_offset: int = NATIVE_TABLE_OFFSET


def member_stub(instruction: MemberInstruction, address: int, pool_pointer: int,
                layout: TableLayout, continuation: int) -> bytes:
    # Use a register that the original operation does not read or write.
    candidates = ('r11','r10','r9','r8','rbx','rsi','rdi')
    scratch = next((r for r in candidates if r not in instruction.registers_used), None)
    if scratch is None or instruction.base_register == 'rsp':
        raise ValueError('The member instruction has no admitted scratch or owner binding.')
    original = instruction.original
    modrm = original[instruction.modrm_offset]
    memory_end = (instruction.displacement_offset+instruction.displacement_size if instruction.displacement_size
                  else instruction.modrm_offset+1+int((modrm & 7) == 4))
    number = REGISTERS.index(scratch)
    prefixes = bytearray(original[:instruction.modrm_offset])
    if instruction.rex:
        rex_position = prefixes.index(instruction.rex)
        prefixes[rex_position] = instruction.rex & 0xFC | (number >> 3)
    elif number >= 8:
        # Place REX after legacy prefixes and before the opcode.
        position = 0
        while prefixes[position] in (0x66,0x67,0xF2,0xF3):
            position += 1
        prefixes[position:position] = bytes([0x41])
    rewritten = bytes(prefixes)+bytes([(modrm & 0x38) | (number & 7)])+original[memory_end:]

    e = Emitter(address)
    e.put(b'\x9c')
    for reg in (scratch,'rax','rcx','rdx'):
        e.push(reg)
    # LEA uses the exact original memory encoding, with a new destination.
    memory = original[instruction.modrm_offset:memory_end]
    lea_modrm = bytes([(memory[0] & 0xC7) | ((number & 7) << 3)])+memory[1:]
    e.put(bytes([0x48 | ((number >> 3) << 2) | (instruction.rex & 3)])+b'\x8d'+lea_modrm)
    e.subtract(scratch, instruction.owner_register)
    e.put(bytes([0x48 | (number >> 3),0x81,0xE8 | (number & 7)])+struct.pack('<I',layout.native_offset))
    e.row_address(instruction.owner_register, pool_pointer, layout)
    e.add(scratch,'rax')
    for reg in ('rdx','rcx','rax'):
        e.pop(reg)
    # Restore input flags before the original operation. Keep its output flags.
    e.put(b'\xff\x74\x24\x08\x9d')
    e.put(rewritten)
    e.pop(scratch)
    e.put(b'\x48\x8d\x64\x24\x08')
    e.put(instruction.trailing_original)
    e.rip(b'\xe9',continuation)
    return bytes(e.code)


def accessor_stub(native_prefix: bytes, address: int, pool_pointer: int, layout: TableLayout) -> bytes:
    if len(native_prefix) != 34 or native_prefix[:3] != b'\x48\x2b\x15':
        raise ValueError('Use the admitted native target-index prefix.')
    e = Emitter(address)
    e.put(b'\x48\x83\xec\x10\x48\x89\x0c\x24')
    prefix = bytearray(native_prefix)
    prefix[3:7] = rel32(address+len(e.code)+7,pool_pointer)
    e.put(bytes(prefix))
    e.put(b'\x48\x89\x54\x24\x08')
    e.row_address('rcx',pool_pointer,layout)
    e.put(b'\x48\x8b\x54\x24\x08\x48\x8d\x0c\xd2\x48\x8d\x04\xc8')
    e.put(b'\x48\x8b\x0c\x24\x48\x83\xc4\x10\xc3')
    return bytes(e.code)


def clear_stub(address: int, pool_pointer: int, layout: TableLayout,
               continuation: int, owner_register: str | None, original: bytes) -> bytes:
    e = Emitter(address)
    e.put(b'\x9c')
    for reg in ('rax','rcx','rdx','rdi'):
        e.push(reg)
    if owner_register is None:
        e.put(b'\x48\xb8'+struct.pack('<Q',layout.external_table))
        size = layout.table_bytes
    else:
        e.row_address(owner_register,pool_pointer,layout)
        size = layout.row_bytes
    e.put(b'\x48\x89\xc7\x31\xc0\xb9'+struct.pack('<I',size//8)+b'\xfc\xf3\x48\xab')
    for reg in ('rdi','rdx','rcx','rax'):
        e.pop(reg)
    e.put(b'\x9d'+original)
    e.rip(b'\xe9',continuation)
    return bytes(e.code)


def load_entry_stub(address: int, pool_pointer: int, layout: TableLayout,
                    continuation: int, native_clear_prefix: bytes) -> bytes:
    e = Emitter(address)
    e.push('rdx')
    e.row_address('rbp',pool_pointer,layout)
    e.put(b'\x48\x89\xc1\x48\x8d\x04\xdb\x48\x8d\x0c\xc1')
    e.pop('rdx')
    e.put(native_clear_prefix)
    e.rip(b'\xe9',continuation)
    return bytes(e.code)


def count_stub(address: int, count: int, below: int, continuation: int,
               register: str = 'rax', condition: int = 0x82) -> bytes:
    e = Emitter(address)
    if register not in ('rax','r8') or condition not in (0x82,0x8C,0x8D):
        raise ValueError('Use an admitted native counter and branch condition.')
    e.put((b'\x48' if register == 'rax' else b'\x49')+b'\x81\xf8'+struct.pack('<I',count))
    e.rip(bytes([0x0F,condition]),below)
    e.rip(b'\xe9',continuation)
    return bytes(e.code)
