import csv
import json
import os
from collections import Counter
from pathlib import Path
from .schemas import OBJECTS, METRICS, SCORES
from .pipeline import effective_metadata
from .photo_scoring import assess_photo, load_rules

def score_key(obj, metric):
    return 'litter_score' if obj == 'litter' else f'{obj}_{metric}_score'

def columns():
    fields = ['filename', 'relative_path', 'image_id', 'territory_type']
    fields += [f'{o}_present' for o in OBJECTS] + list(SCORES)
    fields += [s.replace('_score', '_description') for s in SCORES]
    for o in OBJECTS:
        fields += [f'{o}_description', f'{o}_presence_status', f'{o}_assessability', f'{o}_visibility_reason']
    for s in SCORES:
        fields += [s.replace('_score', '_assessment_status'), s.replace('_score', '_reason')]
    fields += ['latitude', 'longitude', 'gps_status', 'gps_accuracy_m', 'captured_at', 'captured_at_raw',
               'timezone_status', 'metadata_source', 'width', 'height', 'exif_orientation',
               'clockwise_rotation', 'orientation_reason', 'orientation_certain', 'long_side', 'context', 'degraded',
               'surface_type', 'mural_present', 'mural_status', 'geo_status', 'map_hash',
               'gps_buffer_m_used', 'gps_buffer_source', 'territory_visual', 'territory_geo',
               'territory_source', 'territory_description', 'courtyard_candidate_id', 'courtyard_id',
               'courtyard_assignment_status', 'playground_courtyard_link_status', 'parking_courtyard_link_status',
               'processing_status', 'needs_review', 'review_reasons', 'error', 'exact_duplicate_of',
               'near_duplicate_group_id', 'schema_version', 'rubric_version', 'rubric_hash', 'prompt_version',
               'prompt_hash', 'config_hash', 'model_name', 'model_digest', 'ollama_version', 'processed_at']
    fields += ['photo_score', 'photo_score_status', 'photo_score_coverage', 'photo_score_lower_bound',
               'photo_score_upper_bound', 'photo_score_metric_count', 'photo_score_reason',
               'photo_scoring_version', 'photo_scoring_hash']
    return list(dict.fromkeys(fields))

def flat_row(store, row, duplicate=None, scoring_rules=None):
    meta = effective_metadata(store, row)
    v = json.loads(row['visual']) if row['visual'] else {}
    geo = json.loads(row['geo']) if row['geo'] else {}
    prov = json.loads(row['provenance'])
    out = {k: meta.get(k) for k in columns() if k in meta}
    out.update(filename=Path(row['relative_path']).name, relative_path=row['relative_path'], image_id=row['image_id'],
               processing_status=row['status'], error=row['error'] or meta.get('read_error'),
               processed_at=row['processed_at'], exact_duplicate_of=duplicate)
    out.update({k: value for k, value in prov.items() if k in columns()})
    orientation = prov.get('orientation') or {}
    out.update(orientation_reason=orientation.get('reason'), orientation_certain=int(orientation['certain']) if orientation else None)
    reasons = list(meta.get('quality_flags', [])) + v.get('review_reasons', []) + geo.get('geo_review_reasons', [])
    for obj, observation in v.get('objects', {}).items():
        for k in ('present', 'presence_status', 'description', 'assessability', 'visibility_reason'):
            out[f'{obj}_{k}'] = observation[k]
        if observation['presence_status'] == 'uncertain':
            reasons.append(f'{obj}_presence_uncertain')
        for metric, assessment in observation['metrics'].items():
            key = score_key(obj, metric)
            out[key] = assessment['score']
            for k in ('description', 'assessment_status', 'reason'):
                out[key.replace('_score', '_' + k)] = assessment[k]
            if assessment['assessment_status'] in ('partial', 'not_assessable'):
                reasons.append(f'{key}_{assessment["assessment_status"]}')
    for k in ('surface_type', 'mural_present', 'mural_status', 'territory_description', 'territory_visual'):
        out[k] = v.get(k)
    out.update({k: val for k, val in geo.items() if k in columns()})
    out.setdefault('territory_type', v.get('territory_visual', 'unknown'))
    if v.get('territory_visual') in ('unknown', 'mixed'):
        reasons.append('territory_ambiguous')
    if v.get('mural_status') == 'mural_or_graffiti_uncertain':
        reasons.append('mural_or_graffiti_uncertain')
    if orientation and not orientation['certain']:
        reasons.append('orientation_uncertain')
    if prov.get('degraded'):
        reasons.append('reduced_resolution_or_context')
    if row['status'] in ('model_error', 'unsupported', 'unreadable', 'pending'):
        reasons.append(row['status'])
    out.update(store.overrides(row['image_id']))
    out['review_reasons'] = ' | '.join(sorted(set(reasons)))
    out['needs_review'] = int(bool(reasons))
    if v:
        out['processing_status'] = 'processed_with_review' if reasons else 'processed'
    out.update(assess_photo(out,scoring_rules))
    return out

