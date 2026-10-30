"""Deterministic, explicitly experimental score of the visible part of one frame."""
import math
from pathlib import Path
import yaml
from .config import RESOURCES, digest
from .schemas import SCORES

def load_rules(path=None):
    rules=yaml.safe_load((Path(path) if path else RESOURCES/'photo_scoring.yaml').read_text(encoding='utf-8'))
    weights=rules.get('weights',{})
    if set(weights)!=set(SCORES) or any(type(w) not in (int,float) or not math.isfinite(w) or w<=0 for w in weights.values()):
        raise ValueError('Photo score needs a positive finite weight for every metric')
    if not 0<rules['minimum_coverage']<=1 or not 0<rules['partial_information_factor']<=1:
        raise ValueError('Invalid score information thresholds')
    if rules['minimum_condition_metrics']<1 or rules['minimum_condition_objects']<1:
        raise ValueError('At least one condition metric/object must be required')
    for name,default in (('baseline_quality',10.0),('damage_penalty',1.0),('vegetation_reference',10.0),('vegetation_bonus_per_point',1.0)):
        value=rules.get(name,default)
        if type(value) not in (int,float) or not math.isfinite(value) or value<0:
            raise ValueError(f'Invalid scoring parameter: {name}')
    if rules.get('baseline_quality',10)>10 or rules.get('vegetation_reference',10)>10:
        raise ValueError('Scoring baseline/reference must be within 0..10')
    return rules

DEFAULT=load_rules()

def assess_photo(row,rules=None):
    rules=rules or DEFAULT
    result=dict(photo_score=None,photo_score_status='insufficient_data',photo_score_coverage=None,
                photo_score_lower_bound=None,photo_score_upper_bound=None,
                photo_score_metric_count=0,photo_score_reason='',
                photo_scoring_version=str(rules['version']),photo_scoring_hash=digest(rules))
    if not row.get('processing_status','').startswith('processed'):
        result['photo_score_reason']='Нет валидного результата визуальной модели.'
        return result
    eligible,known,weighted=0.0,0.0,0.0
    condition_count=0
    condition_objects=set()
    metric_count=0
    for key,weight in rules['weights'].items():
        obj=key.split('_')[0]
        presence=row.get(obj+'_presence_status')
        # Absence is never a condition defect; uncertain contributes to missing information.
        if presence=='absent' or presence is None:
            continue
        eligible+=weight
        score=row.get(key)
        status=row.get(key.replace('_score','_assessment_status'))
        if presence!='present' or score is None or status not in ('assessable','partial'):
            continue
        factor=1.0 if status=='assessable' else rules['partial_information_factor']
        observed_weight=weight*factor
        baseline=rules.get('baseline_quality',10.0)
        if key=='vegetation_abundance_score':
            quality=(baseline+rules.get('vegetation_bonus_per_point',1.0)*(score-rules.get('vegetation_reference',baseline)))
        else:
            quality=baseline-rules.get('damage_penalty',1.0)*score
        quality=max(0.0,min(10.0,quality))
        known+=observed_weight
        weighted+=quality*observed_weight
        metric_count+=1
        if key!='vegetation_abundance_score':
            condition_count+=1
            condition_objects.add(obj)
    result['photo_score_metric_count']=metric_count
    if not eligible:
        result['photo_score_reason']='Нет видимых или потенциально присутствующих оцениваемых объектов.'
        return result
    coverage=known/eligible
    result.update(photo_score_coverage=round(coverage,4),photo_score_lower_bound=round(weighted/eligible,2),
                  photo_score_upper_bound=round((weighted+10*(eligible-known))/eligible,2))
    if coverage<rules['minimum_coverage'] or condition_count<rules['minimum_condition_metrics'] or len(condition_objects)<rules['minimum_condition_objects']:
        result['photo_score_reason']='Недостаточное покрытие или менее двух различных объектов с оценкой состояния.'
        return result
    provisional=bool(row.get('needs_review'))
    result.update(photo_score=round(weighted/known,2),photo_score_status='provisional' if provisional else 'available',
                  photo_score_reason='Экспериментальная оценка только видимой части; требуется проверка.' if provisional else
                  'Экспериментальная оценка только видимой части; точность требует ручной калибровки.')
    return result
