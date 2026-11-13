#!/bin/bash
# Double-clique sur ce fichier dans le Finder pour parler à JARVIS à la voix.
cd "$(dirname "$0")" || exit 1
source .venv/bin/activate
python jarvis.py
