import io
import json
import pytest
from PIL import Image
from city_photo.config import Config
from city_photo.metadata import inspect, prepare
from city_photo.storage import Store
from city_photo.pipeline import import_photos, analyze
from city_photo.export import write_csv
from city_photo.review import review_import
from test_pipeline import Fake

def test_gps_read_from_original_and_bad_gps(tmp_path):
    path=tmp_path/'gps.jpg'
    exif=Image.Exif()
    exif[34853]={1:'S',2:(55.0,30.0,0.0),3:'W',4:(86.0,15.0,0.0)}
    Image.new('RGB',(20,30),'white').save(path,exif=exif)
    meta,status=inspect(path,Config())
    assert status=='pending' and meta['latitude']==-55.5 and meta['longitude']==-86.25
    exif[34853]={1:'N',2:(55.0,30.0,0.0)}
    Image.new('RGB',(20,30),'white').save(path,exif=exif)
    meta,status=inspect(path,Config())
    assert status=='pending' and meta['gps_status']=='invalid'
    assert meta['latitude'] is None

def test_uncertain_orientation_and_manual_rotation(tmp_path):
    photos=tmp_path/'photos'
    photos.mkdir()
    Image.new('RGB',(40,20),'red').save(photos/'test.jpg')
    store=Store(tmp_path/'work')
    cfg=Config(retries=0)
    class Ambiguous(Fake):
        def orientation(self,image):
            return dict(clockwise_rotation=180,certain=False,reason='Synthetic ambiguity')
    backend=Ambiguous()
    import_photos(store,photos,cfg)
    analyze(store,cfg,backend=backend)
    row=store.rows()[0]
    assert json.loads(row['provenance'])['clockwise_rotation']==0
    corrections=tmp_path/'c.csv'
    write_csv(corrections,[dict(image_id=row['image_id'],relative_path=row['relative_path'],author='Test',reason='Synthetic rotation',clockwise_rotation=90)],
              ['image_id','relative_path','author','reason','clockwise_rotation'])
    review_import(store,cfg,corrections)
    analyze(store,cfg,resume=True,backend=backend)
    assert backend.calls==2
    assert Image.open(store.path/'derived'/f'{row["image_id"]}.jpg').size==(20,40)
    store.db.close()
