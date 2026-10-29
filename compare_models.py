"""Compare two local Qwen variants on twelve identical originals; resumable."""
import argparse
import hashlib
import json
import random
import statistics
from pathlib import Path
from city_photo.config import load
from city_photo.storage import Store, dumps, now
from city_photo.schemas import OBJECTS, SCORES
from city_photo.pipeline import analyze
from city_photo.export import export_all, flat_row, write_csv
from city_photo.review import review_export
from city_photo.vision import Ollama

INSTRUCT='qwen3-vl:4b-instruct-q4_K_M'
THINKING='qwen3-vl:4b'

class SharedOrientation(Ollama):
    def __init__(self,cfg,orientation_cfg,output):
        super().__init__(cfg)
        self.orienter=Ollama(orientation_cfg)
        self.file=output/'shared_orientation.json'
        self.shared=json.loads(self.file.read_text(encoding='utf-8')) if self.file.exists() else {}
        self.orientation_identity=self.orienter.identity()
    def identity(self):
        return dict(super().identity(),orientation_model=self.orientation_identity,
                    orientation_policy='shared-instruct-v1')
    def orientation(self,image):
        key=hashlib.sha256(image).hexdigest()
        if key not in self.shared:
            self.shared[key]=self.orienter.orientation(image)
            tmp=self.file.with_suffix('.tmp')
            tmp.write_text(dumps(self.shared),encoding='utf-8')
            tmp.replace(self.file)
        return self.shared[key]

