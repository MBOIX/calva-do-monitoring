# Plan d'implémentation — ETL qualité robuste aux versions Hub'Eau (TODO n° 7)

Statut : **validé le 2026-11-26**, à implémenter dans une session dédiée (rédigé le 2026-11-24).
Hors périmètre : ETL hydro (traité par `docs/plans/fraicheur-donnees.md`), affichage du
statut « provisoire » dans l'onglet Qualité, gate d'intégrité (n° 1), écriture atomique (n° 2,
pré-requis réalisé juste avant, voir §7).

## 1. Objectif

1. **Une analyse = un enregistrement** : chaque mesure du cache qualité porte l'identifiant
   Hub'Eau de l'analyse (`code_analyse`) et son statut de validation (`code_statut`).
2. **Ne jamais remplacer une valeur par une « Analyse non faite »**, ni perdre une
   analyse parce que Hub'Eau ne la renvoie plus.
3. **Restaurer les 9 mesures de janvier-février 2023** disparues de Hub'Eau, récupérées
   dans l'historique git du cache.

## 2. Constats préalables (vérifiés le 2026-11-24 sur les 9 stations qualité)

### 2.1 Hub'Eau sert plusieurs versions d'une même analyse

Une analyse peut exister en plusieurs versions : une version brute saisie à l'avance, puis
des versions contrôlées. Hub'Eau ne choisit pas toujours la bonne et en renvoie parfois
plusieurs :

- **Doublons** : 176 analyses sont renvoyées **deux fois**, avec le même `code_analyse`, la
  même date et la même valeur, mais deux statuts différents (2 « contrôlée niveau 1 » et
  3 « validée ») et deux `date_maj_analyse`. Elles datent de 2020 (20) et de 2024 (156).
  Le cache actuel les contient toutes en double, si bien que ces mesures pèsent deux fois
  dans les moyennes mensuelles.
- **Régressions** : en janvier-février 2023 (laboratoire CARSO), Hub'Eau renvoie pour
  certaines analyses **seulement** la version brute : `resultat: null`, `code_remarque: 0`
  (« Analyse non faite »), datée du 1ᵉʳ du mois à 10 h 00, `date_maj_analyse` 2023-03-08.
  La version validée de 2024, avec la vraie date et la vraie valeur, n'est plus servie.
  Le basculement a eu lieu entre le 29/09/2026 et le 23/11/2026 : l'extraction complète
  de la Seulles du 29/09 (`ff8d38e`) contenait encore ces valeurs. Six appels identiques
  donnent aujourd'hui la même réponse : l'état est stable, il n'est pas aléatoire.

### 2.2 Les 9 valeurs disparues ont un identifiant retrouvable

Ces valeurs figurent dans les versions git du cache jusqu'à `aa28341` (2026-11-23) et sont
absentes aujourd'hui. Pour chacune, on cherche les autres analyses du même jour et leur
`code_prelevement`. Ce prélèvement contient **exactement une** « Analyse non faite » du
même paramètre : c'est l'analyse dont la version validée a disparu.

| Rivière | Station | Paramètre | Date | Valeur | `code_analyse` | Version servie aujourd'hui |
|---|---|---|---|---|---|---|
| odon | 03244000 | 1339 NO₂ | 2023-02-17 | 0.04 | 120929270 | non faite, 2023-02-01 |
| odon | 03244000 | 1340 NO₃ | 2023-02-17 | 61.0 | 120929271 | non faite, 2023-02-01 |
| orne | 03236395 | 1302 pH | 2023-01-05 | 8.1 | 120756093 | non faite, 2023-01-01 |
| orne | 03236395 | 1302 pH | 2023-02-16 | 8.1 | 120904915 | non faite, 2023-02-01 |
| orne | 03236395 | 1335 NH₄ | 2023-01-05 | 0.03 | 120756081 | non faite, 2023-01-01 |
| orne | 03236395 | 1340 NO₃ | 2023-02-16 | 31.0 | 120904902 | non faite, 2023-02-01 |
| seulles | 03246000 | 1302 pH | 2023-01-05 | 8.1 | 120760992 | non faite, 2023-01-01 |
| seulles | 03246000 | 1335 NH₄ | 2023-02-21 | 0.04 | 120938293 | non faite, 2023-02-01 |
| seulles | 03246000 | 1340 NO₃ | 2023-01-05 | 47.0 | 120760982 | non faite, 2023-01-01 |

