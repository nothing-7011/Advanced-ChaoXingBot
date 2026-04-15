import base64
import json
import os
import re
import time
from io import BytesIO
from typing import Any, Dict, Optional

import requests

from google import genai
from google.genai import types
from PIL import Image

from api.logger import logger
from api.collector import QuestionCollector


class ImageParserAgent:
    def __init__(
        self,
        api_type: str,
        api_key: str,
        model_name: str = "gemini-2.0-flash",
        temperature: float = 0.7,
        endpoint: Optional[str] = None,
        headers: Optional[Dict[str, Any]] = None,
        cookies: Optional[Dict[str, Any]] = None,
        parsed_path: str = "data/parsed.json",
    ):
        self.api_type = api_type
        self.api_key = api_key
        self.model_name = model_name
        self.temperature = temperature
        self.endpoint = endpoint
        self.headers = headers
        self.cookies = cookies
        self.parsed_cache_path = parsed_path
        self.parsed_cache = {}
        self._load_parsed_cache()
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
                logger.error(f"Failed to initialize Gemini client: {e}")

    def _openai_chat_completions_url(self) -> str:
        base_url = (self.endpoint or "https://api.openai.com/v1").rstrip("/")
        if base_url.endswith("/chat/completions"):
            return base_url
        if base_url.endswith("/v1"):
            return f"{base_url}/chat/completions"
        return f"{base_url}/v1/chat/completions"

    def _load_parsed_cache(self):
        if os.path.exists(self.parsed_cache_path):
            try:
                with open(self.parsed_cache_path, "r", encoding="utf-8") as f:
                    self.parsed_cache = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load parsed cache: {e}")

    def _save_parsed_cache(self):
        temp_path = self.parsed_cache_path + ".tmp"
        try:
            os.makedirs(os.path.dirname(self.parsed_cache_path), exist_ok=True)
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.parsed_cache, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, self.parsed_cache_path)
        except Exception as e:
            logger.error(f"Failed to save parsed cache: {e}")
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass

    def _download_image(self, url: str) -> Optional[Image.Image]:
        try:
            # Simple retry mechanism
            for _ in range(3):
                try:
                    resp = requests.get(
                        url, headers=self.headers, cookies=self.cookies, timeout=15
                    )
                    if resp.status_code == 200:
                        return Image.open(BytesIO(resp.content))
                except requests.RequestException:
                    time.sleep(1)
            return None
        except Exception as e:
            logger.error(f"Failed to download image {url}: {e}")
        return None

    def _image_to_data_url(self, image: Image.Image) -> str:
        buffer = BytesIO()
        image.save(buffer, format="PNG")
        encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{encoded}"

    def _parse_image_with_gemini(self, image: Image.Image, prompt: str) -> str:
        if not self.client:
            raise RuntimeError("Gemini client is not initialized")

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=[image, prompt],
            config=types.GenerateContentConfig(temperature=self.temperature),
        )
        return response.text.strip() if response.text else ""

    def _parse_image_with_openai(self, image: Image.Image, prompt: str) -> str:
        payload = {
            "model": self.model_name,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": self._image_to_data_url(image)},
                        },
                    ],
                }
            ],
            "temperature": self.temperature,
            "stream": False,
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
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()

    def _parse_image(self, image: Image.Image, prompt: str) -> str:
        if self.api_type == "gemini_v1beta":
            return self._parse_image_with_gemini(image, prompt)
        if self.api_type == "openai_compatible":
            return self._parse_image_with_openai(image, prompt)
        raise ValueError(f"Unsupported parser api_type: {self.api_type}")

    def _process_image(self, image: Image.Image) -> Image.Image:
        """
        Process the image to ensure it's in a supported format (RGB).
        Handles transparency by compositing on a white background.
        """
        if image.mode == "RGB":
            return image

        try:
            # Handle transparency
            if image.mode in ("RGBA", "LA") or (
                image.mode == "P" and "transparency" in image.info
            ):
                image = image.convert("RGBA")
                background = Image.new("RGB", image.size, (255, 255, 255))
                background.paste(image, mask=image.split()[3])
                return background

            return image.convert("RGB")
        except Exception as e:
            logger.error(f"Failed to process image format: {e}")
            # Fallback to converting to RGB directly if complex processing fails
            return image.convert("RGB")

    def _process_text_with_images(self, text: str) -> str:
        if not text:
            return text

        # Regex to find img tags: <img ... src="url" ...>
        # Handles single/double quotes, and src attribute position
        img_pattern = re.compile(
            r'<img[^>]+src=["\']([^"\']+)["\'][^>]*>', re.IGNORECASE
        )

        matches = list(img_pattern.finditer(text))
        if not matches:
            return text

        urls = []
        for m in matches:
            urls.append(m.group(1))

        processed_map = {}

        for url in urls:
            if url in processed_map:
                continue

            # Check if URL is valid
            if not url.startswith("http"):
                if url.startswith("//"):
                    url = "https:" + url
                else:
                    logger.warning(f"Skipping potentially relative URL: {url}")
                    continue

            # Check cache
            if url in self.parsed_cache:
                logger.info(f"Using cached image text for: {url}")
                processed_map[url] = self.parsed_cache[url]
                print(f"[Image Parsed] ...{url[-10:]}: {self.parsed_cache[url]}")
                continue

            logger.info(f"Processing image: {url}")
            image = self._download_image(url)
            if not image:
                logger.error(f"Failed to download: {url}")
                processed_map[url] = "[图片下载失败]"
                continue

            # Process image to handle transparency and format
            image = self._process_image(image)

            try:
                prompt = "Identify the content of this image. If it contains mathematical formulas, convert them to LaTeX format. Return only the plain text result. Do not modify any content within the image, including the original language (e.g., Chinese)."
                description = self._parse_image(image, prompt)
                processed_map[url] = f" [{description}] "

                # Update cache
                self.parsed_cache[url] = processed_map[url]
                self._save_parsed_cache()
                print(f"[Image Parsed] ...{url[-10:]}: {processed_map[url]}")
            except Exception as e:
                logger.error(f"Image parsing failed for {url}: {e}")
                processed_map[url] = "[图片解析失败]"

            time.sleep(1)

        def replace_callback(match):
            url = match.group(1)
            if url.startswith("//"):
                lookup_url = "https:" + url
            else:
                lookup_url = url
            return processed_map.get(lookup_url, match.group(0))

        new_text = img_pattern.sub(replace_callback, text)
        return new_text

    def parse_images(self, course_id: str):
        if not self.api_key:
            logger.error("Parser Agent not initialized (missing API key).")
            return

        collector = QuestionCollector()
        file_path = collector._get_file_path(course_id)
        plain_file_path = os.path.join(
            os.path.dirname(file_path), "plain_questions.json"
        )

        if not os.path.exists(file_path):
            logger.warning(f"No questions file found for course {course_id}")
            return

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load questions JSON: {e}")
            return

        if not data.get("finished", False):
            logger.warning(
                f"Course {course_id} collection not marked as finished. Skipping parsing."
            )
            return

        logger.info(f"Starting image parsing for course {course_id}...")

        questions = data.get("questions", [])
        updated_count = 0

        for q in questions:
            # Process title
            if "title" in q:
                original = q["title"]
                q["title"] = self._process_text_with_images(q["title"])
                if original != q["title"]:
                    updated_count += 1

            # Process options
            if "options" in q and isinstance(q["options"], str):
                original = q["options"]
                q["options"] = self._process_text_with_images(q["options"])
                if original != q["options"]:
                    updated_count += 1

        try:
            with open(plain_file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            if updated_count > 0:
                logger.info(
                    f"Updated {updated_count} questions with parsed images. Saved to {plain_file_path}."
                )
            else:
                logger.info(
                    f"No images found or parsed. Saved copy to {plain_file_path}."
                )
        except Exception as e:
            logger.error(f"Failed to save parsed questions to {plain_file_path}: {e}")
