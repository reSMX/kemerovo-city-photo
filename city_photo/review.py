import csv
import json
import random
from collections import defaultdict
from pathlib import Path
from .export import flat_row, columns, write_csv, safe_cell
from .schemas import OBJECTS, SCORES, TERRITORIES
from .storage import now, dumps

EDITABLE = ['territory_type', *[f'{o}_present' for o in OBJECTS], *SCORES,
            *[c for c in columns() if c.endswith(('_presence_status', '_assessability', '_visibility_reason', '_assessment_status', '_reason', '_description'))],
            'latitude', 'longitude', 'clockwise_rotation', 'courtyard_id', 'courtyard_assignment_status',
            'playground_courtyard_link_status', 'parking_courtyard_link_status']
EDITABLE = list(dict.fromkeys(EDITABLE))

def validate_changes(current, changes):
    merged = dict(current, **changes)
    if merged.get('territory_type') not in TERRITORIES:
        raise ValueError('Invalid territory_type')
    if 'clockwise_rotation' in changes and changes['clockwise_rotation'] not in (None, 0, 90, 180, 270):
        raise ValueError('Rotation must be 0/90/180/270 or <NULL> for automatic detection')
    for obj in OBJECTS:
        presence = merged.get(f'{obj}_presence_status')
        present = merged.get(f'{obj}_present')
        if presence is not None and presence not in ('present', 'absent', 'uncertain'):
            raise ValueError('Invalid presence_status')
        if present is not None and (type(present) is not int or present not in (0, 1)):
            raise ValueError('Presence must be 0/1')
        if presence and present != int(presence == 'present'):
            raise ValueError('Presence fields inconsistent; update both explicitly')
        for key in [s for s in SCORES if s.startswith(obj + '_')]:
            score = merged.get(key)
            status = merged.get(key.replace('_score', '_assessment_status'))
            reason = merged.get(key.replace('_score', '_reason'))
            if score is not None and (type(score) is not int or not 0 <= score <= 10):
                raise ValueError('Scores must be integer 0..10 or <NULL>')
            if score is not None and (presence != 'present' or status not in ('assessable', 'partial')):
                raise ValueError('Score requires present/assessable object')
            if score == 0 and status != 'assessable':
                raise ValueError('Zero requires assessable')
            if status and status not in ('assessable', 'partial', 'not_assessable', 'not_applicable'):
                raise ValueError('Invalid metric assessment status')
            if score is None and status and not reason:
                raise ValueError('Null score requires reason')
        assessability = merged.get(f'{obj}_assessability')
        if assessability and assessability not in ('assessable', 'partial', 'not_assessable', 'not_applicable'):
            raise ValueError('Invalid object assessability')
        if assessability in ('not_assessable', 'not_applicable') and any(merged.get(s) is not None for s in SCORES if s.startswith(obj + '_')):
            raise ValueError('Unassessable object cannot have scores')
    lat, lon = merged.get('latitude'), merged.get('longitude')
    if (lat is None) != (lon is None):
        raise ValueError('Latitude/longitude must both be specified or both null')
    if lat is not None and not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError('Invalid GPS range')
    for k in ('courtyard_assignment_status', 'playground_courtyard_link_status', 'parking_courtyard_link_status'):
        if merged.get(k) not in (None, '', 'unknown', 'candidate', 'confirmed'):
            raise ValueError('Invalid courtyard link status')
    if merged.get('courtyard_id') and merged.get('courtyard_assignment_status') != 'confirmed':
        raise ValueError('courtyard_id requires explicit confirmed status')

