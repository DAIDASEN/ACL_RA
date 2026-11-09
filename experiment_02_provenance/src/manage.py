"""Local workspace checks and a clearly separated mock run; no real API calls."""
import argparse
import csv
import hashlib
import importlib.util
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ITEMS = ['literariness', 'overall', 'creativity', 'writing', 'enjoyment', 'naturalness']


def validate_passages(path, expected=120):
    with Path(path).open(encoding='utf-8-sig', newline='') as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != ['passage_id', 'passage']:
            raise ValueError('final CSV must contain exactly passage_id,passage in that order')
        rows = list(reader)
    if len(rows) != expected:
        raise ValueError(f'expected {expected} passages, found {len(rows)}')
    ids, texts = set(), set()
    for row in rows:
        if None in row or any(value is None for value in row.values()):
            raise ValueError('malformed CSV row')
        pid, passage = row['passage_id'].strip(), row['passage'].strip()
        if not pid or pid in ids:
            raise ValueError(f'empty or duplicate passage_id: {pid}')
        # Mirrors the supplied selector word counting rule (whitespace split).
        if not 150 <= len(passage.split()) <= 300:
            raise ValueError(f'{pid}: expected 150-300 whitespace-delimited words')
        normalized = ' '.join(passage.split())
        if normalized in texts:
            raise ValueError(f'{pid}: duplicate passage text')
        ids.add(pid)
        texts.add(normalized)
    return rows


def check_mock_results(path):
    rows = [json.loads(line) for line in Path(path).read_text().splitlines()]
    keys = {(r['passage_id'], r['label'], r['rep']) for r in rows}
    expected = {(pid, f'L{label:02d}', 0) for pid in ['SMOKE_001', 'SMOKE_002']
                for label in range(1, 15)}
    if len(rows) != 28 or keys != expected:
        raise ValueError('mock output is incomplete or duplicated')
    for row in rows:
        if row['model'] != 'mock' or row['justification'] != 'mock':
            raise ValueError('unexpected real or non-mock data in smoke output')
        if not all(type(row[item]) is int and 1 <= row[item] <= 7 for item in ITEMS):
            raise ValueError('invalid mock scores')
    return len(rows)


def smoke():
    if importlib.util.find_spec('pandas') is None:
        raise SystemExit('pandas is required: install requirements.txt in the project virtualenv')
    run_id = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = ROOT / 'results/smoke' / run_id
    out.mkdir(parents=True, exist_ok=False)
    with (out / 'synthetic_passages.csv').open('x', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=['passage_id', 'passage'])
        writer.writeheader()
        for i in (1, 2):
            # Deliberately synthetic text, never used as research materials.
            text = ' '.join([f'Synthetic smoke fixture {i} only.'] * 35)
            writer.writerow(dict(passage_id=f'SMOKE_{i:03d}', passage=text))
    command = [sys.executable, str(ROOT / 'src/teacher/run_experiment.py'),
               '--model', 'mock', '--mock', '--reps', '1',
               '--passages', str(out / 'synthetic_passages.csv'), '--outdir', str(out)]
    subprocess.run(command, cwd=ROOT, check=True)
    count = check_mock_results(out / 'mock.jsonl')
    # Re-running the supplied script must not add duplicate successful jobs.
    before = (out / 'mock.jsonl').read_bytes()
    subprocess.run(command, cwd=ROOT, check=True)
    if before != (out / 'mock.jsonl').read_bytes():
        raise ValueError('mock resume changed completed results')
    (out / 'verification.json').write_text(json.dumps(dict(
        status='mock_only_not_research_data', rows=count, resume_verified=True,
        results_sha256=hashlib.sha256(before).hexdigest()), indent=2) + '\n')
    print(f'OK: {count} mock rows and resume verified; {out}')


def status():
    candidate_files = sorted((ROOT / 'data/processed/candidates').rglob('candidates.csv'))
    print(f'candidate selections: {len(candidate_files)} files (including verification/trial runs; not human-approved)')
    active = ROOT / 'configs/active_candidates.json'
    if active.exists():
        info = json.loads(active.read_text())
        print(f"active candidate file: {info['candidates_path']}")
        print(f"human review: {info.get('human_review_status', 'pending')}")
    paths = ['data/processed/final/final_passages.csv',
             'data/processed/memorization/memorization.csv']
    for rel in paths:
        print(f'{rel}: {"present (not yet audited)" if (ROOT / rel).exists() else "not prepared"}')
    for stage in ('pilot', 'formal'):
        files = sorted((ROOT / 'results' / stage).glob('*.jsonl'))
        print(f'{stage}: {len(files)} result files (presence does not imply completion)')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status')
    commands.add_parser('smoke')
    check = commands.add_parser('validate-passages')
    check.add_argument('--path', type=Path, default=ROOT / 'data/processed/final/final_passages.csv')
    check.add_argument('--expected', type=int, default=120)
    args = parser.parse_args()
    if args.command == 'status':
        status()
    elif args.command == 'smoke':
        smoke()
    else:
        rows = validate_passages(args.path, args.expected)
        print(f'OK: {len(rows)} passages; manual review still required')


if __name__ == '__main__':
    main()
