# Calva'do — Tableau de bord hydrologique multi cours d'eau

Dashboard statique (HTML/JS) qui visualise les données de plusieurs cours d'eau de Normandie récupérées depuis les API [Hub'Eau](https://hubeau.eaufrance.fr/), avec un **sélecteur de cours d'eau** :

- **Orne** (fleuve côtier, dépts 61 & 14)
- **Odon** (rivière du Calvados, affluent de l'Orne)

Pour chaque cours d'eau, deux familles de métriques :

- **Hydrométrie** — hauteur d'eau max journalière (HIXnJ) + débit moyen journalier (QmnJ)
- **Qualité physico-chimique** — O₂, pH, nitrates, nitrites, ammonium

## Prérequis

- Python 3 (stdlib uniquement, aucune dépendance à installer)
- Connexion internet (uniquement pour rafraîchir le cache)

## Architecture

```
.
├── index.html                  # interface (Chart.js via CDN) — sélecteur de cours d'eau
├── config/
│   └── rivers.json             # manifeste des cours d'eau (source de vérité)
├── scripts/
│   ├── fetch_hydro_data.py     # ETL hydrométrie  → data_cache/<river>/
│   └── fetch_quality_data.py   # ETL qualité      → data_cache/<river>/
├── data_cache/
│   ├── orne/                   # JSON consommés par le dashboard (Orne)
│   └── odon/                   # JSON consommés par le dashboard (Odon)
└── .github/workflows/deploy.yml  # déploiement GitHub Pages
```

Le fichier **`config/rivers.json`** décrit chaque cours d'eau (id, nom, code SANDRE
qualité, liste des stations hydrométriques, et narratif d'analyse + sources). Il est
lu **à la fois** par le dashboard (sélecteur + textes d'analyse) et par les scripts Python.
Pour ajouter un nouveau cours d'eau, il suffit d'ajouter une entrée dans ce fichier puis
de lancer les scripts de fetch.

## 1. Rafraîchir les données (manuel)

Les dossiers `data_cache/<river>/` contiennent déjà des JSON. Pour les mettre à jour :

```bash
python3 scripts/fetch_hydro_data.py              # hydrométrie, tous les cours d'eau
python3 scripts/fetch_quality_data.py            # qualité, tous les cours d'eau
```

Options utiles :

```bash
python3 scripts/fetch_hydro_data.py --river odon            # un seul cours d'eau
python3 scripts/fetch_hydro_data.py --station I362101001    # une seule station
python3 scripts/fetch_hydro_data.py --since 2024-01-01      # incrémental depuis une date
python3 scripts/fetch_quality_data.py --river odon --discover  # lister les stations qualité
```

Après un fetch, **commitez les JSON modifiés** : c'est l'état de `data_cache/` qui est
servi par le site (pas d'automatisation côté serveur).

Le bouton **« Actualiser »** du dashboard récupère les données en direct depuis l'API
dans le navigateur et **télécharge** des fichiers JSON ; déposez-les ensuite dans
`data_cache/<river>/` puis commitez.

## 2. Lancer le dashboard en local

Le dashboard charge ses données via `fetch('data_cache/...')`, bloqué par CORS en `file://`.
Servir le dossier en HTTP local :

```bash
python3 -m http.server 8000
```

Puis ouvrir : <http://localhost:8000/>

## 3. Déploiement GitHub Pages

Le site est **100 % statique** (HTML + JS + JSON commités). Un workflow GitHub Actions
(`.github/workflows/deploy.yml`) publie le dépôt sur Pages à chaque push sur `main`.

Mise en route une fois le dépôt poussé sur GitHub :

1. **Settings → Pages → Build and deployment → Source : GitHub Actions**.
2. Pousser sur `main` (ou lancer le workflow manuellement via *Actions → Deploy to GitHub Pages → Run workflow*).
3. Le site est publié sur `https://<utilisateur>.github.io/<dépôt>/`.

Le fichier `.nojekyll` à la racine évite que Pages ne traite le dépôt avec Jekyll.

## Sources de données

Toutes les mesures proviennent du portail public **[Hub'Eau](https://hubeau.eaufrance.fr/)**
(Office français de la biodiversité / SANDRE), API v2, accès libre sans clé.

### Hydrométrie — `scripts/fetch_hydro_data.py`

- **API** : [Hydrométrie v2](https://hubeau.eaufrance.fr/page/api-hydrometrie) — endpoint `/api/v2/hydrometrie/obs_elab`
- **Grandeurs** (codes SANDRE) : `HIXnJ` (hauteur max journalière, mm), `QmnJ` (débit moyen journalier, L/s)
- **Stations** : déclarées par cours d'eau dans `config/rivers.json`

### Qualité physico-chimique — `scripts/fetch_quality_data.py`

- **API** : [Qualité des cours d'eau v2](https://hubeau.eaufrance.fr/page/api-qualite-cours-deau) — endpoints `/station_pc` et `/analyse_pc`
- **Producteur** : réseaux DCE (Agences de l'eau, DREAL, OFB) via [SANDRE](https://www.sandre.eaufrance.fr/) et [Naïades](https://naiades.eaufrance.fr/)
- **Sélection** : découverte automatique des stations sur le `quality_code` SANDRE du cours d'eau, top 3 par nombre d'analyses
- **5 paramètres** (codes SANDRE) : 1311 Oxygène dissous, 1302 pH, 1340 Nitrates, 1339 Nitrites, 1335 Ammonium

### Cours d'eau suivis

| id   | Nom  | Code SANDRE qualité | Stations hydro |
|------|------|---------------------|----------------|
| orne | Orne | `I2--0200`          | 9 (dépts 61 & 14) |
| odon | Odon | `I26-0400`          | 2 (Épinay-sur-Odon depuis 1991, Gavrus depuis 2019) |

### Bibliothèques front (via CDN)

- [Chart.js 4.4.7](https://www.chartjs.org/)
- Google Fonts — DM Serif Display, IBM Plex Sans, IBM Plex Mono

### Conditions d'usage

Données publiques sous **[Licence Ouverte Etalab 2.0](https://www.etalab.gouv.fr/licence-ouverte-open-licence)** — réutilisation libre avec mention de la source (Hub'Eau / OFB).


