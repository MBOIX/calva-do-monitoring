---
description: Met à jour les données Hub'Eau (hydro + qualité), valide les caches et committe
argument-hint: [id-rivière] [--since YYYY-MM-DD]
---

Mets à jour les données du dashboard depuis les API Hub'Eau, valide les caches, puis committe.

Arguments reçus : `$ARGUMENTS`
— un id de rivière (`orne`, `odon`, …) et/ou `--since YYYY-MM-DD`, à répercuter sur les deux
scripts. Sans argument : toutes les rivières de `config/rivers.json`, en incrémental.

## Étapes

1. **Récupération des données** (Python stdlib, aucune dépendance) :

   ```bash
   python3 scripts/fetch_hydro_data.py [--river <id>] [--since <date>]
   python3 scripts/fetch_quality_data.py [--river <id>] [--since <date>]
   ```

   Si un appel API échoue (réseau, Hub'Eau indisponible), signale-le et arrête-toi :
   ne committe jamais des données partielles.

2. **Validation** (invariants de CLAUDE.md) :
   - Tous les JSON parsent :
     `find config data_cache -name '*.json' -print0 | xargs -0 -I{} python3 -m json.tool {} > /dev/null`
   - Cohérence `config/rivers.json` ↔ `data_cache/` : chaque `id` a son dossier ;
     un `<code>_HIXnJ.json` par station hydro ; `has_Q: true` ⇒ `<code>_QmnJ.json` présent,
     `has_Q: false` ⇒ absent ; chaque `<code>_quality.json` couvre les 5 codes SANDRE
     `1311, 1302, 1340, 1339, 1335`.
   - Garde-fou : `grep -n "data_cache/" index.html` ne doit matcher que `riverDataPath`.

3. **Revue du diff** avant commit :
   - Les séries s'allongent (nouvelles dates en fin de fichier), aucune suppression
     massive de mesures existantes.
   - Dates au format `YYYY-MM-DD`, fichiers de mesures restés compacts (pas de réindentation).
   - S'il n'y a **aucune donnée nouvelle**, dis-le et arrête-toi (pas de commit vide).

4. **Commit** (conventionnel, en français) :
   - Message type : `data: rafraîchit les caches hydrométrie et qualité`, en précisant
     rivières et période si pertinent
     (ex. `data: rafraîchit les caches hydro + qualité de l'Orne (jusqu'au 2026-08-18)`).
   - Ne committe que `data_cache/` (et `config/rivers.json` seulement s'il a été
     modifié volontairement).
   - **Ne pousse pas** : le push sur `main` déclenche le déploiement GitHub Pages.
     Propose la commande `git push` et laisse-moi décider.

5. **Compte-rendu** : résume par rivière ce qui a été mis à jour (stations, plages de
   dates, nombre de mesures ajoutées) et tout point d'attention (station muette,
   paramètre qualité manquant, valeur aberrante…).

## Agents & modèles

- **Orchestration** : reste dans la session principale (modèle par défaut, ne pas surcharger).
- **Étape 1 (fetch)** : séquentielle et mécanique — exécute les scripts directement,
  sans sous-agent.
- **Étape 2 (validation)** : si plusieurs rivières, délégable à des sous-agents économiques
  en parallèle (`haiku` ou `sonnet`, `effort: low`, une rivière par agent) ; pour une seule
  rivière, exécute les vérifications directement.
- **Étape 3 (revue du diff)** : jugement critique avant commit — reste sur le modèle de
  session, jamais un tier inférieur.
