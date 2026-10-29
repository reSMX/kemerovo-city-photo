import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from .config import Config, load
from .storage import Store
from .vision import Ollama
from .pipeline import import_photos, analyze, geolocate
from .export import export_all
from .review import review_export, review_import
from .evaluation import evaluate
from .geo import import_map

def gpu_info():
    try:
        p = subprocess.run(['nvidia-smi', '--query-gpu=name,memory.total,memory.used', '--format=csv,noheader'],
                           capture_output=True, text=True, timeout=10)
        return p.stdout.strip() or p.stderr.strip()
    except (OSError, subprocess.TimeoutExpired):
        return 'NVIDIA diagnostics unavailable'

def main():
    parser = argparse.ArgumentParser(prog='city-photo', description='Local urban photo analysis; no cloud inference')
    subs = parser.add_subparsers(dest='command', required=True)
    for name in ('doctor','init','import','prepare-map','analyze','geolocate','export','review-export','review-import','benchmark','evaluate'):
        p = subs.add_parser(name)
        p.add_argument('--config')
        p.add_argument('--workspace', default='work')
        if name == 'import':
            p.add_argument('--input')
            p.add_argument('--exiftool', action='store_true')
        if name in ('analyze', 'benchmark'):
            p.add_argument('--limit', type=int, default=20 if name == 'benchmark' else None)
            for flag in ('resume','retry-errors','force','dry-run'):
                p.add_argument('--'+flag, action='store_true')
        if name in ('export', 'review-export'):
            p.add_argument('--output', default='output')
        if name == 'review-export':
            p.add_argument('--limit', type=int, default=100)
        if name == 'review-import':
            p.add_argument('--file', required=True)
        if name == 'evaluate':
            p.add_argument('--labels', required=True)
            p.add_argument('--output', default='output/evaluation.json')
        if name == 'prepare-map':
            p.add_argument('--import-file', required=True)
            p.add_argument('--output', default='maps/kemerovo.geojson')
            p.add_argument('--source', required=True)
            p.add_argument('--license', required=True)
            p.add_argument('--attribution', required=True)
    args = parser.parse_args()
    try:
        cfg = load(args.config)
        if args.command == 'doctor':
            try:
                ollama = Ollama(cfg).identity()
            except Exception as e:
                ollama = {'error': str(e)}
            report = dict(python=sys.version, executable=sys.executable, gpu=gpu_info(),
                          disk_free_gib=round(shutil.disk_usage(Path.cwd()).free/2**30, 2),
                          ollama=ollama, input_exists=Path(cfg.input).is_dir(),
                          map_available=bool(cfg.map_path and Path(cfg.map_path).is_file()))
        elif args.command == 'prepare-map':
            report = {'map_path': import_map(args.import_file, args.output, args.attribution, args.source, args.license)}
        else:
            store = Store(args.workspace)
            try:
                if args.command == 'init':
                    report = {'workspace': str(store.path), 'schema_version': 1}
                elif args.command == 'import':
                    report = {'imported_or_changed': import_photos(store, args.input or cfg.input, cfg, args.exiftool)}
                elif args.command in ('analyze', 'benchmark'):
                    if args.limit is not None and args.limit < 1:
                        raise ValueError('--limit must be positive')
                    memory_before = gpu_info()
                    report = analyze(store, cfg, args.limit, args.resume, args.retry_errors, args.force, args.dry_run)
                    if args.command == 'benchmark':
                        report.update(gpu_before=memory_before, gpu_after=gpu_info(),
                                      memory_note='Snapshots, not peak usage; cache hits are not inference timing')
                        (store.path/'benchmark.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                elif args.command == 'geolocate':
                    geolocate(store, cfg)
                    report = {'geolocated': len(store.rows())}
                elif args.command == 'export':
                    report = export_all(store, cfg, args.output)
                elif args.command == 'review-export':
                    report = review_export(store, cfg, args.output, args.limit)
                elif args.command == 'review-import':
                    report = review_import(store, cfg, args.file)
                    geolocate(store, cfg)
                elif args.command == 'evaluate':
                    report = evaluate(store, cfg, args.labels)
                    path = Path(args.output)
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            finally:
                store.db.close()
        # Full errors/results stay on disk; no image-derived descriptions in terminal output.
        if args.command == 'export':
            report = {k: report[k] for k in ('total_files', 'statuses', 'missing_gps_fraction', 'needs_review')}
        print(json.dumps(report, ensure_ascii=True, indent=2))
    except KeyboardInterrupt:
        print('Interrupted; completed records are saved. Resume with --resume.', file=sys.stderr)
        raise SystemExit(130)
    except Exception as e:
        print(f'{type(e).__name__}: {e}', file=sys.stderr)
        raise SystemExit(1)