def compare_metrics(left,right):
    pairs=list(zip(left,right))
    paired=[(a,b) for a,b in pairs if a.get('processing_status','').startswith('processed') and b.get('processing_status','').startswith('processed')]
    territory=[a.get('territory_type')==b.get('territory_type') for a,b in paired]
    report=dict(n_photos=len(pairs),n_valid_pairs=len(paired),
                territory_agreement=sum(territory)/len(territory) if territory else None,
                presence={},scores={})
    for obj in OBJECTS:
        key=obj+'_present'
        p=[(a.get(key),b.get(key)) for a,b in paired]
        report['presence'][obj]=dict(n=len(p),disagreements=sum(a!=b for a,b in p),
            status_disagreements=sum(a.get(obj+'_presence_status')!=b.get(obj+'_presence_status') for a,b in paired))
    for key in SCORES:
        p=[(a.get(key),b.get(key)) for a,b in paired]
        diffs=[abs(a-b) for a,b in p if a is not None and b is not None]
        report['scores'][key]=dict(n_comparable=len(diffs),mean_absolute_difference=statistics.mean(diffs) if diffs else None,
            max_absolute_difference=max(diffs) if diffs else None,differences_over_2=sum(d>2 for d in diffs),
            null_mismatches=sum((a is None)!=(b is None) for a,b in p),both_null=sum(a is None and b is None for a,b in p))
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',default='work')
    parser.add_argument('--config',default='config.example.yaml')
    parser.add_argument('--output',default='comparison_12')
    parser.add_argument('--limit',type=int,default=12)
    parser.add_argument('--phase',choices=['all','instruct','thinking','report'],default='all')
    args=parser.parse_args()
    cfg=load(args.config)
    output=Path(args.output).resolve()
    output.mkdir(parents=True,exist_ok=True)
    source=Store(args.workspace)
    manifest=output/'selection'/'sample_manifest.json'
    if not manifest.exists():
        review_export(source,cfg,output/'selection',args.limit)
    samples=json.loads(manifest.read_text(encoding='utf-8'))['samples'][:args.limit]
    if len(samples)!=args.limit:
        raise ValueError('Not enough independent candidate groups')
    original={r['image_id']:dict(r) for r in source.rows()}
    stores={}
    models={'instruct':INSTRUCT,'thinking':THINKING}
    orientation_cfg=cfg.model_copy(update={'model':INSTRUCT,'thinking':False})
    for name,model in models.items():
        st=Store(output/name)
        stores[name]=st
        for sample in samples:
            row=original[sample['image_id']]
            with st.db:
                st.db.execute('INSERT OR IGNORE INTO photos(image_id,relative_path,source,sha,metadata,status) VALUES (?,?,?,?,?,?)',
                    (row['image_id'],row['relative_path'],row['source'],row['sha'],row['metadata'],'pending'))
        model_cfg=cfg.model_copy(update={'model':model,'thinking':name=='thinking',
            'temperature':0.2,'context':16384,'max_tokens':12288,'timeout':900,'retries':1})
        if args.phase in ('all',name):
            print(f'Starting {name}: {len(samples)} images; local inference only',flush=True)
            # On 16 GB hosts, retaining both runners can exhaust Windows commit memory.
            control=Ollama(model_cfg)
            loaded=control.request('/api/ps').get('models',[])
            for resident in loaded:
                if resident.get('name') in models.values() and resident.get('name')!=model:
                    control.request('/api/generate',{'model':resident['name'],'keep_alive':0})
            report=analyze(st,model_cfg,resume=True,retry_errors=True,
                           backend=SharedOrientation(model_cfg,orientation_cfg,output))
            (output/f'{name}_run.json').write_text(dumps(report),encoding='utf-8')
        export_all(st,model_cfg,output/name/'export')
    rows={name:[flat_row(st,r) for r in st.rows()] for name,st in stores.items()}
    # Store.rows has the same stable path order for both workspaces.
    report=compare_metrics(rows['instruct'],rows['thinking'])
    for name,st in stores.items():
        records=st.rows()
        run_file=output/f'{name}_run.json'
        run=json.loads(run_file.read_text(encoding='utf-8')) if run_file.exists() else {}
        report[name]=dict(model=models[name],statuses={status:sum(r['status']==status for r in records) for status in set(r['status'] for r in records)},
                         last_run_elapsed_seconds=run.get('elapsed_seconds'),
                         degraded_files=sum(bool(json.loads(r['provenance']).get('degraded')) for r in records),
                         assessment_seconds=sum((json.loads(r['provenance']).get('stats',{}).get('total_duration') or 0)/1e9 for r in records),
                         assessment_tokens=sum((json.loads(r['provenance']).get('stats',{}).get('eval_count') or 0) for r in records))
        measured=[]
        loads=[]
        compute=[]
        for row in records:
            stats=json.loads(row['provenance']).get('stats') or {}
            if stats.get('total_duration') is not None:
                measured.append(stats['total_duration']/1e9)
                loads.append((stats.get('load_duration') or 0)/1e9)
                compute.append((stats['total_duration']-(stats.get('load_duration') or 0))/1e9)
        report[name]['timing']=dict(n_successfully_measured=len(measured),
            mean_seconds_per_photo=statistics.mean(measured) if measured else None,
            median_seconds_per_photo=statistics.median(measured) if measured else None,
            min_seconds_per_photo=min(measured) if measured else None,
            max_seconds_per_photo=max(measured) if measured else None,
            mean_seconds_excluding_model_load=statistics.mean(compute) if compute else None,
            total_model_load_seconds=sum(loads),
            all_attempts_wall_seconds_per_selected_photo=run.get('elapsed_seconds')/len(samples) if run.get('elapsed_seconds') is not None else None,
            note='Ollama total_duration of successful assessment requests; includes request-side model load, excludes separate shared orientation. Wall average includes orientation, failures, retries, loading and preprocessing; resumed runs may include only remaining files.')
    report.update(created_at=now(),notes=['Differences, not accuracy: independent human labels required.',
        'Identical 12 originals and shared orientation from Instruct; 1280px, context 16384, output limit 12288, temperature .2, seed 42.',
        'Thinking enabled explicitly for Thinking weights. Nulls excluded from numeric differences; null disagreements reported separately.',
        'One representative per dHash/exact/camera-tile connected group. Sampling heuristics do not prove site independence.'])
    (output/'comparison_summary.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    order=['instruct','thinking']
    random.Random(cfg.seed).shuffle(order)
    (output/'model_key.json').write_text(dumps({letter:models[name] for letter,name in zip(('A','B'),order)}),encoding='utf-8')
    blind=[]
    fields=['image_id','relative_path','original_file','upright_copy','A_processing_status','B_processing_status']
    measures=['territory_type',*[f'{o}_present' for o in OBJECTS],*SCORES]
    explanations=['territory_description',*[f'{o}_presence_status' for o in OBJECTS],*[s.replace('_score','_description') for s in SCORES],*[s.replace('_score','_assessment_status') for s in SCORES],*[s.replace('_score','_reason') for s in SCORES]]
    for key in measures+explanations:
        fields.extend(['A_'+key,'B_'+key])
    fields.extend('human_'+key for key in measures)
    fields.append('human_notes')
    by_id={name:{r['image_id']:r for r in rs} for name,rs in rows.items()}
    for sample in samples:
        iid=sample['image_id']
        record=dict(image_id=iid,relative_path=original[iid]['relative_path'],original_file=original[iid]['source'],
                    upright_copy=str(stores['instruct'].path/'derived'/f'{iid}.jpg'))
        for letter,name in zip(('A','B'),order):
            p=by_id[name][iid]
            record[letter+'_processing_status']=p['processing_status']
            for key in measures+explanations:
                record[letter+'_'+key]=p.get(key)
        blind.append(record)
    write_csv(output/'blind_review.csv',blind,fields,cfg.delimiter)
    timing_rows=[]
    for sample in samples:
        iid=sample['image_id']
        record=dict(image_id=iid,relative_path=original[iid]['relative_path'])
        for name,st in stores.items():
            raw=st.db.execute('SELECT provenance,status FROM photos WHERE image_id=?',(iid,)).fetchone()
            stats=json.loads(raw['provenance']).get('stats') or {}
            record[name+'_status']=raw['status']
            for key in ('total_duration','load_duration','eval_duration'):
                value=stats.get(key)
                record[name+'_'+key+'_seconds']=value/1e9 if value is not None else None
            record[name+'_generated_tokens']=stats.get('eval_count')
        a,b=record.get('instruct_total_duration_seconds'),record.get('thinking_total_duration_seconds')
        record['thinking_to_instruct_ratio']=b/a if a and b else None
        timing_rows.append(record)
    timing_fields=['image_id','relative_path']
    for name in models:
        timing_fields.extend([name+'_status',*[name+'_'+key+'_seconds' for key in ('total_duration','load_duration','eval_duration')],name+'_generated_tokens'])
    timing_fields.append('thinking_to_instruct_ratio')
    write_csv(output/'timings.csv',timing_rows,timing_fields,cfg.delimiter)
    human=[dict(image_id=s['image_id'],relative_path=original[s['image_id']]['relative_path']) for s in samples]
    write_csv(output/'human_labels.csv',human,['image_id','relative_path',*measures],cfg.delimiter)
    lines=['# Сравнение двух локальных Qwen на 12 фото','',
           f'Пар с валидными ответами: {report["n_valid_pairs"]}/{report["n_photos"]}.',
           f'Совпадение типа территории: {report["territory_agreement"]}.','',
           'Это расхождения моделей, не измерение точности. Для независимой оценки заполните human_labels.csv.',
           'blind_review.csv: A/B рядом, объяснения, оригинал, копия с исправленной ориентацией, поля human_*.',
           'model_key.json раскрывает обозначения. Разметка до просмотра A/B снижает влияние подсказок.',
           'shared_orientation.json: общая предобработка обеих моделей.','',
           '| Показатель | Сопоставимых | Среднее абсолютное расхождение | Разница >2 | Различие null |',
           '|---|---:|---:|---:|---:|']
    for key,m in report['scores'].items():
        lines.append(f'| {key} | {m["n_comparable"]} | {m["mean_absolute_difference"]} | {m["differences_over_2"]} | {m["null_mismatches"]} |')
    lines.extend(['','Время и статусы по моделям:'])
    for name in models:
        lines.append(f'- {name}: статусы {report[name]["statuses"]}; API-время успешных оценок {report[name]["assessment_seconds"]:.1f} с; деградированных кадров {report[name]["degraded_files"]}.')
        t=report[name]['timing']
        lines.append(f'  Среднее секунд/фото: {t["mean_seconds_per_photo"]}; медиана {t["median_seconds_per_photo"]}; min/max {t["min_seconds_per_photo"]}/{t["max_seconds_per_photo"]}; без загрузки весов {t["mean_seconds_excluding_model_load"]}; измерено {t["n_successfully_measured"]} фото. Полное время в среднем, включая повторы и ориентацию: {t["all_attempts_wall_seconds_per_selected_photo"]}.')
    lines.append('timings.csv содержит время каждого кадра, загрузку модели, генерацию, число токенов и отношение времени Thinking/Instruct.')
    lines.extend(['','Полное время запуска включает загрузку модели, ориентацию и повторы. API-время только успешных оценок исключает ошибки, поэтому не является полным сравнением скорости.',
                  'Точное сравнение качества: заполнить human_labels.csv и выполнить evaluate для обеих папок.'])
    (output/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'photos':report['n_photos'],'valid_pairs':report['n_valid_pairs'],
                      'territory_agreement':report['territory_agreement'],'output':str(output)},indent=2),flush=True)
    source.db.close()
    for st in stores.values():
        st.db.close()

if __name__=='__main__':
    main()
