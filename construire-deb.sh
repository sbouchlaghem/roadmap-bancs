#!/usr/bin/env bash
# Construit le paquet Ubuntu :  ./construire-deb.sh  ->  build/roadmap-bancs_<version>_all.deb
# Version = la dernière version livrée du CHANGELOG.md (même numéro que le tag Git), + « +devDATE » si [Unreleased] n'est pas vide.
set -euo pipefail
cd "$(dirname "$0")"
command -v dpkg-deb >/dev/null || { echo "dpkg-deb introuvable (Ubuntu / Debian requis)"; exit 1; }

python3 -m unittest discover -s tests -q   # pas de paquet si un test échoue

VERSION=$(grep -m1 -oP '^## \[\K\d+\.\d+\.\d+(?=\])' CHANGELOG.md)
# [Unreleased] non vide : paquet de test « 1.1.1+dev202611091530 », plus récent que 1.1.1 pour apt, plus ancien que 1.2.0
if awk '/^## \[Unreleased\]/{f=1;next} /^## \[/{f=0} f && /^- /{found=1} END{exit !found}' CHANGELOG.md; then
  VERSION="${VERSION}+dev$(date +%Y%m%d%H%M)"
  echo "⚠ [Unreleased] non vide : version de test $VERSION (livrer la version dans le CHANGELOG pour un paquet officiel)"
fi
PKG=build/roadmap-bancs_${VERSION}_all
rm -rf "$PKG"
mkdir -p "$PKG/DEBIAN" "$PKG/usr/lib/roadmap-bancs" "$PKG/usr/bin" "$PKG/usr/share/applications"

# code (lecture seule) ; les données de chaque utilisateur vont dans ~/.local/share/roadmap-bancs
cp -r main.py src "$PKG/usr/lib/roadmap-bancs/"
find "$PKG" -name __pycache__ -prune -exec rm -rf {} +
cp packaging/roadmap-bancs "$PKG/usr/bin/"                                # lanceur
cp packaging/roadmap-bancs.desktop "$PKG/usr/share/applications/"         # icône du menu
chmod -R u=rwX,go=rX "$PKG"   # 755 / 644 quel que soit l'umask
chmod 755 "$PKG/usr/bin/roadmap-bancs"

cat > "$PKG/DEBIAN/control" <<EOF
Package: roadmap-bancs
Version: $VERSION
Architecture: all
Maintainer: Roadmap Bancs <roadmap@example.com>
Depends: python3 (>= 3.10), git
Installed-Size: $(du -sk --exclude=DEBIAN "$PKG" | cut -f1)
Section: misc
Priority: optional
Description: Roadmap Outils & Bancs de Test
 Suivi des versions des outils et bancs de test, synchronisation des
 ROADMAP.md / CHANGELOG.md des dépôts et export de la roadmap PowerPoint.
EOF

# une instance lancée avant la mise à jour garde l'ancien code Python en mémoire mais sert la nouvelle page web :
# les nouveaux champs seraient ignorés sans message. On l'arrête ; rien n'est perdu (chaque enregistrement est sur disque)
cat > "$PKG/DEBIAN/postinst" <<'FIN'
#!/bin/sh
set -e
if [ "$1" = configure ] && pkill -f /usr/lib/roadmap-bancs/main.py; then
  echo "Roadmap Bancs (ancienne version) arrêté : relancer l'application depuis le menu"
fi
exit 0
FIN
chmod 755 "$PKG/DEBIAN/postinst"

dpkg-deb --build --root-owner-group "$PKG" >/dev/null
rm -rf "$PKG"   # dossier intermédiaire
echo "Paquet : $PKG.deb"
echo "Installer : sudo apt install ./$PKG.deb   (l'application en cours est arrêtée : la relancer ensuite)"
