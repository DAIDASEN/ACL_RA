"""Small, explicitly authorized API interface test; not pilot or formal data.

Standard library only. Credentials are loaded from a local dotenv without shell
execution and are never placed in requests.csv, logs, command arguments or errors.
There are no automatic retries; ambiguous attempts require investigation.
"""
import argparse
import csv
import hashlib
import json
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from build_requests import SYSTEM, prompt

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_FIELDS = ['story_id', 'stage', 'model', 'country', 'genre', 'wording',
                   'replicate', 'system_prompt', 'user_prompt', 'schedule_index']
STORY_FIELDS = ['story_id', 'country', 'genre', 'replicate', 'status', 'actual_model',
                'word_count', 'length_600_900', 'finish_reason', 'input_tokens',
                'cached_input_tokens', 'output_tokens', 'reasoning_tokens', 'total_tokens',
                'elapsed_seconds', 'raw_story_path', 'raw_response_path']


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def read_dotenv(path):
    values = {}
    for number, line in enumerate(Path(path).read_text(encoding='utf-8-sig').splitlines(), 1):
        text = line.strip()
        if not text or text.startswith('#'):
            continue
        text = text.removeprefix('export ').strip()
        key, sep, value = text.partition('=')
        if not sep or not re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]*', key.strip()):
            raise ValueError(f'invalid dotenv assignment at line {number}; value hidden')
        value = value.strip()
        if value[:1] in ('"', "'"):
            if len(value) < 2 or value[-1] != value[0]:
                raise ValueError(f'unclosed dotenv quote at line {number}; value hidden')
            value = value[1:-1]
        else:
            value = re.split(r'\s+#', value, maxsplit=1)[0].rstrip()
        values[key.strip()] = value
    return values


def credentials(path):
    values = read_dotenv(path)
    key = values.get('key') or values.get('OPENAI_API_KEY')
    base = values.get('base_url') or values.get('OPENAI_BASE_URL') or 'https://api.openai.com/v1'
    if not key:
        raise ValueError('dotenv requires key or OPENAI_API_KEY')
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
        raise ValueError('base_url must be an HTTPS URL without credentials, query or fragment')
    return key, base.rstrip('/')


def redact(value, secret):
    if isinstance(value, str):
        return value.replace(secret, '[REDACTED]')
    if isinstance(value, dict):
        return {k: redact(v, secret) for k, v in value.items()}
    if isinstance(value, list):
        return [redact(v, secret) for v in value]
    return value


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write('\n')
        handle.flush()
        os.fsync(handle.fileno())


def append_attempt(path, value):
    with Path(path).open('a', encoding='utf-8') as handle:
        handle.write(json.dumps(value, ensure_ascii=False) + '\n')
        handle.flush()
        os.fsync(handle.fileno())


def normalize_usage(data):
    """Unknown usage stays None; never infer billed tokens from word counts."""
    usage = data.get('usage') or {}
    prompt_details = usage.get('prompt_tokens_details') or usage.get('input_tokens_details') or {}
    output_details = usage.get('completion_tokens_details') or usage.get('output_tokens_details') or {}
    return dict(input_tokens=usage.get('prompt_tokens', usage.get('input_tokens')),
                cached_input_tokens=prompt_details.get('cached_tokens'),
                output_tokens=usage.get('completion_tokens', usage.get('output_tokens')),
                reasoning_tokens=output_details.get('reasoning_tokens'),
                total_tokens=usage.get('total_tokens'))


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def make_manifest(model):
    rows = []
    for country in ('GB', 'CN'):
        for genre in ('OPEN', 'horror'):
            for rep in (1, 2):
                rows.append(dict(story_id=f'T_LUNA_{country}_{genre}_A_{rep:03d}',
                                 stage='interface_test', model=model, country=country,
                                 genre=genre, wording='A', replicate=str(rep),
                                 system_prompt=SYSTEM, user_prompt=prompt(country, genre, 'A')))
    random.Random(20261106).shuffle(rows)
    for i, row in enumerate(rows, 1):
        row['schedule_index'] = str(i)
    return rows


def request_payload(row, model):
    return dict(model=model, temperature=0.8, top_p=1, max_completion_tokens=2500,
                reasoning_effort='none', stream=False,
                messages=[dict(role='system', content=row['system_prompt']),
                          dict(role='user', content=row['user_prompt'])])


