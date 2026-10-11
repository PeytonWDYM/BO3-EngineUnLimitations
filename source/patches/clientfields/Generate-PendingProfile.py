"""Generate the exact callback manifest without reading or admitting a new game build."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'actor_pool'))
from pending_callbacks import load_inventory


def generate(inventory_path: Path,output: Path) -> None:
    inventory=load_inventory(inventory_path)
    rows,guards=inventory['instructions'],inventory['guards']
    if len(rows)!=17 or len(guards)!=7 or len({row['rva'] for row in rows})!=17:
        raise ValueError('The complete callback inventory is required.')
    def values(raw: bytes) -> str:return '{'+','.join(f'0x{value:02x}' for value in raw)+'}'
    lines=['#pragma once','#include "source/patches/clientfields/PendingProfile.h"','namespace bo3::clientfields {',
           'inline constexpr std::array<PendingInstruction,17> PendingInstructions{{']
    for row in rows:
        raw=bytes.fromhex(row['bytes'])
        if not (4<=len(raw)<=8 and row['operandSize'] in (1,4) and 0<=row['operandOffset']<=len(raw)-row['operandSize']
                and any(guard['rva']<=row['rva'] and row['rva']+len(raw)<=guard['rva']+guard['size'] for guard in guards)):
            raise ValueError('A complete callback instruction lacks its owner guard.')
        lines.append(f'{{0x{row["rva"]:x},{values(raw)},{len(raw)},{row["operandOffset"]},{row["operandSize"]},PendingOperand::{row["kind"].capitalize()}}},')
    lines+=['}};','inline constexpr std::array<enhanced::CodeGuard,7> PendingGuards{{']
    for row in guards:
        raw=bytes.fromhex(row['sha256'])
        if len(raw)!=32 or not 0<row['size']<=inventory['imageSize']-row['rva']:
            raise ValueError('A complete callback guard exceeds the image.')
        lines.append(f'{{0x{row["rva"]:x},{row["size"]},{values(raw)}}},')
    lines+=['}};','}']
    if output.exists():raise FileExistsError('Use a new generated header path.')
    output.write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('inventory','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();generate(args.inventory,args.output)
