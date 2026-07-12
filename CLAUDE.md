# CLAUDE.md

Guide pour les agents (Claude Code) travaillant sur ce dépôt.

## Quoi

Tableau de bord **statique** (HTML/CSS/JS, aucun build) visualisant des données
hydrologiques et de qualité de l'eau de cours d'eau de Normandie, depuis les API
publiques [Hub'Eau](https://hubeau.eaufrance.fr/) (OFB / SANDRE, accès libre **sans clé**).
Multi cours d'eau via un **sélecteur** ; piloté par un fichier de configuration unique.

## Architecture (l'essentiel)

```
index.html            Dashboard mono-fichier (Chart.js via CDN). Tout le JS est inline.
config/rivers.json    SOURCE DE VÉRITÉ — lue par le dashboard ET les scripts Python.
scripts/              ETL Python (stdlib uniquement, pas de dépendances).
data_cache/<river>/   JSON par cours d'eau, VERSIONNÉS (= données servies par le site).
.github/workflows/    deploy.yml — déploiement GitHub Pages statique (pas d'ETL).
```

### `config/rivers.json` — le pivot

Chaque cours d'eau y déclare : `id`, `name`, `region_label_by_dept`, `quality_code`
(code SANDRE rivière pour la qualité), `stations` (hydrométrie), et `narrative`
(textes d'analyse + sources, **propres à chaque rivière**, affichés tels quels).

- Le **dashboard** lit ce fichier pour : peupler le sélecteur, résoudre les chemins
  `data_cache/<id>/…`, et injecter les textes d'analyse (`narrative.*`).
- Les **scripts** le lisent pour connaître stations et `quality_code` par rivière.

### Flux de données

`scripts/fetch_*.py` → écrivent `data_cache/<id>/{stations.json, quality_stations.json,
<code>_HIXnJ.json, <code>_QmnJ.json, <code>_quality.json}` → le dashboard les `fetch()`.

Grandeurs hydro : `HIXnJ` (hauteur max journalière, mm), `QmnJ` (débit moyen journalier, L/s).
Qualité (5 codes SANDRE) : 1311 O₂, 1302 pH, 1340 nitrates, 1339 nitrites, 1335 ammonium.

## Commandes

```bash
# Récupérer / mettre à jour les données (manuel, puis committer les JSON)
python3 scripts/fetch_hydro_data.py [--river odon] [--station CODE] [--since YYYY-MM-DD]
python3 scripts/fetch_quality_data.py [--river odon] [--discover] [--since YYYY-MM-DD]

# Lancer le dashboard en local (CORS interdit le file://)
python3 -m http.server 8000   # puis http://localhost:8000/
```

## Ajouter un nouveau cours d'eau

1. Trouver le code SANDRE qualité et les stations hydro via l'API Hub'Eau
   (`/api/v2/hydrometrie/referentiel/stations?libelle_cours_eau=…`,
   `/api/v2/qualite_rivieres/station_pc?nom_cours_eau=…`).
2. Ajouter une entrée dans `config/rivers.json` (stations + `quality_code` + `narrative`).
3. `python3 scripts/fetch_hydro_data.py --river <id>` puis `fetch_quality_data.py --river <id>`.
4. Committer `config/rivers.json` + `data_cache/<id>/`.

## Intégrité des données (invariants à préserver)

`config/rivers.json` ↔ `data_cache/<id>/` ↔ dashboard forment un **contrat implicite** : le
dashboard ne valide rien à l'exécution. Un fichier manquant ou mal formé = graphe **vide et
silencieux** (les `fetch()` renvoient `null`, aucune erreur visible). À garder vrai à chaque modif :

- **`id` = nom du dossier** `data_cache/<id>/` (tous les chemins passent par `riverDataPath`).
- **Chaque station hydro a un `<code>_HIXnJ.json`** ; `has_Q: true` ⇒ aussi `<code>_QmnJ.json`,
  `has_Q: false` ⇒ **pas** de QmnJ (le dashboard saute la grandeur). Invariant tenu aujourd'hui.
- **`region_label_by_dept` couvre chaque `dept`** listé dans `stations` (sinon bandeau région vide).
- **Qualité** : `quality_stations.json` + un `<code>_quality.json` par station top-3, contenant
  les 5 paramètres SANDRE `1311 / 1302 / 1340 / 1339 / 1335`.
- **Clés `narrative` lues par le dashboard** : `heightTrendNote`, `flowTrendNote`, `summerNote`,
  `projectionInsight.{value,detail}`, `contextParagraph`, `projectionsParagraph`, `sources[].{label,url}`.
  Une clé absente dégrade en silence (texte vide), pas d'erreur → à relire à l'œil.
- **Format JSON** : UTF-8, compact (`separators=(",",":")`), `date` en `YYYY-MM-DD` — triable
  lexicographiquement, dont dépendent l'incrémental des scripts et les agrégations du dashboard.

## Valider avant de committer

Sans aucune dépendance (stdlib + outils déjà présents) :

```bash
# 1. Syntaxe JSON de toute la config + tous les caches
find config data_cache -name '*.json' -print0 | xargs -0 -I{} python3 -m json.tool {} > /dev/null

# 2. Aucun chemin data_cache/… en dur réintroduit dans index.html (doit matcher uniquement riverDataPath)
grep -n "data_cache/" index.html

# 3. Servir en local et vérifier la console SANS erreur (un cache manquant = graphe vide silencieux)
python3 -m http.server 8000
```

Cohérence `rivers.json` ↔ `data_cache/` (id = dossier, HIXnJ par station, `has_Q` ⇒ QmnJ, 5 codes
qualité) : pas de script dédié pour l'instant — vérifier à la main, ou l'automatiser (cf. CI ci-dessous).

## Conventions / contraintes

- **Pas de build, pas de framework, pas de dépendance** : HTML/JS vanilla, Python stdlib.
  Ne pas introduire npm/bundler/venv sans raison forte.
- Le JS du dashboard construit le DOM via `createEl(...)` (pas d'`innerHTML` avec données).
  Garder ce pattern (sécurité XSS).
- La logique d'analyse **calculée** (tendances, percentiles, bandes climato) reste
  **générique** ; tout texte spécifique à une rivière va dans `narrative` de `rivers.json`,
  jamais codé en dur dans `index.html`.
- `data_cache/` est **volontairement versionné** (données statiques du site) — ne pas l'ignorer.
- Toutes les lectures de données passent par `riverDataPath(file)` ; ne pas réintroduire
  de chemin `data_cache/...` en dur dans les `fetch()`.

## Déploiement & CI (GitHub Pages)

- Site 100 % statique, publié par `.github/workflows/deploy.yml` à chaque push sur `main`.
- **Pré-requis manuel une fois** : *Settings → Pages → Source : GitHub Actions* (sinon
  `Get Pages site failed / Not Found`), et *Workflow permissions : Read and write*.
- Mise à jour des données = **manuelle** (lancer les scripts en local + committer) ; il n'y
  a **pas** de cron/ETL côté GitHub Actions, uniquement du déploiement.
- **Gate qualité recommandé (pas encore en place)** : avant le déploiement, faire échouer le
  build si un JSON ne parse pas ou si `rivers.json` ↔ `data_cache/` est incohérent (étapes de
  « Valider avant de committer »). 100 % stdlib, **aucune dépendance ajoutée au site livré**.

## Données & licence

Source unique : Hub'Eau (OFB / SANDRE), API v2. Données publiques sous
**Licence Ouverte Etalab 2.0** (réutilisation libre avec mention de la source).
