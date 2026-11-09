"""Build an offline request manifest; never calls an API."""
import argparse
import csv
import hashlib
import itertools
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COUNTRIES = {
    'GB': 'the United Kingdom', 'US': 'the United States', 'FR': 'France',
    'CN': 'China', 'BR': 'Brazil', 'NG': 'Nigeria', 'IS': 'Iceland', 'NONE': '',
}
GENRES = ['OPEN', 'romance', 'horror', 'science fiction', 'crime', 'comedy']
SYSTEM = 'You are a fiction writer.'
TEMPLATES = {
    'A': ('Write a complete original short story in English of approximately 750 words.',
          'The genre is {genre}.', 'Set the story in {country}.',
          'Return only the story, without a title or commentary.'),
    'B': ('Create an original, complete short story of about 750 words in English.',
          'Write it as a {genre} story.', 'The story takes place in {country}.',
          'Provide only the story text, without a title or commentary.'),
    'C': ('Tell a complete fictional story in English, using approximately 750 words.',
          'Use the {genre} genre.', 'Use {country} as the setting.',
          'Output the story only, without a title or commentary.'),
}
FIELDS = ['request_id', 'story_id', 'stage', 'model', 'actual_model', 'country',
          'genre', 'wording', 'replicate', 'batch', 'schedule_index',
          'system_prompt', 'user_prompt', 'config_version', 'config_sha256']


def prompt(country, genre, wording):
    intro, genre_sentence, country_sentence, ending = TEMPLATES[wording]
    parts = [intro]
    if genre != 'OPEN':
        parts.append(genre_sentence.format(genre=genre))
    if country != 'NONE':
        parts.append(country_sentence.format(country=COUNTRIES[country]))
    parts.append(ending)
    return ' '.join(parts)


def load_config(path):
    raw = Path(path).read_bytes()
    config = json.loads(raw)
    return config, hashlib.sha256(raw).hexdigest()


def design(config, stage):
    if stage not in ('pilot', 'formal'):
        raise ValueError('stage must be pilot or formal')
    spec = config['stages'][stage]
    expected_wordings = ['A', 'B'] if stage == 'pilot' else ['A', 'B', 'C']
    if spec['wordings'] != expected_wordings:
        raise ValueError('wordings differ from the supplied teacher design')
    reps = spec['replicates']
    if type(reps) is not int or reps < 2:
        raise ValueError('replicates must be an integer >= 2')
    if stage == 'pilot' and reps != 3:
        raise ValueError('pilot must use 3 replicates')
    if list(config['models']) != ['M1', 'M2']:
        raise ValueError('expected exactly two logical model IDs: M1 and M2')
    if stage == 'formal':
        if config.get('formal_approved') is not True:
            raise ValueError('formal design requires the teacher-confirmed formal_approved flag')
        if any(m.get('api_model') in (None, '', 'pending') for m in config['models'].values()):
            raise ValueError('formal manifests require exact model identifiers')
    if type(config['schedule_seed']) is not int:
        raise ValueError('schedule_seed must be an integer')
    if not config.get('config_version'):
        raise ValueError('config_version is required')
    return spec


def build_rows(config, stage, config_hash):
    spec = design(config, stage)
    prefix = 'P' if stage == 'pilot' else 'F'
    rows = []
    for model, country, genre, wording, rep in itertools.product(
            config['models'], COUNTRIES, GENRES, spec['wordings'],
            range(1, spec['replicates'] + 1)):
        genre_id = 'scifi' if genre == 'science fiction' else genre
        sid = f'{prefix}_{model}_{country}_{genre_id}_{wording}_{rep:03d}'
        rows.append(dict(
            request_id=sid, story_id=sid, stage=stage, model=model,
            actual_model=config['models'][model]['api_model'], country=country,
            genre=genre, wording=wording, replicate=f'{rep:03d}', batch=f'{prefix}_001',
            system_prompt=SYSTEM, user_prompt=prompt(country, genre, wording),
            config_version=config['config_version'], config_sha256=config_hash,
        ))
    random.Random(config['schedule_seed']).shuffle(rows)
    for index, row in enumerate(rows, 1):
        row['schedule_index'] = index
    validate_rows(rows, config, stage, config_hash)
    return rows