### 2.3 Champs Hub'Eau utiles (fractions eau `23` et `3` uniquement)

- `code_analyse` : toujours renseigné. Il est unique par analyse, sauf dans le cas des
  doublons de versions (§2.1).
- `code_statut` : **codes propres à la qualité**, différents de ceux de l'hydrométrie
  (4 / 8 / 12 / 16, voir `fraicheur-donnees.md`).

  | `code_statut` | `mnemo_statut` | Analyses |
  |---|---|---|
  | 1 | Donnée brute | 184 |
  | 2 | Donnée contrôlée niveau 1 (données contrôlées) | 561 |
  | 3 | Donnée contrôlée niveau 2 (données validées) | 15 516 |

- `code_remarque` : `1` quantifié (14 692), `10` < seuil de quantification (1 527),
  `0` « Analyse non faite » (42). On a vérifié que `resultat` est `null` **si et seulement
  si** `code_remarque` vaut `0`.
- Volume : au plus **835 analyses par station et par paramètre**, ce qui tient en un seul
  appel (`size=5000`). Une extraction complète représente 45 appels (9 stations × 5
  paramètres). Avec `fields`, chaque réponse ne contient que les champs utiles.

### 2.4 L'incrémental actuel ne peut pas suivre ces évolutions

`fetch_station_quality` reprend à partir de la dernière date en cache. À date égale,
l'enregistrement existant l'emporte (`r["date"] not in existing_dates`). Deux défauts en
découlent :
- une analyse publiée en retard, dont la date est antérieure à la dernière date en cache,
  n'est jamais récupérée (cas de Serans : les mesures du 10/02/2026 sont arrivées après le
  01/03/2026) ;
- une correction faite par Hub'Eau n'est jamais prise en compte.

### 2.5 Le dashboard n'est pas concerné

`index.html` ne lit que `date` et `value` dans les fichiers qualité (`loadQualityData`,
agrégations mensuelles). Les nouvelles clés sont ignorées. Aucun code navigateur n'écrit de
cache qualité : `buildCacheObject` ne sert qu'à l'hydrométrie.

## 3. Décisions

Validées le 2026-11-24 :

| Sujet | Décision |
|---|---|
| Portée | Ce plan, puis implémentation dans une session dédiée. |
| Mesures perdues de 2023 | **Restauration depuis l'historique git** (les 9 valeurs du §2.2). |
| Statut de validation | Stocké **dans la même migration** que l'identifiant, pour ne faire qu'une seule extraction complète. |

Validées à la relecture le 2026-11-26 :

