import json
import os
import threading
from typing import List, Dict, Any
from api.logger import logger

class QuestionCollector:
    _instance = None
    _lock = threading.RLock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # Prevent re-initialization
        if not hasattr(self, "_initialized"):
            self.data_dir = "data"
            self._file_locks = {}
            self._initialized = True

    def _get_file_lock(self, course_id: str):
        with self._lock:
            if course_id not in self._file_locks:
                self._file_locks[course_id] = threading.RLock()
            return self._file_locks[course_id]

    def _get_file_path(self, course_id: str):
        return os.path.join(self.data_dir, str(course_id), "questions.json")

    def _ensure_dir(self, course_id: str):
        path = os.path.join(self.data_dir, str(course_id))
        os.makedirs(path, exist_ok=True)

    def add_questions(self, course_id: str, questions: List[Dict[str, Any]]):
        if not questions:
            return

        self._ensure_dir(course_id)
        file_path = self._get_file_path(course_id)
        lock = self._get_file_lock(course_id)

        with lock:
            current_data = {"finished": False, "questions": []}
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                        if content:
                            current_data = json.loads(content)
                except Exception as e:
                    logger.error(f"Failed to load existing questions for course {course_id}: {e}")

            existing_ids = {str(q.get("id")) for q in current_data["questions"] if "id" in q}

            added_count = 0
            for q in questions:
                q_id = str(q.get("id"))
                if q_id and q_id in existing_ids:
                    continue
                current_data["questions"].append(q)
                if q_id:
                    existing_ids.add(q_id)
                added_count += 1

            if added_count > 0:
                try:
                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(current_data, f, ensure_ascii=False, indent=2)
                    logger.info(f"Saved {added_count} new questions for course {course_id}")
                except Exception as e:
                    logger.error(f"Failed to save questions for course {course_id}: {e}")

    def mark_finished(self, course_id: str):
        self._ensure_dir(course_id)
        file_path = self._get_file_path(course_id)
        lock = self._get_file_lock(course_id)

        with lock:
            current_data = {"finished": False, "questions": []}
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                         content = f.read()
                         if content:
                             current_data = json.loads(content)
                except Exception as e:
                    logger.error(f"Failed to load questions for marking finish {course_id}: {e}")

            if not current_data["finished"]:
                current_data["finished"] = True
                try:
                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(current_data, f, ensure_ascii=False, indent=2)
                    logger.info(f"Marked course {course_id} questions collection as finished.")
                except Exception as e:
                    logger.error(f"Failed to mark finished for course {course_id}: {e}")
            else:
                logger.info(f"Course {course_id} already marked as finished.")
