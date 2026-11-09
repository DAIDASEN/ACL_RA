"""Prepare local human review files from a completed candidate selection.

No API use, automatic approvals or changes to source candidates. The reading
pack hides prompt titles and quality tiers; all human decisions remain blank.
"""
import argparse
import csv
import hashlib
import json
import random
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ATTENTION_RULES = {
    'possible_scifi_or_impossible_space': r'\b(?:interstellar|interplanetary|extraterrestrial|star[- ]faring|space travel|time travel|laws of physics|parallel universes?|another dimension)\b',
    'possible_supernatural_or_religious_content': r'\b(?:gods|deities|deity|ghosts?|spirits?|souls?|supernatural|possessed|possession|witchcraft|sorcery|levitat\w*|teleport\w*|demonic|eternity)\b',
    'specific_institution_or_title': r'\b(?:sheriff|senator|congress|parliament|duchess|duke|baron|your majesty|your highness)\b|\b(?:Mr|Mrs|Ms|Dr)\.',
    'specific_drink_or_food_to_review': r'\b(?:scotch|bourbon|whisky|whiskey|vodka|sushi|kimchi|taco|tacos)\b',
    'possible_english_slang': r"\b(?:innit|blimey|dunno|kinda|sorta|fella|fellas|arse|bollocks|bloody hell)\b",
}


def build(source, out):
    source, out = Path(source).resolve(), Path(out).resolve()
    if out.exists() and any(out.iterdir()):
        raise FileExistsError('Review directory must be new/empty; never overwrite human judgments')
    with source.open(encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames
        rows = list(reader)
    if not rows or len({r['passage_id'] for r in rows}) != len(rows):
        raise ValueError('Candidate input empty or IDs duplicated')
    out.mkdir(parents=True, exist_ok=True)
    with (out / 'review_sheet.csv').open('x', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields + ['reviewer_id', 'review_date'])
        writer.writeheader()
        writer.writerows({**row, 'reviewer_id': '', 'review_date': ''} for row in rows)
    normalized = [' '.join(row['passage'].split()).casefold() for row in rows]
    counts = Counter(normalized)
    checks = []
    for row, text in zip(rows, normalized):
        words = len(row['passage'].split())
        checks.append(dict(passage_id=row['passage_id'], words=words,
            words_match_selector=words == int(row['words']), word_range_ok=150 <= words <= 300,
            date_before_cutoff=row['posted'] < '2022-11-30',
            normalized_duplicate_text=counts[text] > 1,
            passage_sha256=hashlib.sha256(row['passage'].encode()).hexdigest()))
    with (out / 'technical_checks.csv').open('x', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(checks[0]))
        writer.writeheader()
        writer.writerows(checks)
    attention = []
    for row in rows:
        hits = {name: sorted({m.group(0) for m in re.finditer(pattern, row['passage'], re.I)})
                for name, pattern in ATTENTION_RULES.items()}
        hits = {name: matches for name, matches in hits.items() if matches}
        attention.append(dict(passage_id=row['passage_id'], source_story_id=row['story_id'],
            needs_attention=bool(hits), rule_matches_json=json.dumps(hits, ensure_ascii=False),
            decision='pending_human_review'))
    with (out / 'attention_flags.csv').open('x', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(attention[0]))
        writer.writeheader()
        writer.writerows(attention)
    shuffled = rows.copy()
    random.Random(20261107).shuffle(shuffled)
    reading = ['# 候选文本阅读包（仅本地审核）', '',
        '此包只显示 passage_id 与正文，不显示原始 prompt、来源说明、点赞或质量档。阅读次序已用固定种子打乱。', '',
        '逐段检查来源线索、英语双关/俚语、科幻奇幻、完整性及可评价性；在 review_sheet.csv 填 yes/no 和理由。', '',
        '合理性检查请实际 2–3 位读者独立完成。读者须判断假设为中文/约鲁巴语/印地语/法语译文或尼日利亚/印度英语原创是否合理。', '',
        '本包和技术检查均不表示人工审核通过，不能用于冒充真人判断。原文不公开发布。', '']
    for row in shuffled:
        reading += [f"## {row['passage_id']}", '', row['passage'], '']
    (out / 'reading_pack.md').write_text('\n'.join(reading), encoding='utf-8')
    with (ROOT / 'validation/templates/plausibility_review.csv').open(encoding='utf-8', newline='') as handle:
        plausibility_fields = next(csv.reader(handle))
    for index in (1, 2, 3):
        with (out / f'plausibility_reviewer_{index}.csv').open('x', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=plausibility_fields)
            writer.writeheader()
            for row in shuffled:
                record = {field: '' for field in plausibility_fields}
                record['passage_id'] = row['passage_id']
                writer.writerow(record)
    metadata = dict(source_candidates=str(source), source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    n=len(rows), tier_counts=dict(Counter(row['tier'] for row in rows)),
                    reading_order_seed=20261107, human_review_completed=False,
                    heuristic_attention_rows=sum(r['needs_attention'] for r in attention),
                    heuristic_attention_is_not_exclusion=True,
                    normalized_duplicate_rows=sum(c['normalized_duplicate_text'] for c in checks),
                    technical_failures=sum(not(c['word_range_ok'] and c['words_match_selector'] and c['date_before_cutoff']) for c in checks))
    (out / 'review_pack_metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + '\n')
    instructions = ['# 本批人工审核说明', '',
        '1. 用 reading_pack.md 阅读正文，在 review_sheet.csv 填 keep_manual=yes/no，并在 notes 记原因、reviewer_id/review_date 记实际审读者。',
        '2. 如果按老师允许的方式修改一两个人名，在审核表 passage 放修改稿，neutralized_edits 逐项记替换；原始 candidates.csv 不改。',
        '3. 将相同阅读包分别交给 2–3 位读者，各填自己的 plausibility_reviewer 文件。任何人认为某一来源不合理即排除。',
        '4. 人工意见汇总后填 plausibility_ok；尚未完成全部待用模型的记忆探测时，probe_recognized 留空或 pending，不填 no。',
        '5. 通过者再分档选定 120 段。不要把空表、技术检查通过或自动候选当成最终通过。', '',
        '技术检查见 technical_checks.csv；attention_flags.csv 是本地词表补充提示，命中不等于应排除，未命中不等于合格，须结合正文判断。',
        '这些提示没有改变原始候选或老师的筛选词表，也不代替人工识别隐含科幻、双关和文化线索。', '']
    (out / 'README.md').write_text('\n'.join(instructions), encoding='utf-8')
    return metadata


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidates', type=Path, required=True)
    parser.add_argument('--outdir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.candidates, args.outdir), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
