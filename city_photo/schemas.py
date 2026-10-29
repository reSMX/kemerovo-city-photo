from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

TERRITORIES = ('courtyard', 'street', 'boulevard', 'park_square', 'private_sector', 'other', 'mixed', 'unknown')
OBJECTS = ('road', 'sidewalk', 'wall', 'grass', 'curb', 'vegetation', 'playground', 'parking', 'litter')
METRICS = {'road': ('damage',), 'sidewalk': ('damage',), 'wall': ('damage', 'graffiti'),
           'grass': ('damage',), 'curb': ('damage',), 'vegetation': ('abundance', 'damage'),
           'playground': ('damage',), 'parking': ('damage',), 'litter': ('litter',)}
SCORES = tuple('litter_score' if o == 'litter' else f'{o}_{m}_score' for o in OBJECTS for m in METRICS[o])
Territory = Literal['courtyard', 'street', 'boulevard', 'park_square', 'private_sector', 'other', 'mixed', 'unknown']
Status = Literal['assessable', 'partial', 'not_assessable', 'not_applicable']

class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class Assessment(Strict):
    score: int | None = Field(ge=0, le=10)
    assessment_status: Status
    description: str = Field(min_length=1, max_length=500)
    reason: str

    @model_validator(mode='after')
    def consistent(self):
        if self.assessment_status in ('not_assessable', 'not_applicable') and self.score is not None:
            raise ValueError('Unassessable metric must have null score')
        if self.score is None and not self.reason.strip():
            raise ValueError('Null score requires reason')
        if self.score == 0 and self.assessment_status != 'assessable':
            raise ValueError('Zero requires sufficient visibility (assessable)')
        if self.assessment_status == 'partial' and not self.reason.strip():
            raise ValueError('Partial assessment requires limitation')
        return self

class Observation(Strict):
    present: Literal[0, 1]
    presence_status: Literal['present', 'absent', 'uncertain']
    assessability: Status
    description: str = Field(min_length=1, max_length=500)
    visibility_reason: str
    metrics: dict[str, Assessment]

    @model_validator(mode='after')
    def consistent(self):
        if self.present != int(self.presence_status == 'present'):
            raise ValueError('present must agree with presence_status')
        if self.presence_status != 'present' and any(m.score is not None for m in self.metrics.values()):
            raise ValueError('Absent/uncertain object must have null scores')
        if self.assessability in ('not_assessable', 'not_applicable') and any(m.score is not None for m in self.metrics.values()):
            raise ValueError('Unassessable object must have null scores')
        if (self.presence_status == 'uncertain' or self.assessability in ('partial', 'not_assessable')) and not self.visibility_reason.strip():
            raise ValueError('Visibility limitation requires reason')
        return self

class Visual(Strict):
    territory_visual: Territory
    territory_description: str
    surface_type: Literal['paved', 'unpaved', 'mixed', 'unknown']
    mural_present: Literal[0, 1]
    mural_status: Literal['mural', 'no_mural', 'mural_or_graffiti_uncertain']
    objects: dict[str, Observation]
    review_reasons: list[str]

    @model_validator(mode='after')
    def keys(self):
        if set(self.objects) != set(OBJECTS):
            raise ValueError(f'objects must contain exactly {OBJECTS}')
        for obj, metrics in METRICS.items():
            if set(self.objects[obj].metrics) != set(metrics):
                raise ValueError(f'Incorrect metrics for {obj}: expected {metrics}')
        if self.mural_present != int(self.mural_status == 'mural'):
            raise ValueError('Mural fields inconsistent')
        return self

class Orientation(Strict):
    clockwise_rotation: Literal[0, 90, 180, 270]
    certain: bool
    reason: str = Field(max_length=180)

def visual_schema():
    """Concrete properties let Ollama constrain every object and metric key."""
    s = Visual.model_json_schema()
    import copy
    assessment = s['$defs']['Assessment']
    available = copy.deepcopy(assessment)
    available['properties']['assessment_status'] = {'type': 'string', 'const': 'assessable'}
    partial = copy.deepcopy(assessment)
    partial['properties']['assessment_status'] = {'type': 'string', 'const': 'partial'}
    partial['properties']['score'] = {'anyOf': [{'type': 'integer', 'minimum': 1, 'maximum': 10}, {'type': 'null'}]}
    unavailable = copy.deepcopy(assessment)
    unavailable['properties']['assessment_status'] = {'type': 'string', 'enum': ['not_assessable', 'not_applicable']}
    unavailable['properties']['score'] = {'type': 'null'}
    s['$defs']['Assessment'] = {'anyOf': [available, partial, unavailable]}
    obs = s['$defs']['Observation']
    concrete = {}
    for obj, metrics in METRICS.items():
        item = copy.deepcopy(obs)
        item['properties']['metrics'] = {'type': 'object', 'properties': {
            m: {'$ref': '#/$defs/Assessment'} for m in metrics}, 'required': list(metrics), 'additionalProperties': False}
        visible = copy.deepcopy(item)
        visible['properties']['present'] = {'type': 'integer', 'const': 1}
        visible['properties']['presence_status'] = {'type': 'string', 'const': 'present'}
        invisible = copy.deepcopy(item)
        invisible['properties']['present'] = {'type': 'integer', 'const': 0}
        invisible['properties']['presence_status'] = {'type': 'string', 'enum': ['absent', 'uncertain']}
        for m in metrics:
            null_assessment = copy.deepcopy(assessment)
            null_assessment['properties']['score'] = {'type': 'null'}
            invisible['properties']['metrics']['properties'][m] = null_assessment
        concrete[obj] = {'anyOf': [visible, invisible]}
    s['properties']['objects'] = {'type': 'object', 'properties': concrete, 'required': list(OBJECTS), 'additionalProperties': False}
    return s
