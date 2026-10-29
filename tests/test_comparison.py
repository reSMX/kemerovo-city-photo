from compare_models import compare_metrics, write_review_csv

def test_comparison_excludes_null_and_errors():
    left=[dict(processing_status='processed',territory_type='street',road_present=1,road_damage_score=2),
          dict(processing_status='processed',territory_type='street',road_present=0,road_damage_score=None),
          dict(processing_status='model_error')]
    right=[dict(processing_status='processed',territory_type='street',road_present=1,road_damage_score=6),
           dict(processing_status='processed',territory_type='park_square',road_present=1,road_damage_score=0),
           dict(processing_status='processed',road_damage_score=0)]
    r=compare_metrics(left,right)
    assert r['n_valid_pairs']==2 and r['territory_agreement']==.5
    assert r['presence']['road']['disagreements']==1
    assert r['scores']['road_damage_score']['n_comparable']==1
    assert r['scores']['road_damage_score']['mean_absolute_difference']==4
    assert r['scores']['road_damage_score']['null_mismatches']==1

def test_report_preserves_human_annotations(tmp_path):
    import csv
    path=tmp_path/'human.csv'
    fields=['image_id','relative_path','photo_score']
    write_review_csv(path,[dict(image_id='a',relative_path='a.jpg',photo_score='7.5')],fields,['photo_score'])
    write_review_csv(path,[dict(image_id='a',relative_path='a.jpg')],fields,['photo_score'])
    with path.open(encoding='utf-8-sig',newline='') as f:
        assert next(csv.DictReader(f,delimiter=';'))['photo_score']=='7.5'
