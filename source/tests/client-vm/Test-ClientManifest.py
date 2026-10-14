"""Exercise the manifest generator with owned checkout variants and refusals."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def run(output: Path) -> dict:
    repo = Path(__file__).resolve().parents[3]
    output = output.resolve()
    if output.is_relative_to(repo) or output.exists():
        raise ValueError('Use a new manifest-test folder outside Git.')
    output.mkdir(parents=True)
    inventory = (repo / 'source/patches/client_vm/exact_build_inventory.json').read_bytes().replace(b'\r\n', b'\n')
    generator = repo / 'source/launch/enhanced/Generate-ClientProfile.py'
    rows = []
    headers = []
    for name, data, admitted in [('lf-checkout', inventory, True), ('crlf-checkout', inventory.replace(b'\n', b'\r\n'), True),
                                  ('one-byte-change', inventory[:-2] + bytes((inventory[-2] ^ 1,)) + inventory[-1:], False)]:
        source, target = output / f'{name}.json', output / f'{name}.h'
        source.write_bytes(data)
        result = subprocess.run([sys.executable, '-B', str(generator), '--inventory', str(source), '--output', str(target)],
                                capture_output=True, text=True)
        (output / f'{name}.stdout.txt').write_text(result.stdout)
        (output / f'{name}.stderr.txt').write_text(result.stderr)
        rows.append({'case': name, 'exitCode': result.returncode, 'outputWritten': target.exists()})
        if (result.returncode == 0) != admitted or target.exists() != admitted:
            raise AssertionError(f'The manifest checkout outcome differs: {name}.')
        if admitted:
            headers.append(target.read_bytes())
    if headers[0] != headers[1]:
        raise AssertionError('The generated manifest differs between LF and CRLF checkouts.')
    result = {'passed': True, 'cases': rows, 'generatedHeaderSha256': hashlib.sha256(headers[0]).hexdigest(),
              'sourceFiles': {str(path.relative_to(repo)): hashlib.sha256(path.read_bytes()).hexdigest()
                              for path in [generator, Path(__file__)]}, 'gameWrites': 0}
    (output / 'receipt.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    print(json.dumps(run(parser.parse_args().output), indent=2))
