import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from build_requests import build_rows, load_config, prompt, validate_rows
from metrics import combine, cosine_distance, pair_mean, summarize


class FrameworkTests(unittest.TestCase):
    def setUp(self):
        self.config, self.digest = load_config(ROOT / 'configs/config.yaml')

    def test_pilot_complete_unique_and_deterministic(self):
        rows = build_rows(self.config, 'pilot', self.digest)
        self.assertEqual(len(rows), 576)
        self.assertEqual(len({r['story_id'] for r in rows}), 576)
        self.assertEqual(rows, build_rows(self.config, 'pilot', self.digest))

    def test_prompt_omissions_and_articles(self):
        self.assertEqual(prompt('NONE', 'OPEN', 'A'),
                         'Write a complete original short story in English of approximately 750 words. '
                         'Return only the story, without a title or commentary.')
        self.assertIn('Set the story in the United Kingdom.', prompt('GB', 'horror', 'A'))
        self.assertIn('in the United States.', prompt('US', 'OPEN', 'B'))
        self.assertIn('The genre is horror. Set the story in China.', prompt('CN', 'horror', 'A'))
        for wording in 'ABC':
            self.assertNotIn('genre', prompt('NONE', 'OPEN', wording))
            self.assertNotIn('NONE', prompt('NONE', 'horror', wording))

    def test_missing_duplicate_and_tampering_rejected(self):
        rows = build_rows(self.config, 'pilot', self.digest)
        for modified in [rows[:-1], rows[:-1] + [rows[0]]]:
            with self.assertRaises(ValueError):
                validate_rows(modified, self.config, 'pilot', self.digest)
        altered = copy.deepcopy(rows)
        altered[0]['user_prompt'] += ' Be more creative.'
        with self.assertRaises(ValueError):
            validate_rows(altered, self.config, 'pilot', self.digest)

    def test_formal_requires_approval_and_exact_models(self):
        with self.assertRaises(ValueError):
            build_rows(self.config, 'formal', self.digest)
        config = copy.deepcopy(self.config)
        config['formal_approved'] = True
        with self.assertRaises(ValueError):
            build_rows(config, 'formal', self.digest)
        for key in config['models']:
            config['models'][key]['api_model'] = 'TEST_ONLY_EXACT_MODEL'
        self.assertEqual(len(build_rows(config, 'formal', self.digest)), 5760)

    def test_formula_direction(self):
        values = combine(.30, .20, .50)
        self.assertAlmostEqual(values['D_typed'], .44)
        self.assertAlmostEqual(values['Delta'], .14)
        self.assertAlmostEqual(values['Delta'] - .20, -.06)
        self.assertEqual(values['Delta'] - values['Delta'], 0)

    def test_independent_identical_stories_and_self_exclusion(self):
        self.assertAlmostEqual(cosine_distance([1, 1], [1, 1]), 0)
        story = dict(story_id='one', vector=[1, 0])
        self.assertIsNone(pair_mean([story, story]))
        other = dict(story_id='two', vector=[1, 0])
        self.assertEqual(pair_mean([story, other]), 0)

    def test_row_order_missing_and_cell_isolation(self):
        genres = ['OPEN', 'romance', 'horror', 'science fiction', 'crime', 'comedy']
        rows = [dict(story_id=f'{genre}_{i}', genre=genre, vector=[1, i],
                     country='CN', model='M1', wording='A') for genre in genres for i in (0, 1)]
        original = summarize(rows)
        self.assertEqual(original, summarize(list(reversed(rows))))
        moved = [{**r, 'country': 'GB'} for r in rows]
        self.assertEqual(original, summarize(moved))
        self.assertIsNone(summarize(rows[:-1])['Delta'])
        rows[-1]['country'] = 'GB'
        with self.assertRaises(ValueError):
            summarize(rows)


if __name__ == '__main__':
    unittest.main()
