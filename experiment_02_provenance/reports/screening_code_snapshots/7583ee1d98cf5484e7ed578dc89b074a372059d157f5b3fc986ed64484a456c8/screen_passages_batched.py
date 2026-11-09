"""Batch the teacher's unchanged rules for local, complete-data selection.

All first six shuffled windows receive identical lexical/NER checks. The first
passing window is retained in source order, as in the original selector. Extra
NER work after an already-passing window is discarded. No API calls.
"""
import argparse
import csv
import hashlib
import importlib.metadata
import json
import random
import sys
import time
import types
from pathlib import Path

from screen_passages import ROOT, iter_local_posts, load_teacher, now, parquet_inventory, summarize_candidates


def select(files, teacher, nlp, max_posts=None, min_score=2, seed=13,
           n_process=4, batch_size=64, progress_every=5000):
    rng = random.Random(seed)
    stats = {key: 0 for key in ('posts', 'stories', 'too_late', 'bot_or_short',
                               'no_window', 'rejected_markers', 'kept')}
    started = time.monotonic()
    lexical_only = lambda text: types.SimpleNamespace(ents=[])

    def windows_to_check():
        for p_idx, post in enumerate(iter_local_posts(files, 64, progress_every, started)):
            if max_posts is not None and p_idx >= max_posts:
                break
            stats['posts'] += 1
            title = post.get('post_title') or ''
            if not title.upper().startswith(('[WP]', '[SP]', '[EU]', '[CW]', '[TT]')):
                continue
            for k, (text, score, timestamp) in enumerate(zip(post['comment_texts'],
                     post['comment_scores'], post['comment_times'])):
                stats['stories'] += 1
                when = teacher.parse_time(timestamp)
                if when is None or when >= teacher.CUTOFF:
                    stats['too_late'] += 1
                    continue
                if score is None or score < min_score or not text or teacher.BOT_RE.search(text) or len(text.split()) < teacher.MIN_WORDS:
                    stats['bot_or_short'] += 1
                    continue
                windows = teacher.excerpts(teacher.paragraphs(teacher.clean_markdown(text)))
                if not windows:
                    stats['no_window'] += 1
                    continue
                rng.shuffle(windows)
                clean = [(excerpt, words) for excerpt, words in windows[:6]
                         if not teacher.check_text(lexical_only, excerpt)]
                if not clean:
                    stats['rejected_markers'] += 1
                    continue
                info = dict(story_id=f'p{p_idx}_c{k}', prompt_id=f'p{p_idx}',
                            prompt_title=title, upvotes=int(score), posted=when.date().isoformat())
                for index, (excerpt, words) in enumerate(clean):
                    yield excerpt, {**info, 'words': words, 'passage': excerpt,
                                    'last': index == len(clean) - 1}

    kept = []
    current, accepted = None, False
    for doc, info in nlp.pipe(windows_to_check(), as_tuples=True,
                             batch_size=batch_size, n_process=n_process):
        if info['story_id'] != current:
            current, accepted = info['story_id'], False
        if not accepted and not any(ent.label_ in teacher.BLOCK_ENTS for ent in doc.ents):
            kept.append({k: v for k, v in info.items() if k != 'last'})
            stats['kept'] += 1
            accepted = True
        if info['last'] and not accepted:
            stats['rejected_markers'] += 1
    return kept, stats


