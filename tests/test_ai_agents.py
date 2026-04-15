import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest.mock import MagicMock, patch

sys.path.append(os.getcwd())

from agents.parser_agent import ImageParserAgent
from agents.solver_agent import SolverAgent


class TestAIAgents(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.parsed_cache_path = os.path.join(self.test_dir, "parsed.json")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    @patch("agents.parser_agent.Image.open")
    @patch("agents.parser_agent.requests.post")
    @patch("agents.parser_agent.requests.get")
    def test_parser_openai_compatible(self, mock_get, mock_post, mock_image_open):
        mock_get.return_value = MagicMock(status_code=200, content=b"fake_image")
        mock_image = MagicMock()
        mock_image_open.return_value = mock_image

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Image Description"}}]
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        agent = ImageParserAgent(
            api_type="openai_compatible",
            api_key="fake_key",
            endpoint="https://example.com/v1",
            parsed_path=self.parsed_cache_path,
        )

        output = agent._process_text_with_images(
            'hello <img src="http://example.com/a.png">'
        )

        self.assertIn("Image Description", output)
        mock_post.assert_called_once()
        payload = mock_post.call_args.kwargs["json"]
        self.assertEqual(payload["model"], agent.model_name)
        self.assertEqual(payload["messages"][0]["content"][1]["type"], "image_url")

    @patch("agents.solver_agent.genai.Client")
    def test_solver_gemini_structured_response(self, mock_client):
        mock_response = MagicMock()
        mock_response.text = '{"thinking": "reasoning", "answer": "AC"}'
        mock_client.return_value.models.generate_content.return_value = mock_response

        agent = SolverAgent(api_type="gemini_v1beta", api_key="fake_key")
        answer = agent._solve_question("multiple", "Q", "A\nB", "1")

        self.assertEqual(answer, "AC")

    @patch("agents.solver_agent.requests.post")
    def test_solver_openai_json_response(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": '{"answer": "B"}'}}]
        }
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        agent = SolverAgent(
            api_type="openai_compatible",
            api_key="fake_key",
            endpoint="https://example.com/v1",
        )
        answer = agent._solve_question("single", "Q", "A\nB", "2")

        self.assertEqual(answer, "B")
        mock_post.assert_called_once()

    def test_solver_fallback_cleans_polluted_text(self):
        agent = SolverAgent(api_type="openai_compatible", api_key="fake_key")

        self.assertEqual(
            agent._clean_answer_text("C<system-reminder>noise", "single"),
            "C",
        )
        self.assertEqual(
            agent._clean_answer_text("答案是正确", "judgement"),
            "正确",
        )

    def test_solver_extracts_answer_list_json(self):
        agent = SolverAgent(api_type="openai_compatible", api_key="fake_key")
        answer = agent._clean_answer_text(
            '```json\n{"Answer": ["foo", "bar"]}\n```', "completion"
        )
        self.assertEqual(answer, "foo bar")


if __name__ == "__main__":
    unittest.main()
