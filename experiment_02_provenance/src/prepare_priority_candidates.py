"""Exploratory reading-priority queue; does not replace original teacher output.

Stricter text/prompt heuristics and POS proper-noun flags reduce obvious genre
leakage. These rules may exclude usable realistic passages; no human approvals
or final stimulus decisions are made. All original candidates remain untouched.
"""
import argparse
import csv
import hashlib
import json
import random
import re
import time
from collections import Counter
from pathlib import Path

from screen_passages import ROOT, now

PROMPT_PATTERN = r'\b(?:immortal\w*|reincarn\w*|afterlife|heaven|hell|satan|gods?|deities|angels?|demons?|devils?|ghosts?|spirits?|souls?|dream\w*|magic\w*|wizard\w*|witch\w*|dragon\w*|zombi\w*|vampir\w*|werewol\w*|aliens?|extraterrestrial\w*|galax\w*|spaceship\w*|space|universe\w*|world\w*|earth|humans?|humanity|time|future|past|teleport\w*|dimension\w*|portal\w*|parallel|alternate|apocalyp\w*|dystopi\w*|utopi\w*|super\w*|powers?|abilities|ability|bodies|body|swap\w*|simulation\w*|robots?|android\w*|cyborg\w*|AI|artificial intelligence|creature\w*|monster\w*|curse\w*|fairy|fairies|fae|elves|elf|NPC|non-player|sentient|mind[- ]?read\w*|mind control|fourth wall)\b'
TEXT_PATTERN = r'\b(?:immortal\w*|interstellar|interplanetary|star[- ]faring|universe\w*|galax\w*|extraterrestrial\w*|mortals?|gods?|deities|ghosts?|spirits?|souls?|afterlife|supernatural|otherworldly|reincarn\w*|teleport\w*|possess(?:ed|ion)|sorcery|witchcraft|demonic|eternity|monstrosit\w*|creatures?|inhuman|not human|sheriff|senator|congress|parliament|duchess|duke|baron|scotch|bourbon|whisky|whiskey|vodka|sushi|kimchi|tacos?|s[’\x27]?mores|innit|blimey|dunno|kinda|sorta|fellas?|arse|bollocks)\b|\b(?:Mr|Mrs|Ms|Dr)\.|laws of physics|\b(?:they|we|it)(?:[’\x27]re| are| were| is) (?:called|known as)\b|\b(?:went|go|gone|travelled|traveled) back (?:one|two|three|\d+) (?:hours?|days?|years?)\b|\b(?:my|your|his|her|their) (?:old|new) body\b'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pool', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--seed', type=int, default=20261107)
    parser.add_argument('--per-tier', type=int, default=66)
    args = parser.parse_args()
    out = args.outdir.resolve()
    if out.exists() and any(out.iterdir()):
        raise FileExistsError('Use a new empty output directory')
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with args.pool.open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    prompt_re, text_re = re.compile(PROMPT_PATTERN, re.I), re.compile(TEXT_PATTERN, re.I)
    eligible, reasons = [], Counter()
    for row in rows:
        if prompt_re.search(row['prompt_title']):
            reasons['source_prompt_attention'] += 1
        elif text_re.search(row['passage']):
            reasons['excerpt_attention'] += 1
        else:
            eligible.append(row)
    print(json.dumps(dict(event='heuristic_filter_done', pool=len(rows), remaining=len(eligible), reasons=dict(reasons))), flush=True)
    random.Random(args.seed).shuffle(eligible)
    # Interleave old quality tiers so one tier does not take every shared prompt.
    groups = {tier: [row for row in eligible if row['tier'] == tier] for tier in ('high', 'mid', 'low')}
    stream = []
    for i in range(max(map(len, groups.values()), default=0)):
        for tier in groups:
            if i < len(groups[tier]):
                stream.append(groups[tier][i])
    import spacy
    nlp = spacy.load('en_core_web_sm', disable=['lemmatizer'])
    selected, counts, used_prompts, used_texts = [], Counter(), set(), set()
    checked_pos = 0
    for doc, row in nlp.pipe(((row['passage'], row) for row in stream), as_tuples=True, batch_size=64):
        if counts[row['tier']] >= args.per_tier:
            continue
        checked_pos += 1
        if any(token.pos_ == 'PROPN' for token in doc):
            reasons['proper_noun_pos'] += 1
            continue
        normalized = ' '.join(row['passage'].split()).casefold()
        if row['prompt_id'] in used_prompts or normalized in used_texts:
            reasons['duplicate_prompt_or_normalized_excerpt'] += 1
            continue
        selected.append(row)
        counts[row['tier']] += 1
        used_prompts.add(row['prompt_id'])
        used_texts.add(normalized)
        if all(counts[tier] == args.per_tier for tier in groups):
            break
    if not all(counts[tier] == args.per_tier for tier in groups):
        raise RuntimeError('Not enough priority candidates in every tier: ' + str(counts))
    selected = [row for tier in groups for row in selected if row['tier'] == tier]
    fields = ['passage_id', 'tier', 'upvotes', 'posted', 'words', 'prompt_title', 'story_id',
              'passage', 'keep_manual', 'neutralized_edits', 'plausibility_ok', 'probe_recognized', 'notes']
    with (out / 'candidates.csv').open('x', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for index, row in enumerate(selected):
            record = {key: row.get(key, '') for key in fields}
            record['passage_id'] = f'R{index:03d}'
            writer.writerow(record)
    metadata = dict(stage='exploratory_reading_priority_not_final', created_at=now(),
        source_pool=str(args.pool.resolve()), source_pool_sha256=hashlib.sha256(args.pool.read_bytes()).hexdigest(),
        source_pool_size=len(rows), heuristic_remaining=len(eligible), tier_counts=dict(counts),
        checked_pos=checked_pos, filtering_reasons=dict(reasons), seed=args.seed,
        model=nlp.meta.get('name'), model_version=nlp.meta.get('version'),
        rules={'source_prompt_regex': PROMPT_PATTERN, 'excerpt_regex': TEXT_PATTERN,
               'pos_filter': 'no PROPN tokens', 'original_teacher_filters':'already passed in source pool'},
        caveat='Source-prompt heuristics can remove otherwise neutral realistic excerpts; use as a disclosed reading-priority queue, not an approved final selection.',
        human_review_completed=False, memorization_checked=False, api_calls=0,
        elapsed_seconds=round(time.monotonic()-started,3),
        candidates_sha256=hashlib.sha256((out/'candidates.csv').read_bytes()).hexdigest(),
        code_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (out / 'priority_metadata.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print(json.dumps({k:v for k,v in metadata.items() if k!='rules'},indent=2),flush=True)


if __name__ == '__main__':
    main()
