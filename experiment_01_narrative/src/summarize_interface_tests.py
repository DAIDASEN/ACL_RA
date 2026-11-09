"""Summarize saved raw interface responses without API calls or inferred usage."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
from statistics import mean

from interface_test import ROOT, normalize_usage

TOKEN_FIELDS = ('input_tokens', 'output_tokens', 'total_tokens', 'cached_input_tokens', 'reasoning_tokens')


def summarize(run_id):
    raw = ROOT / 'data/raw/interface_test' / run_id
    processed = ROOT / 'data/processed/interface_test' / run_id
    manifest_dir = ROOT / 'data/manifests/interface_test' / run_id
    config = json.loads((manifest_dir / 'run_config.json').read_text())
    with (manifest_dir / 'requests.csv').open(encoding='utf-8', newline='') as handle:
        manifest = list(csv.DictReader(handle))
    samples = []
    hashes = {}
    for request in manifest:
        path = raw / 'responses' / (request['story_id'] + '.json')
        if not path.exists():
            continue
        envelope = json.loads(path.read_text())
        data = envelope.get('response') or {}
        choice = (data.get('choices') or [{}])[0]
        text = (choice.get('message') or {}).get('content')
        usage = normalize_usage(data)
        if usage['cached_input_tokens'] is None:
            usage['cached_input_tokens'] = (data.get('usage') or {}).get('prompt_cache_hit_tokens')
        story_path = raw / 'stories' / (request['story_id'] + '.txt')
        received = envelope['http_status'] == 200 and isinstance(text, str) and bool(text.strip())
        if received and (not story_path.exists() or story_path.read_text() != text):
            raise ValueError('Story copy does not match the authoritative API response: ' + request['story_id'])
        samples.append(dict(story_id=request['story_id'], http_status=envelope['http_status'],
                      received=received, actual_model=data.get('model'), **usage,
                      country=request['country'], genre=request['genre'],
                      word_count=len(text.split()) if isinstance(text, str) else None,
                      finish_reason=choice.get('finish_reason'), elapsed_seconds=envelope['elapsed_seconds']))
        hashes[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    known_totals = {field: sum(r[field] for r in samples if type(r[field]) is int) for field in TOKEN_FIELDS}
    missing = {field: sum(type(r[field]) is not int for r in samples) for field in TOKEN_FIELDS}
    totals = {field: known_totals[field] if not missing[field] and samples else None for field in TOKEN_FIELDS}
    received = [r for r in samples if r['received']]
    summary = dict(run_id=run_id, requested_model=config['requested_model'],
        actual_models=sorted({r['actual_model'] for r in samples if r['actual_model']}),
        planned=len(manifest), responses=len(samples), received_stories=len(received),
        token_totals=totals, known_token_subtotals=known_totals, missing_usage_fields=missing,
        mean_word_count=mean(r['word_count'] for r in received) if received else None,
        min_word_count=min((r['word_count'] for r in received), default=None),
        max_word_count=max((r['word_count'] for r in received), default=None),
        within_600_900=sum(600 <= r['word_count'] <= 900 for r in received),
        stop_count=sum(r['finish_reason'] == 'stop' for r in samples),
        elapsed_seconds=sum(r['elapsed_seconds'] for r in samples),
        mean_elapsed_seconds=mean(r['elapsed_seconds'] for r in samples) if samples else None,
        mean_total_tokens=totals['total_tokens'] / len(samples) if samples and totals['total_tokens'] is not None else None,
        actual_cost='unknown_check_provider_billing', stage='interface_test_not_pilot',
        raw_response_sha256=hashes)
    processed.mkdir(parents=True, exist_ok=True)
    (processed / 'usage_accounting.json').write_text(json.dumps(summary, indent=2) + '\n')
    legacy_path = processed / 'token_summary.json'
    if legacy_path.exists():
        legacy = json.loads(legacy_path.read_text())
        legacy['token_totals'] = totals
        legacy['missing_usage_fields'] = missing
        legacy['usage_accounting_authoritative'] = 'usage_accounting.json'
        legacy['notes'] = 'Provider-reported usage; missing fields remain null; reasoning is an output subcomponent.'
        legacy_path.write_text(json.dumps(legacy, indent=2) + '\n')
    return summary, samples


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run_ids', nargs='+')
    args = parser.parse_args()
    summaries = [summarize(run_id)[0] for run_id in args.run_ids]
    out = ROOT / 'results/interface_test'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'comparison.json').write_text(json.dumps(summaries, indent=2) + '\n')
    fields = ['run_id', 'requested_model', 'received_stories', 'input_tokens', 'output_tokens',
              'total_tokens', 'mean_word_count', 'mean_elapsed_seconds', 'actual_cost']
    with (out / 'comparison.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for summary in summaries:
            record = {k: summary.get(k) for k in fields}
            record.update({k: summary['token_totals'][k] for k in TOKEN_FIELDS if k in fields})
            writer.writerow(record)
    print(json.dumps([{k: v for k, v in s.items() if k != 'raw_response_sha256'} for s in summaries], indent=2))


if __name__ == '__main__':
    main()
