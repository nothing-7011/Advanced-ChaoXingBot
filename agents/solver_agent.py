import json
import os
import time
from typing import List, Dict, Any

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from api.logger import logger
from api.collector import QuestionCollector

class QuestionSolution(BaseModel):
    thinking: str = Field(description="Step-by-step reasoning details")
    answer: str = Field(description="The final answer. For choice questions, return the option letters (e.g., 'A', 'AC'). For judgment, return '正确' or '错误'. For completion, return the text.")

class SolverAgent:
    def __init__(self, api_key: str, model_name: str = "gemini-2.0-flash", temperature: float = 0.7, request_interval: float = 2.0, endpoint: str = None):
        self.api_key = api_key
        self.model_name = model_name
        self.temperature = temperature
        self.request_interval = request_interval
        self.endpoint = endpoint
        self.client = None

        if self.api_key:
            try:
                http_options = None
                if self.endpoint:
                    http_options = types.HttpOptions(base_url=self.endpoint)

                self.client = genai.Client(api_key=self.api_key, http_options=http_options)
            except Exception as e:
                logger.error(f"Failed to initialize Gemini client for SolverAgent: {e}")

    def solve_questions(self, course_id: str):
        if not self.client:
            logger.error("Solver Agent not initialized (missing API key).")
            return

        collector = QuestionCollector()
        original_questions_path = collector._get_file_path(course_id)
        # Use plain_questions.json as source
        questions_path = os.path.join(os.path.dirname(original_questions_path), "plain_questions.json")
        # answers.json path in the same directory
        answers_path = os.path.join(os.path.dirname(original_questions_path), "answers.json")

        if not os.path.exists(questions_path):
            logger.error(f"plain_questions.json not found at {questions_path}. Please run Parser Agent first.")
            return

        try:
            with open(questions_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load questions JSON: {e}")
            return

        questions = data.get("questions", [])
        if not questions:
            logger.info(f"No questions to solve for course {course_id}")
            return

        # Load existing answers
        answers_map = {}
        if os.path.exists(answers_path):
            try:
                with open(answers_path, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
                    existing_answers = []
                    if isinstance(existing_data, list):
                        existing_answers = existing_data
                    elif isinstance(existing_data, dict):
                        existing_answers = existing_data.get("answers", [])

                    for item in existing_answers:
                        if "id" in item:
                            answers_map[str(item["id"])] = item
            except Exception as e:
                logger.error(f"Failed to load existing answers: {e}")

        logger.info(f"Starting solving {len(questions)} questions for course {course_id}...")

        solved_count = 0

        def save_progress():
            is_completed = True
            for q in questions:
                q_id = str(q.get("id"))
                if q_id and q_id not in answers_map:
                    is_completed = False
                    break
            self._save_answers(answers_path, answers_map, is_completed)

        for q in questions:
            q_id = str(q.get("id"))
            if not q_id:
                continue

            if q_id in answers_map:
                continue

            # Rate limit
            time.sleep(self.request_interval)

            title = q.get("title", "")
            options = q.get("options", "")

            # Convert options list to string if necessary
            if isinstance(options, list):
                options = "\n".join([str(opt) for opt in options])

            q_type = q.get("type", "unknown")

            prompt = f"""
You are an expert tutor. Please solve the following question.
Type: {q_type}
Question: {title}
Options: {options}

Please think step-by-step and provide the answer.
For single/multiple choice questions, return the Option Letters (e.g., "A", "AB", "AC").
For judgment questions, return "正确" or "错误".
For completion questions, return the answer text.
"""

            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=self.temperature,
                        response_mime_type="application/json",
                        response_schema=QuestionSolution,
                    )
                )

                answer_text = ""
                if response.text:
                    try:
                        # Parse JSON response using Pydantic
                        solution = QuestionSolution.model_validate_json(response.text)
                        answer_text = solution.answer.strip()
                        if hasattr(solution, 'thinking'):
                            logger.debug(f"Question {q_id} thinking: {solution.thinking}")
                    except Exception as e:
                        logger.warning(f"Failed to parse structured response for question {q_id}: {e}. Raw: {response.text}")
                        # Fallback parsing
                        try:
                            res_json = json.loads(response.text)
                            answer_text = res_json.get("answer", "")
                            if isinstance(answer_text, list):
                                answer_text = " ".join([str(x) for x in answer_text])
                            answer_text = str(answer_text).strip()
                        except:
                            answer_text = response.text.strip()

                if answer_text:
                    logger.info(f"Solved question {q_id}: {answer_text[:50]}...")
                    answers_map[q_id] = {
                        "id": q_id,
                        "answer": answer_text,
                        "type": q_type
                    }
                    solved_count += 1

                    save_progress()

            except Exception as e:
                logger.error(f"Failed to solve question {q_id}: {e}")

        # Final check to ensure completion status is updated even if no new questions were solved
        save_progress()

        logger.info(f"Finished solving. New answers: {solved_count}. Total answers: {len(answers_map)}.")

    def _save_answers(self, path: str, answers_map: Dict, is_completed: bool):
        try:
            # Convert map back to list
            answers_list = list(answers_map.values())
            output_data = {
                "completed": is_completed,
                "answers": answers_list
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save answers to {path}: {e}")
