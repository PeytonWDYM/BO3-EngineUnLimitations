"""Restricted replay of the inspected eligibility bytecode inside the asset E2E.

ACTS independently identifies these operations. This replay reads the asset's
actual import target and branch deltas; it does not execute the complete GSC VM.
"""
import struct


def replay(script: bytes, owns_staminup: bool, upgraded: bool, beast: int | None, weapon: str) -> str:
    pc = 0xF51E
    values = []
    while pc not in (0xF56E, 0xF5AE):
        if pc == 0xF51E:
            function = struct.unpack_from('<I', script, 0x2ADBC)[0]
            if function == 0x88542FCF:
                values.append(owns_staminup)
            elif function == 0x3A6E4201:
                values.append(owns_staminup and upgraded)
            else:
                raise ValueError('Unexpected eligibility import.')
            pc = 0xF530
        elif pc in (0xF530, 0xF53E, 0xF54E):
            branch_when_true = pc != 0xF53E
            delta = struct.unpack_from('<h', script, pc + 2)[0]
            if bool(values[-1]) == branch_when_true:
                pc += 4 + delta
            else:
                values.pop()
                pc += 4
        elif pc == 0xF534:
            values.append(beast); pc = 0xF53C
        elif pc == 0xF53C:
            values[-1] = values[-1] is not None; pc = 0xF53E
        elif pc == 0xF542:
            values.append(beast); pc = 0xF548
        elif pc == 0xF548:
            values.append(script[pc + 2]); pc = 0xF54C
        elif pc in (0xF54C, 0xF568):
            right = values.pop(); left = values.pop(); values.append(left == right); pc += 2
        elif pc == 0xF552:
            values.append(weapon); pc = 0xF560
        elif pc == 0xF560:
            values.append('t6_xl_shockhands'); pc = 0xF568
        elif pc == 0xF56A:
            pc += 4 if values.pop() else 4 + struct.unpack_from('<h', script, pc + 2)[0]
        else:
            raise ValueError(f'Unexpected eligibility branch target {pc:#x}.')
    assert not values
    return 'grant' if pc == 0xF56E else 'remove'


def verify(before: bytes, after: bytes) -> list[dict]:
    rows = []
    for name, owns, upgraded, beast, weapon, old_expected, new_expected in (
        ('ordinary_staminup_no_upgrade', True, False, None, 'launcher_warmachinemp_zm', 'remove', 'grant'),
        ('upgraded_staminup', True, True, None, 'launcher_warmachinemp_zm', 'grant', 'grant'),
        ('without_staminup', False, False, None, 'launcher_warmachinemp_zm', 'remove', 'remove'),
        ('staminup_lost_upgrade_record_remains', False, True, None, 'lmg_death__machine_zm', 'remove', 'remove'),
        ('beast_mode', False, False, 1, 'launcher_warmachinemp_zm', 'grant', 'grant'),
        ('inactive_beast_mode', False, False, 0, 'launcher_warmachinemp_zm', 'remove', 'remove'),
        ('shock_hands', False, False, None, 't6_xl_shockhands', 'grant', 'grant'),
        ('staminup_with_another_gun', True, False, None, 'smg_standard_zm', 'remove', 'grant'),
    ):
        old = replay(before, owns, upgraded, beast, weapon)
        new = replay(after, owns, upgraded, beast, weapon)
        assert (old, new) == (old_expected, new_expected), name
        rows.append({'case': name, 'beforeBranch': old, 'afterBranch': new})
    return rows
