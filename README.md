# Roadmap Outils & Bancs de Test

Application locale pour suivre les versions des outils et bancs de test (historique et versions à venir),
synchroniser les `ROADMAP.md` / `CHANGELOG.md` des dépôts, générer la roadmap PowerPoint
et publier une vue en lecture seule pour toute l'équipe.

- **Version actuelle** : voir [CHANGELOG.md](CHANGELOG.md) — planning : [ROADMAP.md](ROADMAP.md)
- **Standard des dépôts** : [modeles/GUIDE.md](modeles/GUIDE.md)

## Arborescence

```
roadmap-bancs/
├── lancer.sh              lance l'application depuis les sources
├── lancer.bat             idem sous Windows
├── construire-deb.sh      fabrique le paquet Ubuntu (.deb) dans build/
├── installer-serveur.sh   installe un serveur de consultation (Raspberry…) depuis le poste
├── main.py                point d'entrée (options : --port, --sans-navigateur)
├── src/
│   ├── config.defaut.json valeurs par défaut de la configuration
│   ├── server.py          serveur local : API JSON, export PPT, publication
│   ├── store.py           projets, jalons, config, import / export / livraison Git
│   ├── releases.py        lecture / écriture des ROADMAP.md et CHANGELOG.md, statut déduit des dates
│   ├── static/            interface web (index.html, app.js, style.css)
│   └── ppt/               génération du PowerPoint (build_roadmap.py + template.pptx)
├── packaging/
│   ├── roadmap-bancs              lanceur installé dans /usr/bin
│   ├── roadmap-bancs.desktop      icône du menu Applications
│   └── serveur-installer.sh       installation du serveur de consultation (lancé par installer-serveur.sh)
├── modeles/               modèles CHANGELOG / ROADMAP / README + guide pour l'équipe
├── tests/                 tests automatiques
└── build/                 paquets .deb construits (non versionné)
```

**Données** (dossier `$ROADMAP_DATA`, par défaut `~/.local/share/roadmap-bancs`) :

| Fichier | Contenu |
|---|---|
| `projets.json` | liste des projets (nom, pôle, équipe, état, affichage en production, équipes et mises en production par version, dépôt, branche) |
| `releases/<projet>.md` | **un ROADMAP.md par projet : la source des données** |
| `jalons.json` | jalons communs (salons, audits…) |
| `depots/` | copies légères des dépôts distants (liens Git), recréées si besoin |
| `config.json` | configuration de l'utilisateur (voir ci-dessous), écrite par ⚙ Paramètres |
| `exports/` | PPT et pages publiées |

## Configuration

Rien n'est écrit en dur dans le code : titre, thème, port, pôles (nom, abréviation, couleur), couleurs,
serveur et lien de publication, auteur du PPT. Tout se règle dans **⚙ Paramètres** (en haut à droite).

Fichiers lus dans cet ordre, chacun complétant le précédent :

| Fichier | Rôle |
|---|---|
| `src/config.defaut.json` | valeurs par défaut livrées avec l'application (ne pas modifier) |
| `/etc/roadmap-bancs/config.json` | facultatif : réglages communs à tous les utilisateurs du poste |
| `$ROADMAP_CONFIG`, sinon `~/.local/share/roadmap-bancs/config.json` | réglages de l'utilisateur, écrits par ⚙ Paramètres |

```json
{
  "application": {"titre": "Roadmap Outils & Bancs de Test", "titre_court": "Roadmap Outils", "theme": "sombre", "port": 8765},
  "poles": [{"nom": "Library", "court": "LIB", "couleur": "#00a4c8"}],
  "equipe": ["A. Dupont", "B. Durand"],
  "couleurs": {"aujourdhui": "#da1f3d", "jalon": "#1f4e79", "retard": "#dc2626", "supplementaires": ["#a5a5a5"]},
  "publication": {"serveur": "roadmap@192.168.1.50:/var/www/roadmap/index.html", "lien": "http://roadmap-outils-bancs-de-test.local/"},
  "ppt": {"auteur": "A. Dupont", "mention": "Usage interne"}
}
```

