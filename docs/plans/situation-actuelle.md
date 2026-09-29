# Plan d'implémentation — encart « Situation actuelle » (TODO n° 4)

Statut : **à relire avant exécution** (rédigé le 2026-09-29).
Exécution : **exclusivement via le workflow** décrit en §8 (aucune modification à la main).

## 1. Objectif

En tête de l'onglet Hydrologie, pour la station sélectionnée, répondre en un coup
d'œil à « la rivière va-t-elle mal **maintenant** ? » :

1. **Position du dernier débit face à l'historique du même moment de l'année**
   (rang percentile + libellé « très bas / bas / normal / haut / très haut »).
2. **Repère d'étiage calculé** : VCN3 quinquennal sec estimé (débit minimal sur 3 jours
   consécutifs atteint ou dépassé à la baisse une année sur cinq).
3. **Niveau de restriction sécheresse en vigueur** sur la zone de la station
   (vigilance → alerte → alerte renforcée → crise), avec lien vers l'arrêté.

Contexte : au 29/09/2026, VigiEau classe le Bessin (Seulles) et le Virois en **crise**,
Orne moyenne/aval (14) en **alerte renforcée**, Orne moyenne (61) en **crise**.

## 2. Décisions de cadrage (validées le 2026-09-29)

| Sujet | Décision |
|---|---|
| Source restriction | **Appel direct** du navigateur à `api.vigieau.gouv.fr` à chaque affichage (CORS `*` vérifié). Exception assumée et documentée à « les données ne changent que par commit » — précédent : le bouton « Actualiser » appelle déjà Hub'Eau en direct. Échec → encart « indisponible », jamais d'erreur bloquante. |
| Rattachement zone | Champ **`vigieau_zone`** par station dans `config/rivers.json` (code ZAS, ex. `28_14_0001`), type **SUP** (eaux superficielles) filtré côté code. |
| Seuils affichés | **Calculés uniquement** sur l'historique en cache (percentiles + VCN3 quinquennal). Aucun seuil préfectoral saisi à la main. |
| Tests | Logique extraite dans **`js/*.js`** (scripts classiques, sans dépendance), testée par des **pages `tests/*.test.html`** exécutées par Chrome headless via un lanceur **Python stdlib** ; `unittest` pour la config. Rien n'est ajouté au site livré hormis les deux fichiers JS. |

Décisions prises par défaut (à contester à la relecture si besoin) :

- L'encart suit la **station sélectionnée** (pas une station « de référence » par rivière).
- Station sans débit (`has_Q: false`) : percentile calculé sur la **hauteur** (`HIXnJ`),
  pas de VCN3.
- Fenêtre saisonnière : **± 7 jours** autour du même jour de l'année, toutes années
  sauf celle de la dernière mesure.
- Seuils de libellé alignés sur les bandes climato existantes : P10 / P25 / P75 / P90.
- Mesure « provisoire » = `quality` ≠ `"Bonne"` (valeurs observées dans les caches :
  `Bonne`, `Douteuse`, `Non qualifiée`, `null`).
- Dernière mesure de plus de **10 jours** → mention « dernière mesure le JJ/MM/AAAA ».
- Hors périmètre : n° 5 (fraîcheur/automatisation) et n° 6 (indicateurs d'étiage
  annuels, ONDE) du `TODO.md` ; ajout au gate CI (`deploy.yml`) des nouveaux tests.

## 3. API VigiEau (vérifiée le 2026-09-29)

- `GET https://api.vigieau.gouv.fr/api/zones/departement/<dept>` → tableau des zones
  **ayant un arrêté en vigueur**. Champs utiles : `code` (= `CdZAS`), `nom`, `type`
  (`SUP` | `SOU` | `AEP`), `niveauGravite` (`vigilance` | `alerte` |
  `alerte_renforcee` | `crise`), `arrete.dateFinValidite`, `arrete.cheminFichier` (PDF).
- Un même `code` peut apparaître en `SUP` **et** `AEP` → filtrer `type === 'SUP'`.
- Zone absente de la réponse ⇒ **aucune restriction en vigueur** (à confirmer en phase
  Collecte : l'agent note si une zone connue manque alors qu'aucune restriction n'est
  attendue).
