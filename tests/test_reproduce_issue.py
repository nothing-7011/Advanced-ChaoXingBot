import unittest
import json
import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch
import sys

# Add repo root to path
sys.path.append(os.getcwd())

from api.collector import QuestionCollector
from api.base import Chaoxing, Account
from api.answer import Tiku

class TestReproduction(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.original_cwd = os.getcwd()
        # Mock QuestionCollector data dir
        self.patcher = patch("api.collector.QuestionCollector._get_file_path")
        self.mock_get_file_path = self.patcher.start()
        # Ensure that regardless of course_id, we put it in our temp dir
        self.mock_get_file_path.side_effect = lambda course_id: os.path.join(self.test_dir, str(course_id), "questions.json")

        # We also need to mock _ensure_dir in collector to avoid trying to create dirs in real data/
        self.patcher2 = patch("api.collector.QuestionCollector._ensure_dir")
        self.mock_ensure_dir = self.patcher2.start()
        self.mock_ensure_dir.side_effect = lambda course_id: os.makedirs(os.path.join(self.test_dir, str(course_id)), exist_ok=True)


    def tearDown(self):
        self.patcher.stop()
        self.patcher2.stop()
        shutil.rmtree(self.test_dir)

    def test_collector_update_logic(self):
        collector = QuestionCollector()
        course_id = "123"

        # 1. Add initial question
        q1 = {"id": "1", "title": "Old Title", "options": "A,B", "type": "single"}
        collector.add_questions(course_id, [q1])

        # Verify
        file_path = os.path.join(self.test_dir, course_id, "questions.json")
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertEqual(data["questions"][0]["title"], "Old Title")

        # 2. Update question with same ID but new title
        q1_new = {"id": "1", "title": "New Title", "options": "A,B", "type": "single"}
        collector.add_questions(course_id, [q1_new])

        # Verify
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            self.assertEqual(len(data["questions"]), 1)
            self.assertEqual(data["questions"][0]["title"], "New Title")

        print("Collector update logic verified.")

    @patch("api.base.SessionManager")
    def test_key_error_fix(self, mock_sm):
        # Mocking Tiku
        mock_tiku = MagicMock(spec=Tiku)
        mock_tiku.name = 'AI大模型答题'
        mock_tiku.query.return_value = None # Simulate no answer found
        mock_tiku.DISABLE = False
        mock_tiku.COVER_RATE = 0.8
        mock_tiku.get_submit_params.return_value = "1" # Save mode

        # Mocking Chaoxing
        account = Account("user", "pass")
        cx = Chaoxing(account=account, tiku=mock_tiku)

        # Prepare inputs
        course = {"courseId": "1001", "clazzId": "2001", "cpi": "3001"}
        job = {"jobid": "work-12345", "enc": "enc_val"}
        job_info = {"knowledgeid": "k1", "ktoken": "kt", "cpi": "3001"}

        # Mock Session and Responses
        mock_session = MagicMock()
        mock_sm.get_session.return_value = mock_session

        # Mock responses
        mock_resp_get = MagicMock()
        mock_resp_get.status_code = 200
        mock_resp_get.text = "<html>...</html>"

        with patch("api.base.decode_questions_info") as mock_decode:
            mock_decode.return_value = {
                "questions": [
                    {
                        "id": "999",
                        "title": "Test Q",
                        "type": "single",
                        "options": "A. 1\nB. 2",
                        "answerField": {"answer999": "", "answertype999": "0"}
                    }
                ]
            }

            # The GET request returns the mock response
            mock_session.get.return_value = mock_resp_get

            # The POST request (submission)
            mock_resp_post = MagicMock()
            mock_resp_post.status_code = 200
            mock_resp_post.json.return_value = {"status": True, "msg": "Saved"}
            mock_session.post.return_value = mock_resp_post

            # Run study_work
            try:
                cx.study_work(course, job, job_info)
            except KeyError as e:
                self.fail(f"KeyError raised: {e}")
            except Exception as e:
                import traceback
                traceback.print_exc()
                self.fail(f"Exception raised: {e}")

            # Verify that query was called
            mock_tiku.query.assert_called()

            # Verify that the post was called (implying we reached the end without crashing)
            mock_session.post.assert_called()

            print("KeyError fix verified.")

    @patch("api.base.SessionManager")
    def test_completion_submission_format(self, mock_sm):
        # Mocking Tiku
        mock_tiku = MagicMock(spec=Tiku)
        mock_tiku.name = 'AI大模型答题'
        mock_tiku.query.return_value = "MyAnswer"
        mock_tiku.DISABLE = False
        mock_tiku.COVER_RATE = 0.8
        mock_tiku.get_submit_params.return_value = "1" # Save mode

        # Mocking Chaoxing
        account = Account("user", "pass")
        cx = Chaoxing(account=account, tiku=mock_tiku)

        # Prepare inputs
        course = {"courseId": "1001", "clazzId": "2001", "cpi": "3001"}
        job = {"jobid": "work-12345", "enc": "enc_val"}
        job_info = {"knowledgeid": "k1", "ktoken": "kt", "cpi": "3001"}

        # Mock Session and Responses
        mock_session = MagicMock()
        mock_sm.get_session.return_value = mock_session

        # Mock responses
        mock_resp_get = MagicMock()
        mock_resp_get.status_code = 200
        # Minimal HTML reproducing the completion question structure
        mock_resp_get.text = """
        <html>
        <form>
            <input type="hidden" name="tiankongsize123" value="1">
            <div class="singleQuesId" data="123">
                <div class="TiMu newTiMu" data="2">
                    <div class="Zy_TItle">Title</div>
                </div>
                <div class="clearfix">
                    <textarea name="answerEditor1231" id="answerEditor1231"></textarea>
                </div>
            </div>
        </form>
        </html>
        """

        mock_session.get.return_value = mock_resp_get

        # The POST request (submission)
        mock_resp_post = MagicMock()
        mock_resp_post.status_code = 200
        mock_resp_post.json.return_value = {"status": True, "msg": "Saved"}
        mock_session.post.return_value = mock_resp_post

        # Run study_work
        # Note: We are NOT mocking decode_questions_info here, so we test the integration of decode and base
        cx.study_work(course, job, job_info)

        # Verify POST data
        mock_session.post.assert_called()
        args, kwargs = mock_session.post.call_args
        data = kwargs['data']

        print("Posted data:", data)

        # We expect answerEditor1231 to be present and have value "MyAnswer"
        self.assertIn("answerEditor1231", data)
        self.assertEqual(data["answerEditor1231"], "MyAnswer")
        # Ensure tiankongsize is also there
        self.assertIn("tiankongsize123", data)

if __name__ == "__main__":
    unittest.main()
