import json
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

def now():
    return datetime.now(timezone.utc).isoformat()

def dumps(v):
    return json.dumps(v, ensure_ascii=False, default=str)

class Store:
    def __init__(self, workspace):
        self.path = Path(workspace).resolve()
        self.path.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path / 'state.sqlite')
        self.db.row_factory = sqlite3.Row
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version > 1:
            raise ValueError('Workspace schema is newer than this application')
        self.db.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS photos (
          image_id TEXT PRIMARY KEY, relative_path TEXT UNIQUE NOT NULL,
          source TEXT NOT NULL, sha TEXT NOT NULL, metadata TEXT NOT NULL,
          status TEXT NOT NULL, visual TEXT, geo TEXT, cache_key TEXT,
          provenance TEXT NOT NULL DEFAULT '{}', error TEXT, processed_at TEXT);
        CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, visual TEXT NOT NULL, provenance TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS corrections (id INTEGER PRIMARY KEY, image_id TEXT NOT NULL,
          changes TEXT NOT NULL, author TEXT NOT NULL, reason TEXT NOT NULL, created_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY, created_at TEXT, details TEXT);
        CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
        PRAGMA user_version=1;
        ''')

    def rows(self):
        return self.db.execute('SELECT * FROM photos ORDER BY relative_path COLLATE BINARY').fetchall()

    def setting(self, key, value=None):
        if value is not None:
            with self.db:
                self.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, value))
        r = self.db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return r[0] if r else None

    def update(self, image_id, **values):
        allowed = {'status', 'visual', 'geo', 'cache_key', 'provenance', 'error', 'processed_at', 'metadata'}
        if not set(values) <= allowed:
            raise ValueError('Invalid DB update')
        values = {k: dumps(v) if k in ('visual', 'geo', 'metadata', 'provenance') and v is not None else v for k, v in values.items()}
        with self.db:
            self.db.execute('UPDATE photos SET ' + ','.join(f'{k}=?' for k in values) + ' WHERE image_id=?', (*values.values(), image_id))

    def overrides(self, image_id):
        merged = {}
        for r in self.db.execute('SELECT changes FROM corrections WHERE image_id=? ORDER BY id', (image_id,)):
            merged.update(json.loads(r[0]))
        return merged
