"""Agent mémoire : retient ce que l'utilisateur dit sur lui, d'une session à l'autre."""

from __future__ import annotations

from datetime import date

from . import DONNEES, RACINE, Outil

FICHIER_MEMOIRE = DONNEES / "memoire.md"
FICHIER_PROFIL = RACINE / "profil.md"
MAX_CARACTERES = 6000  # pour ne pas saturer un petit modèle local


def lire_profil() -> str:
    if not FICHIER_PROFIL.exists():
        return ""
    return FICHIER_PROFIL.read_text(encoding="utf-8")[:MAX_CARACTERES]


def lire_memoire() -> str:
    if not FICHIER_MEMOIRE.exists():
        return ""
    return FICHIER_MEMOIRE.read_text(encoding="utf-8")[-MAX_CARACTERES:]


def memoriser(information: str) -> str:
    information = information.strip()
    if not information:
        return "Rien à mémoriser."
    with FICHIER_MEMOIRE.open("a", encoding="utf-8") as f:
        f.write(f"- ({date.today():%d/%m/%Y}) {information}\n")
    return "Mémorisé."


def oublier(mot_cle: str) -> str:
    if not FICHIER_MEMOIRE.exists():
        return "La mémoire est vide."
    lignes = FICHIER_MEMOIRE.read_text(encoding="utf-8").splitlines(keepends=True)
    gardees = [l for l in lignes if mot_cle.lower() not in l.lower()]
    FICHIER_MEMOIRE.write_text("".join(gardees), encoding="utf-8")
    return f"{len(lignes) - len(gardees)} souvenir(s) effacé(s)."


def outils(completer) -> list[Outil]:
    return [
        Outil(
            "memoriser",
            "Enregistre durablement une information sur l'utilisateur (compétence, préférence, "
            "objectif, contact, décision). À utiliser spontanément dès qu'il en donne une.",
            memoriser,
            {"information": {"type": "string", "description": "L'information, en une phrase."}},
            ["information"],
        ),
        Outil(
            "oublier",
            "Efface de la mémoire les souvenirs contenant un mot-clé.",
            oublier,
            {"mot_cle": {"type": "string", "description": "Mot-clé à effacer."}},
            ["mot_cle"],
        ),
    ]