def safe_cell(v):
    if isinstance(v, str) and v.lstrip().startswith(('=', '+', '-', '@', '\t', '\r', '\n')):
        return "'" + v
    return v

def write_csv(path, rows, fields, delimiter=';'):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    try:
        with tmp.open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fields, delimiter=delimiter, extrasaction='ignore')
            writer.writeheader()
            for r in rows:
                writer.writerow({k: safe_cell(v) for k, v in r.items()})
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)

def export_all(store, cfg, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    rows, first = [], {}
    scoring_rules=load_rules(cfg.photo_scoring_path)
    for r in store.rows():
        duplicate = first.get(r['sha']) if r['sha'] else None
        if r['sha']:
            first.setdefault(r['sha'], r['image_id'])
        rows.append(flat_row(store, r, duplicate, scoring_rules))
    write_csv(output / 'results.csv', rows, columns(), cfg.delimiter)
    write_csv(output / 'review.csv', (r for r in rows if r['needs_review']), columns(), cfg.delimiter)
    latest = store.db.execute('SELECT details FROM runs ORDER BY id DESC LIMIT 1').fetchone()
    summary = dict(total_files=len(rows), statuses=dict(Counter(r['processing_status'] for r in rows)),
                   missing_gps_fraction=sum(r.get('latitude') is None for r in rows)/len(rows) if rows else None,
                   needs_review=sum(r['needs_review'] for r in rows),
                   last_run=json.loads(latest[0]) if latest else None,
                   errors=[{'relative_path': r['relative_path'], 'error': r['error']} for r in rows if r.get('error')])
    tmp = output / 'run_summary.json.tmp'
    tmp.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, output / 'run_summary.json')
    (output / 'data_dictionary.md').write_text(dictionary(), encoding='utf-8')
    return summary

