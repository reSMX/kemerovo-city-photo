import json
import os
import time
from pathlib import Path
from .config import digest
from .storage import Store, now, dumps
from .metadata import inspect, sha_file, prepare, exiftool_metadata
from .geo import Geography
from .schemas import Visual, visual_schema
from .vision import Ollama
from pydantic import ValidationError

def diagnostic(error):
    if isinstance(error, ValidationError):
        # Never put image descriptions from input_value into logs/CLI diagnostics.
        return 'ValidationError: ' + '; '.join('.'.join(map(str, e['loc'])) + ': ' + e['msg']
            for e in error.errors(include_input=False, include_url=False))
    return f'{type(error).__name__}: {error}'

def import_photos(store, root, cfg, exiftool=False):
    root = Path(root).resolve()
    if not root.is_dir():
        raise ValueError(f'Input folder not found: {root}')
    if store.path == root or root in store.path.parents:
        raise ValueError('Workspace must be outside input tree')
    previous = store.setting('input_root')
    if previous and previous != str(root):
        raise ValueError('Use a separate workspace for a different input root')
    store.setting('input_root', str(root))
    files = sorted(p for p in root.rglob('*') if p.is_file())
    count = 0
    for p in files:
        rel = p.relative_to(root).as_posix()
        image_id = digest(rel)[:24]
        try:
            sha = sha_file(p)
            old = store.db.execute('SELECT sha FROM photos WHERE image_id=?', (image_id,)).fetchone()
            if old and old['sha'] == sha:
                continue
            meta, status = inspect(p, cfg)
            if exiftool and status == 'pending':
                try:
                    ext = exiftool_metadata(p)
                    lat, lon = ext.get('GPSLatitude'), ext.get('GPSLongitude')
                    if lat is not None and lon is not None and -90 <= lat <= 90 and -180 <= lon <= 180:
                        meta.update(latitude=lat, longitude=lon, gps_status='valid', metadata_source='ExifTool')
                        meta['gps_accuracy_m'] = ext.get('GPSHPositioningError')
                    meta['exiftool_raw'] = ext
                except Exception as e:
                    meta['quality_flags'].append(f'exiftool_error: {e}')
        except Exception as e:
            sha, meta, status = '', {'read_error': str(e), 'quality_flags': []}, 'unreadable'
        with store.db:
            store.db.execute('''INSERT INTO photos(image_id,relative_path,source,sha,metadata,status)
                VALUES (?,?,?,?,?,?) ON CONFLICT(image_id) DO UPDATE SET
                source=excluded.source,sha=excluded.sha,metadata=excluded.metadata,status=excluded.status,
                visual=NULL,geo=NULL,cache_key=NULL,provenance='{}',error=NULL,processed_at=NULL''',
                (image_id, rel, str(p), sha, dumps(meta), status))
        count += 1
        if count % 50 == 0:
            print(f'Imported {count}/{len(files)}', flush=True)
    # dHash LSH: candidates only. Never share predictions for near duplicates.
    rows = store.rows()
    groups, parent = {}, {r['image_id']: r['image_id'] for r in rows}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    hashes = {}
    # At most ~1000 photos expected: comparison is bounded in memory, 64-bit Hamming distance.
    for row in rows:
        meta = json.loads(row['metadata'])
        if 'dhash' not in meta:
            continue
        h = int(meta['dhash'], 16)
        for other, oh in hashes.items():
            if (h ^ oh).bit_count() <= cfg.duplicate_distance:
                parent[find(row['image_id'])] = find(other)
        hashes[row['image_id']] = h
    for row in rows:
        groups.setdefault(find(row['image_id']), []).append(row['image_id'])
    for row in rows:
        meta = json.loads(row['metadata'])
        group = groups[find(row['image_id'])]
        meta['near_duplicate_group_id'] = min(group) if len(group) > 1 else None
        store.update(row['image_id'], metadata=meta)
    return count

