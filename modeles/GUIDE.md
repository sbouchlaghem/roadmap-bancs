# Standard des dépôts ( versions et CHANGELOG )

## 1. À la racine de chaque dépôt

| Élément | Rôle |
|---|---|
| `README.md` | ce qu'est le projet, comment l'installer et l'utiliser |
| `CHANGELOG.md` | ce qui a été **livré**, version par version |
| tag Git `vX.Y.Z` | le commit exact de chaque version livrée |
| `ROADMAP.md` | les versions **à venir** et leurs fonctionnalités prévues |

## 2. Numéro de version — SemVer `X.Y.Z`

La question à se poser : **le banc sait-il faire quelque chose de nouveau ?**

| Cas | Exemple | Avant → après |
|---|---|---|
| Il fait mieux ce qu'il faisait déjà → **patch** | mesure de tension fausse corrigée, plantage corrigé | 2.0.2 → **2.0.3** |
| Il sait faire quelque chose de nouveau → **mineure** | nouveau scénario, nouvelle mesure de tension | 2.0.2 → **2.1.0** |
| Les anciennes configs / fichiers ne marchent plus → **majeure** | nouvelle base, config à refaire | 2.1.0 → **3.0.0** |

- Plusieurs changements dans une livraison : le plus fort l'emporte (nouveau scénario + 2 bugs = **2.1.0**).
- Quand Y monte, Z repart à 0 ; quand X monte, Y et Z repartent à 0.
- Toujours 3 nombres. `0.x.y` = prototype, `1.0.0` = première version en production.

## 3. CHANGELOG.md — Keep a Changelog

```markdown
# Changelog

## [Unreleased]
### Added
- Scénario de cyclage thermique

## [2.1.0] - 2026-10-05
### Added
- Mesure de tension sur la voie 3
### Fixed
- Total des mesures faux quand une voie est désactivée

## [2.0.2] - 2026-06-12
### Fixed
- Plantage au démarrage si l'imprimante n'est pas branchée
```

- Version la plus récente en haut, date au format `AAAA-MM-JJ`.
- `[Unreleased]` en haut : on y note les changements au fil de l'eau.
- Sections, uniquement celles qui servent : `Added` (nouveau), `Changed` (modifié),
  `Deprecated` (bientôt supprimé), `Removed` (supprimé), `Fixed` (corrigé), `Security` (faille corrigée).
- Une ligne = un changement.
- On ne modifie jamais une version déjà livrée.

## 4. Livrer une version

1. Renommer `## [Unreleased]` en `## [2.2.0] - 2026-11-05` et remettre un `## [Unreleased]` vide au-dessus.
2. Commit et tag :

```bash
git commit -am "Release v2.2.0"
git tag -a v2.2.0 -m "v2.2.0"
git push && git push --tags
```

Même numéro partout : `[2.2.0]` dans le CHANGELOG, `v2.2.0` pour le tag. Pas de livraison sans tag.

## 5. ROADMAP.md — les versions à venir

Le CHANGELOG dit ce qui est livré, la ROADMAP ce qui est prévu.

```markdown
## [2.2.0] - 2026-10-06 → 2026-11-05
- Scénario de cyclage thermique

## [2.1.0] - 2026-09-01 → 2026-10-05
- Mesure de tension sur la voie 3
```

Dates : `AAAA-MM-JJ`, `AAAA-MM` ou `?`. Pas de statut, l'outil le déduit des dates et du tag. Seule exception : `## [2.3.0] - Bloqué (attente cartes) - 2027-01 → 2027-02`, avec le motif entre parenthèses.

`(prévu …)` après la fin est ajouté par l'outil Roadmap quand la date de fin change : ne pas l'effacer, il mesure la dérive.

Le bouton **🚀 Livrer** de l'outil Roadmap fait l'étape 4 ci-dessus (sauf le `git push`).
