import hashlib
import json
import math
import subprocess
import shutil
from datetime import datetime
from pathlib import Path
from PIL import Image, ImageOps, ImageStat, ImageFilter

FORMATS = {'.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif'}

def sha_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

def gps_decimal(parts, ref):
    if ref not in ('N', 'S', 'E', 'W'):
        raise ValueError('Missing/invalid GPS hemisphere')
    d, m, s = (float(v) for v in parts)
    if d < 0 or not 0 <= m < 60 or not 0 <= s < 60:
        raise ValueError('Invalid GPS DMS')
    v = (d + m / 60 + s / 3600) * (-1 if ref in ('S', 'W') else 1)
    if not math.isfinite(v) or abs(v) > (90 if ref in ('N', 'S') else 180):
        raise ValueError('GPS coordinate outside range')
    return v

def open_image(path):
    if Path(path).suffix.lower() in ('.heic', '.heif'):
        try:
            from pillow_heif import register_heif_opener
            register_heif_opener()
        except ImportError as e:
            raise RuntimeError('HEIF requires pip install pillow-heif==1.1.1') from e
    return Image.open(path)

def inspect(path, cfg):
    meta = {'size_bytes': path.stat().st_size, 'latitude': None, 'longitude': None,
            'gps_status': 'missing', 'metadata_source': 'Pillow', 'gps_accuracy_m': None,
            'captured_at': None, 'timezone_status': 'unknown', 'quality_flags': []}
    if path.suffix.lower() not in FORMATS:
        return meta, 'unsupported'
    try:
        with open_image(path) as im:
            im.load()
            exif = im.getexif()
            meta.update(width=im.width, height=im.height, exif_orientation=exif.get(274, 1))
            try:
                gps = exif.get_ifd(34853)
                if gps:
                    meta.update(latitude=gps_decimal(gps[2], gps[1]), longitude=gps_decimal(gps[4], gps[3]), gps_status='valid')
                    accuracy = gps.get(31)
                    if accuracy is not None and float(accuracy) > 0:
                        meta['gps_accuracy_m'] = float(accuracy)
            except (KeyError, ValueError, TypeError, ZeroDivisionError):
                meta.update(latitude=None, longitude=None, gps_status='invalid')
            detail = exif.get_ifd(34665)
            captured = detail.get(36867) or exif.get(306)
            offset = detail.get(36881)
            if captured:
                meta['captured_at_raw'] = str(captured)
                try:
                    dt = datetime.strptime(str(captured), '%Y:%m:%d %H:%M:%S')
                    if offset:
                        dt = datetime.fromisoformat(dt.isoformat() + str(offset))
                        meta['timezone_status'] = 'exif_offset'
                    elif cfg.normalize_timezone:
                        # Asia/Krasnoyarsk is UTC+07 for contemporary photographs.
                        from zoneinfo import ZoneInfo
                        dt = dt.replace(tzinfo=ZoneInfo(cfg.timezone_assumption))
                        meta['timezone_status'] = 'user_assumption'
                    meta['captured_at'] = dt.isoformat()
                except (ValueError, KeyError):
                    meta['time_error'] = 'Cannot parse EXIF date/time or timezone'
            rgb = ImageOps.exif_transpose(im).convert('RGB')
            grey = rgb.convert('L').resize((256, 256))
            brightness = ImageStat.Stat(grey).mean[0]
            sharpness = ImageStat.Stat(grey.filter(ImageFilter.FIND_EDGES).crop((1, 1, 255, 255))).var[0]
            meta.update(brightness=brightness, sharpness=sharpness)
            if brightness < cfg.dark_threshold:
                meta['quality_flags'].append('dark_image_heuristic')
            if sharpness < cfg.blur_threshold:
                meta['quality_flags'].append('blur_heuristic')
            small = rgb.convert('L').resize((9, 8))
            pixels = list(small.getdata())
            bits = [pixels[y*9+x] > pixels[y*9+x+1] for y in range(8) for x in range(8)]
            meta['dhash'] = f'{sum(int(v) << i for i,v in enumerate(bits)):016x}'
        return meta, 'pending'
    except Exception as e:
        meta['read_error'] = f'{type(e).__name__}: {e}'
        return meta, 'unsupported' if 'HEIF requires' in str(e) else 'unreadable'

def exiftool_metadata(path):
    """Optional explicit diagnostic/fallback; never modifies an original."""
    executable = shutil.which('exiftool')
    if not executable:
        raise RuntimeError('ExifTool not installed')
    r = subprocess.run([executable, '-j', '-n', '-GPSLatitude', '-GPSLongitude', '-GPSHPositioningError',
                        '-DateTimeOriginal', '-OffsetTimeOriginal', str(path)], capture_output=True, timeout=30, check=True)
    return json.loads(r.stdout)[0]

def prepare(path, long_side, rotation=0):
    import io
    with open_image(path) as im:
        rgb = ImageOps.exif_transpose(im).convert('RGB')
        if rotation:
            rgb = rgb.rotate(-rotation, expand=True)
        rgb.thumbnail((long_side, long_side), Image.Resampling.LANCZOS)
        clean = Image.new('RGB', rgb.size)
        clean.paste(rgb)
        out = io.BytesIO()
        clean.save(out, format='JPEG', quality=92)
        return out.getvalue()
