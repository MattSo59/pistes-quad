#!/usr/bin/env python3
"""Construit les tuiles de données de l'appli Pistes Quad à partir d'un extrait OSM (.pbf).

Usage : build_data.py zone-filtree.osm.pbf site/data

Produit site/data/<i>_<j>.json (même format que les réponses Overpass utilisées par l'appli)
et site/data/index.json. La grille (0,08° x 0,12°) est identique à celle de index.html.
"""
import json
import math
import os
import re
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from collections import defaultdict
from datetime import datetime, timezone

TLAT, TLON = 0.08, 0.12
HIGHWAY = re.compile(r'^(track|unclassified|tertiary|tertiary_link|secondary|secondary_link|primary|primary_link'
                     r'|residential|living_street|road|path|bridleway|trunk|trunk_link|motorway)$')
DOM = re.compile(r'domaniale', re.I)
ONF = re.compile(r'ONF|Office national des for', re.I)


def tile_key(lat, lon):
    return f"{math.floor(lat / TLAT)}_{math.floor(lon / TLON)}"


def tiles_for_box(s, w, n, e):
    out = []
    for i in range(math.floor(s / TLAT), math.floor(n / TLAT) + 1):
        for j in range(math.floor(w / TLON), math.floor(e / TLON) + 1):
            out.append(f"{i}_{j}")
    return out


def is_forest(t):
    if 'highway' in t:
        return False
    if t.get('landuse') == 'forest' and (DOM.search(t.get('name', '')) or ONF.search(t.get('operator', ''))):
        return True
    if t.get('boundary') == 'protected_area' and DOM.search(t.get('name', '')):
        return True
    return False


def r7(x):
    return round(x, 7)


class Tiler:
    """Répartit les éléments dans les tuiles (logique indépendante d'osmium, testable)."""

    def __init__(self):
        self.tiles = defaultdict(list)
        self.counts = defaultdict(int)
        self.tracks = {}  # chemins à vérifier au cadastre : id -> (élément, coordonnées)

    def add_way(self, wid, tags, node_ids, coords):
        if len(coords) < 2:
            return
        el = {"type": "way", "id": wid, "tags": tags, "nodes": node_ids,
              "geometry": [{"lat": r7(a), "lon": r7(b)} for a, b in coords]}
        for k in {tile_key(a, b) for a, b in coords}:
            self.tiles[k].append(el)
        self.counts['ways'] += 1
        if tags.get('highway') in ('track', 'unclassified', 'path', 'bridleway'):
            self.tracks[wid] = (el, coords)

    def apply_cadastre(self, result):
        for wid, label in result.items():
            if wid in self.tracks:
                self.tracks[wid][0]['tags']['_cad'] = label
                self.counts['cad_' + label] += 1

    def add_barrier(self, nid, tags, lat, lon):
        self.tiles[tile_key(lat, lon)].append({"type": "node", "id": nid, "lat": r7(lat), "lon": r7(lon), "tags": tags})
        self.counts['barriers'] += 1

    def add_forest(self, el, lines):
        pts = [p for l in lines for p in l]
        if not pts:
            return
        s, n = min(p[0] for p in pts), max(p[0] for p in pts)
        w, e = min(p[1] for p in pts), max(p[1] for p in pts)
        for k in tiles_for_box(s, w, n, e):
            self.tiles[k].append(el)
        self.counts['forests'] += 1

    def write(self, outdir, bbox_keys=None):
        os.makedirs(outdir, exist_ok=True)
        keys = sorted(k for k in self.tiles if bbox_keys is None or k in bbox_keys)
        total = 0
        for k in keys:
            path = os.path.join(outdir, k + '.json')
            with open(path, 'w', encoding='utf-8') as f:
                json.dump({"elements": self.tiles[k]}, f, ensure_ascii=False, separators=(',', ':'))
            total += os.path.getsize(path)
        idx = {"date": datetime.now(timezone.utc).isoformat(timespec='seconds'), "keys": keys,
               "source": "© contributeurs OpenStreetMap, ODbL", "counts": dict(self.counts)}
        with open(os.path.join(outdir, 'index.json'), 'w', encoding='utf-8') as f:
            json.dump(idx, f, ensure_ascii=False)
        return keys, total


# Catégories de points d'intérêt : ajouter une ligne ici (et le filtre osmium du workflow) pour en créer une autre
POI_CATS = {
    'fuel': lambda t: t.get('amenity') == 'fuel',
}
POI_KEEP = {'name', 'brand', 'operator', 'opening_hours', 'self_service', 'automated', 'phone', 'website',
            'addr:street', 'addr:housenumber', 'addr:city', 'access'}


