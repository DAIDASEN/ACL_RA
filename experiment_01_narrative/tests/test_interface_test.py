import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from interface_test import make_manifest, normalize_usage, read_dotenv, redact


class InterfaceTests(unittest.TestCase):
    def test_dotenv_does_not_execute_shell_and_redacts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            path.write_text('# comment\nkey="fake$(id)"\nbase_url=https://example.org/v1 # comment\n')
            values = read_dotenv(path)
            self.assertEqual(values['key'], 'fake$(id)')
            self.assertEqual(values['base_url'], 'https://example.org/v1')
            self.assertEqual(redact({'nested': ['fake$(id)']}, values['key']), {'nested': ['[REDACTED]']})

    def test_missing_usage_stays_unknown(self):
        self.assertIsNone(normalize_usage({})['total_tokens'])
        usage = normalize_usage({'usage': {'prompt_tokens': 12, 'completion_tokens': 34,
                  'total_tokens': 46, 'completion_tokens_details': {'reasoning_tokens': 5}}})
        self.assertEqual(usage['total_tokens'], 46)
        self.assertEqual(usage['reasoning_tokens'], 5)

    def test_test_manifest_is_balanced_and_separate(self):
        rows = make_manifest('gpt-6-luna')
        self.assertEqual(len(rows), 8)
        self.assertEqual(len({r['story_id'] for r in rows}), 8)
        self.assertTrue(all(r['stage'] == 'interface_test' for r in rows))
        self.assertEqual({r['country'] for r in rows}, {'GB', 'CN'})
        for country in ['GB', 'CN']:
            for genre in ['OPEN', 'horror']:
                self.assertEqual(sum(r['country'] == country and r['genre'] == genre for r in rows), 2)


if __name__ == '__main__':
    unittest.main()
