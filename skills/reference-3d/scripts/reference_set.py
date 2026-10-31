#!/usr/bin/env python3
"""Manage immutable, resumable reference-view provenance. No generation calls."""
import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
import sys

VERSION = 1

def digest(data):
    return hashlib.sha256(data).hexdigest()

def encoded(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()

def load(path):
    return json.loads(path.read_text())

def create(path, data):
    # Exclusive creation never replaces a completed artifact, even with concurrent jobs.
    descriptor, temporary = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temporary, path)  # Atomic publication; fails if target exists.
    finally:
        os.unlink(temporary)

def plan():
    angles = [(a, e) for e in (0, 30) for a in range(0, 360, 45)]
    angles += [(a, 75) for a in range(0, 360, 90)]
    return [{'id': f'view-{i:02}', 'azimuth': a, 'elevation': e}
            for i, (a, e) in enumerate(angles, 1)]

def checked(root):
    root = Path(root)
    state = load(root / 'plan.json')
    if state['version'] != VERSION or state['views'] != plan():
        raise ValueError('Unknown or modified view plan')
    if digest((root / 'source.image').read_bytes()) != state['source_sha256']:
        raise ValueError('Identity source changed')
    expected = f"v{VERSION}-{state['source_sha256']}"
    if root.name != expected:
        raise ValueError('Unrelated cache directory')
    return root, state

def prepare(source, output_root):
    source = Path(source).resolve()
    data = source.read_bytes()
    state = {'version': VERSION, 'source_sha256': digest(data), 'views': plan()}
    root = Path(output_root).resolve() / f'v{VERSION}-{digest(data)}'
    root.mkdir(parents=True, exist_ok=True)
    for name, content in [('source.image', data), ('plan.json', encoded(state))]:
        path = root / name
        if path.exists():
            if path.read_bytes() != content:
                raise ValueError(f'Existing cache differs: {path}')
        else:
            create(path, content)
    checked(root)
    return {'set': str(root), **state}

def records(root, state):
    result = []
    for view in state['views']:
        path = root / view['id'] / 'record.json'
        if not path.exists():
            continue
        record = load(path)
        if record['view'] != view or record['source_sha256'] != state['source_sha256']:
            raise ValueError('Stale or unrelated view record')
        if record['model'] != 'gpt-6.1-sol' or record['effort'] != 'low':
            raise ValueError('Unexpected view coordinator')
        for kind in ('image', 'prompt', 'receipt'):
            entry = record[kind]
            local = root / view['id'] / kind
            if entry['path'] != f"{view['id']}/{kind}" or digest(local.read_bytes()) != entry['sha256']:
                raise ValueError(f'Changed {kind} for {view["id"]}')
        result.append(record)
    return result

def verify(root, require_sealed=False, recover_seal=False):
    root, state = checked(root)
    entries = records(root, state)
    hashes = [r['image']['sha256'] for r in entries]
    if len(set(hashes)) != len(hashes):
        raise ValueError('Duplicate view image bytes')
    manifest = {'version': VERSION, 'source_sha256': state['source_sha256'], 'views': entries}
    seal = root / 'manifest.json'
    if seal.exists():
        if len(entries) != 20 or seal.read_bytes() != encoded(manifest):
            raise ValueError('Sealed manifest changed')
        hash_path = root / 'manifest.sha256'
        if not hash_path.exists() and recover_seal:
            pass  # seal() may finish a publication interrupted between the two files.
        elif hash_path.read_text().strip() != digest(seal.read_bytes()):
            raise ValueError('Manifest hash changed')
    elif require_sealed:
        raise ValueError('Reference set is not sealed')
    return root, manifest

def record(root, view_id, image, prompt, receipt, model='gpt-6.1-sol', effort='low'):
    root, state = checked(root)
    verify(root)
    if model != 'gpt-6.1-sol' or effort != 'low':
        raise ValueError('View coordinator must be gpt-6.1-sol / low')
    view = next((v for v in state['views'] if v['id'] == view_id), None)
    if view is None:
        raise ValueError('Unknown view ID')
    paths = {'image': Path(image), 'prompt': Path(prompt), 'receipt': Path(receipt)}
    contents = {kind: p.read_bytes() for kind, p in paths.items()}
    if any(not value for value in contents.values()):
        raise ValueError('Empty image, prompt or receipt')
    value = {'view': view, 'source_sha256': state['source_sha256'], 'model': model, 'effort': effort}
    for kind, path in paths.items():
        value[kind] = {'path': f'{view_id}/{kind}', 'sha256': digest(contents[kind]),
                       'original_path': str(path.resolve())}
    target = root / view_id
    if (target / 'record.json').exists():
        if load(target / 'record.json') == value:
            return value
        raise ValueError('Completed view differs; never overwrite')
    if (root / 'manifest.json').exists():
        raise ValueError('Sealed set is immutable')
    if any(r['image']['sha256'] == value['image']['sha256'] for r in records(root, state)):
        raise ValueError('Duplicate view image bytes')
    target.mkdir(exist_ok=True)
    # Resume partial registration only if the already-copied bytes match exactly.
    for kind, content in contents.items():
        path = target / kind
        if path.exists():
            if path.read_bytes() != content:
                raise ValueError('Partial registration differs; preserve and inspect it')
        else:
            create(path, content)
    create(target / 'record.json', encoded(value))
    return value

def seal(root):
    root, manifest = verify(root, recover_seal=True)
    if len(manifest['views']) != 20:
        raise ValueError('All twenty views are required')
    data = encoded(manifest)
    for name, content in [('manifest.json', data), ('manifest.sha256', (digest(data)+'\n').encode())]:
        path = root / name
        if path.exists():
            if path.read_bytes() != content:
                raise ValueError('Existing seal differs')
        else:
            create(path, content)
    return {'set': str(root), 'manifest_sha256': digest(data), 'views': 20}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    p = sub.add_parser('prepare'); p.add_argument('source'); p.add_argument('--output-root', required=True)
    p = sub.add_parser('record'); p.add_argument('set'); p.add_argument('--view', required=True)
    for name in ('image', 'prompt', 'receipt'):
        p.add_argument('--'+name, required=True)
    p.add_argument('--model', default='gpt-6.1-sol'); p.add_argument('--effort', default='low')
    for name in ('seal', 'verify', 'status'):
        p = sub.add_parser(name); p.add_argument('set')
    args = parser.parse_args()
    try:
        if args.command == 'prepare': result = prepare(args.source, args.output_root)
        elif args.command == 'record': result = record(args.set, args.view, args.image, args.prompt, args.receipt, args.model, args.effort)
        elif args.command == 'seal': result = seal(args.set)
        else:
            root, manifest = verify(args.set, require_sealed=args.command == 'verify')
            result = {'set': str(root), 'completed': len(manifest['views']), 'total': 20,
                      'sealed': (root/'manifest.json').exists(),
                      'missing': [v['id'] for v in plan() if v not in [r['view'] for r in manifest['views']]]}
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, KeyError, json.JSONDecodeError) as exc:
        parser.exit(1, f'Error: {exc}\n')

if __name__ == '__main__':
    main()
