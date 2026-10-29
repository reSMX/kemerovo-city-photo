"""Make two balanced, verified copies without modifying the originals."""
import argparse
import json
import os
import shutil
from pathlib import Path
from city_photo.metadata import FORMATS, sha_file
from city_photo.config import digest
from city_photo.storage import now

def verify_batch(source,manifest_path):
    source=Path(source).resolve()
    manifest=json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    expected={r['relative_path']:r for r in manifest['files']}
    actual={p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file() and p.suffix.lower() in FORMATS}
    if actual!=set(expected):
        raise ValueError('Batch file list differs from manifest')
    for relative,record in expected.items():
        path=(source/relative).resolve()
        if source not in path.parents:
            raise ValueError('Manifest path escapes photo folder')
        if sha_file(path)!=record['sha256']:
            raise ValueError('Batch checksum mismatch')
    return {'verified_files':len(expected),'part':manifest.get('part')}

def split_photos(source,destination):
    source,destination=Path(source).resolve(),Path(destination).resolve()
    if not source.is_dir():
        raise ValueError('Source folder not found')
    if source==destination or source in destination.parents or destination in source.parents:
        raise ValueError('Source and destination trees must be separate')
    files=sorted(p for p in source.rglob('*') if p.is_file() and p.suffix.lower() in FORMATS)
    if not files:
        raise ValueError('No supported photographs found')
    destination.mkdir(parents=True,exist_ok=True)
    manifest_path=destination/'split_manifest.json'
    relative=[p.relative_to(source).as_posix() for p in files]
    sizes=[(len(files)+1)//2,len(files)//2]
    if manifest_path.exists():
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        if manifest['source']!=str(source) or sorted(r['relative_path'] for r in manifest['files'])!=relative:
            raise ValueError('Existing split snapshot differs; use a new destination for another archive')
    else:
        records=[]
        for i,p in enumerate(files):
            rel=p.relative_to(source).as_posix()
            records.append(dict(relative_path=rel,image_id=digest(rel)[:24],sha256=sha_file(p),
                                part=1 if i<sizes[0] else 2,size_bytes=p.stat().st_size))
        manifest=dict(created_at=now(),source=str(source),policy='sorted relative paths; first half / second half',
                      counts={'part_1':sizes[0],'part_2':sizes[1]},files=records)
        tmp=manifest_path.with_suffix('.tmp')
        tmp.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        tmp.replace(manifest_path)
    missing_bytes=sum(r['size_bytes'] for r in manifest['files'] if not (destination/f'part_{r["part"]}'/r['relative_path']).exists())
    if shutil.disk_usage(destination).free<missing_bytes+100*1024**2:
        raise ValueError('Insufficient free space for copies')
    for i,record in enumerate(manifest['files'],1):
        src=source/record['relative_path']
        dst=destination/f'part_{record["part"]}'/record['relative_path']
        if dst.exists():
            if sha_file(dst)!=record['sha256']:
                raise ValueError('Existing destination differs from manifest; no overwrite performed')
        else:
            dst.parent.mkdir(parents=True,exist_ok=True)
            tmp=dst.with_name(dst.name+'.copying')
            shutil.copy2(src,tmp)
            if sha_file(tmp)!=record['sha256']:
                raise ValueError('Copy hash mismatch; source may have changed')
            os.replace(tmp,dst)
        if i%50==0:
            print(f'Copied/verified {i}/{len(files)}',flush=True)
    for part in (1,2):
        records=[r for r in manifest['files'] if r['part']==part]
        # Manifest accompanies each transferable folder, outside its input photo tree.
        (destination/f'part_{part}_manifest.json').write_text(json.dumps(dict(part=part,count=len(records),files=records),ensure_ascii=False,indent=2),encoding='utf-8')
    return manifest['counts']

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True)
    p.add_argument('--output')
    p.add_argument('--verify-manifest')
    a=p.parse_args()
    if a.verify_manifest:
        print(json.dumps(verify_batch(a.input,a.verify_manifest)))
    elif a.output:
        print(json.dumps(split_photos(a.input,a.output)))
    else:
        p.error('Provide --output for splitting or --verify-manifest for verification')
