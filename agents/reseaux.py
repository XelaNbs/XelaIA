"""
Agent réseaux sociaux : prépare les contenus TikTok et Instagram de ton appli.

Il repère les tendances padel du moment sur le web, puis écrit un plan de
publication prêt à tourner : accroche, script plan par plan, texte à l'écran,
légende, hashtags, appel à l'action, meilleur créneau. Tu filmes et tu publies.
Les plans sont dans contenus/.
"""

from __future__ import annotations

from datetime import date

from . import RACINE, Outil, missions

FICHIER_APPLI = RACINE / "appli.md"
DOSSIER_CONTENUS = RACINE / "contenus"

SYSTEME = """Tu es un social media manager spécialiste de TikTok et Instagram dans le \
sport et les applis mobiles. Tu sais faire des vidéos courtes qui accrochent en 2 secondes, \
qui se tournent avec un simple smartphone et qui donnent envie de télécharger l'appli."""


def mission_contenus(ia, nombre: int, theme: str) -> str:
    appli = FICHIER_APPLI.read_text(encoding="utf-8") if FICHIER_APPLI.exists() else ""
    try:
        tendances = ia.rechercher_web(
            "Quelles sont les tendances actuelles (formats, sons, sujets, comptes qui "
            "marchent) sur TikTok et Instagram autour du padel, en France ? Résume en 10 "
            "points concrets et exploitables.", SYSTEME, max_recherches=6)
    except Exception:
        tendances = "non disponibles"

    plan = ia.completer(f"""Prépare {nombre} publications pour TikTok et Instagram.

L'APPLI :
{appli}

TENDANCES DU MOMENT :
{tendances}

{"THÈME DEMANDÉ : " + theme if theme else ""}

Varie les formats : astuce de jeu, erreur fréquente, humour de joueur, démonstration de \
l'appli, progression de classement, coulisses, défi. Pour chaque publication donne, en \
Markdown :
### N. Titre interne
- Format et plateforme (vidéo TikTok/Reel, carrousel…) et durée
- Accroche (2 premières secondes, mot pour mot)
- Script plan par plan (ce qu'on filme + ce qu'on dit)
- Texte à l'écran
- Légende prête à copier
- Hashtags (8 à 12, mélange gros et niches)
- Appel à l'action
- Meilleur jour et heure de publication
Termine par un planning de la semaine.""", SYSTEME)

    DOSSIER_CONTENUS.mkdir(exist_ok=True)
    chemin = DOSSIER_CONTENUS / f"{date.today():%Y-%m-%d}_plan_contenus.md"
    chemin.write_text(f"# Plan de contenus — {date.today():%d/%m/%Y}\n\n{plan}\n\n"
                      f"---\n## Tendances repérées\n{tendances}\n", encoding="utf-8")
    return (f"{nombre} contenus TikTok et Instagram sont prêts à tourner, dans "
            f"{chemin.relative_to(RACINE)}.")


def outils(ia) -> list[Outil]:
    return [
        Outil(
            "preparer_contenus_reseaux",
            "Lance en arrière-plan l'agent réseaux sociaux : il prépare des publications "
            "TikTok et Instagram pour l'appli de padel de l'utilisateur (scripts, légendes, "
            "hashtags, planning).",
            lambda nombre=7, theme="": missions.lancer(
                "contenus réseaux", lambda: mission_contenus(ia, int(nombre), theme)),
            {
                "nombre": {"type": "integer", "description": "Nombre de publications (défaut 7)."},
                "theme": {"type": "string", "description": "Thème ou objectif particulier (optionnel)."},
            },
        ),
    ]
