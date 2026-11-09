"""Trace sampled excerpts back to exact Parquet rows/comments; no API calls."""
import argparse
import bisect
import csv
import hashlib
import json
import re
from pathlib import Path

from screen_passages import ROOT, load_teacher


def verify(candidates, source, out, recheck_rules=False):
    import pyarrow.parquet as pq
    with Path(candidates).open(encoding='utf-8', newline='') as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError('Empty candidate file')
    inventory, ends, total = [], [], 0
    for path in sorted(Path(source).glob('*.parquet')):
        parquet = pq.ParquetFile(path)
        group_ends, subtotal = [], 0
        for i in range(parquet.metadata.num_row_groups):
            subtotal += parquet.metadata.row_group(i).num_rows
            group_ends.append(subtotal)
        inventory.append((path, parquet, total, group_ends))
        total += parquet.metadata.num_rows
        ends.append(total)
    if not inventory:
        raise FileNotFoundError('No source files')
    teacher = load_teacher()
    nlp = None
    if recheck_rules:
        import spacy
        nlp = spacy.load('en_core_web_sm', disable=['lemmatizer'])
    targets = []
    for row in rows:
        match = re.fullmatch(r'p(\d+)_c(\d+)', row['story_id'])
        if not match:
            raise ValueError('Invalid original story ID: ' + row['story_id'])
        post, comment = map(int, match.groups())
        if post >= total:
            raise ValueError('Source post out of bounds')
        targets.append((post, comment, row))
    checked, cache_key, table = [], None, None
    for post, comment, row in sorted(targets, key=lambda item: item[0]):
        file_index = bisect.bisect_right(ends, post)
        path, parquet, offset, group_ends = inventory[file_index]
        file_row = post - offset
        group = bisect.bisect_right(group_ends, file_row)
        within = file_row - (group_ends[group - 1] if group else 0)
        key = (file_index, group)
        if cache_key != key:
            table = parquet.read_row_group(group, columns=['post_title', 'comment_texts', 'comment_scores', 'comment_times'])
            cache_key = key
        texts = table.column('comment_texts')[within].as_py()
        scores = table.column('comment_scores')[within].as_py()
        times = table.column('comment_times')[within].as_py()
        title = table.column('post_title')[within].as_py()
        if comment >= len(texts):
            raise ValueError('Source comment out of bounds')
        original = texts[comment]
        clean = teacher.clean_markdown(original)
        found = ' '.join(row['passage'].split()) in ' '.join(clean.split())
        title_match = (title or '') == row['prompt_title']
        score_match = int(scores[comment]) == int(row['upvotes'])
        when = teacher.parse_time(times[comment])
        date_match = when is not None and when.date().isoformat() == row['posted'] and when < teacher.CUTOFF
        reasons = teacher.check_text(nlp, row['passage']) if nlp is not None else []
        record = dict(passage_id=row['passage_id'], story_id=row['story_id'],
            source_file=str(path.resolve().relative_to(ROOT)), source_file_row=file_row,
            source_row_group=group, source_comment_index=comment,
            original_comment_sha256=hashlib.sha256(original.encode()).hexdigest(),
            excerpt_sha256=hashlib.sha256(row['passage'].encode()).hexdigest(),
            excerpt_found_in_original=found, source_title_matches=title_match,
            source_upvotes_match=score_match, source_date_matches=date_match,
            original_rule_recheck_performed=nlp is not None,
            original_rule_recheck_reasons=json.dumps(reasons, ensure_ascii=False))
        checked.append(record)
        if not (found and title_match and score_match and date_match) or reasons:
            raise ValueError('Source/rule verification failed: ' + json.dumps(record, ensure_ascii=False))
    by_id = {record['passage_id']: record for record in checked}
    with Path(out).open('x', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(checked[0]))
        writer.writeheader()
        writer.writerows(by_id[row['passage_id']] for row in rows)
    summary = dict(checked=len(checked), all_source_checks_passed=True,
                   rule_recheck_performed=nlp is not None, rule_failures=0 if nlp is not None else None,
                   candidates_sha256=hashlib.sha256(Path(candidates).read_bytes()).hexdigest(),
                   audit_sha256=hashlib.sha256(Path(out).read_bytes()).hexdigest(),
                   human_plausibility_or_quality_checked=False, api_calls=0)
    Path(out).with_suffix('.json').write_text(json.dumps(summary, indent=2) + '\n')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidates', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=ROOT / 'data/raw/WritingPrompts_preferences/data')
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--recheck-rules', action='store_true')
    args = parser.parse_args()
    print(json.dumps(verify(args.candidates, args.source, args.out, args.recheck_rules), indent=2))


if __name__ == '__main__':
    main()
