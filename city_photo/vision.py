import base64
import json
import urllib.request
import urllib.error
from .schemas import Visual, Orientation, visual_schema

class TruncatedResponse(ValueError):
    def __init__(self, raw, response):
        super().__init__(f'Model response truncated at token limit; eval_count={response.get("eval_count")}; content_chars={len(raw)}')
        self.raw = raw

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Redirect blocked: inference must stay on loopback')

class Ollama:
    def __init__(self, cfg):
        self.cfg = cfg
        # Ignore environment proxy settings; all inference remains local.
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    def request(self, route, body=None):
        req = urllib.request.Request(self.cfg.ollama_url.rstrip('/') + route,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type': 'application/json'})
        try:
            with self.opener.open(req, timeout=self.cfg.timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            message = e.read(8192).decode('utf-8', errors='replace')
            raise RuntimeError(f'Ollama HTTP {e.code}: {message}') from e

    def identity(self):
        version = self.request('/api/version')['version']
        models = self.request('/api/tags').get('models', [])
        model = next((m for m in models if m.get('name') == self.cfg.model or m.get('model') == self.cfg.model), None)
        if not model:
            raise RuntimeError(f'Local model unavailable. Prepare explicitly: ollama pull {self.cfg.model}')
        info = self.request('/api/show', {'model': self.cfg.model})
        if 'vision' not in info.get('capabilities', []):
            raise RuntimeError('Selected local model does not report vision capability')
        return dict(model_name=self.cfg.model, model_digest=model.get('digest'), ollama_version=version,
                    quantization=model.get('details', {}).get('quantization_level'), capabilities=info.get('capabilities'))

    def chat(self, image, prompt, schema, context=None, tokens=None):
        response = self.request('/api/chat', {
            'model': self.cfg.model, 'stream': False, 'think': self.cfg.thinking, 'keep_alive': '5m',
            'format': schema,
            'messages': [{'role': 'user', 'content': prompt,
                          'images': [base64.b64encode(image).decode('ascii')]}],
            'options': {'temperature': self.cfg.temperature, 'seed': self.cfg.seed,
                        'num_ctx': context or self.cfg.context, 'num_predict': tokens or self.cfg.max_tokens}})
        raw = response.get('message', {}).get('content', '')
        if response.get('done_reason') == 'length':
            raise TruncatedResponse(raw, response)
        return raw, {k: response.get(k) for k in ('total_duration', 'load_duration', 'eval_count', 'eval_duration', 'prompt_eval_count')}

    def orientation(self, image):
        raw, _ = self.chat(image,
            'Determine whether this photo is upright AFTER EXIF correction. Return clockwise_rotation needed to make it upright: '
            '0, 90, 180 or 270. Use buildings, gravity, trees and readable text. Do not rotate merely for camera tilt. '
            'If ambiguous set certain=false and clockwise_rotation=0. reason in Russian, at most eight words. '
            'Respond with exactly one short JSON object, then stop.',
            Orientation.model_json_schema(), tokens=768)
        return Orientation.model_validate_json(raw).model_dump()

    def assess(self, image, prompt, context=None):
        raw, stats = self.chat(image, prompt, visual_schema(), context)
        return raw, stats
