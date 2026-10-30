import base64
import json
import urllib.request
import urllib.error
import http.client
import socket
import threading
import time
from urllib.parse import urlsplit
from .execution import PhotoDeadlineExceeded, SystemMemoryPressure, remaining
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
        self.deadline=None
        self.memory_abort=threading.Event()
        self.active_cancel=None

    def cancel_for_memory(self):
        self.memory_abort.set()
        cancel=self.active_cancel
        if cancel:
            cancel()

    def begin_photo(self,deadline):
        self.deadline=deadline

    def end_photo(self):
        self.deadline=None

    def _stream_chat(self,body):
        # Closing the actual streaming connection propagates request cancellation to Ollama.
        end=self.deadline or (time.monotonic()+self.cfg.photo_deadline_seconds)
        budget=min(remaining(end),self.cfg.timeout)
        endpoint=urlsplit(self.cfg.ollama_url)
        conn=http.client.HTTPConnection(endpoint.hostname,endpoint.port or 80,timeout=budget)
        expired=threading.Event()
        sockets=[]
        chunks=[]
        response=None
        def cancel():
            expired.set()
            for sock in sockets:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            conn.close()
        timer=threading.Timer(budget,cancel)
        timer.daemon=True
        timer.start()
        self.active_cancel=cancel
        try:
            if self.memory_abort.is_set():
                raise SystemMemoryPressure('System commit reserve is low; unload model before resuming')
            conn.connect()
            sockets.append(conn.sock)
            remaining(end)
            conn.request('POST','/api/chat',body=json.dumps(body).encode(),headers={'Content-Type':'application/json','Connection':'close'})
            response=conn.getresponse()
            if response.status!=200:
                raise RuntimeError(f'Ollama HTTP {response.status}')
            while True:
                remaining(end)
                line=response.readline()
                if not line:
                    raise RuntimeError('Ollama stream ended without final completion')
                part=json.loads(line)
                if part.get('error'):
                    raise RuntimeError(str(part['error']))
                chunks.append(part.get('message',{}).get('content',''))
                if part.get('done') or part.get('done_reason') in ('stop','length','unload'):
                    remaining(end)
                    part['message']={'content':''.join(chunks)}
                    return part
        except Exception as e:
            if self.memory_abort.is_set():
                raise SystemMemoryPressure('System commit reserve is low; request cancelled') from e
            if expired.is_set() or time.monotonic()>=end:
                raise PhotoDeadlineExceeded(''.join(chunks)) from e
            raise
        finally:
            self.active_cancel=None
            timer.cancel()
            for sock in sockets:
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            if response:
                response.close()
            conn.close()

    def request(self, route, body=None):
        req = urllib.request.Request(self.cfg.ollama_url.rstrip('/') + route,
            data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type': 'application/json'})
        try:
            with self.opener.open(req, timeout=min(15,self.cfg.timeout)) as r:
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
        response = self._stream_chat({
            'model': self.cfg.model, 'stream': True, 'think': self.cfg.thinking, 'keep_alive': '5m',
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
