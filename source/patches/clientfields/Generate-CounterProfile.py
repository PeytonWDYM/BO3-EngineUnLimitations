"""Generate only the pinned exact-build clientfield counter manifest."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'actor_pool'))
from counters import load_inventory


def generate(inventory_path: Path,output: Path) -> None:
    inventory=load_inventory(inventory_path);rows,guards=inventory['instructions'],inventory['guards']
    if len(rows)!=11 or len(guards)!=3 or len({row['rva'] for row in rows})!=11:
        raise ValueError('The complete counter inventory is required.')
    def values(raw: bytes) -> str:return '{'+','.join(f'0x{value:02x}' for value in raw)+'}'
    names={'pool':'Pool','end':'End','lastField':'LastField','lastState':'LastState','lastCount':'LastCount','bytes':'Bytes','capacity':'Capacity'}
    lines=['#pragma once','#include "source/patches/clientfields/CounterProfile.h"','namespace bo3::clientfields {',
           'inline constexpr std::array<CounterInstruction,11> CounterInstructions{{']
    for row in rows:
        raw=bytes.fromhex(row['bytes'])
        if not (5<=len(raw)<=10 and row['operandSize']==4 and 0<=row['operandOffset']<=len(raw)-4
                and any(guard['rva']<=row['rva'] and row['rva']+len(raw)<=guard['rva']+guard['size'] for guard in guards)):
            raise ValueError('A complete counter instruction lacks its owner guard.')
        lines.append(f'{{0x{row["rva"]:x},{values(raw)},{len(raw)},{row["operandOffset"]},4,CounterOperand::{names[row["kind"]]}}},')
    lines+=['}};','inline constexpr std::array<enhanced::CodeGuard,3> CounterGuards{{']
    for row in guards:
        digest=bytes.fromhex(row['sha256'])
        if len(digest)!=32 or not 0<row['size']<=inventory['imageSize']-row['rva']:
            raise ValueError('A complete counter guard exceeds the image.')
        lines.append(f'{{0x{row["rva"]:x},{row["size"]},{values(digest)}}},')
    lines+=['}};','}']
    if output.exists():raise FileExistsError('Use a new generated header path.')
    output.write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('inventory','output'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();generate(args.inventory,args.output)
