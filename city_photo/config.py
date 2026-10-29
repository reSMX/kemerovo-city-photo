import hashlib
import json
from pathlib import Path
from urllib.parse import urlsplit
import yaml
from pydantic import Field, model_validator
from .schemas import Strict

RESOURCES = Path(__file__).parent / 'resources'

def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()

class Config(Strict):
    input: str = 'D:/map_photos'
    ollama_url: str = 'http://127.0.0.1:11434'
    model: str = 'qwen3-vl:4b-instruct-q4_K_M'
    context: int = Field(default=8192, ge=4096, le=32768)
    max_tokens: int = Field(default=4096, ge=1024, le=16384)
    long_side: int = Field(default=1280, ge=640, le=4096)
    fallback_long_side: int = Field(default=960, ge=640)
    fallback_context: int = Field(default=6144, ge=4096)
    timeout: int = Field(default=300, ge=10, le=1800)
    retries: int = Field(default=1, ge=0, le=3)
    seed: int = 42
    thinking: bool = False
    temperature: float = Field(default=0.0, ge=0, le=1)
    auto_orientation: bool = True
    dark_threshold: float = 35.0
    blur_threshold: float = 70.0
    duplicate_distance: int = Field(default=5, ge=0, le=16)
    map_path: str | None = None
    courtyards_path: str | None = None
    gps_buffer_m: float = Field(default=30.0, gt=0)
    normalize_timezone: bool = False
    timezone_assumption: str = 'Asia/Krasnoyarsk'
    delimiter: str = ';'
    prompt_path: str | None = None
    rubric_path: str | None = None

    @model_validator(mode='after')
    def safe(self):
        u = urlsplit(self.ollama_url)
        if u.scheme != 'http' or u.hostname not in ('127.0.0.1', 'localhost', '::1') or u.username or u.password or u.path not in ('', '/') or u.query or u.fragment:
            raise ValueError('Ollama endpoint must be loopback http, without credentials/path/query')
        if self.model.endswith(':latest') or ':' not in self.model or 'cloud' in self.model.lower():
            raise ValueError('Use an explicit local model tag, not latest/cloud')
        if len(self.delimiter) != 1:
            raise ValueError('CSV delimiter must be one character')
        if self.max_tokens >= self.context:
            raise ValueError('max_tokens must be less than context')
        return self

    def assets(self):
        prompt = Path(self.prompt_path) if self.prompt_path else RESOURCES / 'assessment.txt'
        rubric = Path(self.rubric_path) if self.rubric_path else RESOURCES / 'rubric.yaml'
        return prompt.read_text(encoding='utf-8'), rubric.read_text(encoding='utf-8')

def load(path=None):
    if not path:
        return Config()
    p = Path(path).resolve()
    values = yaml.safe_load(p.read_text(encoding='utf-8-sig')) or {}
    for key in ('input', 'map_path', 'courtyards_path', 'prompt_path', 'rubric_path'):
        if values.get(key) and not Path(values[key]).is_absolute():
            values[key] = str((p.parent / values[key]).resolve())
    return Config(**values)
