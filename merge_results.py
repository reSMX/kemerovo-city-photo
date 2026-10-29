"""Merge disjoint device exports, preserving rows and refusing mismatched model/rubric versions."""
import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from city_photo.export import write_csv

def merge_results(inputs,output,delimiter=';',allow_mixed=False):
    rows,ids,paths,header=[],set(),set(),None
    versions=set()
    for name in inputs:
        with open(name,encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f,delimiter=delimiter)
            if header is None:
                header=reader.fieldnames
            if reader.fieldnames!=header:
                raise ValueError('Different CSV schemas or column ordering')
            for row in reader:
                if row['image_id'] in ids or row['relative_path'] in paths:
                    raise ValueError('Overlapping batches: duplicate image_id or relative_path')
                ids.add(row['image_id'])
                paths.add(row['relative_path'])
                if row['processing_status'].startswith('processed'):
                    versions.add(tuple(row[k] for k in ('model_digest','prompt_hash','rubric_hash','schema_version'))+(row.get('photo_scoring_hash',''),))
                rows.append(row)
    if len(versions)>1 and not allow_mixed:
        raise ValueError('Different model/prompt/rubric versions; explicitly use --allow-mixed only for a labelled mixed export')
    rows.sort(key=lambda r:r['relative_path'])
    # Existing exports already carry formula protection. Avoid escaping their protected cells again.
    write_csv(output,rows,header,delimiter)
    output=Path(output)
    summary=dict(total_files=len(rows),statuses=dict(Counter(r['processing_status'] for r in rows)),
                 version_sets=len(versions),mixed_versions=len(versions)>1,
                 source_exports=[str(Path(p).resolve()) for p in inputs],
                 notes='Input/config paths can differ between devices; provenance retained per row. No row averaging.')
    output.with_suffix('.summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return {'total_files':len(rows),'statuses':summary['statuses'],'mixed_versions':summary['mixed_versions']}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--inputs',nargs='+',required=True)
    p.add_argument('--output',required=True)
    p.add_argument('--delimiter',default=';')
    p.add_argument('--allow-mixed',action='store_true')
    a=p.parse_args()
    print(json.dumps(merge_results(a.inputs,a.output,a.delimiter,a.allow_mixed),indent=2))
