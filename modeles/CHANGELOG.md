# Changelog

<!--
  MODÈLE — CHANGELOG.md (à la racine du dépôt). Ce qui a été LIVRÉ.
  Écrit par le développeur, dans le même commit que la release, avant de poser le tag Git.

  Règles :
  1. Une version = un titre « ## [X.Y.Z] - AAAA-MM-JJ », la plus récente en haut (sans « v »).
     Le numéro est le même que le tag Git (tag : vX.Y.Z, ex. v2.0.2).
  2. Numérotation SemVer : X majeur (rupture / refonte), Y mineur (nouvelle fonction), Z correctif (bug).
  3. Sous chaque version, uniquement ces sections (ne garder que celles qui servent) :
       ### Added    nouveautés
       ### Changed  modifications d'un comportement existant
       ### Fixed    corrections de bugs
       ### Removed  suppressions
  4. Une ligne = un changement, en français, compréhensible par un utilisateur du banc
     (pas « refacto du module X » mais ce que ça change pour lui).
  5. Pendant le développement, écrire au fil de l'eau sous « ## [Unreleased] ».
     Au moment de livrer : renommer en « ## [X.Y.Z] - date du jour », puis tag Git.
  6. Ne jamais modifier une version déjà livrée (sauf faute de frappe).

  Supprimer ce commentaire et l'exemple ci-dessous en reprenant le modèle.
-->

## [Unreleased]
### Added
- Fonction en cours de développement, pas encore livrée

## [1.1.0] - 2026-10-05
### Added
- Marquage des captures d'écran dans le rapport
### Fixed
- Correction du total des mesures dans le rapport PDF

## [1.0.0] - 2026-04-02
### Added
- Première version livrée en production
