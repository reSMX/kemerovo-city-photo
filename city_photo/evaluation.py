import csv
from .schemas import OBJECTS, SCORES, TERRITORIES
from .export import flat_row, safe_cell
from .photo_scoring import load_rules

def evaluate(store, cfg, labels):
    scoring_rules=load_rules(cfg.photo_scoring_path)
    predictions = {r['image_id']: flat_row(store, r, scoring_rules=scoring_rules) for r in store.rows()}
    matched = []
    with open(labels, encoding='utf-8-sig', newline='') as f:
        for label in csv.DictReader(f, delimiter=cfg.delimiter):
            pred = predictions.get(label.get('image_id'))
            if not pred or label.get('relative_path') not in (pred['relative_path'], safe_cell(pred['relative_path'])):
                raise ValueError('Label ID/path does not match workspace')
            matched.append((label, pred))
    result = {'n_rows': len(matched), 'presence': {}, 'scores': {}, 'territory': {}}
    aggregate = {'tp': 0, 'fp': 0, 'fn': 0, 'n_comparable': 0}
    for obj in OBJECTS:
        key = obj+'_present'
        if any(l.get(key) not in (None, '', '0', '1', 'unknown', 'not_assessable', '<NULL>') for l,p in matched):
            raise ValueError(f'Invalid presence label for {obj}')
        labelled = [(int(l[key]), p.get(key)) for l,p in matched if l.get(key) in ('0', '1')]
        pairs = [(a,b) for a,b in labelled if b in (0,1)]
        tp = sum(a == b == 1 for a,b in pairs)
        fp = sum(a == 0 and b == 1 for a,b in pairs)
        fn = sum(a == 1 and b == 0 for a,b in pairs)
        for name, value in (('tp', tp), ('fp', fp), ('fn', fn), ('n_comparable', len(pairs))):
            aggregate[name] += value
        result['presence'][obj] = dict(n_labelled=len(labelled), n_comparable=len(pairs),
            positive_support=sum(a == 1 for a,b in pairs), negative_support=sum(a == 0 for a,b in pairs),
            precision=tp/(tp+fp) if tp+fp else None, recall=tp/(tp+fn) if tp+fn else None,
            f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,
            uncertain_fraction=sum(p.get(obj+'_presence_status') == 'uncertain' for l,p in matched)/len(matched) if matched else None,
            reason=None if pairs else 'No comparable labelled presence observations')
    tp, fp, fn = aggregate['tp'], aggregate['fp'], aggregate['fn']
    result['presence_overall'] = dict(n_comparable=aggregate['n_comparable'],
        precision=tp/(tp+fp) if tp+fp else None, recall=tp/(tp+fn) if tp+fn else None,
        micro_f1=2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else None,
        reason=None if aggregate['n_comparable'] else 'No comparable labelled presence observations')
    matrix = {a: {b: 0 for b in TERRITORIES} for a in TERRITORIES}
    for l,p in matched:
        truth = l.get('territory_type')
        if truth and truth not in TERRITORIES:
            raise ValueError('Invalid labelled territory')
        if truth in TERRITORIES:
            matrix[truth][p.get('territory_type') or 'unknown'] += 1
    f1s = []
    for a in TERRITORIES:
        support = sum(matrix[a].values())
        if support:
            tp = matrix[a][a]
            fp = sum(matrix[b][a] for b in TERRITORIES if b != a)
            fn = support-tp
            f1s.append(2*tp/(2*tp+fp+fn) if 2*tp+fp+fn else 0)
    result['territory'] = dict(confusion_matrix=matrix, macro_f1=sum(f1s)/len(f1s) if f1s else None,
                               support={a: sum(matrix[a].values()) for a in TERRITORIES},
                               reason=None if f1s else 'No labelled territory observations')
    for key in (*SCORES,'photo_score'):
        pairs, labelled, abstained, uncertain_truth, false_confident = [], 0, 0, 0, 0
        for l,p in matched:
            v = l.get(key, '')
            if not v:
                continue
            pred = p.get(key)
            if v in ('unknown', 'not_assessable', '<NULL>'):
                uncertain_truth += 1
                false_confident += pred is not None
                continue
            score = float(v) if key=='photo_score' else int(v)
            if not 0 <= score <= 10:
                raise ValueError('Labelled score outside 0..10')
            labelled += 1
            if pred is None:
                abstained += 1
            else:
                pairs.append(abs(score-pred))
        result['scores'][key] = dict(n_labelled=labelled, n_comparable=len(pairs),
            mae=sum(pairs)/len(pairs) if pairs else None,
            within_2=sum(e <= 2 for e in pairs)/len(pairs) if pairs else None,
            abstention_fraction=abstained/labelled if labelled else None,
            prediction_null_fraction=sum(p.get(key) is None for l,p in matched)/len(matched) if matched else None,
            erroneous_refusals=abstained, human_unassessable=uncertain_truth,
            false_confident_fraction=false_confident/uncertain_truth if uncertain_truth else None,
            reason=None if pairs else 'No comparable numeric observations; blanks are not zeros')
    result['needs_review_fraction'] = sum(p['needs_review'] for l,p in matched)/len(matched) if matched else None
    return result
