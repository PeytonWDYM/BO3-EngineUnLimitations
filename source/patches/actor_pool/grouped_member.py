"""Map four exact native member groups with one saved external-table address."""
from dataclasses import dataclass, replace

from captured_code import CapturedCode, CodeGuard
from table_layout import TableLayout
from x64_table import MemberInstruction, mapped_member_instruction, member_stub


@dataclass(frozen=True)
class MemberGroup:
    rva: int
    instruction_bytes: int
    count: int
    sha256: str

    @property
    def size(self) -> int:
        return self.instruction_bytes*self.count


GROUPS = (
    MemberGroup(0x1648F1A,8,3,'dc2dd849ef850fb59997d5da53b588d132867e3fdf9235e60d5b6b99613ec8a1'),
    MemberGroup(0x164D1BF,10,3,'838300f2d29f34d560cd9e055642a53ceac7da4efbe47207a0001908b8a44932'),
    MemberGroup(0x24B1053,9,2,'4d8d66840fd6211a1b6d2208366623e5a2dab44726369b49e558b1f06e66d791'),
    MemberGroup(0x2506437,8,9,'72e50aacde2ccbe6e0b8fbdef2932b5be5a5de74ebc992ce83868d4a330865f7'),
)
# The complete owner admits fifteen computed destinations. None enters a group interior.
OWNER_JUMP_TABLE = CodeGuard(0x1648F98,60,'1c537c119c2ed405b30f421379e876e36a6466fd8f368a400bcf5846daf6a050')


def group_at(rva: int) -> MemberGroup | None:
    return next((group for group in GROUPS if group.rva <= rva < group.rva+group.size),None)


def group_stub(group: MemberGroup, members: tuple[MemberInstruction, ...], address: int,
               pool_pointer: int, layout: TableLayout, continuation: int) -> bytes:
    """Keep the ordered native operations and restore their address inputs before the first operation."""
    first = members[0]
    address_contract = (first.owner_register,first.base_register,first.index_register,first.scale,first.native_offset)
    used = frozenset().union(*(member.registers_used for member in members))
    if (len(members) != group.count or 'r11' in used
            or any(len(member.original) != group.instruction_bytes or member.trailing_original
                   or (member.owner_register,member.base_register,member.index_register,member.scale,member.native_offset) != address_contract
                   for member in members)):
        raise ValueError('The complete native member group differs from its admitted address contract.')
    following = b''.join(mapped_member_instruction(member,'r11',member.displacement-first.displacement) for member in members[1:])
    return member_stub(replace(first,registers_used=used),address,pool_pointer,layout,continuation,following)


def guard_group(code: CapturedCode, group: MemberGroup) -> bytes:
    code.guarded(OWNER_JUMP_TABLE)
    return code.guarded(CodeGuard(group.rva,group.size,group.sha256))
