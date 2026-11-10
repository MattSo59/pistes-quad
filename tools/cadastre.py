"""Vérification des chemins par le cadastre (Etalab, parcelles par commune).

Principe : un chemin rural n'est en général pas une parcelle numérotée ; il apparaît comme une
bande vide entre les parcelles. Un chemin dessiné à l'intérieur d'une parcelle est probablement
privé (chemin d'exploitation). Chaque chemin est échantillonné tous les ~15 m :
  - « libre »    : ≤ 15 % des points nettement dans une parcelle
  - « parcelle » : ≥ 60 % des points nettement dans une parcelle (à plus de 4 m de son bord)
  - « mixte »    : entre les deux (chemin en limite de parcelles, tracé OSM imprécis…)
"""
import gzip
import json
import math
import os
import urllib.request
from concurrent.futures import ThreadPoolExecutor

GEO_API = "https://geo.api.gouv.fr/departements/{d}/communes?fields=code,centre&format=json"
CAD_URL = "https://cadastre.data.gouv.fr/data/etalab-cadastre/latest/geojson/communes/{d}/{c}/cadastre-{c}-parcelles.json.gz"
UA = {"User-Agent": "pistes-quad-build/1.0 (github.com/MattSo59/pistes-quad)"}


def _get(url, timeout=120):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


_COMMUNES = {}


def communes_list(depts):
    """[(dept, code, lat, lon)] de toutes les communes des départements (une seule requête par département)."""
    out = []
    for d in depts:
        if d not in _COMMUNES:
            _COMMUNES[d] = [(d, c["code"], c["centre"]["coordinates"][1], c["centre"]["coordinates"][0])
                            for c in json.loads(_get(GEO_API.format(d=d))) if c.get("centre")]
        out.extend(_COMMUNES[d])
    return out


def communes_in_bbox(depts, s, w, n, e, margin=0.08):
    return [(d, c) for d, c, lat, lon in communes_list(depts)
            if s - margin <= lat <= n + margin and w - margin <= lon <= e + margin]


def download(communes, cache_dir):
    os.makedirs(cache_dir, exist_ok=True)

    def one(dc):
        d, c = dc
        path = os.path.join(cache_dir, f"{c}.json.gz")
        if not os.path.exists(path):
            try:
                data = _get(CAD_URL.format(d=d, c=c))
                with open(path, "wb") as f:
                    f.write(data)
            except Exception as ex:  # commune absente ou serveur indisponible : on continue
                print("cadastre indisponible pour", c, ex)
                return None
        return path

    with ThreadPoolExecutor(8) as ex:
        return [p for p in ex.map(one, communes) if p]


def load_parcels(paths):
    from shapely.geometry import shape
    polys = []
    for p in paths:
        with gzip.open(p, "rt", encoding="utf-8") as f:
            for feat in json.load(f).get("features", []):
                try:
                    g = shape(feat["geometry"])
                    if not g.is_empty:
                        polys.append(g)
                except Exception:
                    pass
    return polys


def _project(lat, lon, lat0):
    # projection locale en mètres (suffisante à l'échelle d'un chemin)
    return (lon * 111320.0 * math.cos(math.radians(lat0)), lat * 110540.0)


def sample_line(coords, step=15.0):
    """coords [(lat, lon)] -> points tous les `step` mètres environ (lat, lon)."""
    out = [coords[0]]
    for (a0, b0), (a1, b1) in zip(coords, coords[1:]):
        d = math.hypot((a1 - a0) * 110540.0, (b1 - b0) * 111320.0 * math.cos(math.radians(a0)))
        n = max(1, int(d // step))
        for k in range(1, n + 1):
            t = k / n
            out.append((a0 + (a1 - a0) * t, b0 + (b1 - b0) * t))
    return out


def classify(ways_coords, polys, inner=4.0):
    """ways_coords {id: [(lat, lon), ...]} -> {id: 'libre'|'parcelle'|'mixte'}"""
    import numpy as np
    import shapely
    if not polys or not ways_coords:
        return {}
    lat0 = sum(c[0][0] for c in ways_coords.values()) / len(ways_coords)
    # parcelles projetées en mètres
    kx = 111320.0 * math.cos(math.radians(lat0))
    P = shapely.transform(np.array(polys, dtype=object), lambda xy: np.column_stack((xy[:, 0] * kx, xy[:, 1] * 110540.0)))
    tree = shapely.STRtree(P)
    ids, xs, ys = [], [], []
    for wid, cs in ways_coords.items():
        for la, lo in sample_line(cs):
            x, y = _project(la, lo, lat0)
            ids.append(wid); xs.append(x); ys.append(y)
    pts = shapely.points(np.array(xs), np.array(ys))
    pi, gi = tree.query(pts, predicate="within")
    deep = np.zeros(len(pts), dtype=bool)
    if len(pi):
        bounds = shapely.boundary(P[gi])
        dist = shapely.distance(pts[pi], bounds)
        deep[pi[dist > inner]] = True
    total, inside = {}, {}
    for k, wid in enumerate(ids):
        total[wid] = total.get(wid, 0) + 1
        if deep[k]:
            inside[wid] = inside.get(wid, 0) + 1
    out = {}
    for wid, n in total.items():
        f = inside.get(wid, 0) / n
        out[wid] = "parcelle" if f >= 0.6 else ("libre" if f <= 0.15 else "mixte")
    return out


def inside_flags(ways_coords, polys, min_frac=0.5):
    """{id: coords} -> {id: True} pour les chemins dont au moins `min_frac` des points sont dans un polygone."""
    import numpy as np
    import shapely
    if not polys or not ways_coords:
        return {}
    ids, xs, ys = [], [], []
    for wid, cs in ways_coords.items():
        for la, lo in sample_line(cs, 25.0):
            ids.append(wid); xs.append(lo); ys.append(la)
    pts = shapely.points(np.array(xs), np.array(ys))
    tree = shapely.STRtree(np.array(polys, dtype=object))
    pi, _ = tree.query(pts, predicate="within")
    inside = np.zeros(len(pts), dtype=bool)
    inside[pi] = True
    tot, ins = {}, {}
    for k, wid in enumerate(ids):
        tot[wid] = tot.get(wid, 0) + 1
        if inside[k]:
            ins[wid] = ins.get(wid, 0) + 1
    return {wid: True for wid, n in tot.items() if ins.get(wid, 0) / n >= min_frac}
