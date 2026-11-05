import csv
from PIL import Image
import pytest
from scripts.split_photos import split_photos, verify_batch
from scripts.merge_results import merge_results
from city_photo.export import write_csv
from city_photo.metadata import sha_file

def test_balanced_copy_resume_originals(tmp_path):
    source=tmp_path/'original'
    source.mkdir()
    for i in range(4):
        Image.new('RGB',(10+i,20),'red').save(source/f'{i}.jpg')
    hashes={p.name:sha_file(p) for p in source.iterdir()}
    dest=tmp_path/'copies'
    counts=split_photos(source,dest)
    assert counts=={'part_1':2,'part_2':2}
    assert len(list((dest/'part_1').glob('*.jpg')))==2
    assert len(list((dest/'part_2').glob('*.jpg')))==2
    assert {p.name:sha_file(p) for p in source.iterdir()}==hashes
    assert split_photos(source,dest)==counts
    assert verify_batch(dest/'part_2',dest/'part_2_manifest.json')['verified_files']==2
    with pytest.raises(ValueError):
        split_photos(source,source/'nested')

def test_merge_rejects_overlap_versions(tmp_path):
    columns=['image_id','relative_path','processing_status','model_digest','prompt_hash','rubric_hash','schema_version']
    a=dict(image_id='a',relative_path='a.jpg',processing_status='processed',model_digest='m',prompt_hash='p',rubric_hash='r',schema_version='1')
    b=dict(a,image_id='b',relative_path='b.jpg')
    p1,p2=tmp_path/'a.csv',tmp_path/'b.csv'
    write_csv(p1,[a],columns)
    write_csv(p2,[b],columns)
    out=tmp_path/'merged.csv'
    assert merge_results([p1,p2],out)['total_files']==2
    with pytest.raises(ValueError):
        merge_results([p1,p1],out)
    write_csv(p2,[dict(b,model_digest='another')],columns)
    with pytest.raises(ValueError):
        merge_results([p1,p2],out)
