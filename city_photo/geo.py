import json
from pathlib import Path
from shapely.geometry import shape, Point
from shapely.ops import transform
from shapely.strtree import STRtree
from pyproj import Transformer
from .config import digest
from .metadata import sha_file

class Geography:
    """EPSG:4326 input; EPSG:32645 (UTM 45N) for distances in Kemerovo."""
    def __init__(self, cfg):
        self.cfg = cfg
        self.features = []
        self.project = Transformer.from_crs(4326, 32645, always_xy=True).transform
        fingerprints = []
        for p, default_layer in ((cfg.map_path, None), (cfg.courtyards_path, 'courtyard')):
            if not p:
                continue
            path = Path(p)
            if not path.exists():
                continue
            fingerprints.append(sha_file(path))
            data = json.loads(path.read_text(encoding='utf-8-sig'))
            if data.get('type') != 'FeatureCollection':
                raise ValueError('Map must be GeoJSON FeatureCollection in EPSG:4326')
            for feature in data['features']:
                props = dict(feature.get('properties') or {})
                if default_layer:
                    props['layer'] = default_layer
                geom = shape(feature['geometry'])
                if geom.is_empty or not geom.is_valid:
                    raise ValueError('Invalid GeoJSON geometry; repair map before import')
                self.features.append((transform(self.project, geom), props))
        self.tree = STRtree([g for g, _ in self.features]) if self.features else None
        self.hash = digest([fingerprints, cfg.gps_buffer_m, 'geo-v1-utm45'])

    def locate(self, meta, visual):
        v = visual.get('territory_visual', 'unknown') if visual else 'unknown'
        result = dict(territory_visual=v, territory_geo='unknown', territory_type=v,
                      territory_source='visual' if visual else 'unknown', geo_status='map_unavailable',
                      courtyard_candidate_id=None, courtyard_id=None, courtyard_assignment_status='unknown',
                      playground_courtyard_link_status='unknown', parking_courtyard_link_status='unknown',
                      geo_review_reasons=[], map_hash=self.hash)
        if meta.get('latitude') is None or meta.get('longitude') is None:
            result['geo_status'] = 'gps_missing' if self.tree else 'map_unavailable'
            return result
        if not self.tree:
            return result
        lat, lon = meta['latitude'], meta['longitude']
        # Outside projection's intended city region: do not choose nearest city object.
        if not (50 < lat < 60 and 80 < lon < 95):
            result.update(geo_status='outside_region', geo_review_reasons=['outside_city_region'])
            return result
        p = transform(self.project, Point(lon, lat))
        buffer = meta.get('gps_accuracy_m') or self.cfg.gps_buffer_m
        result.update(geo_status='located', gps_buffer_m_used=buffer,
                      gps_buffer_source='exif_accuracy' if meta.get('gps_accuracy_m') else 'configured_assumption')
        boundaries = [g for g, pr in self.features if pr.get('layer') == 'boundary']
        if not boundaries:
            result['geo_review_reasons'].append('city_boundary_unavailable')
        elif not any(g.covers(p) for g in boundaries):
            result.update(geo_status='outside_city')
            result['geo_review_reasons'].append('outside_city')
            return result
        if any(g.boundary.distance(p) <= buffer for g in boundaries):
            result['geo_review_reasons'].append('near_city_boundary')
        candidates, courtyards = set(), []
        for i in self.tree.query(p.buffer(buffer)):
            g, pr = self.features[int(i)]
            layer = pr.get('layer')
            distance = g.distance(p)
            if distance > buffer:
                continue
            if layer == 'courtyard':
                courtyards.append(str(pr.get('courtyard_id') or pr.get('id') or f'feature-{i}'))
                candidates.add('courtyard')
            if layer in ('park', 'pedestrian', 'road'):
                candidates.add({'park': 'park_square', 'pedestrian': 'boulevard', 'road': 'street'}[layer])
            if layer not in ('boundary', 'building') and g.geom_type in ('Polygon', 'MultiPolygon') and g.boundary.distance(p) <= buffer:
                result['geo_review_reasons'].append('near_feature_boundary')
        if len(candidates) == 1:
            result['territory_geo'] = next(iter(candidates))
        elif candidates:
            result['territory_geo'] = 'mixed'
        if courtyards:
            result['courtyard_candidate_id'] = '|'.join(sorted(set(courtyards)))
            result['courtyard_assignment_status'] = 'candidate'
            result['geo_review_reasons'].append('courtyard_requires_manual_confirmation_camera_point_only')
            for obj in ('playground', 'parking'):
                if visual and visual['objects'][obj]['present']:
                    result[f'{obj}_courtyard_link_status'] = 'candidate'
        geo = result['territory_geo']
        if geo not in ('unknown', v):
            result['geo_review_reasons'].append('visual_geo_conflict_or_ambiguity')
        if geo == v and v != 'unknown':
            result['territory_source'] = 'visual_geo_agree_camera_context_only'
        return result

def import_map(source, destination, attribution, source_url, license_name):
    import shutil
    from .storage import now
    src, dst = Path(source).resolve(), Path(destination).resolve()
    data = json.loads(src.read_text(encoding='utf-8-sig'))
    if data.get('type') != 'FeatureCollection':
        raise ValueError('Expected GeoJSON FeatureCollection')
    for f in data['features']:
        if not shape(f['geometry']).is_valid:
            raise ValueError('Invalid map geometry')
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src != dst:
        shutil.copyfile(src, dst)
    dst.with_suffix('.provenance.json').write_text(json.dumps(dict(
        imported_at=now(), source=source_url, attribution=attribution, license=license_name,
        sha256=sha_file(dst), crs='EPSG:4326'), ensure_ascii=False, indent=2), encoding='utf-8')
    return str(dst)
