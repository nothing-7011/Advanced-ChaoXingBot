import unittest
import json
import os
import sys
from unittest.mock import MagicMock, patch

# Add repo root to path
sys.path.append(os.getcwd())

from agents.parser_agent import ImageParserAgent

class TestParserCache(unittest.TestCase):
    def setUp(self):
        self.test_parsed_file = "tests/parsed_test.json"
        if os.path.exists(self.test_parsed_file):
            os.remove(self.test_parsed_file)

    def tearDown(self):
        if os.path.exists(self.test_parsed_file):
            os.remove(self.test_parsed_file)

    @patch("agents.parser_agent.Image.open")
    @patch("agents.parser_agent.genai.Client")
    @patch("agents.parser_agent.requests.get")
    def test_caching_logic(self, mock_get, mock_client, mock_image_open):
        # Mock Gemini response
        mock_response = MagicMock()
        mock_response.text = "Gemini Description"
        mock_client.return_value.models.generate_content.return_value = mock_response

        # Mock Image download
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = b"fake_image_data"
        mock_get.return_value = mock_resp

        # Mock Image.open to return something valid-ish
        mock_image_open.return_value = MagicMock()

        # Initialize agent with test parsed file path
        # We will assume we added the parsed_path argument
        agent = ImageParserAgent(
            api_key="fake_key",
            parsed_path=self.test_parsed_file
        )

        # 1. Test loading: Should be empty initially
        self.assertEqual(agent.parsed_cache, {})

        # 2. Test processing a new URL
        url = "http://example.com/1.png"
        text = f'Check this <img src="{url}">'

        # Capture stdout to verify console output
        from io import StringIO
        captured_output = StringIO()
        original_stdout = sys.stdout
        sys.stdout = captured_output

        try:
            new_text = agent._process_text_with_images(text)
        finally:
            sys.stdout = original_stdout

        console_output = captured_output.getvalue()

        # Verify call to Gemini
        self.assertTrue(mock_client.return_value.models.generate_content.called)
        # Verify replacement
        self.assertIn("Gemini Description", new_text)
        # Verify cache update
        self.assertIn(url, agent.parsed_cache)
        self.assertEqual(agent.parsed_cache[url], " [Gemini Description] ")

        # Verify file saved
        with open(self.test_parsed_file, 'r') as f:
            saved_data = json.load(f)
            self.assertEqual(saved_data[url], " [Gemini Description] ")

        # Verify Console Output
        # Expectation: shorten URL to last 10 chars
        expected_short_url = url[-10:]
        self.assertIn(expected_short_url, console_output)
        self.assertIn("Gemini Description", console_output)

        # 3. Test using cache
        # Reset mocks to ensure they aren't called
        mock_client.return_value.models.generate_content.reset_mock()
        mock_get.reset_mock()

        # Call again with same URL
        new_text_2 = agent._process_text_with_images(text)

        # Verify NO call to Gemini or Download
        mock_client.return_value.models.generate_content.assert_not_called()
        mock_get.assert_not_called()

        self.assertEqual(new_text_2, new_text)

if __name__ == '__main__':
    unittest.main()
