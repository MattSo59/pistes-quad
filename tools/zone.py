#!/usr/bin/env python3
"""Fabrique le contour de la zone couverte (réunion de départements) pour « osmium extract -p ».

Usage : zone.py sortie.geojson 59 02 08 80 60
Les contours viennent de l'API officielle geo.api.gouv.fr (contours des communes, réunis par département).
"""
import json
import sys
import urllib.request

URL = "https://geo.api.gouv.fr/departements/{d}/communes?fields=code&format=geojson&geometry=contour"
UA = {"User-Agent": "pistes-quad-build/1.0 (github.com/MattSo59/pistes-quad)"}


def main(out, depts):
    from shapely.geometry import mapping, shape
    from shapely.ops import unary_union
    geoms = []
    for d in depts:
        req = urllib.request.Request(URL.format(d=d), headers=UA)
        with urllib.request.urlopen(req, timeout=300) as r:
            fc = json.loads(r.read())
        n = 0
        for f in fc.get("features", []):
            if f.get("geometry"):
                g = shape(f["geometry"])
                if not g.is_valid:
                    g = g.buffer(0)
                geoms.append(g)
                n += 1
        print(d, ":", n, "communes")
        if not n:
            sys.exit(f"Aucun contour pour le département {d}")
    # petite marge (~400 m) pour ne pas couper les chemins en limite, contour simplifié pour osmium
    zone = unary_union(geoms).buffer(0.004).simplify(0.0008)
    w, s, e, n = zone.bounds
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"type": "Feature", "properties": {"name": "zone"}, "geometry": mapping(zone)}, f)
    print(f"zone : {zone.geom_type}, bbox {w:.3f},{s:.3f},{e:.3f},{n:.3f}")
    print(f"BBOX={w:.3f},{s:.3f},{e:.3f},{n:.3f}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2:])
