"""Eight-story DeepSeek Flash interface test, isolated from pilot/formal.

Uses provider-specific credentials when configured, otherwise the user's explicit
shared key/base_url pair on that same host. Never forwards a shared key to a new
provider host. Existing Luna scripts and immutable run artifacts are unchanged.
"""
import argparse
import csv
import hashlib
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from interface_test import (ROOT, MANIFEST_FIELDS, NoRedirect, append_attempt,
                            make_manifest, normalize_usage, read_dotenv, redact,
                            refresh_summary, utc_now, write_json)


def api_credentials(env_file):
    values = read_dotenv(env_file)
    key_name = next((k for k in ('DEEPSEEK_API_KEY', 'deepseek_api_key', 'deepseek_key')
                     if values.get(k)), None)
    if key_name:
        key = values[key_name]
        base = values.get('DEEPSEEK_BASE_URL') or values.get('deepseek_base_url') or 'https://api.deepseek.com'
        source = key_name
    elif values.get('key') and values.get('base_url'):
        key, base = values['key'], values['base_url']
        source = 'shared_key_and_explicit_base_url'
    else:
        raise ValueError('No DeepSeek credentials or explicit shared key/base_url pair configured')
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.query or parsed.fragment:
        raise ValueError('API base must be HTTPS without credentials, query or fragment')
    return key, base.rstrip('/'), source


def flash_manifest():
    rows = make_manifest('deepseek-flash')
    for row in rows:
        row['story_id'] = row['story_id'].replace('T_LUNA_', 'T_DEEPSEEK_FLASH_')
    return rows


def flash_payload(row):
    return dict(model='deepseek-flash', temperature=0.8, top_p=1, max_tokens=2500,
                thinking={'type': 'disabled'}, stream=False,
                messages=[{'role': 'system', 'content': row['system_prompt']},
                          {'role': 'user', 'content': row['user_prompt']}])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, default=ROOT.parent / '.env')
    parser.add_argument('--run-id', default='deepseek_flash_interface_20261106')
    parser.add_argument('--limit', type=int, default=1)
    parser.add_argument('--timeout', type=float, default=120)
    args = parser.parse_args()
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]+', args.run_id) or not 1 <= args.limit <= 8:
        parser.error('safe run-id and limit in 1..8 required')
    secret, base, credential_source = api_credentials(args.env_file)
    raw = ROOT / 'data/raw/interface_test' / args.run_id
    processed = ROOT / 'data/processed/interface_test' / args.run_id
    manifest_dir = ROOT / 'data/manifests/interface_test' / args.run_id
    for directory in (raw / 'requests', raw / 'responses', raw / 'stories', processed, manifest_dir):
        directory.mkdir(parents=True, exist_ok=True)
    rows = flash_manifest()
    config = dict(stage='interface_test', requested_model='deepseek-flash', base_url=base,
                  credential_source=credential_source, schedule_seed=20261106, planned_stories=8,
                  parameters={k: v for k, v in flash_payload(rows[0]).items() if k != 'messages'},
                  prompts='unchanged teacher wording A', max_retries=0,
                  official_latest_reference='https://api-docs.deepseek.com/updates/',
                  official_reference_checked_date='2026-11-06',
                  official_alias_documented_release='DeepSeek-V4.1-Flash-1017',
                  source_sha256={name: hashlib.sha256((ROOT / 'src' / name).read_bytes()).hexdigest()
                                 for name in ('deepseek_interface_test.py', 'interface_test.py', 'build_requests.py')})
    config_path = manifest_dir / 'run_config.json'
    if config_path.exists():
        if json.loads(config_path.read_text()) != config:
            raise ValueError('Run config changed; use a new run-id')
        with (manifest_dir / 'requests.csv').open(encoding='utf-8', newline='') as handle:
            if list(csv.DictReader(handle)) != rows:
                raise ValueError('Saved manifest changed')
    else:
        write_json(config_path, config)
        with (manifest_dir / 'requests.csv').open('x', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS)
            writer.writeheader()
            writer.writerows(rows)
    opener = urllib.request.build_opener(NoRedirect)
    for row in rows[:args.limit]:
        sid = row['story_id']
        request_path = raw / 'requests' / f'{sid}.json'
        response_path = raw / 'responses' / f'{sid}.json'
        if response_path.exists():
            if json.loads(response_path.read_text())['http_status'] != 200:
                raise SystemExit('Saved HTTP failure; inspect before continuing')
            continue
        if request_path.exists():
            raise SystemExit('Started request has unknown outcome; investigate before any retry')
        payload = flash_payload(row)
        write_json(request_path, payload)
        started = utc_now()
        append_attempt(raw / 'attempts.jsonl', dict(story_id=sid, attempt_id=sid + '_001',
                       event='started', at=started, requested_model='deepseek-flash'))
        request = urllib.request.Request(base + '/chat/completions', method='POST',
                   data=json.dumps(payload).encode('utf-8'),
                   headers={'Authorization': 'Bearer ' + secret, 'Content-Type': 'application/json'})
        timer = time.monotonic()
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
            append_attempt(raw / 'attempts.jsonl', dict(story_id=sid, event='transport_failed', at=utc_now(),
                error_type=type(error).__name__, error=redact(str(error), secret), usage='unknown',
                elapsed_seconds=round(time.monotonic() - timer, 3)))
            raise SystemExit('Transport error saved; no automatic retry') from None
        elapsed = round(time.monotonic() - timer, 3)
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            data = {'unparsed_response': body}
        data = redact(data, secret)
        write_json(response_path, dict(http_status=status, provider_request_id=provider_id,
            started_at=started, completed_at=utc_now(), elapsed_seconds=elapsed, response=data))
        choices = data.get('choices') or []
        choice = choices[0] if choices else {}
        content = (choice.get('message') or {}).get('content')
        if isinstance(content, str) and content.strip():
            # Response remains authoritative if a crash precedes this derived copy.
            with (raw / 'stories' / f'{sid}.txt').open('x', encoding='utf-8') as handle:
                handle.write(content)
                handle.flush()
                import os
                os.fsync(handle.fileno())
        usage = normalize_usage(data)
        append_attempt(raw / 'attempts.jsonl', dict(story_id=sid, event='returned', at=utc_now(),
                       http_status=status, provider_request_id=provider_id,
                       actual_model=data.get('model'), elapsed_seconds=elapsed, **usage))
        refresh_summary(raw, processed, rows)
        print(json.dumps(dict(story_id=sid, http_status=status, actual_model=data.get('model'),
                              finish_reason=choice.get('finish_reason'), elapsed_seconds=elapsed, **usage)), flush=True)
        if status != 200:
            raise SystemExit('HTTP failure saved; no automatic model or parameter substitution')
        if not isinstance(content, str) or not content.strip() or choice.get('finish_reason') != 'stop':
            raise SystemExit('Missing content or non-stop finish; inspect before continuing')
    print(json.dumps(refresh_summary(raw, processed, rows)), flush=True)


if __name__ == '__main__':
    main()
