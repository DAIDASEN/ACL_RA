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

from screen_passages import ROOT, Tee, load_teacher, now, parquet_inventory, summarize_candidates
from screen_passages_batched import export, select

_WORKER_NLP = None
_BLOCKED = set()


def entity_labels(texts):
    return [[ent.label_ for ent in doc.ents if ent.label_ in _BLOCKED]
            for doc in _WORKER_NLP.pipe(texts, batch_size=64)]


class EntityOnlyPipe:
    def __init__(self, nlp, blocked):
        self.nlp, self.blocked = nlp, blocked

    def pipe(self, texts, as_tuples, batch_size, n_process):
        if not as_tuples:
            raise ValueError('Expected text/context pairs')
        global _WORKER_NLP, _BLOCKED
        _WORKER_NLP, _BLOCKED = self.nlp, self.blocked
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
    metadata = dict(status='running', started_at=now(), engine='ordered_parallel_entity_labels',
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
                pipe = EntityOnlyPipe(nlp, teacher.BLOCK_ENTS)
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
