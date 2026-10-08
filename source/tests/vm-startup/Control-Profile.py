"""Generate fixed compiled observation offsets; no runtime profile override."""
import argparse
from pathlib import Path
import pefile
parser=argparse.ArgumentParser()
parser.add_argument('--helper',type=Path,required=True)
parser.add_argument('--fixture',type=Path)
parser.add_argument('--output',type=Path,required=True)
args=parser.parse_args()
helper=pefile.PE(str(args.helper))
exports={r.name.decode():r.address for r in helper.DIRECTORY_ENTRY_EXPORT.symbols if r.name}
size,pool,hash_rva,name=494186496,0x5124580,0x5124500,'BlackOps3.exe'
if args.fixture:
    assert args.fixture.name=='VmStartupControlTarget.exe'
    fixture=pefile.PE(str(args.fixture))
    fixture_exports={r.name.decode():r.address for r in fixture.DIRECTORY_ENTRY_EXPORT.symbols if r.name}
    size,pool,hash_rva,name=fixture.OPTIONAL_HEADER.SizeOfImage,fixture_exports['ControlPool'],fixture_exports['ControlHash'],args.fixture.name
args.output.write_text('#pragma once\n'
    +f'constexpr wchar_t kControlTargetName[]=L"{name}";\n'
    +f'constexpr bo3::startup_control::Profile kControlProfile{{{size},{pool},{hash_rva},{exports["Bo3EnhancedBoot"]}}};\n')
