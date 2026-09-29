# CLAUDE.md

Tableau de bord **statique** (HTML/CSS/JS vanilla, aucun build) des données hydrologiques et
de qualité de l'eau de cours d'eau de Normandie, alimenté par les API publiques
[Hub'Eau](https://hubeau.eaufrance.fr/) v2 (OFB / SANDRE, sans clé). Multi-rivières via un
sélecteur, piloté par un fichier de configuration unique. Présentation utilisateur : `README.md`.

## Commandes

```bash
# Données (manuel, puis committer les JSON) — préférer la commande /update-data
python3 scripts/fetch_hydro_data.py   [--river <id>] [--station CODE] [--since YYYY-MM-DD]
python3 scripts/fetch_quality_data.py [--river <id>] [--discover]     [--since YYYY-MM-DD]

# Dashboard en local (file:// est bloqué par CORS)
python3 -m http.server 8000   # → http://localhost:8000/
```

## Carte du dépôt

```
index.html            Dashboard mono-fichier, JS inline, Chart.js 4.4.7 épinglé via CDN jsDelivr.
config/rivers.json    SOURCE DE VÉRITÉ — lue par le dashboard ET les scripts Python.
scripts/fetch_*.py    ETL Python stdlib → écrit data_cache/<id>/.
data_cache/<id>/      JSON par rivière, VERSIONNÉS (ce sont les données servies par le site).
.claude/commands/     /update-data : fetch → validation → revue du diff → commit (sans push).
.github/workflows/    deploy.yml — publication GitHub Pages à chaque push sur main (aucun ETL).
TODO.md               Backlog priorisé (gate d'intégrité CI, écriture atomique, état « pas de données »).
```

Flux : `scripts/fetch_*.py` → `data_cache/<id>/{stations.json, quality_stations.json,
<code>_HIXnJ.json, <code>_QmnJ.json, <code>_quality.json}` → `fetch()` du dashboard.

Vocabulaire métier : `HIXnJ` = hauteur max journalière (mm) ; `QmnJ` = débit moyen journalier
(L/s) ; qualité = 5 paramètres SANDRE : `1311` O₂, `1302` pH, `1340` nitrates, `1339` nitrites,
`1335` ammonium.

`config/rivers.json` déclare par rivière : `id`, `name`, `region_label_by_dept`,
`quality_code` (code SANDRE rivière), `stations` (hydrométrie, `has_Q`), `narrative` (textes
d'analyse + sources propres à la rivière, affichés tels quels).

## Règles impératives

- **IMPORTANT — ne jamais `git push`** : un push sur `main` déploie en production. Proposer la
  commande et laisser l'utilisateur décider.
- **Ne jamais committer des données partielles** : si un appel Hub'Eau échoue, s'arrêter et le
  signaler.
- **Zéro dépendance** : pas de npm/bundler/venv/pip. HTML/JS vanilla + Python stdlib uniquement.
- **DOM via `createEl(...)`**, jamais `innerHTML` avec des données (XSS).
- **Toute lecture de données passe par `riverDataPath(file)`** avec `{ cache: 'no-cache' }`
  (sinon le navigateur sert un cache périmé après un rafraîchissement des données). Aucun
  chemin `data_cache/…` en dur.
- **Logique calculée générique** (tendances, percentiles, bandes climato) ; tout texte propre à
  une rivière va dans `narrative` de `rivers.json`, jamais en dur dans `index.html`.
- **`data_cache/` est volontairement versionné** — ne pas l'ignorer ni le nettoyer.

## Contrat de données (le dashboard ne valide rien)

`rivers.json` ↔ `data_cache/` ↔ `index.html` forment un contrat implicite : fichier manquant ou
mal formé = **graphe vide et silencieux** (`fetch()` → `null`, aucune erreur). Invariants :

- `id` = nom du dossier `data_cache/<id>/`.
- Chaque station hydro a un `<code>_HIXnJ.json` ; `<code>_QmnJ.json` présent **ssi** `has_Q: true`.
- `region_label_by_dept` couvre chaque `dept` des `stations` (sinon bandeau région vide).
- `quality_stations.json` + un `<code>_quality.json` par station top-3, avec les 5 codes SANDRE.
- Clés `narrative` lues : `heightTrendNote`, `flowTrendNote`, `summerNote`,
  `projectionInsight.{value,detail}`, `contextParagraph`, `projectionsParagraph`,
  `sources[].{label,url}`. Une clé absente = texte vide, à relire à l'œil.
- Format : UTF-8 ; fichiers de mesures **compacts** (`separators=(",",":")`) avec `date` en
  `YYYY-MM-DD` (tri lexicographique dont dépendent l'incrémental des scripts et les agrégations
  du dashboard) ; index (`stations.json`, `quality_stations.json`) en `indent=2`.

## Vérifier son travail

Pas de suite de tests ni de script de validation dédié (cf. `TODO.md` n° 1). Avant de déclarer
une tâche terminée :

```bash
# 1. Tous les JSON parsent
find config data_cache -name '*.json' -print0 | xargs -0 -I{} python3 -m json.tool {} > /dev/null
# 2. Aucun chemin en dur dans un fetch() : seuls riverDataPath, un commentaire et le message
#    d'aide « Enregistrez les fichiers dans data_cache/… » doivent matcher
grep -n "data_cache/" index.html
# 3. Syntaxe des scripts
python3 -m py_compile scripts/*.py
```

4. Invariants du contrat ci-dessus : à vérifier à la main (ou par un one-liner Python stdlib).
5. **Toute modif de `index.html`** : servir en local, basculer sur **chaque** rivière du
   sélecteur et vérifier graphes non vides + console sans erreur. Un diff qui « a l'air bon »
   ne suffit pas.
6. Mise à jour de données : relire le diff — les séries s'allongent en fin de fichier, pas de
   suppression massive, pas de réindentation des fichiers compacts.

Tests futurs : `unittest` stdlib dans `tests/`, lancés par `python3 -m unittest`.

## Workflows courants

**Rafraîchir les données** → `/update-data [id] [--since YYYY-MM-DD]`.

**Ajouter un cours d'eau** :
1. Trouver stations et code qualité via Hub'Eau :
   `/api/v2/hydrometrie/referentiel/stations?libelle_cours_eau=…`,
   `/api/v2/qualite_rivieres/station_pc?nom_cours_eau=…`.
2. Ajouter l'entrée dans `config/rivers.json` (stations, `quality_code`, `narrative` complet).
3. `fetch_hydro_data.py --river <id>` puis `fetch_quality_data.py --river <id>`.
4. Vérifier (section ci-dessus), puis committer `config/rivers.json` + `data_cache/<id>/`.

## Git

- Commits **conventionnels en français**, préfixe en minuscules (`feat:`, `fix:`, `data:`,
  `docs:`, `chore:`…) + description concise, ex. `data: rafraîchit les caches hydro de l'Orne
  (jusqu'au 2026-08-26)`.
- Un commit = un sujet : ne pas mélanger `data:` et modifications de code.

## Déploiement

- `deploy.yml` publie le dépôt tel quel sur GitHub Pages à chaque push sur `main` (ou
  `workflow_dispatch`). Pré-requis unique : *Settings → Pages → Source : GitHub Actions*
  (sinon `Get Pages site failed / Not Found`).
- Pas de cron ni d'ETL côté CI : les données ne changent que par commit.
- Gate d'intégrité avant déploiement : **pas encore en place** (cf. `TODO.md` n° 1) —
  100 % stdlib, aucune dépendance ajoutée au site livré.

## Données & licence

Source unique : Hub'Eau (OFB / SANDRE), API v2, **Licence Ouverte Etalab 2.0** (réutilisation
libre avec mention de la source — conserver les `sources` dans `narrative`).
