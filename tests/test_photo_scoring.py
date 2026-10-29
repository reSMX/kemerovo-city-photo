from city_photo.photo_scoring import assess_photo

def row():
    return dict(processing_status='processed',needs_review=0,road_present=1,road_presence_status='present',
                road_damage_score=2,road_damage_assessment_status='assessable',sidewalk_present=1,
                sidewalk_presence_status='present',sidewalk_damage_score=4,sidewalk_damage_assessment_status='assessable')

def test_score_direction_and_absence():
    r=row()
    a=assess_photo(r)
    assert a['photo_score']==7.08 and a['photo_score_coverage']==1
    assert assess_photo(dict(r,road_damage_score=8))['photo_score']<a['photo_score']
    assert assess_photo(dict(r,parking_present=0,parking_presence_status='absent'))['photo_score']==a['photo_score']
    low=assess_photo(dict(r,vegetation_presence_status='present',vegetation_abundance_score=1,vegetation_abundance_assessment_status='assessable'))
    high=assess_photo(dict(r,vegetation_presence_status='present',vegetation_abundance_score=9,vegetation_abundance_assessment_status='assessable'))
    assert high['photo_score']>low['photo_score']

def test_unknown_coverage_bounds_and_null():
    r=dict(row(),wall_presence_status='uncertain',vegetation_presence_status='uncertain',playground_presence_status='uncertain')
    a=assess_photo(r)
    assert a['photo_score'] is None and a['photo_score_coverage']<.6
    assert a['photo_score_lower_bound']<a['photo_score_upper_bound']
    assert assess_photo(dict(row(),sidewalk_damage_score=None))['photo_score'] is None
    assert assess_photo(dict(row(),processing_status='model_error'))['photo_score'] is None
    assert assess_photo(dict(row(),needs_review=1))['photo_score_status']=='provisional'

def test_formula_changes_need_no_model_call():
    from city_photo.photo_scoring import DEFAULT
    import copy
    rules=copy.deepcopy(DEFAULT)
    rules['weights']['road_damage_score']=.5
    a,b=assess_photo(row()),assess_photo(row(),rules)
    assert a['photo_score']!=b['photo_score']
    assert a['photo_scoring_hash']!=b['photo_scoring_hash']
