"""Checks for the bounded-memory adapter; optional screening dependencies needed."""
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from screen_passages import iter_local_posts, load_teacher, parquet_inventory

HAS_DEPS = all(importlib.util.find_spec(name) is not None for name in ('pandas', 'pyarrow'))


@unittest.skipUnless(HAS_DEPS, 'requires the isolated screening environment')
class ScreeningReaderTests(unittest.TestCase):
    def test_batch_reader_preserves_original_row_order_and_values(self):
        import pyarrow as pa
        import pyarrow.parquet as pq
        rows = [dict(post_text='', post_title=f'[WP] fixture {i}', post_scores=i,
                     comment_texts=[f'comment {i}', 'second'], comment_scores=[2, 3],
                     comment_times=['1500000000', '1500000001']) for i in range(5)]
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / f'part{i}.parquet' for i in (0, 1)]
            pq.write_table(pa.Table.from_pylist(rows[:2]), paths[0])
            pq.write_table(pa.Table.from_pylist(rows[2:]), paths[1])
            teacher = load_teacher()
            original = list(teacher.iter_posts(types.SimpleNamespace(parquet=[str(p) for p in paths])))
            normalized = [{k: list(v) if k.startswith('comment_') else v for k, v in r.items()} for r in original]
            for batch_size in (1, 3):
                actual = list(iter_local_posts(paths, batch_size, 100, 0))
                self.assertEqual(actual, normalized)
                self.assertEqual(actual, rows)
            self.assertEqual(sum(p['rows'] for p in parquet_inventory(paths)), 5)

    def test_misaligned_comment_lists_fail_loudly(self):
        import pyarrow as pa
        import pyarrow.parquet as pq
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'bad.parquet'
            pq.write_table(pa.Table.from_pylist([dict(post_title='[WP] fixture',
                comment_texts=['one', 'two'], comment_scores=[2], comment_times=['1500000000'])]), path)
            with self.assertRaises(ValueError):
                list(iter_local_posts([path], 1, 100, 0))


if __name__ == '__main__':
    unittest.main()