def dictionary():
    descriptions = {'filename': 'Имя оригинала', 'relative_path': 'Путь от входного корня', 'image_id': 'Стабильный ID относительного пути',
        'territory_type': 'courtyard/street/boulevard/park_square/private_sector/other/mixed/unknown',
        'latitude': 'Широта EPSG:4326, десятичные градусы', 'longitude': 'Долгота EPSG:4326, десятичные градусы',
        'clockwise_rotation': 'Дополнительный поворот по часовой стрелке ПОСЛЕ EXIF: 0/90/180/270',
        'exif_orientation': 'Исходный EXIF 1–8; применяется включая зеркальное отражение',
        'orientation_certain': 'Самооценка ориентации модели 0/1, не калиброванная вероятность',
        'needs_review': '0/1, требуется проверка', 'exact_duplicate_of': 'ID первого точного дубликата',
        'near_duplicate_group_id': 'Кандидаты dHash, оценки не копируются', 'map_hash': 'Версия карты и геоправил',
        'courtyard_id': 'Только подтверждённый вручную ID; GPS — положение камеры',
        'courtyard_candidate_id': 'Кандидаты по карте, не координата объекта',
        'processing_status': 'pending/processed/processed_with_review/unreadable/unsupported/model_error',
        'surface_type': 'paved/unpaved/mixed/unknown', 'mural_status': 'mural/no_mural/mural_or_graffiti_uncertain',
        'photo_score': 'Экспериментальный балл видимого состояния 0–10, больше лучше; не индекс двора/города',
        'photo_score_status': 'available/provisional/insufficient_data; ни один статус не доказывает точность',
        'photo_score_coverage': '0–1 доля взвешенной оценимой информации среди видимых/неуверенных объектов',
        'photo_score_lower_bound': 'Нижняя граница при худшем состоянии всей неоценённой части; не статистический доверительный интервал',
        'photo_score_upper_bound': 'Верхняя граница при лучшем состоянии всей неоценённой части; не статистический доверительный интервал',
        'photo_score_metric_count': 'Число показателей с оценкой, вошедших в сумму',
        'photo_score_reason': 'Ограничение или причина отсутствия итогового балла',
        'photo_scoring_version': 'Версия формулы итогового балла', 'photo_scoring_hash': 'SHA-256 правил итогового балла'}
    lines = ['# Словарь CSV', '', 'UTF-8 BOM; разделитель ; по умолчанию. Пустая ячейка = null. Объектные оценки целые 0–10; итоговый photo_score округлён до двух знаков.',
             'Для координат в Excel: Данные → Из текста/CSV → локаль English (United States), десятичная точка.',
             'Текст с началом формулы экранируется апострофом; SQLite хранит исходный текст.', '', '| Поле | Значение |', '|---|---|']
    for c in columns():
        desc = descriptions.get(c)
        if desc is None:
            if c.endswith('_score'):
                desc = '0–10/null; больше = ' + ('обильнее деревья/кустарники' if 'abundance' in c else 'выраженнее видимая проблема')
            elif c.endswith('_present'):
                desc = '1 только при подтверждённом наличии; иначе 0; для необработанного кадра пусто'
            elif c.endswith('_presence_status'):
                desc = 'present/absent/uncertain'
            elif c.endswith(('_assessment_status', '_assessability')):
                desc = 'assessable/partial/not_assessable/not_applicable'
            elif c.endswith(('_description', '_reason', '_reasons')):
                desc = 'Наблюдаемое объяснение или причина ограничения/проверки'
            elif c.endswith('_hash') or c == 'model_digest':
                desc = 'SHA-256 версии соответствующего входа/модели'
            elif c.endswith('_link_status') or c == 'courtyard_assignment_status':
                desc = 'candidate/confirmed/unknown; подтверждение отдельным ручным решением'
            else:
                desc = {'gps_status': 'valid/missing/invalid', 'gps_accuracy_m': 'Только известная EXIF точность в метрах; иначе null',
                    'gps_buffer_m_used': 'Буфер сопоставления в метрах', 'gps_buffer_source': 'exif_accuracy/configured_assumption',
                    'metadata_source': 'Pillow/ExifTool/manual_correction', 'timezone_status': 'unknown/exif_offset/user_assumption',
                    'width': 'Ширина оригинала в пикселях', 'height': 'Высота оригинала в пикселях',
                    'long_side': 'Фактическое ограничение стороны для инференса', 'context': 'Фактический контекст в токенах',
                    'degraded': 'Снижение разрешения/контекста после ошибки памяти', 'processed_at': 'UTC ISO 8601',
                    'captured_at': 'ISO 8601, без смещения если оно неизвестно', 'captured_at_raw': 'Исходная EXIF строка времени',
                    'geo_status': 'located/map_unavailable/gps_missing/outside_city/outside_region',
                    'territory_visual': 'Категория изображённой территории модели', 'territory_geo': 'Кандидат карты в точке камеры',
                    'territory_source': 'visual/unknown/visual_geo_agree_camera_context_only',
                    'error': 'Ошибка чтения или модели, без base64', 'model_name': 'Явный локальный тег',
                    'ollama_version': 'Версия локального сервера', 'schema_version': 'Версия схемы',
                    'prompt_version': 'Версия промпта', 'rubric_version': 'Версия рабочей рубрики'}.get(c, 'Служебное поле происхождения результата')
        lines.append(f'| {c} | {desc} |')
    return '\n'.join(lines) + '\n'