- Pas d'endpoint par code de zone (`/api/zones/<code>` → 400).
- `GET /api/zones?commune=<INSEE>&profil=particulier` → zones d'une commune
  (utilisé **uniquement** en phase Collecte pour trouver les codes).
- Codes commune des stations : Hub'Eau
  `/api/v2/hydrometrie/referentiel/stations?code_station=<code>&fields=code_commune_station`.

## 4. Contrats d'interface (figés — les agents parallèles s'y conforment)

### 4.1 `js/situation.js` — calculs purs (aucun DOM, aucun `fetch`)

Script classique (pas de module ES), fonctions globales, comme le code existant.
Chargé par `index.html` **avant** le `<script>` inline.

```js
// Déplacé depuis index.html (même signature, même comportement) :
computePercentiles(values, percentiles)            // → {p: value} | null

latestValidRecord(records)                          // → {date, value, quality} | null
sameSeasonValues(records, refDateIso, halfWindowDays)
  // → number[] : valeurs des AUTRES années dont le jour de l'année est à
  //   ± halfWindowDays de refDate (gère le passage déc./janv. et le 29 février)
percentileRank(values, value)                       // → 0..100 | null (ex æquo : demi-rang)
classifyPercentile(rank)
  // → 'tres_bas' (<10) | 'bas' (<25) | 'normal' (≤75) | 'haut' (≤90) | 'tres_haut' | null
annualMinMovingAverage(records, windowDays, minDaysPerYear)
  // → [{year, value}] ; moyenne mobile sur jours CALENDAIRES consécutifs
  //   (un trou casse la fenêtre) ; année ignorée si < minDaysPerYear valeurs
dryReturnPeriodLowFlow(annualMins, returnPeriodYears)
  // → quantile empirique 1/T des minima annuels (T=5 → P20) ; null si < 10 années
dataAgeDays(latestDateIso, todayIso)                // → entier ≥ 0
computeSituation(records, { todayIso, halfWindowDays = 7, withLowFlow })
  // → { latest, rank, category, sampleSize, lowFlowDry5 (null si !withLowFlow),
  //     ageDays, isProvisional }  |  null si aucune donnée
```

### 4.2 `js/vigieau.js` — client VigiEau (aucun DOM)

```js
VIGIEAU_LEVELS  // { vigilance: {label:'Vigilance', severity:1}, alerte: {…2},
                //   alerte_renforcee: {label:'Alerte renforcée', severity:3},
                //   crise: {label:'Crise', severity:4} }
zoneDepartment(zoneCode)          // '28_14_0001' → '14' ; '28_2A_0003' → '2A' ; invalide → null
pickSurfaceZone(zones, zoneCode)  // → zone de type 'SUP' portant ce code | null
safeHttpsUrl(url)                 // → url si elle commence par 'https://', sinon null
async fetchRestriction(zoneCode, { fetchFn = fetch, timeoutMs = 8000 } = {})
  // Ne lève JAMAIS. Retourne :
  //  { status: 'restricted', level, label, severity, zoneName, validUntil, decreeUrl }
  //  { status: 'none' }                        (zone absente de la réponse)
  //  { status: 'unavailable', reason }         (HTTP ≠ 2xx, timeout, JSON invalide, code invalide)
  // Mémoïse la réponse par département pour la session (succès uniquement).
```

### 4.3 `index.html` — intégration

- `<script src="js/situation.js"></script>` et `<script src="js/vigieau.js"></script>`
  après Chart.js, avant le script inline ; suppression de `computePercentiles` inline.
- Encart `#situation-panel` créé en tête de `buildHydroTab()` via `createEl` uniquement.
- `updateSituation()` appelée à la fin de `switchStation()` ; **jeton de requête** pour
  ignorer une réponse VigiEau arrivée après un changement de station ou de rivière.
- Affichage :
  - Ligne 1 : « Débit du JJ/MM : X m³/s — **bas** pour la saison (rang P18, N valeurs) ».
    Débit converti L/s → m³/s pour l'affichage ; hauteur en mm si `has_Q: false`.
    Mention « (provisoire) » si `isProvisional` ; « dernière mesure le … » si `ageDays > 10`.
  - Ligne 2 : « Repère d'étiage (VCN3 quinquennal sec estimé) : Y m³/s » + position
    du débit actuel par rapport à ce repère. Absente si non calculable.
  - Ligne 3 : pastille de niveau VigiEau + nom de zone + « jusqu'au JJ/MM/AAAA » +
    lien « Arrêté (PDF) » (si `safeHttpsUrl`) + lien permanent `https://vigieau.gouv.fr`.
    `none` → « Aucune restriction en vigueur » ; `unavailable` → « Niveau de restriction
    indisponible » ; pas de `vigieau_zone` → ligne absente.