def export(kept, out, n=200, seed=13):
    import pandas as pd
    if not kept:
        return
    frame = pd.DataFrame(kept)
    # Match column order of the original dict and CSV exactly.
    columns = ['story_id', 'prompt_id', 'prompt_title', 'upvotes', 'posted', 'words', 'passage']
    frame = frame[columns]
    frame['tier'] = pd.qcut(frame.upvotes.rank(method='first'), 3, labels=['low', 'mid', 'high'])
    frame.to_csv(out / 'candidates_all.csv', index=False)
    frame = frame.sample(frac=1, random_state=seed).drop_duplicates('prompt_id')
    sample = pd.concat([frame[frame.tier == tier].head(n // 3) for tier in ['high', 'mid', 'low']])
    sample = sample.assign(passage_id=[f'P{i:03d}' for i in range(len(sample))])
    for column in ['keep_manual', 'neutralized_edits', 'plausibility_ok', 'probe_recognized', 'notes']:
        sample[column] = ''
    columns = ['passage_id', 'tier', 'upvotes', 'posted', 'words', 'prompt_title', 'story_id',
               'passage', 'keep_manual', 'neutralized_edits', 'plausibility_ok', 'probe_recognized', 'notes']
    sample[columns].to_csv(out / 'candidates.csv', index=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'data/raw/WritingPrompts_preferences/data')
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--max-posts', type=int)
    parser.add_argument('--n', type=int, default=200)
    parser.add_argument('--min-score', type=int, default=2)
    parser.add_argument('--seed', type=int, default=13)
    parser.add_argument('--n-process', type=int, default=4)
    parser.add_argument('--batch-size', type=int, default=64)
    parser.add_argument('--progress-every', type=int, default=5000)
    args = parser.parse_args()
    if args.n_process < 1 or args.batch_size < 1 or args.progress_every < 1:
        parser.error('positive process/batch/progress counts required')
    if args.max_posts is not None and args.max_posts < 1:
        parser.error('max-posts must be positive')
    out = args.outdir.resolve()
    if out.exists() and any(out.iterdir()):
        raise FileExistsError('Use a new empty output directory')
    files = sorted(args.source.resolve().glob('*.parquet'))
    if not files:
        raise FileNotFoundError('No source Parquet files')
    inventory = parquet_inventory(files)
    out.mkdir(parents=True, exist_ok=True)
    from screen_passages import Tee
    import contextlib
    started = time.monotonic()
    metadata = dict(started_at=now(), status='running', engine='batched_teacher_rules',
        max_posts=args.max_posts, min_score=args.min_score, n=args.n, seed=args.seed,
        n_process=args.n_process, batch_size=args.batch_size, inputs=inventory,
        packages={p: importlib.metadata.version(p) for p in ('pandas', 'numpy', 'pyarrow', 'spacy', 'en_core_web_sm')},
        python=sys.version, api_calls=0, human_review_completed=False,
        source_sha256={p: hashlib.sha256((ROOT / 'src' / p).read_bytes()).hexdigest()
            for p in ('teacher/select_passages.py', 'screen_passages.py', 'screen_passages_batched.py')})
    verification = ROOT / 'configs/download_verification.json'
    if verification.exists():
        metadata['download_verification'] = json.loads(verification.read_text())
    (out / 'run_metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    try:
        with (out / 'filter_stats.log').open('x', encoding='utf-8') as log:
            tee = Tee(sys.stdout, log)
            with contextlib.redirect_stdout(tee), contextlib.redirect_stderr(tee):
                import spacy
                nlp = spacy.load('en_core_web_sm', disable=['lemmatizer'])
                print(json.dumps(dict(event='started', total_source_rows=sum(r['rows'] for r in inventory),
                    max_posts=args.max_posts, n_process=args.n_process)), flush=True)
                kept, stats = select(files, load_teacher(), nlp, args.max_posts, args.min_score,
                    args.seed, args.n_process, args.batch_size, args.progress_every)
                export(kept, out, args.n, args.seed)
                print('filter stats:', stats, flush=True)
                metadata['filter_stats'] = stats
                metadata['output_summary'] = summarize_candidates(out)
                print(json.dumps(metadata['output_summary']), flush=True)
        metadata['status'] = 'completed'
    except BaseException as error:
        metadata.update(status='failed', error_type=type(error).__name__, error=str(error))
        raise
    finally:
        metadata.update(ended_at=now(), elapsed_seconds=round(time.monotonic() - started, 3))
        (out / 'run_metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')


if __name__ == '__main__':
    main()
