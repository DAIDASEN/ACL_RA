"""Run the unchanged teacher selector with bounded-memory local Parquet reads.

Only data loading, progress logging and audit artifacts are added. Filtering,
excerpt selection, random seed, quality tiers and final sampling are delegated
to src/teacher/select_passages.py without changing its bytes.
"""
import argparse
import contextlib
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {'post_title', 'comment_texts', 'comment_scores', 'comment_times'}


def now():
    return datetime.now(timezone.utc).isoformat()


class Tee:
    def __init__(self, *outputs):
        self.outputs = outputs

    def write(self, text):
        for output in self.outputs:
            output.write(text)
            output.flush()
        return len(text)

    def flush(self):
        for output in self.outputs:
            output.flush()


def load_teacher():
    path = ROOT / 'src/teacher/select_passages.py'
    spec = importlib.util.spec_from_file_location('teacher_passage_selector', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def parquet_inventory(files):
    import pyarrow.parquet as pq
    inventory = []
    for path in files:
        parquet = pq.ParquetFile(path)
        fields = set(parquet.schema_arrow.names)
        if not REQUIRED.issubset(fields):
            raise ValueError(f'{path.name}: required fields missing: {sorted(REQUIRED - fields)}')
        inventory.append(dict(path=str(path), bytes=path.stat().st_size,
                              rows=parquet.metadata.num_rows, columns=parquet.schema_arrow.names))
    return inventory


def iter_local_posts(files, batch_size, progress_every, started):
    import pyarrow.parquet as pq
    count = 0
    for path in files:
        for batch in pq.ParquetFile(path).iter_batches(batch_size=batch_size):
            for row in batch.to_pylist():
                lengths = [len(row[key]) for key in ('comment_texts', 'comment_scores', 'comment_times')]
                if len(set(lengths)) != 1:
                    raise ValueError(f'row {count}: comment lists have unequal lengths')
                yield row
                count += 1
                if count % progress_every == 0:
                    print(json.dumps(dict(event='progress', posts_yielded=count,
                        elapsed_seconds=round(time.monotonic() - started, 1))), flush=True)


def summarize_candidates(out):
    import pandas as pd
    summary = {}
    for name in ('candidates.csv', 'candidates_all.csv'):
        path = out / name
        if not path.exists():
            summary[name] = {'exists': False}
            continue
        frame = pd.read_csv(path, keep_default_na=False)
        words = frame['passage'].map(lambda text: len(text.split()))
        summary[name] = dict(exists=True, rows=len(frame),
            word_count_min=int(words.min()), word_count_max=int(words.max()),
            all_words_in_range=bool(words.between(150, 300).all()),
            tier_counts=frame['tier'].value_counts().to_dict(),
            duplicate_texts=int(frame['passage'].duplicated().sum()),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        if name == 'candidates.csv':
            summary[name]['duplicate_passage_ids'] = int(frame['passage_id'].duplicated().sum())
            summary[name]['duplicate_source_prompts'] = int(frame['story_id'].str.extract(r'^(p\d+)')[0].duplicated().sum())
            summary[name]['human_review_fields_empty'] = bool(frame[
                ['keep_manual', 'neutralized_edits', 'plausibility_ok', 'probe_recognized', 'notes']
            ].eq('').all().all())
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT / 'data/raw/WritingPrompts_preferences/data')
    parser.add_argument('--outdir', type=Path, required=True)
    parser.add_argument('--max-posts', type=int)
    parser.add_argument('--n', type=int, default=200)
    parser.add_argument('--min-score', type=int, default=2)
    parser.add_argument('--seed', type=int, default=13)
    parser.add_argument('--batch-size', type=int, default=64)
    parser.add_argument('--progress-every', type=int, default=2500)
    args = parser.parse_args()
    if args.batch_size < 1 or args.progress_every < 1 or (args.max_posts is not None and args.max_posts < 1):
        parser.error('batch-size, progress-every and max-posts must be positive')
    files = sorted(args.source.resolve().glob('*.parquet'))
    if not files:
        raise FileNotFoundError('No local Parquet files found')
    out = args.outdir.resolve()
    if out.exists() and any(out.iterdir()):
        raise FileExistsError('Use a new empty output directory; reviewed data must never be overwritten')
    out.mkdir(parents=True, exist_ok=True)
    inventory = parquet_inventory(files)
    teacher = load_teacher()
    started = time.monotonic()
    metadata = dict(started_at=now(), status='running', command=sys.argv,
        max_posts=args.max_posts, n=args.n, min_score=args.min_score, seed=args.seed,
        batch_size=args.batch_size, inputs=inventory,
        python=sys.version, packages={p: importlib.metadata.version(p) for p in ('pandas', 'numpy', 'pyarrow', 'spacy', 'en_core_web_sm')},
        teacher_script_sha256=hashlib.sha256((ROOT / 'src/teacher/select_passages.py').read_bytes()).hexdigest(),
        wrapper_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        engineering_change='row-order-preserving batched Parquet input and progress only; teacher filters and sampler unchanged',
        api_calls=0, human_review_completed=False)
    verification = ROOT / 'configs/download_verification.json'
    if verification.exists():
        metadata['download_verification'] = json.loads(verification.read_text())
    (out / 'run_metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    # Runtime replacement is confined to I/O. Original source remains unmodified.
    teacher.iter_posts = lambda _args: iter_local_posts(files, args.batch_size, args.progress_every, started)
    saved_argv, saved_cwd = sys.argv, Path.cwd()
    with (out / 'filter_stats.log').open('x', encoding='utf-8') as log:
        tee = Tee(sys.stdout, log)
        try:
            sys.argv = ['select_passages.py', '--n', str(args.n), '--seed', str(args.seed),
                        '--min-score', str(args.min_score)]
            if args.max_posts is not None:
                sys.argv += ['--max-posts', str(args.max_posts)]
            os.chdir(out)
            with contextlib.redirect_stdout(tee), contextlib.redirect_stderr(tee):
                print(json.dumps(dict(event='started', total_source_rows=sum(r['rows'] for r in inventory),
                                      max_posts=args.max_posts)), flush=True)
                teacher.main()
            metadata['status'] = 'completed'
            metadata['output_summary'] = summarize_candidates(out)
        except BaseException as error:
            metadata['status'] = 'failed'
            metadata['error_type'] = type(error).__name__
            metadata['error'] = str(error)
            raise
        finally:
            sys.argv = saved_argv
            os.chdir(saved_cwd)
            metadata['ended_at'] = now()
            metadata['elapsed_seconds'] = round(time.monotonic() - started, 3)
            (out / 'run_metadata.json').write_text(json.dumps(metadata, indent=2) + '\n')
    print(json.dumps(metadata['output_summary'], ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
