# Changelog

## [Unreleased]
### Added
- 📦 En production : une ligne par poste et une colonne « Poste » (le nom du poste n'est plus répété dans État et En production)
- Période du Gantt (Du / au) : bouton 📅 calendrier des mois (Chrome / Edge)
- Fiche projet : bouton 📅 calendrier sur les dates de début et de fin des versions (la saisie au clavier reste possible : AAAA-MM, ?)
- Alerte « livrée, pas encore déployée » en haut de la Roadmap (par version, avec les postes concernés) ; clic : onglet 📦 En production
- État en production : date du changement (« 🔧 En mise à jour · depuis le 10/11/2026 ») au lieu d'une durée
- 📦 En production : filtre par pôle (bancs de dev, de prod…), repris par le CSV ; « à déployer » visible seulement dans l'application, pas sur les pages publiées
- Postes : chaque poste a sa propre version en production (📦 En production, CSV, page publiée), avec son « à déployer » ; installer une version sur un poste « en mise à jour » ne repasse que ce poste en opérationnel
- Paquet .deb : la mise à jour arrête l'instance déjà lancée (elle gardait l'ancien code : nouveaux champs ignorés sans message, ex. Postes)
- Bouton « ⤓ Importer tout » : importe les dépôts de tous les projets à la suite, résumé des échecs à la fin
- Conformité au standard des dépôts sur chaque carte projet (ROADMAP.md, CHANGELOG.md, tags Git, constatée au dernier import) et filtre « Non conformes au standard »
- Période du Gantt : mois affichés en français (« septembre 2026 ») quelle que soit la langue du navigateur
- Légende : échantillons de statut dessinés comme les barres du Gantt (couleur du pôle, foncée ou vive)
- Filtres du Gantt par pôle et par statut (dont « ⚠ Bloqué ou en retard »), repris par l'export PPT et draw.io
- Versions sans dates : pastilles cliquables (ouvrent la fiche) dans un bloc repliable, au lieu d'une longue phrase
- Petit écran : colonne des noms plus étroite, pôles et noms restent visibles quand on fait défiler le Gantt
- Le trait « Aujourd'hui » passe sous le numéro des versions au lieu de le barrer
- Windows : lanceur `lancer.bat` (données dans %APPDATA%\roadmap-bancs)
- **Postes** : un banc qui tourne sur plusieurs postes (fiche projet → Postes) a un état par poste dans 📦 En production, la page publiée et le CSV ; la carte du projet montre l'état le plus grave. Sans poste : rien ne change
- Les enregistrements passent un par un : deux modifications rapprochées ne s'écrasent plus
- Bouton « 🚀 Livrer » sur une version : statut Terminé, fin = aujourd'hui, ROADMAP.md + CHANGELOG.md écrits, commit « Release vX.Y.Z » et tag (sans push)
- Dérive : quand la fin d'une version change, l'outil demande s'il s'agit d'un **décalage du planning** (ancienne date gardée comme date prévue, écart affiché sur le Gantt, la fiche, la carte, le PPT) ou d'une **correction de saisie** (pas de dérive) ; ✕ pour effacer une date prévue erronée ; import (tag) et livraison comptent comme décalage
- Motif du blocage : « Bloqué (attente cartes) », affiché sur le Gantt, les cartes et dans les alertes
- Jalons communs (salons, audits…) : ajout sous le Gantt, trait vertical sur le Gantt et le PPT
- Bouton « ⇪ Publier » : page HTML autonome en lecture seule pour l'équipe : le Gantt de la période choisie, versions à venir seulement (comme le PPT), clic sur une barre : ce qu'apporte la version (Nouveautés, Corrections…), statut, dates, motif, dérive
- Page publiée sur la Raspberry : se recharge seule dans la minute qui suit une nouvelle publication
- Publication sur une Raspberry (ou tout serveur Debian / Ubuntu) : « ⇪ Publier » envoie la page par SSH, consultable par tous à tout moment
- Dépôt d'un projet par **lien Git + branche** (en plus du dossier local) : liste des branches, import du ROADMAP.md / CHANGELOG.md de la branche et des tags, sans clone manuel
- Page publiée : « Aujourd'hui » et les statuts (Planifié → En cours → En retard) avancent chaque jour sans republier ; versions terminées de la période affichées (réglable dans ⚙ Paramètres)
- **Équipe** d'un projet (qui travaille dessus), et au besoin d'une version (vide = équipe du projet) : fiche, cartes, survol du Gantt, détail de la page publiée ; recherche par personne
- **Mise en production** d'une version livrée : marqueur ▲ sur le Gantt, mention dans le détail ; gardée dans l'application (pas dans les ROADMAP.md), conservée à l'import
- Onglet **📦 En production** (application et page publiée) : par projet, état, version en production et depuis quand, « ⚠ vX à déployer » si une version plus récente est livrée, prochaine version
- Export **⬇ CSV** du tableau production (application et page publiée, ouvrable dans Excel) et **⬇ draw.io** de la roadmap (fichier `.drawio` modifiable)
- Publication en **deux pages** : la complète (roadmap + production) et `production.html`, seulement la vue production pour l'équipe prod
- Vue production : clic sur une version (en production, à déployer, prochaine) → ce qu'elle apporte (Nouveautés, Corrections…)
- Vue production : date de mise en production proposée = date de livraison de la version ; « opérationnel depuis » proposé = date de mise en production (modifiables)
- **État** d'un banc / outil : ✅ Opérationnel, 🔧 En mise à jour (→ version à déployer ou prochaine ; repasse opérationnel quand la nouvelle version est installée), ⚠ Dégradé, ⛔ En panne, avec commentaire et date « depuis le » (proposée, modifiable) ; aussi sur les cartes
- Vue **📦 En production** modifiable dans l'application (vue de l'équipe prod) : état, version installée et date, case « Publié » ; enregistrement immédiat ; lien direct `#prod`
- Jalons mieux visibles : trait plein et étiquette « ◆ nom · date » sur le Gantt (raccourcie si la place manque), bloc **📍 Jalons** sous le Gantt avec compte à rebours (application et page publiée)
- **Annuaire de l'équipe** (⚙ Paramètres) : personnes choisies en un clic dans les fiches projet et version, « + personne » pour en ajouter sans quitter la fiche
- **👥 Qui travaille sur quoi** sous le Gantt, masqué par défaut (⚙ Paramètres pour l'afficher) (application et page publiée) : pour chaque personne, versions en cours / en retard / à venir sur la période ; « 5 ✓ » déplie au besoin ses versions terminées
- **🔑 Identifiants** pour un lien Git : utilisateur + jeton (https) enregistrés dans le gestionnaire d'identifiants de Git et testés, ou clé SSH du poste à copier (git@)
- `installer-serveur.sh` : installe le serveur depuis le poste en une commande (nginx, nom `.local` au choix avec `--nom`, compte de publication, clé SSH) et règle la publication dans l'application
- Paquet .deb : tests lancés avant la construction ; version de test « X.Y.Z+devDATE » tant que [Unreleased] n'est pas vide
### Changed
- Configuration centralisée (rien en dur) : `src/config.defaut.json`, `/etc/roadmap-bancs/config.json`, puis le fichier de l'utilisateur ;
  écran **⚙ Paramètres** : titre, thème sombre / clair, port, publication (avec test de connexion), PPT, couleurs, pôles
- Thème sombre par défaut (réglable dans les paramètres)
- Légende limitée aux pôles et statuts affichés sur la période
- Projet réorganisé : `lancer.sh` et `construire-deb.sh` à la racine, génération PPT dans `src/ppt/`
- `lancer.sh` (ex-`run.sh`) utilise les mêmes données que la version installée ; plus d'environnement `.venv` (aucune dépendance)
### Fixed
- Import : `[Unreleased]` du CHANGELOG n'est plus une version « Unreleased » en double ; il est rattaché à la prochaine version prévue du ROADMAP.md (anciens doublons retirés au réimport)
- Import : une version datée dans le CHANGELOG est livrée (Terminé, date de livraison du CHANGELOG) même sans tag Git, avec la fin prévue du ROADMAP.md gardée pour la dérive
- « En retard » enfin visible : barre bordée de rouge, badge coloré, légende (Gantt et PPT ; le PPT l'affichait « En cours »)
- Badges « En cours » sans couleur
- Numéro de version invisible sur les barres courtes (Gantt) : barre élargie juste assez pour l'afficher
- Libellé « Aujourd'hui » qui chevauchait le nom du mois : « Aujourd'hui » et jalons en pastilles sous les mois
- Menu Statut : seuls « Terminé » et « Bloqué » se choisissent (les autres étaient ignorés à l'enregistrement)
- Alertes utiles : version en retard, blocage sans motif (les anciennes ne pouvaient plus se déclencher)
- Versions à 4 nombres (1.2.3.4 / 1.2.3.5) qui se confondaient à l'import
### Security
- Requêtes venant d'une autre page web ou d'un autre nom d'hôte refusées

## [1.1.1] - 2026-11-05
### Fixed
- Période par défaut de la Roadmap calculée à partir de la date du jour (elle était fixée à sept. 2026 → janv. 2027)

## [1.1.0] - 2026-11-05
### Added
- Statut des versions déduit des dates : Planifié, En cours ou En retard, sans rien écrire
- Onglets par pôle dans la vue Projets pour filtrer les cartes (le choix est mémorisé)
- Modèle README.md et guide « Standard des dépôts » (Markdown et Word) pour l'équipe
### Changed
- RELEASE.md renommé ROADMAP.md (l'import lit encore l'ancien nom)
- Seuls « Terminé » et « Bloqué » s'écrivent à la main ; les autres statuts suivent toujours les dates
- Une nouvelle version démarre en statut « auto (dates) » au lieu de « Planifié »

## [1.0.0] - 2026-11-04
### Added
- Application locale : suivi des versions de chaque projet (historique et versions à venir)
- Vue Roadmap (Gantt par pôle) et vue Projets (cartes)
- Import du RELEASE.md / CHANGELOG.md et des tags Git d'un dépôt, export vers le dépôt
- Export de la roadmap en PowerPoint sur une période choisie
