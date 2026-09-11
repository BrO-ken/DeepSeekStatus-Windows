# 🐳 DeepSeek Status pour Windows 11

Adaptation Windows de [DeepSeekStatus](https://github.com/owenzhao/DeepSeekStatus) (macOS, MIT © Zhao Xin) :
une baleine dans la **zone de notification** qui indique en permanence si DeepSeek est
en **plein tarif** (baleine bleue éveillée) ou en **heures creuses** (baleine grise endormie),
avec un panneau de détails au design Fluent sombre.

## Règle horaire — vérifiée sur la doc officielle

Source : [api-docs.deepseek.com/quick_start/pricing](https://api-docs.deepseek.com/quick_start/pricing)
(consulté le 11/09/2026) — *« Off-peak rates are half of the peak rates. Peak hours are
01:00 - 04:00 and 06:00 - 10:00 UTC, Monday through Friday »*.

| Heure de Pékin (UTC+8) | Heure UTC | Période | Prix |
|---|---|---|---|
| Lun–Ven 09:00–12:00 | 01:00–04:00 | Plein | 100 % |
| Lun–Ven 12:00–14:00 | 04:00–06:00 | Creux | 50 % |
| Lun–Ven 14:00–18:00 | 06:00–10:00 | Plein | 100 % |
| Soirs, nuits, week-end | — | Creux | 50 % |

- Bornes **semi-ouvertes** : à 12:00 et 18:00 pile, on est déjà en heures creuses ;
  à 09:00 pile, déjà en plein.
- La décision est **toujours prise en heure de Pékin** (pas d'heure d'été), quel que soit
  le fuseau du PC. Les jours fériés ne font pas partie de la règle (comme chez DeepSeek).

## Fonctions

- 🐳 Icône dans la zone de notification : bleue en plein tarif, grise en heures creuses.
- Info-bulle permanente : période + compte à rebours (« … · 02:31:05 avant 12:00 »).
- Panneau (clic gauche sur la baleine) : aquarium animé (baleine qui nage / dort),
  compte à rebours géant, progression du bloc en cours, barres de prix ×1,0 / ×0,5,
  **heatmap 7×24** de la semaine type, note de fuseau.
- **Aperçu** : forcer l'affichage plein / creux (n'affecte jamais le calcul réel).
- **Démarrer avec Windows** (clé `HKCU\...\Run`, opt-in).
- Instance unique, aucun réseau, aucun compte, aucune donnée collectée.

## Utilisation

- **Clic gauche** sur la baleine : ouvre/masque le panneau.
- **Clic droit** : aperçu, démarrage avec Windows, quitter.
- **Échap** ou ✕ : ferme le panneau.

## Lancer

- Version empaquetée : `dist\DeepSeekStatus.exe` (aucune installation).
- Depuis les sources : `venv\Scripts\python app.py` (ou `--show` pour ouvrir le panneau au lancement).

## Vérifier la règle

```
venv\Scripts\python tests\test_schedule.py
```

27 vérifications : bornes 08:59/09:00/11:59/12:00/13:59/14:00/17:59/18:00, week-end,
pont vendredi→lundi, secondes restantes, indépendance des fuseaux (UTC/New York/Tokyo),
conformité heure par heure à la règle officielle UTC, progression dans le bloc.

## Construire l'exécutable

```
Tools\build_exe.cmd        → dist\DeepSeekStatus.exe
```

## Crédits

- Projet original macOS : [owenzhao/DeepSeekStatus](https://github.com/owenzhao/DeepSeekStatus) (MIT).
- La baleine est la marque officielle de DeepSeek, tracée d'après le vectoriel
  [Simple Icons](https://simpleicons.org/) (CC0). Projet non officiel, non affilié à DeepSeek.
- Licence MIT (voir `LICENSE`).