| Sujet | Décision |
|---|---|
| Stratégie d'extraction | **Extraction complète à chaque exécution**, sans incrémental. Le coût est de 45 appels d'une seule page, car les 15 minutes actuelles (897 s le 2026-11-23) viennent surtout du classement des stations. Cette stratégie corrige le §2.4 sans logique de fenêtre. `--since` est **conservé**, car `/update-data` le transmet aux deux scripts : il limite la fenêtre d'extraction, et la fusion préserve les analyses plus anciennes sans les compter comme absentes. |
| Analyses « non faites » | **Jamais stockées.** Elles n'ont pas de valeur, et le dashboard les ignore déjà. Les 42 `null` actuels disparaissent, ce qui rend `record_count` et `date_max` exacts. La fusion n'a plus de cas où une « non faite » écraserait une valeur. |
| Choix de la version d'une analyse | Version **avec valeur**, puis la plus **validée** (`code_statut` maximal), puis la plus **récente** (`date_maj_analyse` maximale). Les 176 doublons observés ont la même valeur dans leurs deux versions : l'ordre ne change que le statut stocké. Cas limite assumé : une valeur dévalidée pour correction garde l'ancienne valeur validée en attendant la nouvelle. |
| Analyse absente de la réponse | **Conservée**. C'est la même règle que `fraicheur-donnees.md` §4.2 : aucune suppression silencieuse. Le rapport de fusion sépare deux cas et **liste leurs identifiants** (§4.2) : l'analyse **revenue en « non faite »** (régression Hub'Eau connue, sans danger) et l'analyse **totalement absente** (suppression réelle possible, à vérifier, puis à purger à la main si besoin). |
| Marquage des valeurs restaurées | Clé facultative `restored_from: "aa28341"` (dernier commit qui contenait la valeur) et `status: null` : ces valeurs étaient très probablement validées, comme leurs voisines du même prélèvement, mais rien ne le prouve. La clé disparaît d'elle-même si Hub'Eau renvoie à nouveau la version validée. |
| Migration des caches existants | **Manuelle**, comme la purge des sédiments (`d2145bb`) : supprimer les 9 fichiers `<code>_quality.json`, puis lancer une extraction complète (§7). L'ETL ne contient **aucun code de migration**, qui ne servirait qu'une fois : un enregistrement sans `id` lève une erreur explicite avant tout appel à l'API (§4.2). |
| Script de restauration | **Non versionné** : il ne sert qu'une fois. La table du §2.2 et le message du commit `data:` suffisent à refaire l'opération. |
| Signalement à Hub'Eau | **Oui, en plus de la restauration** : la restauration ne corrige que ce cache, le signalement corrige la source pour tous les réutilisateurs. Il s'appuie sur les identifiants du §2.2 (§7, étape 4). |
| Ordre de réalisation | Après le **n° 2** (écriture atomique) : il touche la même fonction `save_station_cache` et protège la migration, qui réécrit les 9 fichiers qualité. **Avant** `fraicheur-donnees.md` : ce plan corrige des données affichées aujourd'hui (176 mesures comptées deux fois, 9 mesures manquantes), il est plus petit, et il prépare le badge « provisoire » de l'onglet Qualité. |

## 4. Contrats d'interface

### 4.1 Format d'un enregistrement qualité (`<code>_quality.json`)

```json
{"date":"2023-02-21","value":0.05,"id":"120938294","status":3}
{"date":"2023-01-05","value":47.0,"id":"120760982","status":null,"restored_from":"aa28341"}
```

- `id` : `code_analyse`, en chaîne de caractères, **unique** dans un paramètre.
- `status` : `code_statut` en entier (1, 2 ou 3), ou `null`.
- `value` : jamais `null`.
- Tri par `(date, id)` : il reste lexicographique sur `date`, comme l'exige le contrat
  de CLAUDE.md.
- Les métadonnées par paramètre ne changent pas (`name`, `unit`, `record_count`,
  `date_min`, `date_max`). Taille : **576 Ko → environ 1 Mo** pour les 9 fichiers.

### 4.2 ETL — `scripts/fetch_quality_data.py`

```python
VALIDATED_STATUS = 3   # qualité : 1 brute, 2 contrôlée niv. 1, 3 validée (≠ hydro : 16)
API_FIELDS = "code_analyse,date_prelevement,resultat,code_fraction,libelle_fraction,code_statut,date_maj_analyse"

def fetch_parameter_records(station_code, param_code, date_start=None)  # + fields=API_FIELDS
def best_versions(raw_records)        # -> une version par code_analyse (règle du §3)
def simplify_record(raw)              # -> {"date", "value", "id", "status"}
def merge_analyses(existing, fetched, not_done_ids, window_start=None)  # -> (merged, MergeReport)
```

Ordre des étapes dans `fetch_station_quality`, pour chaque paramètre :
`keep_water_analyses` (existant) → `best_versions` → séparation des analyses sans valeur,
dont on ne garde que les identifiants (`not_done_ids`) → `simplify_record` →
`merge_analyses`. `window_start` vaut la date de `--since`, ou `None` pour une extraction
complète.

**Ancien format** : au chargement du cache, avant tout appel à l'API, un enregistrement sans
`id` lève une erreur explicite. Le message nomme le fichier et la marche à suivre : supprimer
les fichiers `<code>_quality.json`, puis relancer une extraction complète. Aucune donnée n'est
écrite.

`merge_analyses`, avec les analyses existantes et les nouvelles indexées par `id` :
1. Une analyse renvoyée **remplace** l'analyse de même `id` : les corrections de Hub'Eau
   sont ainsi prises en compte, et `restored_from` disparaît. Elle n'est comptée comme
   « mise à jour » que si `date`, `value` ou `status` change : une exécution sans
   nouveauté rapporte 0 mise à jour.
2. Une analyse existante **absente** de la réponse est **conservée** : soit Hub'Eau ne la
   sert plus qu'en « non faite » (son `id` est dans `not_done_ids`), soit elle a
   totalement disparu.
3. Une analyse nouvelle est ajoutée.
4. Avec `window_start`, seules les analyses existantes datées de `window_start` ou après
   sont comparées à la réponse : les plus anciennes sont conservées sans être comptées
   comme absentes.

`MergeReport`, affiché par paramètre :

- comptes : ajoutées et mises à jour (calculés par `merge_analyses`), versions fusionnées
  (doublons de `code_analyse` résolus par `best_versions`) et « non faites » écartées
  (calculés en amont par `fetch_station_quality`) ;
- deux listes d'**identifiants** conservés, affichées seulement si elles ne sont pas
  vides :
  - **revenues en « non faite »** : régression connue de Hub'Eau, sans danger, la valeur
    est gardée ;
  - **totalement absentes** : suppression réelle possible, à vérifier chez Hub'Eau, puis à
    purger à la main si elle est confirmée.

C'est l'élément à relire pendant `/update-data` : une liste « totalement absentes » qui
s'allonge signale une dérive de Hub'Eau.

La logique incrémentale (`last_date`, `existing_dates`) est supprimée.

## 5. Restauration des 9 valeurs (une seule fois, pendant le commit `data:`)

On exécute un script ponctuel, **non versionné** (§3), après l'extraction complète. La table
du §2.2 est la source de vérité. Pour chaque ligne :

- vérifier que l'`id` est absent du cache et que Hub'Eau sert toujours la version
  « non faite » ; sinon, ne pas restaurer et le signaler ;
- insérer `{"date", "value", "id", "status": null, "restored_from": "aa28341"}` ;
- recalculer `record_count`, `date_min` et `date_max`.

Lors des exécutions suivantes, la règle 2 de `merge_analyses` protège ces valeurs.

## 6. Tests — `tests/test_fetch_quality_data.py` (aucun réseau)

- `simplify_record` : `id` et `status` sont lus, `status` est converti en `int` et vaut
  `None` si le champ est absent.
- `best_versions` :
  - la version avec valeur l'emporte sur la « non faite », quel que soit l'ordre ;
  - le statut 3 l'emporte sur le statut 2 ;
  - à statut égal, la `date_maj_analyse` la plus récente l'emporte ;
  - deux `id` différents à la même date restent deux analyses.
- `merge_analyses` :
  - une correction de valeur est propagée ;
  - **régression de 2023** : valeur existante + version « non faite » seule → la valeur
    est conservée ;
  - une analyse revenue en « non faite » et une analyse totalement absente sont toutes
    deux conservées, mais rapportées dans deux listes distinctes, avec leurs identifiants ;
  - avec `window_start`, une analyse existante antérieure à la fenêtre est conservée sans
    être rapportée comme absente ;
  - une analyse renvoyée à l'identique n'est pas comptée comme mise à jour ;
  - une valeur restaurée est remplacée (et `restored_from` disparaît) quand la version
    validée revient ;
  - le tri se fait par `(date, id)`, sans doublon d'`id`.
- Intégration de `fetch_station_quality` (API simulée, dossier temporaire) :
  - deux versions d'une même analyse, une analyse de sédiments et une « non faite »
    donnent un fichier écrit avec une seule analyse ;
  - une seconde exécution où l'analyse régresse en « non faite » conserve la valeur ;
  - un cache à l'ancien format (enregistrement sans `id`) lève l'erreur explicite, sans
    aucun appel à l'API ni écriture de fichier.
- `fetch_parameter_records` : l'URL contient `fields=` (avec `fetch_json` simulé).

## 7. Étapes et commits

Un commit = un sujet (CLAUDE.md). Avant de commencer, `python3 -m unittest -v` doit passer.

**Pré-requis** : TODO n° 2 (écriture atomique) réalisé et committé juste avant, dans son
propre commit `fix:`.

1. **`fix:` ETL** : identifiants, statut, choix de version, fusion et rapport, erreur sur
   l'ancien format, suppression de l'incrémental, tests du §6.
2. **`data:` migration manuelle** :
   - supprimer les 9 fichiers de mesures : `rm data_cache/*/*_quality.json` (le motif
     n'atteint pas `quality_stations.json`) ;
   - `python3 scripts/fetch_quality_data.py` : extraction complète, sans `--since`. En
     cas d'échec, `git restore data_cache/` puis recommencer : rien n'est committé ;
   - restauration du §5 ;
   - contrôles par un one-liner Python :
     - 100 % des enregistrements ont `id` et `status` ;
     - aucune `value: null` ;
     - aucun `id` en double dans un paramètre ;
     - les 9 valeurs restaurées sont présentes ;
     - le nombre d'enregistrements est égal au nombre d'`id` distincts avec valeur chez
       Hub'Eau, plus les 9 restaurées ;
   - relire le diff : 176 doublons de versions et 42 `null` en moins, et aucune autre
     valeur disparue. Les 23 autres paires (date, valeur) identiques du cache actuel sont
     des analyses distinctes (identifiants différents) : elles doivent rester ;
   - message : `data: identifiants et statuts d'analyse dans les caches qualité, restaure 9 mesures de 2023`.
3. **`docs:`** :
   - `CLAUDE.md` : format des enregistrements qualité dans le contrat de données, avec
     les codes de statut qualité, différents de ceux de l'hydrométrie ;
   - `README.md` : ETL qualité (extraction complète, versions, fusion) ;
   - `.claude/commands/update-data.md` : la qualité n'est plus incrémentale (« Sans
     argument : … en incrémental » ne vaut plus que pour l'hydro) ; à l'étape 3 (revue du
     diff), relire le rapport de fusion, en particulier la liste « totalement absentes » ;
   - `TODO.md` : cocher le n° 7 ;
   - archiver ce plan.
4. **Hors dépôt, par le mainteneur** : signaler à Hub'Eau la régression de janvier-février
   2023, avec la table du §2.2 (identifiants, valeurs, version servie aujourd'hui).

## 8. Vérifications

- Commandes de la section « Vérifier son travail » de `CLAUDE.md` (1 à 4).
- `python3 -m http.server 8000` → onglet Qualité, pour **chaque** rivière et **chaque**
  station : graphes non vides, console sans erreur. Années 2020, 2023 et 2024 : les
  moyennes mensuelles bougent légèrement (doublons retirés, valeurs restaurées), ce qui
  est attendu.
- Seconde exécution de l'ETL juste après : aucun changement dans `data_cache/`, sauf les
  horodatages (`fetched_at`, `updated_at`). C'est le test d'idempotence. Le rapport doit
  afficher 0 ajoutée et 0 mise à jour, aucune « totalement absente », et exactement les
  9 identifiants du §2.2 dans « revenues en non faite ».

## 9. Risques

| Risque | Parade |
|---|---|
| Hub'Eau réattribue un `code_analyse` (rebancarisation). | L'ancienne analyse serait conservée en plus de la nouvelle. Son identifiant apparaît dans la liste « totalement absentes » du `MergeReport`, et elle se purge à la main après vérification. Non observé à ce jour. |
| Une analyse réellement supprimée chez Hub'Eau reste en cache. | Choix assumé, identique à l'hydro. Son identifiant est listé dans « totalement absentes ». |
| Une analyse invalidée passe en « non faite » et sa valeur est conservée à tort. | Non observé. Une invalidation passe normalement par la qualification (`code_qualification`), pas par `code_remarque: 0`. À surveiller dans la liste « revenues en non faite » : hors des 9 analyses de 2023 connues, tout nouvel identifiant mérite une vérification. |
| Confusion entre les codes de statut qualité (1 à 3) et hydro (4 à 16). | Une constante par script, avec un commentaire, et la mention dans le contrat de données de CLAUDE.md. |
| Une extraction complète en échec laisse un cache partiel. | Couvert par le n° 2 (écriture atomique), réalisé juste avant : chaque fichier est soit l'ancien, soit le nouveau. Le script s'arrête sur l'exception, et on ne committe pas. Pendant la migration : `git restore data_cache/`. |
| La migration manuelle est oubliée sur un poste. | Le premier lancement lève l'erreur explicite sur l'ancien format, sans appel à l'API ni écriture : rien ne peut être committé par erreur. |

## 10. Suites possibles (non planifiées)

- Badge « provisoire » dans l'onglet Qualité (`status !== 3`), dans la continuité de
  `fraicheur-donnees.md` §9, que ce plan rend possible.
- Valeurs sous le seuil de quantification (`code_remarque: 10`, 1 527 analyses, valeur =
  seuil) : elles sont aujourd'hui tracées comme des mesures. Les distinguer ?
- Classement des stations (`discover_stations`) : une erreur d'appel compte la station à
  0 sans alerte, et les totaux incluent les sédiments et les doublons.
