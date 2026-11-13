#!/bin/bash
# Double-clique sur ce fichier dans le Finder pour écrire à JARVIS au clavier.
cd "$(dirname "$0")" || exit 1
source .venv/bin/activate
python jarvis.py --texte