def effective_metadata(store, row):
    meta = json.loads(row['metadata'])
    changes = store.overrides(row['image_id'])
    for k in ('latitude', 'longitude'):
        if k in changes:
            meta[k] = changes[k]
            meta['metadata_source'] = 'manual_correction'
    if any(k in changes for k in ('latitude', 'longitude')):
        meta['gps_accuracy_m'] = None
    return meta

def geolocate(store, cfg):
    geo = Geography(cfg)
    for row in store.rows():
        visual = json.loads(row['visual']) if row['visual'] else None
        changes = store.overrides(row['image_id'])
        if visual and 'territory_type' in changes:
            visual = dict(visual, territory_visual=changes['territory_type'])
        result = geo.locate(effective_metadata(store, row), visual)
        store.update(row['image_id'], geo=result)

def analyze(store, cfg, limit=None, resume=False, retry_errors=False, force=False, dry_run=False, backend=None):
    backend = backend or Ollama(cfg)
    prompt, rubric = cfg.assets()
    if dry_run:
        return {'dry_run': True, 'files': len(store.rows()), 'limit': limit, 'model': cfg.model, 'no_inference': True}
    identity = backend.identity()
    params = cfg.model_dump(exclude={'input', 'map_path', 'courtyards_path', 'gps_buffer_m', 'delimiter', 'normalize_timezone', 'timezone_assumption', 'prompt_path', 'rubric_path'})
    base = {'preprocessing': 'v3-exif-auto-orientation-short', 'schema': visual_schema(), 'config': params,
            'identity': identity, 'prompt_hash': digest(prompt), 'rubric_hash': digest(rubric)}
    model_prompt = prompt + '\nRUBRIC:\n' + rubric
    done, cached, start = 0, 0, time.monotonic()
    run_stamp = now().replace(':', '-').replace('.', '-')
    geo_error = None
    try:
        geo = Geography(cfg)
    except Exception as e:
        geo_error = f'{type(e).__name__}: map could not be loaded'
        geo = Geography(cfg.model_copy(update={'map_path': None, 'courtyards_path': None}))
    targets = store.rows()
    for row in targets:
        if row['status'] in ('unsupported', 'unreadable'):
            continue
        rotation_override = store.overrides(row['image_id']).get('clockwise_rotation')
        key = digest([row['sha'], base, rotation_override])
        if not force and row['visual'] and row['cache_key'] == key:
            continue
        if row['status'] == 'model_error' and not (retry_errors or force) and row['cache_key'] == key:
            continue
        if limit is not None and done >= limit:
            break
        if not Path(row['source']).is_file() or sha_file(row['source']) != row['sha']:
            store.update(row['image_id'], status='unreadable', error='Source missing or changed: import again', visual=None, geo=None)
            continue
        hit = None if force else store.db.execute('SELECT * FROM cache WHERE key=?', (key,)).fetchone()
        provenance = dict(identity, config_hash=digest(cfg.model_dump()), prompt_version='1', rubric_version='1',
                          prompt_hash=digest(prompt), rubric_hash=digest(rubric), schema_version='1')
        visual, errors = None, []
        file_started = time.monotonic()
        assessment_wall = 0.0
        orientation_wall = 0.0
        if hit:
            visual = json.loads(hit['visual'])
            provenance = dict(json.loads(hit['provenance']), config_hash=digest(cfg.model_dump()), cache_hit=True)
            cached += 1
        else:
            side, context = cfg.long_side, cfg.context
            rotation, orientation = 0, None
            if rotation_override is not None:
                rotation = rotation_override
                orientation = dict(clockwise_rotation=rotation, certain=True, reason='Manual correction after EXIF')
            for attempt in range(cfg.retries + 1):
                raw = None
                try:
                    image = prepare(row['source'], side)
                    if cfg.auto_orientation and orientation is None:
                        phase_started = time.monotonic()
                        try:
                            orientation = backend.orientation(image)
                        finally:
                            orientation_wall += time.monotonic() - phase_started
                        rotation = orientation['clockwise_rotation'] if orientation['certain'] else 0
                    if rotation:
                        image = prepare(row['source'], side, rotation)
                    feedback = '\nPrevious response was invalid. Correct these rules: ' + ' | '.join(errors) if errors else ''
                    phase_started = time.monotonic()
                    try:
                        raw, stats = backend.assess(image, model_prompt + feedback, context)
                    finally:
                        assessment_wall += time.monotonic() - phase_started
                    visual = Visual.model_validate_json(raw).model_dump()
                    provenance.update(orientation=orientation, clockwise_rotation=rotation, long_side=side,
                                      context=context, stats=stats, degraded=side != cfg.long_side,
                                      inference_errors=errors)
                    # Save metadata-free, correctly oriented derived image locally for review.
                    derived = store.path / 'derived'
                    derived.mkdir(exist_ok=True)
                    (derived / f'{row["image_id"]}.jpg').write_bytes(image)
                    break
                except Exception as e:
                    raw = getattr(e, 'raw', raw)
                    errors.append(diagnostic(e))
                    if any(s in str(e).lower() for s in ('memory', 'cuda', 'vram', 'allocat')):
                        side, context = cfg.fallback_long_side, cfg.fallback_context
                    if attempt < cfg.retries:
                        time.sleep(1)
                finally:
                    rawdir = store.path / 'raw'
                    rawdir.mkdir(exist_ok=True)
                    (rawdir / f'{row["image_id"]}-{run_stamp}-{attempt}.json').write_text(dumps({'raw': raw, 'errors': errors}), encoding='utf-8')
        if not hit:
            provenance['timing'] = dict(total_processing_seconds=time.monotonic()-file_started,
                assessment_requests_seconds=assessment_wall, orientation_requests_seconds=orientation_wall)
        if visual:
            geographical = geo.locate(effective_metadata(store, row), visual)
            if geo_error:
                geographical['geo_status'] = 'map_error'
                geographical['geo_review_reasons'].append(geo_error)
            review = bool(visual['review_reasons'] or geographical['geo_review_reasons'] or json.loads(row['metadata']).get('quality_flags')
                          or provenance.get('degraded') or (provenance.get('orientation') and not provenance['orientation']['certain'])
                          or visual['territory_visual'] in ('mixed', 'unknown') or visual['mural_status'].endswith('uncertain')
                          or any(o['presence_status'] == 'uncertain' or o['assessability'] in ('partial', 'not_assessable') for o in visual['objects'].values())
                          or any(m['assessment_status'] in ('partial', 'not_assessable') for o in visual['objects'].values() for m in o['metrics'].values()))
            # Cache and per-file result are one durable transaction.
            with store.db:
                store.db.execute('INSERT OR REPLACE INTO cache VALUES (?,?,?)', (key, dumps(visual), dumps(provenance)))
                store.db.execute('UPDATE photos SET status=?,visual=?,geo=?,cache_key=?,provenance=?,error=NULL,processed_at=? WHERE image_id=?',
                                 ('processed_with_review' if review else 'processed', dumps(visual), dumps(geographical), key, dumps(provenance), now(), row['image_id']))
        else:
            store.update(row['image_id'], status='model_error', visual=None, geo=None, cache_key=key, provenance=provenance,
                         error=' | '.join(errors), processed_at=now())
        done += 1
        elapsed = time.monotonic() - start
        remaining = max(0, min(len(targets), limit or len(targets)) - done)
        eta = f'{remaining * elapsed / done:.0f}s' if done >= 3 else 'warming up'
        print(f'{done} processed, {remaining} remaining | {row["relative_path"]} | {elapsed:.1f}s | ETA {eta}', flush=True)
    report = dict(processed=done, cache_hits=cached, elapsed_seconds=time.monotonic()-start,
                  seconds_per_photo=(time.monotonic()-start)/done if done else None, identity=identity,
                  config=cfg.model_dump(), finished_at=now())
    with store.db:
        store.db.execute('INSERT INTO runs(created_at,details) VALUES (?,?)', (now(), dumps(report)))
    return report
