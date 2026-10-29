from compare_models import compare_metrics

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
