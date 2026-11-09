"""Same batched teacher rules; workers return entity labels instead of full Docs.

This avoids serializing tokenized spaCy documents in the parent process. The
parent retains original ordering, RNG, source metadata and sampling. No API use.
"""
import argparse
import contextlib
import hashlib
import importlib.metadata
import itertools
import json
import multiprocessing
import sys
import time
import types
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from screen_passages import ROOT, Tee, iter_local_posts, load_teacher, now, parquet_inventory, summarize_candidates
from screen_passages_batched import export

_WORKER_NLP = None
_BLOCKED = set()
_WORKER_TEACHER = None


def entity_labels(texts):
    # A blocked-label sentinel marks lexical rejection. It is never treated as
    # an actual detected entity or reported as one; the caller only needs pass/fail.
    sentinel = next(iter(_BLOCKED))
    output = [[sentinel] for _ in texts]
    lexical_only = lambda text: types.SimpleNamespace(ents=[])
    clean = [(i, text) for i, text in enumerate(texts)
             if not _WORKER_TEACHER.check_text(lexical_only, text)]
    docs = _WORKER_NLP.pipe((text for _, text in clean), batch_size=64)
    for (index, _), doc in zip(clean, docs, strict=True):
        output[index] = [ent.label_ for ent in doc.ents if ent.label_ in _BLOCKED]
    return output


class EntityOnlyPipe:
    def __init__(self, nlp, teacher):
        self.nlp, self.teacher = nlp, teacher

    def pipe(self, texts, as_tuples, batch_size, n_process):
        if not as_tuples:
            raise ValueError('Expected text/context pairs')
        global _WORKER_NLP, _BLOCKED, _WORKER_TEACHER
        _WORKER_NLP, _BLOCKED, _WORKER_TEACHER = self.nlp, self.teacher.BLOCK_ENTS, self.teacher
        iterator = iter(texts)

        def take_batch():
            return list(itertools.islice(iterator, batch_size))

        def emit(batch, labels):
            if len(batch) != len(labels):
                raise ValueError('NER results and text metadata became misaligned')
            for (_, info), entities in zip(batch, labels, strict=True):
                yield types.SimpleNamespace(ents=[types.SimpleNamespace(label_=label) for label in entities]), info

        if n_process == 1:
            while batch := take_batch():
                yield from emit(batch, entity_labels([text for text, _ in batch]))
            return
        # The repository runs on Linux. Explicit fork preserves the loaded model
        # without serializing its weights; no task generator is consumed in a thread.
        with ProcessPoolExecutor(max_workers=n_process, mp_context=multiprocessing.get_context('fork')) as pool:
            pending = deque()
            exhausted = False
            while pending or not exhausted:
                while not exhausted and len(pending) < n_process * 2:
                    batch = take_batch()
                    if not batch:
                        exhausted = True
                        break
                    future = pool.submit(entity_labels, [text for text, _ in batch])
                    pending.append((batch, future))
                if pending:
                    batch, future = pending.popleft()
                    yield from emit(batch, future.result())


def select(files, teacher, nlp, max_posts=None, min_score=2, seed=13,
           n_process=32, batch_size=64, progress_every=5000):
    """Lexical and NER checks run together in workers; ordering stays in parent."""
    import random
    rng = random.Random(seed)
    stats = {key: 0 for key in ('posts', 'stories', 'too_late', 'bot_or_short',
                               'no_window', 'rejected_markers', 'kept')}
    started = time.monotonic()

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
                windows = windows[:6]
                info = dict(story_id=f'p{p_idx}_c{k}', prompt_id=f'p{p_idx}',
                            prompt_title=title, upvotes=int(score), posted=when.date().isoformat())
                for index, (excerpt, words) in enumerate(windows):
                    yield excerpt, {**info, 'words': words, 'passage': excerpt,
                                    'last': index == len(windows) - 1}

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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'data/raw/WritingPrompts_preferences/data')
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--max-posts', type=int)
    parser.add_argument('--n', type=int, default=200)
    parser.add_argument('--min-score', type=int, default=2)
    parser.add_argument('--seed', type=int, default=13)
    parser.add_argument('--n-process', type=int, default=32)
    parser.add_argument('--batch-size', type=int, default=64)
    parser.add_argument('--progress-every', type=int, default=5000)
    args = parser.parse_args()
    if args.n_process < 1 or args.batch_size < 1 or args.progress_every < 1:
        parser.error('positive process/batch/progress counts required')
    if args.max_posts is not None and args.max_posts < 1:
        parser.error('max-posts must be positive')
    out = args.outdir.resolve()
    if out.exists() and any(out.iterdir()):
        raise FileExistsError('Output must be a new empty directory')
    files = sorted(args.source.resolve().glob('*.parquet'))
    if not files:
        raise FileNotFoundError('No source files')
    inventory = parquet_inventory(files)
    out.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    metadata = dict(status='running', started_at=now(), engine='ordered_parallel_lexical_and_entity_labels',
        max_posts=args.max_posts, min_score=args.min_score, n=args.n, seed=args.seed,
        n_process=args.n_process, batch_size=args.batch_size, inputs=inventory,
        packages={p: importlib.metadata.version(p) for p in ('pandas', 'numpy', 'pyarrow', 'spacy', 'en_core_web_sm')},
        python=sys.version, api_calls=0, human_review_completed=False,
        source_sha256={p: hashlib.sha256((ROOT / 'src' / p).read_bytes()).hexdigest() for p in
            ('teacher/select_passages.py', 'screen_passages.py', 'screen_passages_batched.py', 'screen_passages_parallel.py')})
    verification = ROOT / 'configs/download_verification.json'
    if verification.exists():
        metadata['download_verification'] = json.loads(verification.read_text())
    (out / 'run_metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    try:
        with (out / 'filter_stats.log').open('x', encoding='utf-8') as log:
            with contextlib.redirect_stdout(Tee(sys.stdout, log)), contextlib.redirect_stderr(Tee(sys.stderr, log)):
                import spacy
                nlp = spacy.load('en_core_web_sm', disable=['lemmatizer'])
                teacher = load_teacher()
                print(json.dumps(dict(event='started', total_source_rows=sum(r['rows'] for r in inventory),
                    max_posts=args.max_posts, n_process=args.n_process)), flush=True)
                pipe = EntityOnlyPipe(nlp, teacher)
                kept, stats = select(files, teacher, pipe, args.max_posts, args.min_score,
                    args.seed, args.n_process, args.batch_size, args.progress_every)
                export(kept, out, args.n, args.seed)
                metadata['filter_stats'] = stats
                metadata['output_summary'] = summarize_candidates(out)
                print('filter stats:', stats, flush=True)
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
