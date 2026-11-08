# Pistes Quad & SSV – fiche projet

À donner à Claude au début d'une nouvelle conversation (ou à mettre dans les connaissances d'un projet claude.ai).

## En bref
- Appli web (PWA) pour créer des itinéraires quad / SSV sur chemins autorisés autour de Fourmies (Sud-Avesnois).
- En ligne : https://mattso59.github.io/pistes-quad/ (installable sur iPhone, Android, PC).
- Code : dépôt GitHub public `MattSo59/pistes-quad` (branche `main`). Toute modification poussée est publiée automatiquement (GitHub Actions → GitHub Pages, ~4 min).
- Version actuelle : v8.1 (affichée en bas de l'onglet Aide).
- Règle convenue : **mettre à jour le guide PDF et la présentation de démarrage à chaque changement, sans demander.**

## Organisation du dépôt
- `site/index.html` : toute l'appli (HTML + CSS + JS, Leaflet 1.9.4 via unpkg).
- `site/sw.js` : service worker (cache hors-ligne). Incrémenter `pq-shell-vN` à chaque publication.
- `site/guide.pdf` : guide express 2 pages (source HTML gardée hors dépôt, à régénérer avec Chrome headless).
- `tools/build_data.py` : génère `site/data/*.json` (tuiles 0,08° × 0,12°) depuis les extraits OSM Geofabrik.
- `tools/cadastre.py` : vérification cadastre Etalab (59, 02, 08) + repérage des chemins en forêt/bois.
- `.github/workflows/publier.yml` : téléchargement OSM (Nord-Pas-de-Calais, Picardie, Champagne-Ardenne), zone `3.55,49.70,4.55,50.35`, génération, publication. Relancé chaque 1er du mois.

## Classement des chemins (ordre de priorité)
1. Notes de l'utilisateur (✓ vérifié = cyan, ⛔ = interdit) – stockées sur l'appareil.
2. Tags OSM (`atv`, `motorcar`, `motor_vehicle`, `vehicle`, `access`, conditionnels).
3. Cadastre : hors parcelles → vert « ouvert » ; dans une parcelle → rose « privé probable » ; limite → inchangé.
4. Forêt domaniale (ONF) → violet ; bois/forêt sans preuve d'accès (`_bois`) → orange pointillé, exclu par défaut.
5. Voisinage : chemin vert qui ne débouche que sur un interdit → rose (propagé) ; si « ouvert », pénalisé.
Catégories utilisées par défaut dans les tracés : vérifié, ouvert, sans restriction connue, routes (liaison).

## Calcul des itinéraires
- A* sur graphe des chemins autorisés ; routes ×3 en génération ; points de passage accrochés seulement sur chemins verts traversants.
- Génération de boucle : jusqu'à 45 essais (3 à 5 points sur un cercle), score = part de vert + respect de la distance − restreints.
- Tracé figé : chaque étape garde son chemin ; seules les étapes modifiées sont recalculées ; un tronçon devenu interdit est contourné au plus près (patchPath).
- Faux culs-de-sac (< 12 m d'un autre chemin) raccordés ; vrais culs-de-sac écartés des points de passage.
- Points de contrôle Street View à chaque virage (≥ 35° à un carrefour) et entrée de chemin, caméra orientée vers le chemin.

## Fonctions principales
Boucle auto (15–80 km), tracé manuel, tracé coloré par type, points de contrôle + Street View (lien ou intégré avec clé Google Maps Embed API, champ « Carte → Données »), retour automatique au point après Street View, historique automatique (30) + favoris ⭐, affichage des favoris sur la carte, mode Balade (GPS, alerte hors tracé, enregistrement), GPX / OsmAnd (CarPlay), lien de partage, export/import des données, hors-ligne (cartes IGN + chemins), profil altimétrique IGN, guide PDF.

## Historique des décisions
- Hébergement : d'abord Cloudflare (abandonné), la section « mini » du site de gestion bloque tout appel réseau (CSP `connect-src 'none'`), d'où GitHub Pages.
- Serveurs Overpass publics trop saturés → données pré-calculées chaque mois par GitHub (Overpass reste un secours hors zone).
- CarPlay impossible pour une appli web → export GPX vers OsmAnd.
- IA (LLM / analyse Street View) : jugée non utile pour le tracé, écartée par l'utilisateur.
- Dépôt privé + site public = GitHub Pro payant ; alternative gratuite possible via Cloudflare (non faite).

## Limites connues
- Données indicatives : le panneau sur place fait foi (arrêtés municipaux non cartographiés).
- iPhone : GPS coupé écran verrouillé (appli web).
- Belgique non gérée.
