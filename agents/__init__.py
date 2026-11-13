"""
L'équipe d'agents de JARVIS.

Chaque agent expose des « outils » (une fonction Python + une description) que
le cerveau de JARVIS peut appeler tout seul. Pour ajouter un agent : créer un
module dans ce dossier avec une fonction `outils(completer)` qui renvoie une
liste d'Outil, puis l'ajouter à AGENTS ci-dessous.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

RACINE = Path(__file__).resolve().parent.parent
DONNEES = RACINE / "donnees"
DONNEES.mkdir(exist_ok=True)


@dataclass
class Outil:
    nom: str
    description: str
    fonction: Callable[..., object]
    parametres: dict = field(default_factory=dict)  # {nom: {"type":..., "description":...}}
    requis: list[str] = field(default_factory=list)

    def _schema(self) -> dict:
        return {"type": "object", "properties": self.parametres, "required": self.requis}

    def schema_ollama(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.nom,
                "description": self.description,
                "parameters": self._schema(),
            },
        }

    def schema_claude(self) -> dict:
        return {"name": self.nom, "description": self.description, "input_schema": self._schema()}


def charger_outils(completer: Callable[[str, str], str]) -> list[Outil]:
    from . import emploi, memoire

    AGENTS = [memoire, emploi]
    return [o for agent in AGENTS for o in agent.outils(completer)]