Changer de serveur de publication : ⚙ Paramètres → Publication → nouveau serveur → **Tester la connexion** → Enregistrer.
Un pôle encore utilisé par un projet ne peut pas être supprimé ni renommé (changer d'abord le pôle du projet).

## Prérequis

- Python 3.10 ou plus — aucune dépendance externe (bibliothèque standard uniquement)
- Git (tags des dépôts, livraison)

## Lancer

```bash
./lancer.sh                    # ouvre http://127.0.0.1:8765/ dans le navigateur
./lancer.sh --port 9000        # autre port
./lancer.sh --sans-navigateur
```

`lancer.sh` utilise les mêmes données que la version installée. Autre dossier : `ROADMAP_DATA=/chemin ./lancer.sh`.
Tests : `python3 -m unittest discover -s tests`.

## Windows

Installer [Python 3.10+](https://www.python.org/downloads/windows/) et [Git for Windows](https://git-scm.com/download/win),
copier le dossier, puis double-cliquer sur `lancer.bat` (mêmes options que `lancer.sh`).
Données dans `%APPDATA%\roadmap-bancs`. Publication sur la Raspberry : client OpenSSH de Windows 10/11 (`ssh`, `scp`).
`/etc/roadmap-bancs/config.json` n'existe pas sous Windows : tout se règle dans ⚙ Paramètres.

## Paquet Ubuntu (.deb)

```bash
./construire-deb.sh                                # → build/roadmap-bancs_<version>_all.deb
sudo apt install ./build/roadmap-bancs_<version>_all.deb
```

Puis menu Applications → « Roadmap Outils & Bancs » (ou la commande `roadmap-bancs`).
Un clic sur l'icône démarre le serveur et ouvre le navigateur ; un 2e clic rouvre l'onglet.
À l'installation, une instance déjà lancée est arrêtée (sinon elle garderait l'ancien code) : relancer depuis le menu.

- Le script lance les tests d'abord et s'arrête si l'un échoue.
- Version = dernière version livrée du CHANGELOG.md. Si `[Unreleased]` contient des lignes :
  paquet de test `X.Y.Z+devAAAAMMJJHHMM` (s'installe par-dessus X.Y.Z, remplacé par la prochaine version).

## Fonctions

- **Roadmap** : Gantt par pôle, ligne « aujourd'hui », jalons (◆ sur le Gantt + bloc 📍 Jalons avec compte à rebours),
  alertes (en retard, bloqué sans motif).
- **Projets** : cartes par pôle ; fiche projet avec son **équipe** (qui travaille dessus) et ses versions.
  Une version peut avoir sa propre équipe (vide = équipe du projet). La recherche filtre aussi par personne.
  Les personnes se choisissent en un clic dans l'**annuaire** (⚙ Paramètres → Équipe, une par ligne) ;
  « + personne » dans une fiche ajoute directement quelqu'un à l'annuaire.
- **👥 Qui travaille sur quoi** (option de ⚙ Paramètres, masqué par défaut ; sous le Gantt et sur la page publiée) : par personne, ses versions en cours, en retard
  ou à venir sur la période (« 5 ✓ » déplie ses versions terminées) ; affiché dès qu'une équipe est renseignée.
- **Dépôt d'un projet** : un **dossier local**, ou un **lien Git** (`https://…`, `git@…`) avec le **choix de la branche**
  (↻ Charger les branches). Pour un lien, une copie légère est gardée dans `$ROADMAP_DATA/depots/` et mise à jour à chaque import ;
  **🔑 Identifiants** : lien `https://` → utilisateur + mot de passe ou jeton d'accès, enregistrés dans le gestionnaire
  d'identifiants de Git (pas dans l'application) puis testés, rien n'est gardé s'ils sont refusés ;
  lien `git@…` → clé SSH du poste à copier dans le profil du serveur Git.
- **⤓ Importer du dépôt** : lit ROADMAP.md / CHANGELOG.md de la branche et les tags Git ; **⤒ → dépôt** : les réécrit
  (dossier local seulement, comme 🚀 Livrer).
- **🚀 Livrer** : fait l'étape « Livrer une version » du guide (statut, CHANGELOG, commit, tag) ;
  il reste `git push && git push --tags`.
- **📦 En production** : la vue de l'**équipe production** (les fiches projet servent au développement).
  Dans l'application, chaque ligne se modifie directement et s'enregistre aussitôt : **état** du banc
  (✅ Opérationnel / 🔧 En mise à jour → version visée / ⚠ Dégradé / ⛔ En panne, commentaire, « depuis le » au choix),
  **version installée** et sa date (installer une nouvelle version sur un banc en mise à jour le repasse ✅ Opérationnel),
  case **Publié** (afficher ou non sur la page publiée).
  **Postes** : si le banc tourne sur plusieurs postes (fiche projet → Postes, séparés par des virgules), chaque poste a son état ;
  la version en production reste commune au projet. Installer une nouvelle version repasse ✅ tous les postes en mise à jour. Sous la version installée : « ⚠ vX à déployer » si une version plus
  récente est livrée. Et la prochaine version. « Terminé » = livrée (tag, CHANGELOG), pas forcément en production.
  Dates proposées (modifiables) : mise en production = date de livraison (« Terminé ») de la version,
  opérationnel depuis = date de mise en production. **⬇ CSV** : le tableau pour Excel (aussi sur la page publiée).
  Clic sur une version (en production, à déployer, prochaine) : ce qu'elle apporte.
  **⇪ Publier** envoie deux pages : `http://<serveur>/` (roadmap + production) et
  `http://<serveur>/production.html` (seulement la vue production, pour l'équipe prod).
- **⬇ Export PPT** : roadmap PowerPoint sur la période choisie. **⬇ draw.io** : la même roadmap en fichier `.drawio` modifiable.
- **⇪ Publier** : page HTML autonome en lecture seule : le Gantt de la période choisie, versions à venir seulement. Sans `config.json` : téléchargée (à déposer sur Teams,
  SharePoint, un dossier réseau). Avec `config.json` : envoyée sur la Raspberry.

## Consultation par tous : serveur (Raspberry ou autre)

Le serveur n'héberge que la page publiée (nginx, lecture seule). L'application, les données et Git restent sur le poste.
Serveur : Raspberry Pi OS Lite 64 bits, ou tout Debian / Ubuntu, avec SSH activé et un compte qui a `sudo`.

**Installation en une commande, depuis le poste :**

```bash
./installer-serveur.sh pi@192.168.1.50 --nom roadmap-outils-bancs-de-test
```

- `--nom` : nom du serveur sur le réseau → lien **http://roadmap-outils-bancs-de-test.local/** (sans `--nom` : demandé ; vide = inchangé).
- `--lien URL` : lien à donner à l'équipe s'il est différent (ex. nom DNS fourni par le service informatique).

Le script crée la clé SSH du poste si besoin, envoie et lance `packaging/serveur-installer.sh` sur le serveur
(nginx, avahi pour le `.local`, compte `roadmap` limité à la page publiée), teste la connexion, puis enregistre
le serveur et le lien dans ⚙ Paramètres. Mots de passe demandés : celui du serveur, puis `sudo`. Relançable sans risque.

Ensuite : **⇪ Publier** dans l'application. Changer de serveur plus tard : relancer le script avec la nouvelle adresse,
ou ⚙ Paramètres → Publication.

Sans le poste (à la main, sur le serveur) : `sudo bash serveur-installer.sh --nom NOM --cle "ssh-ed25519 AAAA…"`.

## Format d'un ROADMAP.md

```markdown
## [2.2.0] - 2027-01 → 2027-02
- Fonctionnalité prévue

## [2.1.0] - Bloqué (cartes non reçues) - 2026-09-21 → 2026-11-13 (prévu 2026-10-30)
- Fonctionnalité en attente
```

- Dates : `AAAA-MM-JJ`, `AAAA-MM` ou `?`.
- Pas de statut : il est déduit (tag Git = Terminé, début à venir = Planifié, début passé = En cours,
  fin passée sans tag = En retard). Seule exception : `Bloqué`, avec son motif entre parenthèses.
- `(prévu …)` après la fin : fin prévue initialement. Quand tu modifies une fin, l'outil demande : décalage du planning
  (date prévue gardée, dérive affichée) ou correction d'une erreur de saisie (rien). ✕ dans la fiche pour l'effacer.
- Import : ROADMAP.md = le prévu, CHANGELOG.md = le livré. Une version datée dans le CHANGELOG (ou taguée) est Terminé ;
  `[Unreleased]` est le travail de la prochaine version prévue (pas une version à part).
- L'import lit aussi l'ancien nom `RELEASE.md` et les changelogs existants
  (`## 1.0.2`, `## [2.2.0] — 2026-08-28`, `## [Unreleased]`).
