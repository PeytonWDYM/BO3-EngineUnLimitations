"""Record the exact owned helper loader surface without executing the helper."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import pefile

parser = argparse.ArgumentParser()
parser.add_argument('--bin', type=Path, required=True)
parser.add_argument('--dumpbin', type=Path, required=True)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--production', action='store_true')
args = parser.parse_args()
helper = args.bin / 'VmStartupHelper.dll'
pe = pefile.PE(str(helper))
imports = [{'module': item.dll.decode(), 'names': [entry.name.decode() if entry.name else entry.ordinal for entry in item.imports]}
           for item in pe.DIRECTORY_ENTRY_IMPORT]
assert {row['module'].lower() for row in imports} == {'kernel32.dll'}, imports
exports = {entry.name.decode(): entry.address for entry in pe.DIRECTORY_ENTRY_EXPORT.symbols if entry.name}
required = ('Bo3VmStateBindings', 'ReadNativeState', 'WriteNativeState', 'InsertNativeStateKey',
            'ClearNativeImportContext',
            'Bo3VmErrorBindings', 'ReadStateOrDrop', 'WriteStateOrDrop', 'VmErrorPrelude',
            'NativeOriginalReader', 'NativeOriginalWriter', 'NativeOriginalInsert', 'NativeOriginalError',
            'NativeOriginalInsertBody', 'VmErrorPreludeBody')
if args.production:
    required += ('Bo3EnhancedBoot',)
    assert not any(name.startswith('Fixture') for name in exports)
    assert not any(pe.get_data(exports['Bo3EnhancedBoot'], 24))
else:
    required += ('FixtureBindingReader', 'FixtureBindingWriter')
assert all(name in exports for name in required)
storage = pe.get_data(exports['Bo3VmStateBindings'], 48)
assert not any(storage)
assert not any(pe.get_data(exports['Bo3VmErrorBindings'],32))
prefixes = {'NativeOriginalReader': '48895c2410', 'NativeOriginalWriter': '48895c2408',
            'NativeOriginalInsert': '4053498bd8', 'NativeOriginalError': '4c894c2420'}
for name, expected in prefixes.items():
    assert pe.get_data(exports[name],5).hex() == expected, name
objects = {}
for name in ('Helper.obj', 'StateAdapter.obj', 'NativeStateBridge.obj', 'StateErrors.obj'):
    result = subprocess.run([str(args.dumpbin), '/headers', str(args.bin/name)], text=True,
                            capture_output=True, check=True)
    assert '.CRT$XCU' not in result.stdout, name
    objects[name] = {'sha256': hashlib.sha256((args.bin/name).read_bytes()).hexdigest(), 'dynamicCppInitializerTable': False}
callbacks = []
tls = None
if hasattr(pe, 'DIRECTORY_ENTRY_TLS'):
    record = pe.DIRECTORY_ENTRY_TLS.struct
    address = record.AddressOfCallBacks - pe.OPTIONAL_HEADER.ImageBase
    for index in range(64):
        callback = struct.unpack('<Q', pe.get_data(address+index*8, 8))[0]
        if not callback:
            break
        rva = callback-pe.OPTIONAL_HEADER.ImageBase
        callbacks.append({'rva': rva, 'first64BytesSha256': hashlib.sha256(pe.get_data(rva,64)).hexdigest()})
    tls = {'rawDataRva': record.StartAddressOfRawData-pe.OPTIONAL_HEADER.ImageBase,
           'rawDataBytes': record.EndAddressOfRawData-record.StartAddressOfRawData,
           'zeroFillBytes': record.SizeOfZeroFill, 'callbacks': callbacks}
    assert tls['rawDataBytes'] == 24 and tls['zeroFillBytes'] == 0 and not callbacks
report = {'helperSha256': hashlib.sha256(helper.read_bytes()).hexdigest(), 'imports': imports,
          'entryRva': pe.OPTIONAL_HEADER.AddressOfEntryPoint, 'tls': tls,
          'exports': {name: exports[name] for name in required}, 'bindingBytes': len(storage),
          'bindingDiskBytesZero': True, 'ownedObjects': objects,
          'errorBindingBytes': 32, 'errorBindingDiskBytesZero': True, 'originalEntryPrefixes': prefixes,
          'scope': 'Exact owned binary loader inventory. Platform dependency initialization and stock loader chronology remain unproved.'}
assert not args.output.exists()
args.output.write_text(json.dumps(report, indent=2))
