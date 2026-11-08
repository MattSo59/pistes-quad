# Pistes Quad & SSV

Appli web (PWA) pour tracer des itinéraires quad / SSV sur les chemins autorisés autour de Fourmies.

- `site/` : l'appli (index.html, service worker, manifest, icônes)
- `tools/build_data.py` : construit `site/data/` à partir des extraits OpenStreetMap de Geofabrik
- `.github/workflows/publier.yml` : chaque mois (et à chaque modification), GitHub télécharge les données OSM
  (Nord-Pas-de-Calais, Picardie, Champagne-Ardenne), découpe la zone Avesnois / Thiérache, génère les
  tuiles et publie le tout sur GitHub Pages.

Dans la zone couverte, l'appli lit ses propres données : plus besoin des serveurs Overpass publics.
Hors zone, elle les utilise encore.

## Mise en route
1. Settings → Pages → Source : **GitHub Actions**.
2. Actions → « Données et publication » → **Run workflow** (≈ 5 min).
3. L'appli est en ligne sur `https://<compte>.github.io/<dépôt>/`.

Agrandir la zone : modifier `BBOX` dans `.github/workflows/publier.yml` (ouest,sud,est,nord).

Données © contributeurs OpenStreetMap (ODbL) · Cartes © IGN Géoplateforme.