def validate_rows(rows, config, stage, config_hash):
    spec = design(config, stage)
    expected = set(itertools.product(config['models'], COUNTRIES, GENRES,
                                    spec['wordings'], range(1, spec['replicates'] + 1)))
    observed = set()
    ids = set()
    prefix = 'P' if stage == 'pilot' else 'F'
    for index, row in enumerate(rows, 1):
        key = (row['model'], row['country'], row['genre'], row['wording'], int(row['replicate']))
        if key in observed or key not in expected:
            raise ValueError(f'duplicate or invalid condition: {key}')
        observed.add(key)
        genre_id = 'scifi' if row['genre'] == 'science fiction' else row['genre']
        sid = f"{prefix}_{row['model']}_{row['country']}_{genre_id}_{row['wording']}_{int(row['replicate']):03d}"
        if row['story_id'] != sid or row['request_id'] != sid or sid in ids:
            raise ValueError(f'invalid or duplicate ID: {row["story_id"]}')
        ids.add(sid)
        expected_values = dict(
            stage=stage, actual_model=config['models'][row['model']]['api_model'],
            system_prompt=SYSTEM, user_prompt=prompt(*key[1:4]),
            config_version=config['config_version'], config_sha256=config_hash,
            batch=f'{prefix}_001',
        )
        for field, value in expected_values.items():
            if row[field] != value:
                raise ValueError(f'{sid}: incorrect {field}')
        if int(row['schedule_index']) != index:
            raise ValueError(f'{sid}: schedule_index does not match row order')
        if '{' in row['user_prompt'] or 'OPEN' in row['user_prompt'] or 'NONE' in row['user_prompt']:
            raise ValueError(f'{sid}: unresolved prompt token')
    if observed != expected or len(rows) != len(expected):
        raise ValueError(f'incomplete design: {len(rows)} rows, expected {len(expected)}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT / 'configs/config.yaml')
    parser.add_argument('--stage', choices=['pilot', 'formal'], default='pilot')
    parser.add_argument('--outdir', type=Path)
    parser.add_argument('--check-only', action='store_true')
    args = parser.parse_args()
    config, digest = load_config(args.config)
    out = args.outdir or ROOT / 'data/manifests' / args.stage
    if args.check_only:
        with (out / 'requests.csv').open(encoding='utf-8', newline='') as handle:
            rows = list(csv.DictReader(handle))
        validate_rows(rows, config, args.stage, digest)
        # Validate actual random ordering, not only the numbering column.
        planned = build_rows(config, args.stage, digest)
        if [r['story_id'] for r in rows] != [r['story_id'] for r in planned]:
            raise ValueError('manifest order differs from the configured schedule seed')
        meta = json.loads((out / 'manifest_meta.json').read_text())
        actual_hash = hashlib.sha256((out / 'requests.csv').read_bytes()).hexdigest()
        if meta['requests_sha256'] != actual_hash or meta['config_sha256'] != digest:
            raise ValueError('manifest or configuration hash mismatch')
        print(f'OK: {len(rows)} planned requests; no API calls')
        return
    rows = build_rows(config, args.stage, digest)
    out.mkdir(parents=True, exist_ok=True)
    if (out / 'requests.csv').exists() or (out / 'manifest_meta.json').exists():
        raise FileExistsError('manifest already exists; use --check-only or a new --outdir')
    with (out / 'requests.csv').open('x', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    meta = dict(stage=args.stage, n_requests=len(rows), config_version=config['config_version'],
                config_sha256=digest, schedule_seed=config['schedule_seed'],
                requests_sha256=hashlib.sha256((out / 'requests.csv').read_bytes()).hexdigest(),
                status='planned_only_no_API_calls')
    (out / 'manifest_meta.json').write_text(json.dumps(meta, indent=2) + '\n')
    print(f'Created {len(rows)} planned requests in {out}; no API calls')


if __name__ == '__main__':
    main()