def refresh_summary(raw, processed, rows):
    selected = []
    for row in rows:
        response = raw / 'responses' / f"{row['story_id']}.json"
        if not response.exists():
            continue
        envelope = json.loads(response.read_text())
        data = envelope.get('response') or {}
        choices = data.get('choices') or []
        choice = choices[0] if choices else {}
        message = choice.get('message') or {}
        content = message.get('content')
        story_path = raw / 'stories' / f"{row['story_id']}.txt"
        text = story_path.read_text() if story_path.exists() else ''
        if envelope['http_status'] != 200:
            status = 'http_failed'
        elif not isinstance(content, str) or not content.strip():
            status = 'returned_without_story'
        else:
            status = 'received_content'
        wc = len(text.split())
        selected.append(dict(
            story_id=row['story_id'], country=row['country'], genre=row['genre'],
            replicate=row['replicate'], status=status, actual_model=data.get('model'),
            word_count=wc, length_600_900=600 <= wc <= 900,
            finish_reason=choice.get('finish_reason'), **normalize_usage(data),
            elapsed_seconds=envelope['elapsed_seconds'],
            raw_story_path=str(story_path.relative_to(ROOT)) if story_path.exists() else '',
            raw_response_path=str(response.relative_to(ROOT)),
        ))
    with (processed / 'stories.csv').open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=STORY_FIELDS)
        writer.writeheader()
        writer.writerows(selected)
    complete = [r for r in selected if r['status'] == 'received_content']
    token_fields = ['input_tokens', 'cached_input_tokens', 'output_tokens', 'reasoning_tokens', 'total_tokens']
    totals = {field: sum(r[field] for r in selected if isinstance(r[field], int)) for field in token_fields}
    summary = dict(stage='interface_test_not_pilot', planned=8, responses=len(selected),
                   received_stories=len(complete),
                   usage_missing_count=sum(r['total_tokens'] is None for r in selected),
                   token_totals=totals, totals_include_all_saved_responses=True,
                   actual_models=sorted({r['actual_model'] for r in selected if r['actual_model']}),
                   length_600_900_count=sum(r['length_600_900'] for r in complete),
                   word_counts=[r['word_count'] for r in complete],
                   elapsed_seconds=sum(r['elapsed_seconds'] for r in selected),
                   actual_cost='unknown_check_provider_billing',
                   notes='Provider-reported usage; no independent token verification; no retries.')
    (processed / 'token_summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, default=ROOT.parent / '.env')
    parser.add_argument('--model', default='gpt-6-luna')
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--limit', type=int, default=1, help='maximum scheduled jobs to reach, at most 8')
    parser.add_argument('--timeout', type=float, default=120)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.run_id) or not 1 <= args.limit <= 8:
        parser.error('safe run-id and limit in 1..8 required')
    secret, base = credentials(args.env_file)
    raw = ROOT / 'data/raw/interface_test' / args.run_id
    processed = ROOT / 'data/processed/interface_test' / args.run_id
    manifest_dir = ROOT / 'data/manifests/interface_test' / args.run_id
    for directory in [raw / 'responses', raw / 'stories', raw / 'requests', processed, manifest_dir]:
        directory.mkdir(parents=True, exist_ok=True)
    rows = make_manifest(args.model)
    config = dict(stage='interface_test', requested_model=args.model, base_url=base,
                  schedule_seed=20261106, planned_stories=8,
                  parameters={k: v for k, v in request_payload(rows[0], args.model).items() if k != 'messages'},
                  max_retries=0, prompts='unchanged teacher wording A',
                  code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    config_path = manifest_dir / 'run_config.json'
    if config_path.exists():
        if json.loads(config_path.read_text()) != config:
            raise ValueError('saved run config differs; use a new run-id, never overwrite old records')
        with (manifest_dir / 'requests.csv').open(newline='') as handle:
            if list(csv.DictReader(handle)) != rows:
                raise ValueError('saved request manifest differs')
    else:
        write_json(config_path, config)
        with (manifest_dir / 'requests.csv').open('x', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    opener = urllib.request.build_opener(NoRedirect)
    endpoint = base + '/chat/completions'
    for row in rows[:args.limit]:
        sid = row['story_id']
        response_path = raw / 'responses' / f'{sid}.json'
        request_path = raw / 'requests' / f'{sid}.json'
        if response_path.exists():
            saved = json.loads(response_path.read_text())
            if saved['http_status'] != 200:
                raise SystemExit('previous HTTP failure; inspect saved response before continuing')
            continue
        if request_path.exists():
            raise SystemExit('request was started without a saved response; investigate before any retry')
        payload = request_payload(row, args.model)
        write_json(request_path, payload)
        started = utc_now()
        append_attempt(raw / 'attempts.jsonl', dict(story_id=sid, event='started', at=started,
                                                   requested_model=args.model, attempt_id=sid + '_001'))
        request = urllib.request.Request(endpoint, data=json.dumps(payload).encode(),
                    headers={'Authorization': 'Bearer ' + secret, 'Content-Type': 'application/json'}, method='POST')
        start = time.monotonic()
        try:
            with opener.open(request, timeout=args.timeout) as response:
                status = response.status
                body = response.read().decode('utf-8')
                provider_id = response.headers.get('x-request-id') or response.headers.get('request-id')
        except urllib.error.HTTPError as error:
            status = error.code
            body = error.read().decode('utf-8', errors='replace')
            provider_id = error.headers.get('x-request-id') if error.headers else None
        except Exception as error:
            append_attempt(raw / 'attempts.jsonl', dict(story_id=sid, event='transport_failed',
                at=utc_now(), elapsed_seconds=round(time.monotonic() - start, 3),
                error_type=type(error).__name__, error=redact(str(error), secret), usage='unknown'))
            raise SystemExit('transport failed; details saved, no automatic retry') from None
        elapsed = round(time.monotonic() - start, 3)
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = {'unparsed_response': body}
        data = redact(data, secret)
        envelope = dict(http_status=status, provider_request_id=provider_id, started_at=started,
                        completed_at=utc_now(), elapsed_seconds=elapsed, response=data)
        write_json(response_path, envelope)
        choices = data.get('choices') or []
        content = ((choices[0].get('message') or {}).get('content')) if choices else None
        if isinstance(content, str) and content.strip():
            with (raw / 'stories' / f'{sid}.txt').open('x', encoding='utf-8') as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        usage = normalize_usage(data)
        append_attempt(raw / 'attempts.jsonl', dict(story_id=sid, event='returned', at=utc_now(),
                http_status=status, provider_request_id=provider_id, actual_model=data.get('model'),
                elapsed_seconds=elapsed, **usage))
        refresh_summary(raw, processed, rows)
        print(json.dumps(dict(story_id=sid, http_status=status, actual_model=data.get('model'),
                              elapsed_seconds=elapsed, **usage)), flush=True)
        if status != 200:
            raise SystemExit('HTTP failure; response saved, no automatic parameter/model substitution')
        if not isinstance(content, str) or not content.strip():
            raise SystemExit('no story returned; response saved, inspect before continuing')
    summary = refresh_summary(raw, processed, rows)
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
