import json
import os
import re
from typing import List, Dict, Any, Set

# Try to use the project logger, fallback to print
try:
    from api.logger import logger
except ImportError:
    import logging
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("ClusterManager")

class ClusterManager:
    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        self.sets_dir = os.path.join(data_dir, "sets")

    def run(self):
        if not os.path.exists(self.sets_dir):
            logger.info(f"Sets directory {self.sets_dir} does not exist. Nothing to do.")
            return

        course_ids = [d for d in os.listdir(self.sets_dir) if os.path.isdir(os.path.join(self.sets_dir, d))]

        for course_id in course_ids:
            target_dir = os.path.join(self.data_dir, course_id)
            if not os.path.exists(target_dir):
                continue

            logger.info(f"Processing course {course_id}...")
            self.process_course(course_id)

    def process_course(self, course_id: str):
        source_dir = os.path.join(self.sets_dir, course_id)
        target_dir = os.path.join(self.data_dir, course_id)

        # Load Source Data
        src_q_path = os.path.join(source_dir, "questions.json")
        src_pq_path = os.path.join(source_dir, "plain_questions.json")
        src_ans_path = os.path.join(source_dir, "answers.json")

        if not os.path.exists(src_q_path) or not os.path.exists(src_ans_path):
            logger.warning(f"Missing source files for course {course_id}")
            return

        try:
            with open(src_q_path, 'r', encoding='utf-8') as f:
                src_questions_data = json.load(f)
            src_questions = src_questions_data.get("questions", [])

            src_plain_questions = {}
            if os.path.exists(src_pq_path):
                with open(src_pq_path, 'r', encoding='utf-8') as f:
                    pq_data = json.load(f)
                    for q in pq_data.get("questions", []):
                        if "id" in q:
                            src_plain_questions[str(q["id"])] = q

            with open(src_ans_path, 'r', encoding='utf-8') as f:
                src_answers_data = json.load(f)

            src_answers = {}
            if isinstance(src_answers_data, list):
                 for a in src_answers_data:
                     if "id" in a: src_answers[str(a["id"])] = a
            elif isinstance(src_answers_data, dict):
                 for a in src_answers_data.get("answers", []):
                     if "id" in a: src_answers[str(a["id"])] = a

        except Exception as e:
            logger.error(f"Error loading source data for {course_id}: {e}")
            return

        # Load Target Data
        tgt_q_path = os.path.join(target_dir, "questions.json")
        if not os.path.exists(tgt_q_path):
            logger.warning(f"Target questions.json not found for {course_id}")
            return

        try:
            with open(tgt_q_path, 'r', encoding='utf-8') as f:
                tgt_questions_data = json.load(f)
            tgt_questions = tgt_questions_data.get("questions", [])
        except Exception as e:
            logger.error(f"Error loading target questions for {course_id}: {e}")
            return

        # Prepare Target Output
        tgt_ans_path = os.path.join(target_dir, "answers.json")
        tgt_pq_path = os.path.join(target_dir, "plain_questions.json")

        tgt_answers_map = {}
        if os.path.exists(tgt_ans_path):
             try:
                with open(tgt_ans_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        for a in data.get("answers", []): tgt_answers_map[str(a["id"])] = a
             except: pass

        tgt_plain_questions_list = []
        if os.path.exists(tgt_pq_path):
             try:
                with open(tgt_pq_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    tgt_plain_questions_list = data.get("questions", [])
             except: pass

        tgt_plain_questions_map = {str(q.get("id")): q for q in tgt_plain_questions_list if "id" in q}

        src_by_title = {}
        for q in src_questions:
            t = self._clean_text(q.get("title", ""))
            if t not in src_by_title:
                src_by_title[t] = []
            src_by_title[t].append(q)

        matched_count = 0

        for tgt_q in tgt_questions:
            tgt_title = self._clean_text(tgt_q.get("title", ""))
            candidates = src_by_title.get(tgt_title, [])

            match = None
            for cand in candidates:
                if self._compare_options(cand.get("options"), tgt_q.get("options")):
                    match = cand
                    break

            if match:
                match_id = str(match.get("id"))
                tgt_id = str(tgt_q.get("id"))

                # 1. Map Answer
                if match_id in src_answers:
                    src_ans_entry = src_answers[match_id]
                    src_ans_text = src_ans_entry.get("answer", "")

                    mapped_ans = self._map_answer(src_ans_text, match.get("options"), tgt_q.get("options"), tgt_q.get("type"))

                    if mapped_ans:
                        tgt_answers_map[tgt_id] = {
                            "id": tgt_id,
                            "answer": mapped_ans,
                            "type": tgt_q.get("type")
                        }
                        matched_count += 1

                # 2. Extract Plain Text
                if match_id in src_plain_questions:
                    src_pq = src_plain_questions[match_id]
                    new_pq = tgt_q.copy()
                    new_pq["title"] = src_pq.get("title", tgt_q.get("title"))

                    src_pq_opts = src_pq.get("options")
                    tgt_opts = tgt_q.get("options")

                    mapped_pq_opts = self._map_parsed_options(
                        match.get("options"), # Raw Source
                        src_pq_opts,          # Parsed Source
                        tgt_opts              # Raw Target
                    )

                    new_pq["options"] = mapped_pq_opts
                    tgt_plain_questions_map[tgt_id] = new_pq

        logger.info(f"Course {course_id}: Matched and updated {matched_count} answers.")

        # Save Outputs
        try:
            tgt_ans_list = list(tgt_answers_map.values())
            output_ans = {"completed": False, "answers": tgt_ans_list}
            if len(tgt_ans_list) >= len(tgt_questions) and len(tgt_questions) > 0:
                output_ans["completed"] = True

            with open(tgt_ans_path, 'w', encoding='utf-8') as f:
                json.dump(output_ans, f, ensure_ascii=False, indent=2)

            output_pq = {"finished": True, "questions": list(tgt_plain_questions_map.values())}

            with open(tgt_pq_path, 'w', encoding='utf-8') as f:
                json.dump(output_pq, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.error(f"Failed to save output for {course_id}: {e}")

    def _clean_text(self, text):
        if not text: return ""
        text = re.sub(r'<[^>]+>', '', text)
        text = text.strip()
        return text

    def _get_option_content(self, opt_str):
        clean = self._clean_text(opt_str)
        clean = re.sub(r'^[A-Za-z][\.\,、\s]+', '', clean)
        return clean.strip()

    def _get_options_list(self, options):
        if isinstance(options, str):
            return options.split('\n')
        return options or []

    def _compare_options(self, src_opts, tgt_opts):
        s_list = self._get_options_list(src_opts)
        t_list = self._get_options_list(tgt_opts)

        if len(s_list) != len(t_list): return False

        s_set = {self._get_option_content(o) for o in s_list}
        t_set = {self._get_option_content(o) for o in t_list}

        return s_set == t_set

    def _map_answer(self, src_ans, src_opts, tgt_opts, q_type):
        if not re.match(r'^[A-Z]+$', src_ans):
            return src_ans

        s_list = self._get_options_list(src_opts)
        t_list = self._get_options_list(tgt_opts)

        t_map = {}
        for i, opt in enumerate(t_list):
            content = self._get_option_content(opt)
            label = chr(ord('A') + i)
            t_map[content] = label

        new_ans = []
        for char in src_ans:
            idx = ord(char) - ord('A')
            if 0 <= idx < len(s_list):
                content = self._get_option_content(s_list[idx])
                if content in t_map:
                    new_ans.append(t_map[content])
                else:
                    return "" # Mapping failed

        new_ans.sort()
        return "".join(new_ans)

    def _replace_label(self, text, new_label):
        # Remove existing label A. / A、 etc.
        clean = self._clean_text(text)
        clean = re.sub(r'^[A-Za-z][\.\,、\s]+', '', clean)
        return f"{new_label}. {clean}"

    def _map_parsed_options(self, raw_src_opts, parsed_src_opts, raw_tgt_opts):
        rs_list = self._get_options_list(raw_src_opts)
        ps_list = self._get_options_list(parsed_src_opts)
        rt_list = self._get_options_list(raw_tgt_opts)

        if len(rs_list) != len(ps_list) or len(rs_list) != len(rt_list):
            return ps_list

        content_map = {}
        for r, p in zip(rs_list, ps_list):
            c = self._get_option_content(r)
            content_map[c] = p

        new_opts = []
        for i, t in enumerate(rt_list):
            c = self._get_option_content(t)
            parsed_content = content_map.get(c, t)

            # Re-label
            new_label = chr(ord('A') + i)
            re_labeled = self._replace_label(parsed_content, new_label)
            new_opts.append(re_labeled)

        return new_opts

if __name__ == "__main__":
    ClusterManager().run()
