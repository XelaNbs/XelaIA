#!/usr/bin/env python3
"""Fail before each commit if a private artifact is staged OR tracked."""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
FORBIDDEN_DIRS = {"donnees", "candidatures", "contenus", "mon_cv", "data", "models", "pilot-private", ".venv"}
FORBIDDEN_NAMES = {".env", "mon_cv.pdf", "profil.md", "access-token", "gmail-oauth.json", "elevenlabs-key"}
EXTENSIONS = {".sqlite", ".sqlite3", ".db", ".wav", ".mp3", ".aiff", ".m4a", ".webm", ".ogg", ".flac", ".caf"}

def private(path):
    p=pathlib.PurePosixPath(path)
    return bool(set(p.parts)&FORBIDDEN_DIRS or p.name in FORBIDDEN_NAMES or p.suffix.lower() in EXTENSIONS or any(x in p.name for x in (".sqlite3-", ".db-")))

def main():
    files=subprocess.check_output(["git","ls-files","-z"],cwd=ROOT).decode().split('\0')
    bad=[f for f in files if f and private(f)]
    if bad:
        print("COMMIT REFUSÉ : fichiers personnels suivis :\n"+'\n'.join(bad),file=sys.stderr)
        return 1
    print("Contrôle public : aucun fichier personnel, SQLite ou audio suivi par git.")
    return 0

if __name__=='__main__':sys.exit(main())
