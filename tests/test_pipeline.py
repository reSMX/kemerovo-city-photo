"""Synthetic fixtures; these tests do not measure real model quality."""
import csv
import io
import json
import pytest
from PIL import Image
from pydantic import ValidationError
from city_photo.config import Config
from city_photo.schemas import Visual, OBJECTS, METRICS
from city_photo.metadata import gps_decimal, prepare, sha_file
from city_photo.storage import Store
from city_photo.pipeline import import_photos, analyze, geolocate
from city_photo.export import export_all, write_csv
from city_photo.review import review_import
from city_photo.geo import Geography
from city_photo.evaluation import evaluate

def synthetic_visual():
    return dict(territory_visual='street', territory_description='Синтетический пример',
        surface_type='unknown', mural_present=0, mural_status='no_mural', review_reasons=[],
        objects={o: dict(present=0, presence_status='absent', assessability='not_applicable',
            description='Не виден', visibility_reason='', metrics={m: dict(score=None,
            assessment_status='not_applicable', description='Не виден', reason='Отсутствует') for m in METRICS[o]}) for o in OBJECTS})

class Fake:
    def __init__(self, fail=False):
        self.calls, self.fail = 0, fail
    def identity(self):
        return dict(model_name='qwen3-vl:4b', model_digest='synthetic', ollama_version='test')
    def orientation(self, image):
        return dict(clockwise_rotation=0, certain=True, reason='Synthetic')
    def assess(self, image, prompt, context=None):
        self.calls += 1
        if self.fail:
            raise RuntimeError('Synthetic failure')
        return json.dumps(synthetic_visual()), {}

@pytest.fixture
def workspace(tmp_path):
    photos = tmp_path/'photos'
    (photos/'a').mkdir(parents=True)
    (photos/'b').mkdir()
    Image.new('RGB', (30,20), 'red').save(photos/'a'/'same.jpg')
    (photos/'b'/'same.jpg').write_bytes((photos/'a'/'same.jpg').read_bytes())
    (photos/'bad.jpg').write_bytes(b'broken synthetic JPEG')
    (photos/'unsupported.xyz').write_text('synthetic')
    store = Store(tmp_path/'work')
    cfg = Config(retries=0)
    import_photos(store, photos, cfg)
    yield store, cfg
    store.db.close()

def test_gps():
    assert gps_decimal((55,30,0), 'S') == -55.5
    assert gps_decimal((86,15,0), 'W') == -86.25
    with pytest.raises(ValueError):
        gps_decimal((0,0,0), '?')

def test_orientation_original(tmp_path):
    path = tmp_path/'rotated.jpg'
    exif = Image.Exif()
    exif[274] = 6
    Image.new('RGB', (40,20), 'blue').save(path, exif=exif)
    before = sha_file(path)
    im = Image.open(io.BytesIO(prepare(path, 1280)))
    assert im.size == (20,40) and not im.getexif()
    assert Image.open(io.BytesIO(prepare(path, 1280, 90))).size == (40,20)
    assert sha_file(path) == before

def test_schema():
    v = synthetic_visual()
    Visual.model_validate(v)
    v['objects']['road']['metrics']['damage']['score'] = 0
    with pytest.raises(ValidationError):
        Visual.model_validate(v)
    v = synthetic_visual()
    v['objects']['road']['presence_status'] = 'uncertain'
    v['objects']['road']['visibility_reason'] = 'Слишком далеко'
    Visual.model_validate(v)
    v['objects']['road']['metrics']['damage']['score'] = 11
    with pytest.raises(ValidationError):
        Visual.model_validate(v)

def test_cache_duplicates_rubric(workspace,tmp_path):
    store,cfg = workspace
    backend = Fake()
    analyze(store,cfg,backend=backend)
    assert backend.calls == 1 and len(store.rows()) == 4
    analyze(store,cfg,resume=True,backend=backend)
    assert backend.calls == 1
    rubric = tmp_path/'rubric.yaml'
    rubric.write_text('version: changed', encoding='utf-8')
    cfg.rubric_path = str(rubric)
    analyze(store,cfg,resume=True,backend=backend)
    assert backend.calls == 2
    out = tmp_path/'out'
    export_all(store,cfg,out)
    with (out/'results.csv').open(encoding='utf-8-sig',newline='') as f:
        rows = list(csv.DictReader(f,delimiter=';'))
    assert len(rows) == 4
    assert sum(bool(r['exact_duplicate_of']) for r in rows) == 1
    assert all(r['road_damage_score'] == '' for r in rows)

def test_model_errors(workspace):
    store,cfg = workspace
    analyze(store,cfg,backend=Fake(fail=True))
    statuses = [r['status'] for r in store.rows()]
    assert statuses.count('model_error') == 2
    assert 'unreadable' in statuses and 'unsupported' in statuses

