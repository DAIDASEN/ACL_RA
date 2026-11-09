import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from deepseek_interface_test import api_credentials, flash_manifest, flash_payload
from interface_test import make_manifest


class DeepSeekInterfaceTests(unittest.TestCase):
    def test_provider_key_and_shared_key_stay_on_their_hosts(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / '.env'
            path.write_text('key=shared_fake\nbase_url=https://gateway.example/v1\n')
            self.assertEqual(api_credentials(path)[:2], ('shared_fake', 'https://gateway.example/v1'))
            path.write_text('key=shared_fake\nbase_url=https://gateway.example/v1\nDEEPSEEK_API_KEY=ds_fake\n')
            self.assertEqual(api_credentials(path)[:2], ('ds_fake', 'https://api.deepseek.com'))
            path.write_text('key=shared_fake\n')
            with self.assertRaises(ValueError):
                api_credentials(path)

    def test_same_prompts_and_independent_ids(self):
        flash = flash_manifest()
        luna = make_manifest('gpt-6-luna')
        self.assertEqual([r['user_prompt'] for r in flash], [r['user_prompt'] for r in luna])
        self.assertTrue(all(r['story_id'].startswith('T_DEEPSEEK_FLASH_') for r in flash))
        self.assertEqual(flash_payload(flash[0])['thinking'], {'type': 'disabled'})
        self.assertEqual(flash_payload(flash[0])['max_tokens'], 2500)


if __name__ == '__main__':
    unittest.main()
