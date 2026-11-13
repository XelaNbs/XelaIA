"""Agent mémoire : retient ce que l'utilisateur dit sur lui, d'une session à l'autre."""

from __future__ import annotations

from datetime import date

from . import DONNEES, RACINE, Outil
from . import stockage

FICHIER_MEMOIRE = DONNEES / "memoire.md"
FICHIER_PROFIL = RACINE / "profil.md"
FICHIER_CIBLES = RACINE / "cibles.md"
MAX_CARACTERES = 6000  # pour ne pas saturer un petit modèle local


FICHIER_CV_MAITRE = DONNEES / "cv_maitre.json"


def lire_profil() -> str:
    """Ton CV d'origine (transcrit depuis mon_cv.pdf) + tes notes de profil.md."""
    morceaux = []
    cv = stockage.charger_cv()
    if cv is not None:
        import json
        morceaux.append("CV d'origine (données exactes, ne rien inventer au-delà) :\n"
                        + json.dumps(cv, ensure_ascii=False))
    if FICHIER_PROFIL.exists():
        morceaux.append("Notes de l'utilisateur :\n"
                        + FICHIER_PROFIL.read_text(encoding="utf-8")[:MAX_CARACTERES])
    return "\n\n".join(morceaux)


def lire_cibles() -> str:
    if not FICHIER_CIBLES.exists():
        return ""
    return FICHIER_CIBLES.read_text(encoding="utf-8")


def lire_memoire() -> str:
    return stockage.lire_memoire(MAX_CARACTERES)


def memoriser(information: str) -> str:
    information = information.strip()
    if not information:
        return "Rien à mémoriser."
    stockage.memoriser(information, f"{date.today():%d/%m/%Y}")
    return "Mémorisé."


def oublier(mot_cle: str) -> str:
    if not stockage.lire_memoire():
        return "La mémoire est vide."
    count = stockage.oublier(mot_cle)
    return f"{count} souvenir(s) effacé(s)."


def outils(ia) -> list[Outil]:
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