def test_manual_map_no_vision(workspace,tmp_path):
    store,cfg = workspace
    backend = Fake()
    analyze(store,cfg,backend=backend)
    row = next(r for r in store.rows() if r['visual'])
    corrections = tmp_path/'corrections.csv'
    write_csv(corrections,[dict(image_id=row['image_id'],relative_path=row['relative_path'],author='Тест',reason='Тест',territory_type='park_square')],
              ['image_id','relative_path','author','reason','territory_type'])
    review_import(store,cfg,corrections)
    geolocate(store,cfg)
    analyze(store,cfg,force=True,backend=backend)
    assert store.overrides(row['image_id'])['territory_type'] == 'park_square'
    before = backend.calls
    cfg.gps_buffer_m = 60.0
    geolocate(store,cfg)
    analyze(store,cfg,resume=True,backend=backend)
    assert backend.calls == before

def test_geo_meters_conflict(tmp_path):
    data = {'type':'FeatureCollection','features':[
        {'type':'Feature','properties':{'layer':'boundary'},'geometry':{'type':'Polygon','coordinates':[[[85.9,55.2],[86.2,55.2],[86.2,55.5],[85.9,55.5],[85.9,55.2]]]}},
        {'type':'Feature','properties':{'layer':'park'},'geometry':{'type':'Polygon','coordinates':[[[86.0,55.3],[86.02,55.3],[86.02,55.32],[86.0,55.32],[86.0,55.3]]]}}]}
    path = tmp_path/'synthetic.geojson'
    path.write_text(json.dumps(data))
    geo = Geography(Config(map_path=str(path)))
    result = geo.locate(dict(latitude=55.31,longitude=86.00001,gps_accuracy_m=None),synthetic_visual())
    assert result['territory_geo'] == 'park_square'
    assert 'visual_geo_conflict_or_ambiguity' in result['geo_review_reasons']
    assert 'near_feature_boundary' in result['geo_review_reasons']
    assert result['gps_buffer_m_used'] == 30 and result['territory_type'] == 'street'

def test_csv(workspace,tmp_path):
    p = tmp_path/'test.csv'
    write_csv(p,[dict(name='=SUM(1;2)',text='Кириллица; "кавычки"',score=None)],['name','text','score'])
    assert p.read_bytes().startswith(b'\xef\xbb\xbf')
    with p.open(encoding='utf-8-sig',newline='') as f:
        row = next(csv.DictReader(f,delimiter=';'))
    assert row == dict(name="'=SUM(1;2)",text='Кириллица; "кавычки"',score='')

def test_resume(workspace):
    store,cfg = workspace
    analyze(store,cfg,limit=1,backend=Fake())
    backend=Fake()
    analyze(store,cfg,resume=True,backend=backend)
    assert backend.calls == 0
    assert len([r for r in store.rows() if r['visual']]) == 2

def test_offline():
    with pytest.raises(ValidationError):
        Config(ollama_url='https://example.com')
    from city_photo.vision import NoRedirect
    with pytest.raises(ValueError):
        NoRedirect().redirect_request(None,None,302,'',{},'https://example.com')

def test_evaluate_blanks(workspace,tmp_path):
    store,cfg=workspace
    analyze(store,cfg,backend=Fake())
    row=store.rows()[0]
    path=tmp_path/'labels.csv'
    write_csv(path,[dict(image_id=row['image_id'],relative_path=row['relative_path'],road_damage_score='')],['image_id','relative_path','road_damage_score'])
    assert evaluate(store,cfg,path)['scores']['road_damage_score']['mae'] is None

def test_bad_correction_atomic(workspace,tmp_path):
    store,cfg=workspace
    analyze(store,cfg,backend=Fake())
    row=store.rows()[0]
    path=tmp_path/'corrections.csv'
    write_csv(path,[dict(image_id=row['image_id'],relative_path=row['relative_path'],author='Тест',reason='Тест',road_damage_score=99)],
              ['image_id','relative_path','author','reason','road_damage_score'])
    with pytest.raises(ValueError):
        review_import(store,cfg,path)
    assert not store.overrides(row['image_id'])

def test_update_analyzes_only_new_content(workspace):
    store,cfg=workspace
    backend=Fake()
    analyze(store,cfg,backend=backend)
    assert backend.calls==1
    from pathlib import Path
    photos=Path(store.setting('input_root'))
    Image.new('RGB',(45,30),'green').save(photos/'new.jpg')
    assert import_photos(store,photos,cfg)==1
    analyze(store,cfg,resume=True,backend=backend)
    assert backend.calls==2
    assert import_photos(store,photos,cfg)==0
    analyze(store,cfg,resume=True,backend=backend)
    assert backend.calls==2
    (photos/'duplicate.jpg').write_bytes((photos/'new.jpg').read_bytes())
    assert import_photos(store,photos,cfg)==1
    analyze(store,cfg,resume=True,backend=backend)
    assert backend.calls==2

def test_invalid_map_does_not_block_vision(workspace,tmp_path):
    store,cfg=workspace
    bad=tmp_path/'bad.geojson'
    bad.write_text('{broken json')
    cfg.map_path=str(bad)
    backend=Fake()
    analyze(store,cfg,backend=backend)
    assert backend.calls==1
    processed=[r for r in store.rows() if r['visual']]
    assert len(processed)==2
    assert all(json.loads(r['geo'])['geo_status']=='map_error' for r in processed)