def main(pbf, outdir):
    import osmium  # pyosmium

    # Passe 1 : relations « forêt domaniale » et ways membres à récupérer
    class RelPass(osmium.SimpleHandler):
        def __init__(self):
            super().__init__()
            self.rels = []
            self.need = set()

        def relation(self, r):
            t = {x.k: x.v for x in r.tags}
            if is_forest(t):
                mem = [(m.ref, m.role) for m in r.members if m.type == 'w']
                self.rels.append((r.id, t, mem))
                self.need.update(ref for ref, _ in mem)

    rp = RelPass()
    rp.apply_file(pbf)

    tiler = Tiler()

    # Points d'intérêt (POI) : un seul petit fichier pois.json pour toute la zone
    pois = {k: [] for k in POI_CATS}

    def add_poi(t, lat, lon, oid):
        for cat, test in POI_CATS.items():
            if test(t):
                keep = {k: v for k, v in t.items() if k in POI_KEEP or k.startswith('fuel:')}
                pois[cat].append({"id": oid, "lat": r7(lat), "lon": r7(lon), "tags": keep})

    # Passe 2 : chemins, barrières, forêts (avec coordonnées)
    wkb = osmium.geom.WKBFactory()

    class MainPass(osmium.SimpleHandler):
        def __init__(self):
            super().__init__()
            self.member_geom = {}
            self.woods = []

        def area(self, a):
            # tous les bois et forêts (pour repérer les chemins forestiers)
            if a.tags.get('landuse') == 'forest' or a.tags.get('natural') == 'wood':
                try:
                    self.woods.append(wkb.create_multipolygon(a))
                except Exception:
                    pass

        def node(self, n):
            if not n.location.valid():
                return
            if 'barrier' in n.tags:
                tiler.add_barrier(n.id, {x.k: x.v for x in n.tags}, n.location.lat, n.location.lon)
            if 'amenity' in n.tags:
                add_poi({x.k: x.v for x in n.tags}, n.location.lat, n.location.lon, 'n%d' % n.id)

        def way(self, w):
            ids, coords = [], []
            for nd in w.nodes:
                if nd.location.valid():
                    ids.append(nd.ref)
                    coords.append((nd.location.lat, nd.location.lon))
            if w.id in rp.need:
                self.member_geom[w.id] = coords
            if 'amenity' in w.tags and coords:
                add_poi({x.k: x.v for x in w.tags}, sum(c[0] for c in coords) / len(coords),
                        sum(c[1] for c in coords) / len(coords), 'w%d' % w.id)
            hw = w.tags.get('highway')
            if hw and HIGHWAY.match(hw):
                tiler.add_way(w.id, {x.k: x.v for x in w.tags}, ids, coords)
                return
            t = {x.k: x.v for x in w.tags}
            if is_forest(t) and len(coords) > 2:
                tiler.add_forest({"type": "way", "id": w.id, "tags": t,
                                  "geometry": [{"lat": r7(a), "lon": r7(b)} for a, b in coords]}, [coords])

    mp = MainPass()
    mp.apply_file(pbf, locations=True)

    for rid, t, mem in rp.rels:
        members, lines = [], []
        for ref, role in mem:
            g = mp.member_geom.get(ref)
            if g and len(g) > 1:
                members.append({"type": "way", "ref": ref, "role": role,
                                "geometry": [{"lat": r7(a), "lon": r7(b)} for a, b in g]})
                lines.append(g)
        if lines:
            tiler.add_forest({"type": "relation", "id": rid, "tags": t, "members": members}, lines)

    # chemins en forêt / bois
    try:
        import shapely
        import cadastre
        polys = [shapely.from_wkb(bytes.fromhex(h)) for h in mp.woods]
        flags = cadastre.inside_flags({k: v[1] for k, v in tiler.tracks.items()}, polys)
        for wid in flags:
            tiler.tracks[wid][0]['tags']['_bois'] = '1'
        tiler.counts['en_bois'] = len(flags)
        print(len(polys), 'bois/forêts,', len(flags), 'chemins en forêt')
    except Exception as ex:
        print('::warning::Repérage des bois impossible :', repr(ex)[:300])

    depts = os.environ.get('CADASTRE_DEPTS', '').split()
    bbox = os.environ.get('BBOX')  # ouest,sud,est,nord
    if depts and bbox and tiler.tracks:
        import cadastre
        w, s_, e, n = map(float, bbox.split(','))
        try:
            com = cadastre.communes_in_bbox(depts, s_, w, n, e)
            print(len(com), 'communes au cadastre')
            paths = cadastre.download(com, os.environ.get('CADASTRE_CACHE', 'cadastre'))
            polys = cadastre.load_parcels(paths)
            print(len(polys), 'parcelles,', len(tiler.tracks), 'chemins à vérifier')
            tiler.apply_cadastre(cadastre.classify({k: v[1] for k, v in tiler.tracks.items()}, polys))
        except Exception as ex:  # le cadastre est un plus : on publie quand même sans lui
            print('::warning::Vérification cadastre impossible :', repr(ex)[:300])

    keys, total = tiler.write(outdir)
    with open(os.path.join(outdir, 'pois.json'), 'w', encoding='utf-8') as f:
        json.dump({"date": datetime.now(timezone.utc).isoformat(timespec='seconds'), "pois": pois},
                  f, ensure_ascii=False, separators=(',', ':'))
    print('::notice::POI : ' + ', '.join(f'{k} {len(v)}' for k, v in pois.items()))
    print(f"::notice::{len(keys)} tuiles, {total / 1e6:.1f} Mo, {dict(tiler.counts)}")
    if not keys:
        sys.exit("Aucune donnée produite : vérifier l'extrait OSM")


if __name__ == '__main__':
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
