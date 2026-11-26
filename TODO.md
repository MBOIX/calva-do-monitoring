# TODO

Améliorations identifiées le 12 juillet 2026 (analyse multi-angles : intégrité/CI,
robustesse front, scripts ETL, produit/UX). Les trois retenues se complètent :
la n° 2 empêche la corruption des données à la source, la n° 1 la bloque avant
publication, la n° 3 la rend visible si elle passe quand même.

Complété le 29 septembre 2026 par un volet produit lié à la sécheresse (n° 4 à 6) :
fin septembre 2026, les secteurs Bessin et Virois du Calvados sont en **crise**,
Orne moyenne et aval en **alerte renforcée** (source : API VigiEau).

Complété le 24 novembre 2026 par le n° 7 : Hub'Eau sert plusieurs versions d'une même
analyse qualité, ce qui crée des doublons et fait disparaître des mesures validées.

## À implémenter (par ordre de priorité)

### 1. Gate d'intégrité `rivers.json` ↔ `data_cache/` dans le déploiement — effort M

`deploy.yml` publie aujourd'hui sans aucune validation : un cache cassé ou une
config désynchronisée part en production silencieusement (graphe vide, aucune
erreur). C'est le « gate qualité recommandé » déjà appelé de ses vœux par CLAUDE.md.

- [ ] Écrire `scripts/validate_data_integrity.py` (stdlib uniquement : `json`, `os`, `sys`)
      qui vérifie, pour chaque rivière de `config/rivers.json` :
  - dossier `data_cache/<id>/` existant, JSON valide pour chaque fichier référencé ;
  - un `<code>_HIXnJ.json` par station ; `<code>_QmnJ.json` présent **ssi** `has_Q: true` ;
  - `quality_stations.json` + un `<code>_quality.json` par station qualité,
    avec les 5 codes SANDRE `1311 / 1302 / 1340 / 1339 / 1335` ;
  - chaque `dept` des stations couvert par `region_label_by_dept` ;
  - `exit(1)` avec message clair sur la première violation.
- [ ] Ajouter l'étape `python3 scripts/validate_data_integrity.py` dans
      `.github/workflows/deploy.yml` juste après le checkout.

**Fichiers** : `scripts/validate_data_integrity.py` (nouveau), `.github/workflows/deploy.yml`

### 2. Écriture atomique des caches JSON dans les scripts ETL — effort S

Les quatre fonctions d'écriture (`save_cache`, `build_stations_index` dans
`fetch_hydro_data.py` ; `save_station_cache`, `build_quality_stations_index` dans
`fetch_quality_data.py`) écrivent directement dans le fichier final : une
interruption (Ctrl-C, coupure réseau en pleine pagination, disque plein) laisse
un JSON tronqué, quasi indétectable dans un diff compact.

- [ ] Factoriser un helper `write_json_atomic(filepath, data, **dump_kwargs)` :
      écriture vers `filepath + '.tmp'` puis `os.replace(tmp, filepath)`
      (atomique sur POSIX).
- [ ] L'utiliser dans les quatre fonctions d'écriture.

**Fichiers** : `scripts/fetch_hydro_data.py`, `scripts/fetch_quality_data.py`

### 3. État « pas de données » pour le graphe de hauteur d'eau — effort S

Dans `updateCharts()` (`index.html` ~l. 1254-1266), le graphe de débit a un
fallback visible (`#no-flow-msg`) mais le graphe de hauteur — le graphe
principal du site — reste simplement vide si les données manquent : impossible
pour un visiteur de distinguer « panne de données » de « rien à signaler ».

- [ ] Dans `buildHydroTab()` (~l. 794-803), ajouter un élément `#no-height-msg`
      au chart-container du panneau hauteur (markup identique à `#no-flow-msg`).
- [ ] Dans `updateCharts()`, répliquer symétriquement le bloc conditionnel du
      débit : message affiché + canvas masqué quand `!heightData ||
      heightData.records.length === 0`, l'inverse sinon.

**Fichiers** : `index.html`

### 7. ETL qualité robuste aux versions des analyses Hub'Eau — effort M

Hub'Eau renvoie parfois plusieurs versions d'une même analyse : 176 doublons
(contrôlée et validée) sont aujourd'hui comptés deux fois dans le cache. Il lui arrive
aussi de ne plus servir que la version brute « Analyse non faite » : 9 mesures validées
de janvier-février 2023 ont ainsi disparu entre fin septembre et novembre 2026. L'incrémental, qui
reprend à la dernière date en cache, rate en outre les publications tardives et les
corrections. Plan d'implémentation détaillé, validé le 2026-11-26 :
`docs/plans/etl-qualite-versions.md`. **Pré-requis** : n° 2 (même fonction
`save_station_cache`), à faire juste avant. À faire avant `docs/plans/fraicheur-donnees.md`.

- [ ] Stocker l'identifiant (`code_analyse`) et le statut de validation (`code_statut`)
      de chaque analyse, et fusionner par identifiant : une « non faite » ne remplace
      jamais une valeur, et une analyse absente de la réponse est conservée et listée
      dans le rapport de fusion.
