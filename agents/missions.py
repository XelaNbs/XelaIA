"""
Missions en arrière-plan : les agents travaillent pendant que tu parles à JARVIS.

Quand une mission se termine, son rapport part dans une file que JARVIS lit à
voix haute dès qu'il est libre, et une notification macOS s'affiche.
"""

from __future__ import annotations

import platform
import queue
import subprocess
import threading
import traceback
from datetime import datetime
from typing import Callable

from . import DONNEES, Outil

RAPPORTS: "queue.Queue[str]" = queue.Queue()
JOURNAL = DONNEES / "journal.md"
_missions: dict[str, threading.Thread] = {}


def notifier_mac(titre: str, texte: str) -> None:
    if platform.system() != "Darwin":
        return
    texte = texte.replace('"', "'")[:200]
    titre = titre.replace('"', "'")
    subprocess.run(
        ["osascript", "-e", f'display notification "{texte}" with title "{titre}" sound name "Glass"'],
        check=False, capture_output=True,
    )


def journaliser(texte: str) -> None:
    with JOURNAL.open("a", encoding="utf-8") as f:
        f.write(f"\n## {datetime.now():%d/%m/%Y %H:%M}\n{texte}\n")


def executer_mission(nom: str, fonction: Callable[[], str]) -> str:
    """Exécute une mission tout de suite (utilisé par la routine du matin)."""
    try:
        rapport = fonction()
    except Exception as e:
        traceback.print_exc()
        rapport = f"La mission « {nom} » a échoué : {e}"
    journaliser(f"**{nom}** — {rapport}")
    notifier_mac("JARVIS", rapport)
    return rapport


def lancer(nom: str, fonction: Callable[[], str]) -> str:
    """Lance une mission en arrière-plan. Renvoie tout de suite."""
    en_cours = _missions.get(nom)
    if en_cours and en_cours.is_alive():
        return f"La mission « {nom} » est déjà en cours."

    def travail():
        RAPPORTS.put(executer_mission(nom, fonction))

    t = threading.Thread(target=travail, name=nom, daemon=True)
    _missions[nom] = t
    t.start()
    return f"Mission « {nom} » lancée en arrière-plan. Tu seras prévenu à la fin."


def rapports_en_attente() -> list[str]:
    rapports = []
    while not RAPPORTS.empty():
        rapports.append(RAPPORTS.get_nowait())
    return rapports


def etat_missions() -> str:
    actives = [n for n, t in _missions.items() if t.is_alive()]
    if not actives:
        return "Aucune mission en cours."
    return "Missions en cours : " + ", ".join(actives)


def outils(ia) -> list[Outil]:
    return [Outil("etat_missions", "Indique quelles missions d'agents tournent en ce moment.",
                  etat_missions)]
