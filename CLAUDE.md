# CLAUDE.md

Tableau de bord **statique** (HTML/CSS/JS vanilla, aucun build) des données hydrologiques et
de qualité de l'eau de cours d'eau de Normandie, alimenté par les API publiques
[Hub'Eau](https://hubeau.eaufrance.fr/) v2 (OFB / SANDRE, sans clé) et [VigiEau](https://vigieau.gouv.fr/).
Multi-rivières via un sélecteur, piloté par un fichier de configuration unique. Encart
« Situation actuelle » : débit actuel vs saison, repère d'étiage (VCN3 quinquennal estimé),
restrictions sécheresse en vigueur par zone. Présentation utilisateur : `README.md`.

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
index.html            Dashboard : sélecteur de rivière + onglets Hydrologie & Qualité + encart Situation actuelle.
                      JS inline, Chart.js 4.4.7 via CDN jsDelivr. Charge js/situation.js et js/vigieau.js.
js/situation.js       Calculs purs (percentiles, VCN3 quinquennal estimé, rang saisonnier).
js/vigieau.js         Client VigiEau (restrictions sécheresse par zone, pas de DOM).
config/rivers.json    SOURCE DE VÉRITÉ — lue par le dashboard ET les scripts Python.
scripts/fetch_*.py    ETL Python stdlib → écrit data_cache/<id>/.
data_cache/<id>/      JSON par rivière, VERSIONNÉS (ce sont les données servies par le site).
tests/                Tests unitaires et d'intégration (pages HTML + lanceur Python).
.claude/commands/     /update-data : fetch → validation → revue du diff → commit (sans push).
.github/workflows/    deploy.yml — publication GitHub Pages à chaque push sur main (aucun ETL).
TODO.md               Backlog priorisé (gate d'intégrité CI, écriture atomique, état « pas de données »).
docs/plans/           Plans d'implémentation (validés et archivés).
```

Flux : `scripts/fetch_*.py` → `data_cache/<id>/{stations.json, quality_stations.json,
<code>_HIXnJ.json, <code>_QmnJ.json, <code>_quality.json}` → `fetch()` du dashboard.

Vocabulaire métier : `HIXnJ` = hauteur max journalière (mm) ; `QmnJ` = débit moyen journalier
(L/s) ; qualité = 5 paramètres SANDRE : `1311` O₂, `1302` pH, `1340` nitrates, `1339` nitrites,
`1335` ammonium.

`config/rivers.json` déclare par rivière : `id`, `name`, `name_with_article` (optionnel,
sinon « l'<name> »), `region_label_by_dept`,
`quality_code` (code SANDRE rivière), `stations` (hydrométrie, `has_Q`, optionnel `vigieau_zone` pour l'encart),
`narrative` (textes d'analyse + sources propres à la rivière, affichés tels quels).

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
- **Exception VigiEau** : contrairement à Hub'Eau, l'encart « Situation actuelle » appelle
  `api.vigieau.gouv.fr` **directement depuis le navigateur** à chaque affichage (CORS `*` vérifié).
  Échec (réseau, timeout, API indisponible) → encart « indisponible », jamais d'erreur bloquante.

## Contrat de données (le dashboard ne valide rien)

`rivers.json` ↔ `data_cache/` ↔ `index.html` forment un contrat implicite : fichier manquant ou
mal formé = **graphe vide et silencieux** (`fetch()` → `null`, aucune erreur). Invariants :

- `id` = nom du dossier `data_cache/<id>/`.
- Chaque station hydro a un `<code>_HIXnJ.json` ; `<code>_QmnJ.json` présent **ssi** `has_Q: true`.
- `vigieau_zone` (optionnel) : code ZAS au format `\d+_[0-9AB]{2,3}_\d{4}` (ex. `28_14_0001`).
  Le département du code doit correspondre au `dept` de la station.
- `region_label_by_dept` couvre chaque `dept` des `stations` (sinon bandeau région vide).
- `quality_stations.json` + un `<code>_quality.json` par station top-3, avec les 5 codes SANDRE.
- Clés `narrative` lues : `heightTrendNote`, `flowTrendNote`, `summerNote`,
  `projectionInsight.{value,detail}`, `contextParagraph`, `projectionsParagraph`,
  `sources[].{label,url}`. Une clé absente = texte vide, à relire à l'œil.
- Format : UTF-8 ; fichiers de mesures **compacts** (`separators=(",",":")`) avec `date` en
  `YYYY-MM-DD` (tri lexicographique dont dépendent l'incrémental des scripts et les agrégations
  du dashboard) ; index (`stations.json`, `quality_stations.json`) en `indent=2`.

## Vérifier son travail

Avant de déclarer une tâche terminée :

```bash
# 1. Tests
python3 -m unittest -v
# 2. Tous les JSON parsent
find config data_cache -name '*.json' -print0 | xargs -0 -I{} python3 -m json.tool {} > /dev/null
# 3. Aucun chemin en dur dans un fetch() : seuls riverDataPath, un commentaire et le message
#    d'aide « Enregistrez les fichiers dans data_cache/… » doivent matcher
grep -n "data_cache/" index.html
# 4. Syntaxe des scripts
python3 -m py_compile scripts/*.py
```

5. Invariants du contrat ci-dessus : à vérifier à la main (ou par un one-liner Python stdlib).
6. **Toute modif de `index.html`** : servir en local, basculer sur **chaque** rivière du
   sélecteur et vérifier graphes non vides + console sans erreur. Un diff qui « a l'air bon »
   ne suffit pas.
7. Mise à jour de données : relire le diff — les séries s'allongent en fin de fichier, pas de
   suppression massive, pas de réindentation des fichiers compacts.

## Workflows courants

**Rafraîchir les données** → `/update-data [id] [--since YYYY-MM-DD]`.

**Ajouter un cours d'eau** :
1. Trouver stations et code qualité via Hub'Eau :
   `/api/v2/hydrometrie/referentiel/stations?libelle_cours_eau=…`,
   `/api/v2/qualite_rivieres/station_pc?nom_cours_eau=…`.
   Récupérer aussi le code commune INSEE de chaque station.
2. Trouver `vigieau_zone` (optionnel mais recommandé) : pour chaque station, requête
   `GET https://api.vigieau.gouv.fr/api/zones?commune=<INSEE>&profil=particulier` puis
   filtrer le résultat sur `type === 'SUP'`. Si aucune zone SUP : vérifier via
   `/api/zones/departement/<dept>`.
3. Ajouter l'entrée dans `config/rivers.json` (stations avec optionnel `vigieau_zone`,
   `quality_code`, `narrative` complet).
4. `fetch_hydro_data.py --river <id>` puis `fetch_quality_data.py --river <id>`.
5. Vérifier (section ci-dessus), puis committer `config/rivers.json` + `data_cache/<id>/`.

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

Deux sources :

- **Hub'Eau** (OFB / SANDRE), API v2, **Licence Ouverte Etalab 2.0** (réutilisation libre
  avec mention de la source — conserver les `sources` dans `narrative`). Hydrométrie et
  qualité des cours d'eau mises en cache via ETL Python.
- **VigiEau** (Ministère de la Transition écologique), API publique CORS `*`, restrictions
  sécheresse **par zone** (ZAS). Consulté directement depuis le navigateur sans cache
  (données fraîches à chaque affichage). Licence de réutilisation non vérifiée : citer la source.