def review_export(store, cfg, output, limit=100):
    output = Path(output)
    records = [flat_row(store, r) for r in store.rows()]
    # Connected dHash components, exact duplicates, same courtyard or 150m camera tile stay together.
    # Camera tiles are sampling guards only, never inferred courtyard boundaries.
    ids = {r['image_id']: i for i, r in enumerate(records)}
    parent = list(range(len(records)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    seen = {}
    source = {r['image_id']: r for r in store.rows()}
    for i, r in enumerate(records):
        raw = source[r['image_id']]
        keys = [('sha', raw['sha'])]
        if r.get('near_duplicate_group_id'):
            keys.append(('near', r['near_duplicate_group_id']))
        if r.get('courtyard_id') or r.get('courtyard_candidate_id'):
            keys.append(('yard', r.get('courtyard_id') or r.get('courtyard_candidate_id')))
        if r.get('latitude') is not None:
            from pyproj import Transformer
            x, y = Transformer.from_crs(4326, 32645, always_xy=True).transform(r['longitude'], r['latitude'])
            keys.append(('tile', int(x//150), int(y//150)))
        for key in keys:
            if key in seen:
                parent[find(i)] = find(seen[key])
            seen[key] = i
    groups = defaultdict(list)
    for i, r in enumerate(records):
        groups[find(i)].append(r)
    rng = random.Random(cfg.seed)
    buckets = defaultdict(list)
    for g in groups.values():
        representative = rng.choice(g)
        buckets[(representative.get('territory_type'), bool(representative['needs_review']))].append((g, representative))
    for bucket in buckets.values():
        rng.shuffle(bucket)
    selected = []
    while len(selected) < limit and any(buckets.values()):
        for bucket in buckets.values():
            if bucket and len(selected) < limit:
                selected.append(bucket.pop())
    rng.shuffle(selected)
    manifest = []
    for index, (group, representative) in enumerate(selected):
        split = 'calibration' if index < len(selected)//2 else 'control'
        manifest.append(dict(image_id=representative['image_id'], relative_path=representative['relative_path'],
                             split=split, group_members=[r['image_id'] for r in group]))
    output.mkdir(parents=True, exist_ok=True)
    (output/'sample_manifest.json').write_text(dumps({'seed': cfg.seed, 'sampling': 'stratified territory/review; one per connected group; inspect adjacent tiles manually', 'samples': manifest}), encoding='utf-8')
    write_csv(output/'labels.csv', [dict(image_id=m['image_id'], relative_path=m['relative_path'], split=m['split']) for m in manifest],
              ['image_id', 'relative_path', 'split', 'territory_type', *[f'{o}_present' for o in OBJECTS], *SCORES], cfg.delimiter)
    write_csv(output/'corrections.csv', [dict(image_id=r['image_id'], relative_path=r['relative_path']) for r in records],
              ['image_id', 'relative_path', 'author', 'reason', *EDITABLE], cfg.delimiter)
    write_csv(output/'current_values.csv', records, columns(), cfg.delimiter)
    return {'sampled_groups': len(manifest), 'total_files': len(records)}

def review_import(store, cfg, file):
    changes_pending = []
    with open(file, encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f, delimiter=cfg.delimiter)
        unknown = set(reader.fieldnames or []) - {'image_id', 'relative_path', 'author', 'reason', *EDITABLE}
        if unknown:
            raise ValueError(f'Unknown correction columns: {unknown}')
        for lineno, record in enumerate(reader, 2):
            changes = {}
            for k in EDITABLE:
                value = record.get(k, '')
                if value in ('', None):
                    continue
                if value == '<NULL>':
                    changes[k] = None
                elif k in SCORES or k.endswith('_present') or k == 'clockwise_rotation':
                    changes[k] = int(value)
                elif k in ('latitude', 'longitude'):
                    changes[k] = float(value)
                else:
                    changes[k] = value
            if not changes:
                continue
            row = store.db.execute('SELECT * FROM photos WHERE image_id=?', (record['image_id'],)).fetchone()
            if row is None or record.get('relative_path') not in (row['relative_path'], safe_cell(row['relative_path'])):
                raise ValueError(f'Line {lineno}: identifier/path mismatch')
            if not record.get('author', '').strip() or not record.get('reason', '').strip():
                raise ValueError(f'Line {lineno}: author and reason required')
            try:
                validate_changes(flat_row(store, row), changes)
            except ValueError as e:
                raise ValueError(f'Line {lineno}: {e}') from e
            changes_pending.append((row['image_id'], dumps(changes), record['author'], record['reason'], now()))
    with store.db:
        store.db.executemany('INSERT INTO corrections(image_id,changes,author,reason,created_at) VALUES (?,?,?,?,?)', changes_pending)
    return {'applied_rows': len(changes_pending)}
