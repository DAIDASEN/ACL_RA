import csv
import hashlib
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from build_passage_review_pack import build


class ReviewPackTests(unittest.TestCase):
    def test_flags_do_not_approve_or_mutate_candidates_and_reading_hides_source(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            source = directory / 'candidates.csv'
            row = dict(passage_id='P000', tier='high', upvotes='5', posted='2015-01-01',
                words='150', prompt_title='PRIVATE_PROMPT_SENTINEL', story_id='p10_c1',
                passage=' '.join(['interstellar'] + ['word'] * 149),
                keep_manual='', neutralized_edits='', plausibility_ok='', probe_recognized='', notes='')
            with source.open('w', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=list(row))
                writer.writeheader()
                writer.writerow(row)
            before = hashlib.sha256(source.read_bytes()).hexdigest()
            out = directory / 'review'
            metadata = build(source, out)
            self.assertFalse(metadata['human_review_completed'])
            self.assertEqual(metadata['heuristic_attention_rows'], 1)
            self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(), before)
            with (out / 'review_sheet.csv').open() as handle:
                sheet = list(csv.DictReader(handle))
            for field in ('keep_manual', 'plausibility_ok', 'probe_recognized', 'reviewer_id'):
                self.assertEqual(sheet[0][field], '')
            self.assertNotIn('PRIVATE_PROMPT_SENTINEL', (out / 'reading_pack.md').read_text())
            for index in (1, 2, 3):
                with (out / f'plausibility_reviewer_{index}.csv').open() as handle:
                    ratings = list(csv.DictReader(handle))
                self.assertTrue(all(value == '' for key, value in ratings[0].items() if key != 'passage_id'))
            with self.assertRaises(FileExistsError):
                build(source, out)


if __name__ == '__main__':
    unittest.main()