- [ ] Extraction complète à chaque exécution (45 appels d'une page) au lieu de
      l'incrémental.
- [ ] Migration manuelle des caches (suppression des 9 fichiers puis extraction
      complète) et restauration des 9 mesures de 2023 depuis l'historique git
      (identifiants retrouvés par prélèvement).
- [ ] Signaler la régression de janvier-février 2023 à Hub'Eau (identifiants dans le plan).

**Fichiers** : `scripts/fetch_quality_data.py`, `tests/test_fetch_quality_data.py`,
`data_cache/*/*_quality.json`, `CLAUDE.md` (contrat de données), `README.md`,
`.claude/commands/update-data.md`

## Volet sécheresse (produit)

### 4. Encart « Situation actuelle » en tête du dashboard — effort M/L — ✅ fait le 2026-09-29

Le dashboard montre des tendances longues mais ne dit pas si la rivière va mal
**maintenant**. Plan d'implémentation détaillé : `docs/plans/situation-actuelle.md`.

- [x] Position du dernier débit face à l'historique du même jour de l'année
      (percentile, libellé « très bas / bas / normal / haut »).
- [x] Repères d'étiage calculés sur l'historique (ex. VCN3 quinquennal sec).
- [x] Niveau de restriction en vigueur (vigilance → crise) via l'API VigiEau
      (`api.vigieau.gouv.fr`, publique, sans clé, CORS `*`).

**Fichiers** : `index.html`, `config/rivers.json`, `CLAUDE.md` (contrat), tests.

Suites relevées par la revue (non bloquantes) :

- [ ] Afficher la ligne Étiage quand le VCN3 estimé vaut 0 (cours d'eau intermittent) :
      aujourd'hui `buildLowFlowLine` la masque.
- [ ] Remplacer « rang P0 » par une formulation lisible (« plus bas que toutes les
      années ») quand le débit est sous tout l'historique de la saison.
- [ ] Tester un changement rapide de **station** (même rivière) dans `tests/smoke.test.html`.
- [ ] Vérifier la licence de réutilisation des données VigiEau.
- [ ] Revérifier les codes `vigieau_zone` à chaque nouvel arrêté-cadre (La Courbe et
      Tierceville rattachées par déduction : la commune ne renvoie aucune zone).

### 5. Fraîcheur des données visible et automatisable — effort M

En crise sécheresse, une semaine de retard fausse la lecture ; or les données ne
changent que par commit manuel.

- [ ] Badge « Données au JJ/MM/AAAA » dans le header et l'onglet Qualité
      (`date_max` / `fetched_at` déjà présents dans les caches) — reprend l'idée
      auparavant écartée.
- [ ] Distinguer visuellement les mesures provisoires : les valeurs récentes
      Hub'Eau portent `quality: "Douteuse"` (ex. Seulles, septembre 2026) et sont
      aujourd'hui tracées comme des valeurs validées (pointillé ou opacité réduite).
- [ ] **Décision à prendre** : rafraîchissement planifié (GitHub Actions `schedule`)
      qui exécute l'ETL, valide et committe. Revient sur le choix documenté dans
      `CLAUDE.md` (« pas de cron ni d'ETL côté CI »). **Pré-requis impératifs** :
      n° 1 (gate d'intégrité) et n° 2 (écriture atomique), sinon un appel Hub'Eau
      en échec publierait des données partielles.

**Fichiers** : `index.html`, éventuellement `.github/workflows/refresh.yml` (nouveau).

### 6. Indicateurs d'étiage et observations de terrain — effort M

La moyenne annuelle masque la sécheresse ; ce sont les minima d'été qui la révèlent.

- [ ] Indicateurs d'étiage annuels calculés génériquement sur `QmnJ` : débit
      minimal annuel (VCN3/VCN10), QMNA, nombre de jours sous un seuil de basse
      eau, et leur tendance depuis l'ouverture de la station.
- [ ] Observations ONDE (réseau national d'observation visuelle des étiages) via
      Hub'Eau `/api/v1/ecoulement/observations` : écoulement visible / non visible
      / assec. Vérifié le 29/09/2026 : 2 940 observations pour le Calvados, dont
      « Écoulement non visible » le 23/09/2026. Nouveau fichier de cache par
      rivière (`onde.json`) produit par un script ETL stdlib.
- [ ] Optionnel : température de l'eau via Hub'Eau `/api/v1/temperature`
      (11 stations dans le Calvados) pour éclairer les baisses d'O₂ estivales.

**Fichiers** : `index.html`, `scripts/fetch_onde_data.py` (nouveau),
`config/rivers.json`, `CLAUDE.md` (contrat de données).

## À creuser

- [ ] **Station qualité Odon 03243120 inactive** : plus aucune analyse publiée
      depuis le 9 décembre 2024 (145 mesures au total, contre 1 200+ ailleurs).
      Vérifier via `python3 scripts/fetch_quality_data.py --river odon --discover`
      si une station de remplacement existe sur l'Odon ; sinon le top-3 qualité
      de l'Odon affiche une station gelée.

## Écartées pour l'instant (avec raison, pour ne pas réévaluer de zéro)

- **Try/catch + `console.warn` dans `switchRiver`/`switchStation`/`loadCacheFile`** —
  réel, mais largement couvert par le gate CI (n° 1) et le fallback hauteur (n° 3) ;
  le risque résiduel (échec réseau en session) est rare sur un site statique.
- **Jeton anti-réponses tardives + indicateur de chargement sur `switchStation`** —
  bug de concurrence réel mais nécessite un double-clic rapide entre stations ;
  probabilité faible face à l'effort.
- **Isolation des erreurs par station dans les scripts ETL (continue au lieu
  d'avorter)** — confort du mainteneur uniquement, n'affecte jamais les visiteurs
  (données publiées après relecture et commit manuels).
- **Extraction de `merge_records()` en fonction pure + tests unitaires** — écartée
  faute de bug connu ; **réévaluée le 2026-11-24** : bugs avérés, repris côté qualité
  dans le n° 7 et côté hydro dans `docs/plans/fraicheur-donnees.md`.
- **Renommage/confirmation du bouton « Actualiser »** (télécharge sans persister) —
  confusion réelle mais purement cosmétique, aucun risque de donnée fausse.
