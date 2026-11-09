# Nom du projet

<!--
  MODÈLE — README.md (à la racine du dépôt). Ce qu'est le projet et comment s'en servir.
  Court : quelqu'un qui découvre le dépôt doit pouvoir le lancer en 5 minutes.
  Supprimer ce commentaire en reprenant le modèle.
-->

Banc de test d'endurance des cartes BR : pilote les alimentations, enregistre les mesures
et génère le rapport PDF de l'essai.

- **Pôle** : SYS
- **Responsable** : Prénom Nom
- **Version actuelle** : voir [CHANGELOG.md](CHANGELOG.md) — planning : [ROADMAP.md](ROADMAP.md)

## Prérequis

- Windows 10, Python 3.11
- Alimentation programmable XYZ, pilote NI-VISA installé

## Installation

```bash
git clone <url-du-dépôt>
cd nom-du-projet
pip install -r requirements.txt
```

## Utilisation

```bash
python main.py --config config/banc1.yaml
```

Le rapport est écrit dans `rapports/AAAA-MM-JJ_<n° de série>.pdf`.

## Organisation

| Chemin | Rôle |
|---|---|
| `main.py` | point d'entrée |
| `config/` | une configuration par banc |
| `tests/` | tests automatiques |
