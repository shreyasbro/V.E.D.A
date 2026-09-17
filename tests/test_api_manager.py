import unittest
from veda.api_manager import api_manager

class TestAPIManager(unittest.TestCase):
    def setUp(self):
        # Clear providers for test
        with api_manager._lock:
            api_manager.providers.clear()
            api_manager.save_providers()

    def tearDown(self):
        with api_manager._lock:
            api_manager.providers.clear()
            api_manager.save_providers()

    def test_clean_slate_on_empty(self):
        self.assertEqual(len(api_manager.providers), 0)
        label, tip = api_manager.format_header_label('None')
        self.assertIn('NO AI CONFIGURED', label)
        pill, color = api_manager.format_status_pill(True, 'None')
        self.assertEqual(pill, 'NO AI CONFIGURED')

    def test_add_and_primary_selection(self):
        p1 = api_manager.add_provider('Provider 1', 'openai_compatible', 'http://localhost:11434/v1', 'llama3', '')
        self.assertTrue(p1.is_primary)
        self.assertEqual(len(api_manager.providers), 1)

        p2 = api_manager.add_provider('Provider 2', 'openai_compatible', 'https://api.openai.com/v1', 'gpt-4o', 'sk-test')
        self.assertFalse(p2.is_primary)

        api_manager.set_primary(p2.id)
        self.assertTrue(p2.is_primary)
        self.assertFalse(p1.is_primary)

    def test_remove_provider(self):
        p = api_manager.add_provider('Temporary', 'gemini', '', 'gemini-2.5-flash', '')
        self.assertEqual(len(api_manager.providers), 1)
        api_manager.remove_provider(p.id)
        self.assertEqual(len(api_manager.providers), 0)

if __name__ == '__main__':
    unittest.main()
