import unittest

from app.service_browsing import is_menu_request


class ServiceBrowsingTests(unittest.TestCase):
    def test_general_menu_requests(self):
        for text in ('What services do you offer?', 'Show me the menu', 'Services please', 'Which treatments are available?'):
            with self.subTest(text=text):
                self.assertTrue(is_menu_request(text))

    def test_specific_questions_and_refusals_use_normal_conversation(self):
        for text in ('Tell me about Hair Spa', 'Book a haircut', "Don't show the services", 'What are the service prices?', 'What aftercare do your treatments need?'):
            with self.subTest(text=text):
                self.assertFalse(is_menu_request(text))
