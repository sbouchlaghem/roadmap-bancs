#!/usr/bin/env python3
"""Roadmap Outils & Bancs de Test — lance l'application :  python3 main.py

Ouvre l'interface dans le navigateur (serveur local, accessible uniquement depuis ce poste).
Options : --port N (par défaut : application.port de la configuration)   --sans-navigateur
Données : dossier $ROADMAP_DATA (par défaut ./data ; installé : ~/.local/share/roadmap-bancs).
"""
import argparse
import os
import sys
import threading
import urllib.request
import webbrowser

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "src"))
import server  # noqa: E402


def deja_lance(url):
    """L'application tourne déjà sur ce port ? (en-tête Server: Roadmap/… de server.Handler)"""
    try:
        with urllib.request.urlopen(url, timeout=1) as r:
            return r.headers.get("Server", "").startswith("Roadmap/")
    except OSError:
        return False


def main():
    ap = argparse.ArgumentParser(description="Roadmap Outils & Bancs de Test")
    ap.add_argument("--port", type=int, help="port (par défaut : celui de la configuration)")
    ap.add_argument("--sans-navigateur", action="store_true", help="ne pas ouvrir le navigateur")
    args = ap.parse_args()
    port = args.port or server.store.config()["application"]["port"]
    url = f"http://127.0.0.1:{port}/"
    if deja_lance(url):  # 2e clic sur l'icône : on rouvre juste l'onglet
        if not args.sans_navigateur:
            webbrowser.open(url)
        return
    srv, url = server.run(port)
    print(f"Roadmap : {url}   données : {server.store.DATA}   (Ctrl+C pour arrêter)")
    if not args.sans_navigateur:
        threading.Timer(0.5, webbrowser.open, [url]).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt.")
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
