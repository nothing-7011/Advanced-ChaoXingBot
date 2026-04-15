import json
import os
import re
import time
from typing import Dict, Optional

import requests
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from api.logger import logger
from api.collector import QuestionCollector


class QuestionSolution(BaseModel):
    thinking: str = Field(description="Step-by-step reasoning details")
    answer: str = Field(
        description="The final answer. For choice questions, return the option letters (e.g., 'A', 'AC'). For judgment, return '正确' or '错误'. For completion, return the text."
    )


class SolverAgent:
    def __init__(
        self,
        api_type: str,
        api_key: str,
        model_name: str = "gemini-2.0-flash",
        temperature: float = 0.7,
        request_interval: float = 2.0,
        endpoint: Optional[str] = None,
    ):
        self.api_type = api_type
        self.api_key = api_key
        self.model_name = model_name
        self.temperature = temperature
        self.request_interval = request_interval
        self.endpoint = endpoint
        self.client = None

        if self.api_key and self.api_type == "gemini_v1beta":
            try:
                http_options = None
                if self.endpoint:
                    http_options = types.HttpOptions(base_url=self.endpoint)

                self.client = genai.Client(
                    api_key=self.api_key, http_options=http_options
                )
            except Exception as e:
                logger.error(f"Failed to initialize Gemini client for SolverAgent: {e}")

    def _openai_chat_completions_url(self) -> str:
        base_url = (self.endpoint or "https://api.openai.com/v1").rstrip("/")
        if base_url.endswith("/chat/completions"):
            return base_url
        if base_url.endswith("/v1"):
            return f"{base_url}/chat/completions"
        return f"{base_url}/v1/chat/completions"

    def _remove_md_json_wrapper(self, text: str) -> str:
        match = re.search(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", text, re.DOTALL)
        return match.group(1).strip() if match else text.strip()

    def _extract_answer_from_json(self, raw_text: str) -> Optional[str]:
        try:
            parsed = json.loads(self._remove_md_json_wrapper(raw_text))
        except Exception:
            return None

        if isinstance(parsed, dict):
            answer = parsed.get("answer")
            if answer is None:
                answer = parsed.get("Answer")
        else:
            answer = None

        if isinstance(answer, list):
            return (
                " ".join(
                    str(item).strip() for item in answer if str(item).strip()
                ).strip()
                or None
            )
        if answer is not None:
            answer_text = str(answer).strip()
            return answer_text or None
        return None

    def _extract_choice_letters(self, raw_text: str) -> Optional[str]:
        normalized = re.sub(r"[^A-Z]", "", raw_text.upper())
        if not normalized:
            return None

        deduped = ""
        for char in normalized:
            if char in "ABCDEFGH" and char not in deduped:
                deduped += char
        return deduped or None

    def _clean_answer_text(self, raw_text: str, q_type: str) -> str:
        raw_text = raw_text.strip()
        json_answer = self._extract_answer_from_json(raw_text)
        if json_answer:
            return json_answer

        raw_text = self._remove_md_json_wrapper(raw_text)
        if "<" in raw_text:
            raw_text = raw_text.split("<", 1)[0].strip()

        if q_type in {"single", "multiple"}:
            choice_answer = self._extract_choice_letters(raw_text)
            if choice_answer:
                return choice_answer
        elif q_type == "judgement":
            if "正确" in raw_text:
                return "正确"
            if "错误" in raw_text:
                return "错误"
        return raw_text

    def _build_solver_prompt(self, q_type: str, title: str, options: str) -> str:
        return f"""
You are an expert tutor. Please solve the following question.
Type: {q_type}
Question: {title}
Options: {options}

Please think step-by-step and provide the answer.
For single/multiple choice questions, return the Option Letters (e.g., \"A\", \"AB\", \"AC\").
For judgment questions, return \"正确\" or \"错误\".
For completion questions, return the answer text.
"""

    def _solve_with_gemini(self, prompt: str, q_id: str) -> str:
        if not self.client:
            raise RuntimeError("Gemini client is not initialized")

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=self.temperature,
                response_mime_type="application/json",
                response_schema=QuestionSolution,
            ),
        )

        if not response.text:
            return ""

        try:
            solution = QuestionSolution.model_validate_json(response.text)
            if getattr(solution, "thinking", None):
                logger.debug(f"Question {q_id} thinking: {solution.thinking}")
            return solution.answer.strip()
        except Exception as e:
            logger.warning(
                f"Failed to parse structured response for question {q_id}: {e}. Raw: {response.text}"
            )
            return response.text.strip()

    def _solve_with_openai(self, prompt: str) -> str:
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": 'Return JSON only: {"answer": "..."}. For choice questions, answer with option letters. For judgement, answer with 正确 or 错误.',
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            "stream": False,
            "temperature": self.temperature,
            "response_format": {"type": "text"},
        }

        response = requests.post(
            self._openai_chat_completions_url(),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=60,
        )
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"]
        return content.strip()

    def _solve_question(self, q_type: str, title: str, options: str, q_id: str) -> str:
        prompt = self._build_solver_prompt(q_type, title, options)
        if self.api_type == "gemini_v1beta":
            raw_answer = self._solve_with_gemini(prompt, q_id)
        elif self.api_type == "openai_compatible":
            raw_answer = self._solve_with_openai(prompt)
        else:
            raise ValueError(f"Unsupported solver api_type: {self.api_type}")
        return self._clean_answer_text(raw_answer, q_type)

    def solve_questions(self, course_id: str):
        if not self.api_key:
            logger.error("Solver Agent not initialized (missing API key).")
            return

        collector = QuestionCollector()
        original_questions_path = collector._get_file_path(course_id)
        # Use plain_questions.json as source
        questions_path = os.path.join(
            os.path.dirname(original_questions_path), "plain_questions.json"
        )
        # answers.json path in the same directory
        answers_path = os.path.join(
            os.path.dirname(original_questions_path), "answers.json"
        )

        if not os.path.exists(questions_path):
            logger.error(
                f"plain_questions.json not found at {questions_path}. Please run Parser Agent first."
            )
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

        logger.info(
            f"Starting solving {len(questions)} questions for course {course_id}..."
        )

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

            try:
                answer_text = self._solve_question(q_type, title, options, q_id)

                if answer_text:
                    logger.info(f"Solved question {q_id}: {answer_text[:50]}...")
                    answers_map[q_id] = {
                        "id": q_id,
                        "answer": answer_text,
                        "type": q_type,
                    }
                    solved_count += 1

                    save_progress()

            except Exception as e:
                logger.error(f"Failed to solve question {q_id}: {e}")

        # Final check to ensure completion status is updated even if no new questions were solved
        save_progress()

        logger.info(
            f"Finished solving. New answers: {solved_count}. Total answers: {len(answers_map)}."
        )

    def _save_answers(self, path: str, answers_map: Dict, is_completed: bool):
        try:
            # Convert map back to list
            answers_list = list(answers_map.values())
            output_data = {"completed": is_completed, "answers": answers_list}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(output_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save answers to {path}: {e}")
