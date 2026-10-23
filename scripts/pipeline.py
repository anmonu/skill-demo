"""Validate committed manifests, scan instructions and build deterministic artifacts."""
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lifecycle import PolicyError, package, scan, validate
ROOT = Path(__file__).resolve().parents[1]

def main():
    out = ROOT / 'build'
    out.mkdir(exist_ok=True)
    results, failed = [], False
    paths = sorted((ROOT / 'skills').glob('*/manifest.json'))
    if not paths:
        print('No skill manifests found.', file=sys.stderr)
        return 1
    for path in paths:
        try:
            manifest = validate(json.loads(path.read_text()))
            if path.parent.name != manifest['name']:
                raise PolicyError('Directory name must match manifest name.')
            report = scan(manifest)
            record = {'path': str(path.relative_to(ROOT)), **report}
            if report['passed']:
                artifact = package(manifest)
                name = manifest['name'] + '-' + manifest['version'] + '.zip'
                (out / name).write_bytes(artifact)
                record.update(artifact=name, sha256=hashlib.sha256(artifact).hexdigest())
            else:
                failed = True
            results.append(record)
        except (PolicyError, ValueError) as exc:
            failed = True
            results.append({'path': str(path.relative_to(ROOT)), 'passed': False, 'error': str(exc)})
    (out / 'scan-report.json').write_text(json.dumps(results, indent=2) + '\n')
    print(json.dumps(results, indent=2))
    return int(failed)

if __name__ == '__main__':
    sys.exit(main())