- Styles : classes `.situation-*`, couleurs via nouveaux tokens `:root`
  (`--level-vigilance`, `--level-alerte`, `--level-alerte-renforcee`, `--level-crise`)
  cohérents avec la palette sombre existante ; libellé textuel toujours présent
  (pas d'information portée par la couleur seule).
- Textes en français **accentué** ; aucun texte propre à une rivière (règle `narrative`).

### 4.4 `config/rivers.json`

Ajout de `"vigieau_zone": "28_14_0001"` (optionnel) sur chaque station hydro.

## 5. Tests

| Fichier | Type | Contenu |
|---|---|---|
| `tests/js/harness.js` | outil | Mini-harnais sans dépendance : `test(name, fn)` (sync/async), `assertEqual`, `assertClose`, `assertTrue` ; écrit le bilan dans `<pre id="test-results" data-status="pass\|fail">` (+ détail des échecs). |
| `tests/situation.test.html` | unitaire | Chaque fonction de §4.1 : cas nominal, tableau vide, `null`/valeurs manquantes, passage déc./janv., 29 février, ex æquo, trous dans la moyenne mobile, < 10 années, année incomplète, `todayIso` antérieur. Données synthétiques Arrange-Act-Assert. |
| `tests/vigieau.test.html` | unitaire | `fetchFn` simulé : zone SUP trouvée, zone AEP seule ignorée, zone absente → `none`, HTTP 500, JSON invalide, timeout (promesse jamais résolue + `AbortSignal`), code invalide, URL `http://`/`javascript:` rejetée, mémoïsation par département (1 seul appel pour 2 zones du 14), échec non mémoïsé. |
| `tests/situation.integration.test.html` | intégration | Charge `data_cache/seulles/I403201001_QmnJ.json` : `lowFlowDry5` ∈ [200, 350] L/s (référence Banque Hydro : 270 L/s) ; `data_cache/odon/I371201001_QmnJ.json` : ∈ [5, 60] L/s (référence 15 L/s) ; `computeSituation` non nul pour chaque station de chaque rivière. |
| `tests/smoke.test.html` | bout en bout | Charge `index.html` dans une iframe (même origine), parcourt **chaque** rivière du sélecteur (`change`), attend l'encart, vérifie : lignes 1–2 présentes quand `has_Q`, ligne 3 dans l'un des 3 états, aucune erreur capturée (`window.onerror` + `unhandledrejection` de l'iframe). Indépendant de l'état réel de VigiEau. |
| `tests/run_browser_tests.py` | lanceur | Stdlib : `http.server` sur port libre (thread) à la racine du dépôt ; Chrome via `$CHROME_BIN` puis chemins macOS/Linux usuels ; `--headless=new --dump-dom --timeout=15000` par page, `subprocess` timeout 60 s ; parse `data-status` ; code retour ≠ 0 si échec ou page sans bilan. |
| `tests/test_browser.py` | unittest | Enveloppe le lanceur (une méthode par page) ; `skipTest` **explicite** si Chrome introuvable. |
| `tests/test_rivers_config.py` | unittest | `vigieau_zone` **quand présent** : format `^\d+_[0-9AB]{2,3}_\d{4}$`, département du code = `dept` de la station. (Complétude non testée : une zone introuvable est omise et signalée par le workflow.) |

Commande unique : `python3 -m unittest` (déjà prévue par `CLAUDE.md`).

Note : Chrome headless s'est bloqué avec `--virtual-time-budget` lors de l'ajout de
la Seulles ; `--timeout` + timeout `subprocess` ont fonctionné.

## 6. Documentation

- `CLAUDE.md` : carte du dépôt (`js/`, `tests/`, `docs/plans/`), « Dashboard
  mono-fichier » → « + `js/situation.js`, `js/vigieau.js` » ; contrat (`vigieau_zone`) ;
  règle d'exception VigiEau en direct ; section « Vérifier son travail » :
  `python3 -m unittest` ; workflow « Ajouter un cours d'eau » : trouver `vigieau_zone`.
- `README.md` : une phrase sur l'encart et la source VigiEau (licence à vérifier par
  l'agent — mentionner la source).
- `TODO.md` : n° 4 coché à la fin (par la session principale, après relecture).

## 7. Risques

| Risque | Parade |
|---|---|
| API VigiEau non contractuelle (schéma qui change) | Client défensif, état `unavailable`, tests sur JSON inattendu. |
| Codes ZAS renouvelés avec un nouvel arrêté-cadre | Zone absente ⇒ « aucune restriction » affiché à tort : documenté dans `CLAUDE.md` (revérifier les codes à chaque printemps) ; la phase Collecte consigne la date de vérification. |
| VCN3 empirique ≠ VCN3 officiel (ajustement de loi) | Libellé « estimé » ; test d'intégration avec tolérance vs valeur Banque Hydro. |
| Réponse tardive après changement de station | Jeton de requête (§4.3), testé dans le smoke test par un changement rapide. |
| Agents parallèles qui se marchent dessus | Fichiers **disjoints** par agent en phase Implémentation ; `index.html` touché par un seul agent, après. |

## 8. Exécution par workflow

### 8.1 Pré-requis (session principale, avant lancement)

1. Relecture et validation de ce plan par l'utilisateur.
2. `git status` propre ; vérifications existantes de `CLAUDE.md` (JSON, `grep data_cache/`,
   `py_compile`) au vert → état de référence.

### 8.2 Phases, agents et modèles

Budget : **9 agents** (11 au maximum si une boucle de correction est nécessaire).

| Phase | Agent | Modèle / effort | Critique ? | Fichiers écrits |
|---|---|---|---|---|
| 1. Collecte | `collect-zones` : station → commune INSEE (Hub'Eau) → code ZAS `SUP` (VigiEau) | haiku / low | non | aucun (sortie structurée) |
| 2. Implémentation (parallèle) | `impl-situation` : `js/situation.js` + `tests/situation.test.html` + `tests/js/harness.js` | sonnet / medium | moyen | ces 3 fichiers |
| | `impl-vigieau` : `js/vigieau.js` + `tests/vigieau.test.html` | sonnet / medium | moyen | ces 2 fichiers |
| | `impl-runner` : `tests/run_browser_tests.py`, `tests/test_browser.py`, `tests/test_rivers_config.py` | sonnet / low | non | ces 3 fichiers |
| | `impl-config-docs` : `vigieau_zone` dans `rivers.json` + `CLAUDE.md` + `README.md` | haiku / low | non | ces 3 fichiers |
| 3. Intégration | `impl-ui` : `index.html` (§4.3) + `tests/situation.integration.test.html` + `tests/smoke.test.html` | sonnet / high | moyen | ces 3 fichiers |
| 4. Vérification (parallèle) | `run-checks` : `python3 -m unittest -v` + vérifications `CLAUDE.md` 1-3 | haiku / low | non | aucun |
| | `review` : revue adversariale (exactitude hydrologique, contrats §4, règles `CLAUDE.md` : `createEl`, `riverDataPath`, zéro dépendance, texte générique ; XSS sur URL externes ; jeton de requête ; qualité des tests) | **modèle de session / high** | **oui** | aucun |
| 5. Correction (si besoin, 1 boucle max) | `fix` puis `run-checks` | sonnet / medium puis haiku / low | — | fichiers concernés |

La collecte n'écrit rien : son résultat est passé en argument à `impl-config-docs`.
Aucun agent ne commit ni ne push. Pas d'isolation `worktree` : fichiers disjoints.

### 8.3 Script

```js
export const meta = {
  name: 'situation-actuelle',
  description: 'Implémente l\'encart « Situation actuelle » (TODO n° 4) selon docs/plans/situation-actuelle.md',
  phases: [
    { title: 'Collecte', detail: 'codes de zone VigiEau par station', model: 'haiku' },
    { title: 'Implémentation', detail: 'js/situation.js, js/vigieau.js, lanceur de tests, config + docs', model: 'sonnet' },
    { title: 'Intégration', detail: 'index.html + tests d\'intégration et smoke', model: 'sonnet' },
    { title: 'Vérification', detail: 'tests + revue adversariale' },
    { title: 'Correction', detail: 'une boucle au plus', model: 'sonnet' },
  ],
}

const PLAN = 'docs/plans/situation-actuelle.md'
const TODAY = args.todayIso   // passé par la session principale, ex. '2026-09-29'

const ZONES_SCHEMA = { type: 'object', required: ['stations'], properties: { stations: { type: 'array', items: {
  type: 'object', required: ['river', 'code', 'commune', 'zone', 'zone_name', 'note'],
  properties: { river: {type:'string'}, code: {type:'string'}, commune: {type:'string'},
    zone: {type:['string','null']}, zone_name: {type:['string','null']}, note: {type:'string'} } } } } }
const DONE_SCHEMA = { type: 'object', required: ['files', 'summary', 'open_issues'], properties: {
  files: {type:'array', items:{type:'string'}}, summary: {type:'string'},
  open_issues: {type:'array', items:{type:'string'}} } }
const CHECKS_SCHEMA = { type: 'object', required: ['passed', 'failures'], properties: {
  passed: {type:'boolean'}, failures: {type:'array', items:{type:'string'}}, output_tail: {type:'string'} } }
const REVIEW_SCHEMA = { type: 'object', required: ['blocking'], properties: { blocking: { type: 'array', items: {
  type: 'object', required: ['file', 'problem', 'fix'],
  properties: { file:{type:'string'}, problem:{type:'string'}, fix:{type:'string'} } } },
  minor: {type:'array', items:{type:'string'}} } }

const implPrompt = (section, files) =>
  `Lis ${PLAN} en entier. Implémente ${section}. Tu n'écris QUE ces fichiers : ${files}. ` +
  `Respecte exactement les signatures du plan (d'autres agents codent en parallèle contre elles). ` +
  `Lance les tests qui te concernent si le lanceur existe déjà, sinon vérifie au moins la syntaxe. ` +
  `Ne commit pas. Rends la liste des fichiers écrits et les points ouverts.`

phase('Collecte')
const zones = await agent(
  `Pour chaque station hydro de config/rivers.json : 1) code commune INSEE via ` +
  `https://hubeau.eaufrance.fr/api/v2/hydrometrie/referentiel/stations?code_station=<code>&fields=code_commune_station ; ` +
  `2) zones via https://api.vigieau.gouv.fr/api/zones?commune=<INSEE>&profil=particulier ; retiens la zone type "SUP". ` +
  `Si aucune zone SUP : regarde /api/zones/departement/<dept> et propose la zone du même secteur par son nom, ` +
  `en l'indiquant dans "note" ; sinon zone=null. N'écris aucun fichier. curl + jq uniquement.`,
  { label: 'collect-zones', phase: 'Collecte', model: 'haiku', effort: 'low', schema: ZONES_SCHEMA })
const missing = zones.stations.filter(s => !s.zone)
if (missing.length) log(`Zones introuvables : ${missing.map(s => s.code).join(', ')} (champ omis, à compléter)`)

phase('Implémentation')
const impl = await parallel([
  () => agent(implPrompt('§4.1 et la ligne situation.test.html + harness.js du §5',
      'js/situation.js, tests/situation.test.html, tests/js/harness.js'),
    { label: 'impl-situation', phase: 'Implémentation', model: 'sonnet', effort: 'medium', schema: DONE_SCHEMA }),
  () => agent(implPrompt('§4.2 et la ligne vigieau.test.html du §5 (le harnais tests/js/harness.js est écrit en parallèle ' +
      'par un autre agent selon le §5 : utilise uniquement test/assertEqual/assertClose/assertTrue)',
      'js/vigieau.js, tests/vigieau.test.html'),
    { label: 'impl-vigieau', phase: 'Implémentation', model: 'sonnet', effort: 'medium', schema: DONE_SCHEMA }),
  () => agent(implPrompt('les lignes run_browser_tests.py, test_browser.py et test_rivers_config.py du §5',
      'tests/run_browser_tests.py, tests/test_browser.py, tests/test_rivers_config.py'),
    { label: 'impl-runner', phase: 'Implémentation', model: 'sonnet', effort: 'low', schema: DONE_SCHEMA }),
  () => agent(implPrompt('§4.4 et §6 (hors TODO.md). Codes de zone à utiliser : ' + JSON.stringify(zones.stations) +
      '. Omets vigieau_zone pour une station dont zone=null. Conserve la mise en forme existante de rivers.json',
      'config/rivers.json, CLAUDE.md, README.md'),
    { label: 'impl-config-docs', phase: 'Implémentation', model: 'haiku', effort: 'low', schema: DONE_SCHEMA }),
])
if (impl.some(r => !r)) throw new Error('Un agent d\'implémentation a échoué : arrêt avant intégration')

phase('Intégration')
const ui = await agent(implPrompt('§4.3 et les lignes situation.integration.test.html et smoke.test.html du §5. ' +
    'Pour l\'aperçu local, python3 -m http.server. Points ouverts des agents précédents : ' +
    JSON.stringify(impl.flatMap(r => r.open_issues)),
    'index.html, tests/situation.integration.test.html, tests/smoke.test.html'),
  { label: 'impl-ui', phase: 'Intégration', model: 'sonnet', effort: 'high', schema: DONE_SCHEMA })

const runChecks = (label) => agent(
  `Exécute et rapporte fidèlement (sans rien corriger) : python3 -m unittest -v ; puis les vérifications 1 à 3 ` +
  `de la section « Vérifier son travail » de CLAUDE.md. passed=true seulement si tout est vert et qu'aucun test ` +
  `n'est ignoré (skip) faute de Chrome.`,
  { label, phase: label.startsWith('re') ? 'Correction' : 'Vérification', model: 'haiku', effort: 'low', schema: CHECKS_SCHEMA })

phase('Vérification')
const [checks, review] = await parallel([
  () => runChecks('run-checks'),
  () => agent(
    `Revue adversariale de git diff (et des fichiers non suivis) contre ${PLAN}. Cherche à PROUVER que c'est faux : ` +
    `définitions hydrologiques (VCN3, quantile 1/T, fenêtre saisonnière, 29 février, trous), respect exact des contrats §4, ` +
    `règles CLAUDE.md (createEl sans innerHTML, riverDataPath + no-cache, zéro dépendance, aucun texte propre à une rivière), ` +
    `URL externes non https, jeton de requête, tests réellement déterministes et couvrant les cas d'erreur du §5. ` +
    `N'édite rien. "blocking" = défaut réel et reproductible uniquement ; le reste dans "minor".`,
    { label: 'review', phase: 'Vérification', effort: 'high', schema: REVIEW_SCHEMA }),
])

let final = checks
if (!checks?.passed || !review || review.blocking.length) {
  phase('Correction')
  await agent(
    `Corrige ces problèmes sans élargir le périmètre de ${PLAN}. Échecs de tests : ${JSON.stringify(checks?.failures)}. ` +
    `Défauts bloquants de la revue : ${JSON.stringify(review?.blocking)}. Ne commit pas.`,
    { label: 'fix', phase: 'Correction', model: 'sonnet', effort: 'medium', schema: DONE_SCHEMA })
  final = await runChecks('re-run-checks')
}

return { zones: zones.stations, impl, ui, checks: final, review, today: TODAY }
```

Lancement (session principale) : `Workflow({ script, args: { todayIso: '<date du jour>' } })`.

### 8.4 Après le workflow (session principale)

1. Lire le retour : `checks.passed`, `review.minor`, zones manquantes.
2. **Vérification visuelle** exigée par `CLAUDE.md` : servir en local, basculer sur
   chaque rivière et chaque station, console sans erreur ; capture de l'encart pour
   la Seulles (crise attendue au 29/09/2026).
3. Si `checks.passed` est faux après la boucle de correction : **arrêt**, rapport à
   l'utilisateur, pas de commit.
4. Proposer les commits (sans push) :
   - `feat: encart « Situation actuelle » (débit vs saison, VCN3, restrictions VigiEau)`
     — `js/`, `index.html`, `config/rivers.json`, `tests/` ;
   - `docs: documente l'encart Situation actuelle et les tests navigateur`
     — `CLAUDE.md`, `README.md`, `TODO.md`, `docs/plans/`.
