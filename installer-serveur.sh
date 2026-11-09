#!/usr/bin/env bash
# Installe un serveur de consultation (Raspberry ou autre Debian / Ubuntu) DEPUIS ce poste, en une commande :
#
#   ./installer-serveur.sh UTILISATEUR@ADRESSE [--nom roadmap-outils-bancs-de-test] [--lien http://…/]
#
#   UTILISATEUR@ADRESSE  compte qui a sudo sur le serveur, ex. pi@192.168.1.50
#   --nom NOM            nom du serveur sur le réseau → lien http://NOM.local/ (sinon : demandé, vide = inchangé)
#   --lien URL           lien à donner à l'équipe, s'il est différent (ex. nom DNS fourni par le service informatique)
#
# Étapes : clé SSH du poste (créée si absente) → envoi et exécution de packaging/serveur-installer.sh
# → test de connexion → serveur et lien enregistrés dans la configuration de l'application (⚙ Paramètres).
set -euo pipefail
cd "$(dirname "$0")"

CIBLE="" NOM="" LIEN="" NOM_DONNE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --nom) NOM="${2:-}"; NOM_DONNE=1; shift 2 ;;
    --lien) LIEN="${2:-}"; shift 2 ;;
    -h|--aide) sed -n '2,11p' "$0"; exit 0 ;;
    -*) echo "Option inconnue : $1 (voir --aide)"; exit 1 ;;
    *) CIBLE="$1"; shift ;;
  esac
done
[[ "$CIBLE" =~ ^[A-Za-z0-9._-]+@[A-Za-z0-9.-]+$ ]] || { echo "Usage : $0 UTILISATEUR@ADRESSE [--nom NOM] [--lien URL]   (voir --aide)"; exit 1; }
ADRESSE="${CIBLE#*@}"
if [ "$NOM_DONNE" -eq 0 ] && [ -t 0 ]; then
  read -rp "Nom du serveur sur le réseau (ex. roadmap-outils-bancs-de-test, vide = inchangé) : " NOM
fi
if [ -n "$NOM" ] && ! [[ "$NOM" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]]; then
  echo "Nom invalide : minuscules, chiffres et tirets seulement (ni espace, ni accent, ni &)"; exit 1
fi
if [ -n "$LIEN" ] && ! [[ "$LIEN" =~ ^https?://[^[:space:]]+$ ]]; then
  echo "Lien invalide : http://… ou https://…"; exit 1
fi
[ -n "$LIEN" ] || LIEN="http://${NOM:-$ADRESSE}${NOM:+.local}/"

CLE_FICHIER="$HOME/.ssh/id_ed25519"
if [ ! -f "$CLE_FICHIER.pub" ]; then
  echo "== Création de la clé SSH du poste ($CLE_FICHIER)"
  mkdir -p "$HOME/.ssh" && chmod 700 "$HOME/.ssh"
  ssh-keygen -q -t ed25519 -N "" -f "$CLE_FICHIER"
fi

# une seule connexion (un seul mot de passe) pour l'envoi et l'installation
CTRL="${XDG_RUNTIME_DIR:-/tmp}/roadmap-ssh-%r@%h:%p"
SSH_OPTS=(-o ControlMaster=auto -o "ControlPath=$CTRL" -o ControlPersist=120 -o StrictHostKeyChecking=accept-new)

echo "== Envoi du script d'installation sur $CIBLE (mot de passe du serveur demandé)"
ssh "${SSH_OPTS[@]}" "$CIBLE" "cat > /tmp/roadmap-serveur-installer.sh" < packaging/serveur-installer.sh
echo "== Installation sur le serveur (mot de passe sudo demandé)"
ssh -t "${SSH_OPTS[@]}" "$CIBLE" \
  "sudo bash /tmp/roadmap-serveur-installer.sh $(printf '%q ' --nom "$NOM" --cle "$(cat "$CLE_FICHIER.pub")"); rm -f /tmp/roadmap-serveur-installer.sh"
ssh "${SSH_OPTS[@]}" -O exit "$CIBLE" 2>/dev/null || true

SERVEUR="roadmap@$ADRESSE:/var/www/roadmap/index.html"
echo "== Test de la publication (sans mot de passe)"
ssh -o BatchMode=yes -o ConnectTimeout=10 -o StrictHostKeyChecking=accept-new "roadmap@$ADRESSE" true \
  || { echo "Connexion refusée pour roadmap@$ADRESSE : l'installation a-t-elle réussi ?"; exit 1; }

echo "== Configuration de l'application (⚙ Paramètres → Publication)"
export ROADMAP_DATA="${ROADMAP_DATA:-${XDG_DATA_HOME:-$HOME/.local/share}/roadmap-bancs}"   # comme lancer.sh / la version installée
python3 - "$SERVEUR" "$LIEN" <<'EOF'
import sys
sys.path.insert(0, "src")
import store
store.save_config({"publication": {"serveur": sys.argv[1], "lien": sys.argv[2]}})
print(f"   serveur : {sys.argv[1]}\n   lien    : {sys.argv[2]}\n   fichier : {store.CONFIG}")
EOF

echo
echo "Terminé. Dans l'application : F5 puis « ⇪ Publier ». Lien pour l'équipe : $LIEN"
[ -z "$NOM" ] || echo "(le nom .local peut mettre une minute à apparaître sur le réseau ; secours : http://$ADRESSE/)"
