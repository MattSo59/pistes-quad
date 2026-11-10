# Pistes Quad & SSV – fiche projet

À donner à Claude au début d'une nouvelle conversation (ou à mettre dans les connaissances d'un projet claude.ai).

## En bref
- Appli web (PWA) pour créer des itinéraires quad / SSV sur chemins autorisés autour de Fourmies (Sud-Avesnois).
- En ligne : https://mattso59.github.io/pistes-quad/ et https://quad.team-somatcha.fr/ (installables sur iPhone, Android, PC). Connexion avec un compte validé par l'admin.
- Code : dépôt GitHub public `MattSo59/pistes-quad` (branche `main`). Toute modification poussée est publiée automatiquement (GitHub Actions → branche `publication` → Worker Cloudflare, ~5 min).
- Version actuelle : v25 (GPX importé = pseudo-chemin `gpx` repris point par point dans buildGraph (`links` avec `pts`, nœuds virtuels ≤ -1e14), aucun recalcul ; coupe exacte + petit raccord auto ≤ 25 m vers le réseau ; v23 : liaisons à la main `pq_links` : arêtes ajoutées dans buildGraph, synchronisées avec le compte, 600 m max ; v22 : zone étendue à 5 départements, données séparées de l'appli ; v21 : points d'intérêt affichables : stations essence, fichier data/pois.json généré par build_data.py, catégories dans POI_CATS côté outil et côté appli ; v20 : couper le tracé sur la carte ✂, flèches de sens, bouton afficher/masquer le tracé (V), « Ouvrir un GPX pour le modifier », fond IGN 1:25 000 (clé publique ign_scan_ws), Street View en fenêtre à part sur PC, correction des faux carrefours en boucle ; v18 : routes goudronnées affichées par défaut, GPX avec Départ/Arrivée seulement, présentation à jour ; v17 : contrôles automatiques retirés, contrôle à la volée en touchant le tracé, drapeau au vrai bout, pas de grand détour pour éviter un chemin déjà pris ; aucun numéro sur la carte, 📷 = contrôle Street View ; tracé manuel uniquement ; points intermédiaires sans numéro, D et 🏁 seuls ; bouton ✓ direct, « ↩ Annuler », « 🏁 Terminer ici » → GPX CarPlay/OsmAnd, favori, lien) (affichée en bas de l'onglet Aide).
- Règle convenue : **mettre à jour le guide PDF et la présentation de démarrage à chaque changement, sans demander.**

## Hébergement et comptes (v13, 9/11/2026)
- Appli publiée à deux adresses : https://mattso59.github.io/pistes-quad/ (GitHub Pages, dépôt public) et https://quad.team-somatcha.fr/ (Worker Cloudflare `pistes-quad`, branche `publication`). Plus de Cloudflare Access (retiré).
- Comptes maison : écran de connexion à l'ouverture. « Créer un compte » (prénom, e-mail, mot de passe ≥ 8) → compte **en attente** ; l'admin (reconnu par `ADMIN_HASH`, l'empreinte SHA-256 de son e-mail, dans `worker/wrangler.jsonc` ; validé d'office) valide / refuse / supprime dans Tracés → Mon compte → Comptes.
- API dans `worker/worker.js` sur quad.team-somatcha.fr/api (CORS autorisé pour github.io) : register, login (jeton 60 jours), me, logout, password, data, admin/users, admin/user. Mots de passe PBKDF2-SHA256 100 000 itérations + sel ; 10 essais ratés → blocage 15 min.
- KV `DATA` → `pistes-quad-donnees` : `acct:<email>`, `sess:<jeton>`, `data:<email>`, `fail:<email>`.
- Données synchronisées par compte (historique, favoris, notes, sorties, points vus). Hors ligne : l'appli reste utilisable si on s'est connecté une fois sur l'appareil. Déconnexion = données effacées de l'appareil (gardées sur le compte).
- Limite : le code de l'appli et les tuiles OSM restent publics (dépôt public) ; ce sont les données des utilisateurs qui sont privées. Mot de passe oublié : l'admin supprime le compte, la personne se réinscrit.

## Données et publication séparées (10/11/2026)
- Zone couverte : départements 59, 02, 08, 80, 60 entiers (contour = réunion des communes, `tools/zone.py`). 511 tuiles, ~305 Mo, 382 000 voies, 747 stations essence.
- `.github/workflows/donnees.yml` « Cartographie (données) » : le 1er du mois, à la demande, ou si `tools/**` change. ~15 min. Résultat dans la branche `donnees`. Cadastre traité par carreaux de 0,4° × 0,6° (mémoire), téléchargements gardés en cache.
- `.github/workflows/publier.yml` « Publication de l'appli » : à chaque push (hors `tools/**`), ~2 min ; reprend `data/` de la branche `donnees` (à défaut `publication`) et pousse la branche `publication`. Se relance seule après la cartographie.
- Belgique : non couverte (extraits Geofabrik français uniquement, pas de cadastre équivalent, règles différentes).

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
- **Pas de génération automatique** (retirée en v9 à la demande de l'utilisateur : trop d'erreurs, difficile à corriger).
- Construction **carrefour par carrefour** : depuis le bout du tracé, liste des chemins possibles jusqu'au prochain carrefour (direction, type, longueur, Street View orienté vers le chemin), interdits listés en grisé ; toucher un choix ouvre d'abord un **aperçu** (chemin surligné, photo Panoramax si dispo, Street View orienté, ✓ Oui / ✗ Non / ⛔ Panneau) ; « Oui » ajoute l'étape (chemin figé dans legCache). Suivi « Tracé en cours » (étapes, ✂ couper ici) dans l'onglet Tracé, à droite sur PC. Bouton Boucler = retour au départ par A*.
- Toucher la carte plus loin = étape calculée par A* (routes ×2 à ×3, chemins verts favorisés).
- Tracé figé : chaque étape garde son chemin ; seules les étapes modifiées sont recalculées ; un tronçon devenu interdit est contourné au plus près (patchPath).
- Faux culs-de-sac (< 12 m d'un autre chemin) raccordés, y compris au milieu d'un segment.
- Points de contrôle Street View à chaque virage (≥ 35° à un carrefour) et entrée de chemin, caméra orientée vers le chemin ; retour automatique au point après Street View.

## Fonctions principales
Tracé carrefour par carrefour, tracé manuel libre, tracé coloré par type, points de contrôle + Street View (lien ou intégré avec clé Google Maps Embed API, champ « Carte → Données »), retour automatique au point après Street View, historique automatique (30) + favoris ⭐, affichage des favoris sur la carte, mode Balade (GPS, alerte hors tracé, enregistrement), GPX / OsmAnd (CarPlay), lien de partage, export/import des données, hors-ligne (cartes IGN + chemins), profil altimétrique IGN, guide PDF.

## Historique des décisions
- Hébergement : d'abord Cloudflare (abandonné), la section « mini » du site de gestion bloque tout appel réseau (CSP `connect-src 'none'`), d'où GitHub Pages.
- Serveurs Overpass publics trop saturés → données pré-calculées chaque mois par GitHub (Overpass reste un secours hors zone).
- CarPlay impossible pour une appli web → export GPX vers OsmAnd.
- IA (LLM / analyse Street View, détection Mapillary) : écartée par l'utilisateur.
- Clé Google Maps Embed (Street View intégré) : l'utilisateur préfère ne pas l'utiliser (carte bancaire) ; l'appli fonctionne sans.
- Génération automatique de boucles : retirée en v9.
- Dépôt privé + site public = GitHub Pro payant ; alternative gratuite possible via Cloudflare (non faite).

## Limites connues
- Données indicatives : le panneau sur place fait foi (arrêtés municipaux non cartographiés).
- iPhone : GPS coupé écran verrouillé (appli web).
- Belgique non gérée.
