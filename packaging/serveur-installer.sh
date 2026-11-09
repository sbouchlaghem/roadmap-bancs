#!/usr/bin/env bash
# Installe le serveur de consultation de la roadmap (lecture seule) sur une Raspberry ou tout Debian / Ubuntu.
# Normalement lancé par ./installer-serveur.sh depuis le poste ; à la main, SUR le serveur :
#
#   sudo bash serveur-installer.sh --nom roadmap-outils-bancs-de-test --cle "ssh-ed25519 AAAA…"
#
#   --nom NOM   nom du serveur sur le réseau → lien http://NOM.local/  (vide : garder le nom actuel)
#   --cle CLÉ   clé publique SSH du poste qui publie (contenu de ~/.ssh/id_ed25519.pub)
# Sans option, les valeurs sont demandées. Relançable sans risque (ne fait que ce qui manque).
set -euo pipefail

NOM="" CLE="" NOM_DONNE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --nom) NOM="${2:-}"; NOM_DONNE=1; shift 2 ;;
    --cle) CLE="${2:-}"; shift 2 ;;
    -h|--aide) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "Option inconnue : $1 (voir --aide)"; exit 1 ;;
  esac
done
[ "$(id -u)" -eq 0 ] || { echo "À lancer avec sudo"; exit 1; }
command -v apt-get >/dev/null || { echo "Système non pris en charge (Debian, Ubuntu ou Raspberry Pi OS attendu)"; exit 1; }

if [ -t 0 ]; then   # questions seulement si quelqu'un est au clavier
  [ "$NOM_DONNE" -eq 1 ] || read -rp "Nom sur le réseau (ex. roadmap-outils-bancs-de-test, vide = garder « $(hostname) ») : " NOM
  [ -n "$CLE" ] || read -rp "Clé publique SSH du poste qui publie (ssh-ed25519 AAAA…) : " CLE
fi
if [ -n "$NOM" ] && ! [[ "$NOM" =~ ^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$ ]]; then
  echo "Nom invalide : minuscules, chiffres et tirets seulement (ni espace, ni accent, ni &)"; exit 1
fi
[[ "$CLE" == ssh-* ]] || { echo "Clé SSH manquante ou invalide (elle commence par ssh-ed25519 ou ssh-rsa)"; exit 1; }

echo "== Paquets : nginx (pages web) + avahi (nom en .local)"
apt-get update -q
apt-get install -y -q nginx avahi-daemon

if [ -n "$NOM" ] && [ "$NOM" != "$(hostname)" ]; then
  echo "== Nom du serveur : $NOM"
  hostnamectl set-hostname "$NOM"
  if grep -q '^127\.0\.1\.1' /etc/hosts; then
    sed -i "s/^127\.0\.1\.1.*/127.0.1.1\t$NOM/" /etc/hosts
  else
    printf '127.0.1.1\t%s\n' "$NOM" >> /etc/hosts
  fi
fi
systemctl enable --now avahi-daemon
systemctl restart avahi-daemon   # annonce le nom sur le réseau

echo "== Compte « roadmap » : il ne peut qu'écrire la page publiée"
id roadmap >/dev/null 2>&1 || adduser --disabled-password --gecos "Publication roadmap" roadmap
install -d -o roadmap -g roadmap -m 755 /var/www/roadmap
install -d -o roadmap -g roadmap -m 700 /home/roadmap/.ssh
AUTH=/home/roadmap/.ssh/authorized_keys
touch "$AUTH"
grep -qF "$CLE" "$AUTH" || echo "restrict $CLE" >> "$AUTH"   # restrict : pas de tunnel ni de terminal
chown roadmap:roadmap "$AUTH"; chmod 600 "$AUTH"
[ -f /var/www/roadmap/index.html ] || {
  echo '<!doctype html><meta charset="utf-8"><title>Roadmap</title><p>Rien de publié pour l’instant.</p>' > /var/www/roadmap/index.html
  chown roadmap:roadmap /var/www/roadmap/index.html
}

echo "== Site web"
cat > /etc/nginx/sites-available/roadmap <<'EOF'
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    root /var/www/roadmap;
    index index.html;
    add_header Cache-Control "no-cache";   # toujours la dernière publication
    location / { try_files $uri $uri/ =404; }
}
EOF
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/roadmap /etc/nginx/sites-enabled/roadmap
nginx -t
systemctl enable --now nginx
systemctl reload nginx

IP=$(hostname -I | awk '{print $1}')
echo
echo "Prêt."
echo "  Lien pour l'équipe : http://$(hostname).local/   (secours : http://$IP/)"
echo "  Serveur de publication (⚙ Paramètres) : roadmap@$IP:/var/www/roadmap/index.html"
