"""
Cerveau de JARVIS : le modèle de langage et la boucle d'outils.

Deux moteurs au choix (variable JARVIS_MOTEUR dans .env) :
  - "ollama" (par défaut) : modèle local sur le Mac, 100 % gratuit, hors ligne.
  - "claude"              : API Claude, payante, plus intelligente.

Le cerveau ne fait pas tout lui-même : il délègue aux agents (dossier agents/)
en appelant leurs outils, puis résume le résultat à l'oral.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime

from agents import Outil, charger_outils
from agents.memoire import lire_memoire, lire_profil

MAX_TOURS_HISTORIQUE = 10   # échanges gardés en mémoire de conversation
MAX_ETAPES_OUTILS = 8       # nombre max d'appels d'outils enchaînés par demande

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]

PERSONNALITE = """\
Tu es JARVIS, l'assistant personnel de l'utilisateur et le chef d'une équipe d'agents IA \
qui travaillent pour lui. Tu es son porte-parole : il te parle, tu fais travailler les agents \
et tu lui rends compte.

Caractère : loyal, efficace, un peu pince-sans-rire à la façon d'un majordome britannique \
high-tech. Tu peux plaisanter quand l'ambiance s'y prête, sans jamais ralentir le travail.

Règles de travail :
- Tu AGIS directement. Quand une demande est claire, utilise tes outils tout de suite, \
sans demander la permission ni de confirmation. Ne pose une question que s'il manque une \
information indispensable, et une seule question à la fois.
- Quand l'utilisateur te donne une information durable sur lui (compétences, préférences, \
objectifs, contacts…), enregistre-la avec l'outil memoriser sans le lui demander.
- Après avoir utilisé des outils, fais un compte rendu oral court : l'essentiel, puis ce que \
tu proposes de faire ensuite.
- Réponds toujours en français. Tes réponses sont lues à voix haute : pas de Markdown, pas \
de listes à puces, pas d'emojis, pas d'URL lues à voix haute. Phrases courtes et naturelles.
"""


def prompt_systeme() -> str:
    maintenant = datetime.now()
    jour = JOURS[maintenant.weekday()]
    mois = MOIS[maintenant.month - 1]
    morceaux = [PERSONNALITE,
                f"Nous sommes le {jour} {maintenant.day} {mois} {maintenant.year}, "
                f"il est {maintenant:%H:%M}."]
    profil = lire_profil()
    if profil:
        morceaux.append("Profil et CV de l'utilisateur :\n" + profil)
    memoire = lire_memoire()
    if memoire:
        morceaux.append("Ce que tu sais déjà sur l'utilisateur :\n" + memoire)
    return "\n\n".join(morceaux)


def nettoyer(texte: str) -> str:
    """Retire les balises de réflexion éventuelles et le Markdown résiduel."""
    texte = re.sub(r"<think>.*?</think>", "", texte, flags=re.S)
    texte = re.sub(r"[*#`_]{1,3}", "", texte)
    return texte.strip()


# --------------------------------------------------------------------------- #
# Moteur local : Ollama
# --------------------------------------------------------------------------- #

class MoteurOllama:
    def __init__(self) -> None:
        import ollama

        self.modele = os.getenv("JARVIS_MODELE_LOCAL", "qwen3:8b")
        self.client = ollama.Client(host=os.getenv("OLLAMA_HOST", "http://localhost:11434"))
        try:
            self.client.show(self.modele)
        except Exception as e:
            raise SystemExit(
                f"❌ Ollama ou le modèle « {self.modele} » est indisponible ({e}).\n"
                f"   Lance l'application Ollama, puis : ollama pull {self.modele}"
            )

    def _chat(self, messages: list[dict], outils: list[Outil] | None = None):
        kwargs = {"model": self.modele, "messages": messages, "think": False}
        if outils:
            kwargs["tools"] = [o.schema_ollama() for o in outils]
        return self.client.chat(**kwargs).message

    def completer(self, consigne: str, systeme: str = "") -> str:
        messages = [{"role": "system", "content": systeme}] if systeme else []
        messages.append({"role": "user", "content": consigne})
        return nettoyer(self._chat(messages).content or "")

    def tour(self, historique: list[dict], outils: list[Outil]) -> str:
        index = {o.nom: o for o in outils}
        messages = [{"role": "system", "content": prompt_systeme()}, *historique]
        for _ in range(MAX_ETAPES_OUTILS):
            msg = self._chat(messages, outils)
            if not msg.tool_calls:
                return nettoyer(msg.content or "")
            messages.append(msg)
            for appel in msg.tool_calls:
                nom, args = appel.function.name, appel.function.arguments or {}
                resultat = executer(index, nom, args)
                messages.append({"role": "tool", "content": resultat, "tool_name": nom})
        return "J'ai beaucoup travaillé sur cette demande sans terminer. Peux-tu la préciser ?"


# --------------------------------------------------------------------------- #
# Moteur payant : API Claude
# --------------------------------------------------------------------------- #

class MoteurClaude:
    def __init__(self) -> None:
        import anthropic

        if not os.getenv("ANTHROPIC_API_KEY"):
            raise SystemExit("❌ ANTHROPIC_API_KEY manquante dans .env (moteur claude).")
        self.client = anthropic.Anthropic()
        self.modele = os.getenv("JARVIS_MODELE", "claude-sonnet-5-5")
        self.effort = os.getenv("JARVIS_EFFORT", "low")

    def _creer(self, messages, outils=None, systeme=""):
        kwargs = dict(
            model=self.modele,
            max_tokens=4000,
            system=systeme,
            messages=messages,
            output_config={"effort": self.effort},
        )
        if outils:
            kwargs["tools"] = [o.schema_claude() for o in outils]
        return self.client.messages.create(**kwargs)

    def completer(self, consigne: str, systeme: str = "") -> str:
        rep = self._creer([{"role": "user", "content": consigne}], systeme=systeme)
        return "".join(b.text for b in rep.content if b.type == "text").strip()

    def tour(self, historique: list[dict], outils: list[Outil]) -> str:
        index = {o.nom: o for o in outils}
        messages = list(historique)
        for _ in range(MAX_ETAPES_OUTILS):
            rep = self._creer(messages, outils, prompt_systeme())
            if rep.stop_reason != "tool_use":
                return nettoyer("".join(b.text for b in rep.content if b.type == "text"))
            messages.append({"role": "assistant", "content": rep.content})
            resultats = [
                {
                    "type": "tool_result",
                    "tool_use_id": b.id,
                    "content": executer(index, b.name, b.input),
                }
                for b in rep.content
                if b.type == "tool_use"
            ]
            messages.append({"role": "user", "content": resultats})
        return "J'ai beaucoup travaillé sur cette demande sans terminer. Peux-tu la préciser ?"


# --------------------------------------------------------------------------- #
# Exécution des outils et façade
# --------------------------------------------------------------------------- #

def executer(index: dict[str, Outil], nom: str, args: dict) -> str:
    outil = index.get(nom)
    if outil is None:
        return f"Erreur : outil inconnu « {nom} »."
    print(f"   🛠️  {nom}({json.dumps(args, ensure_ascii=False)})")
    try:
        resultat = outil.fonction(**args)
    except TypeError as e:
        return f"Erreur d'arguments pour {nom} : {e}"
    except Exception as e:  # un agent qui plante ne doit pas tuer JARVIS
        return f"Erreur pendant {nom} : {e}"
    return resultat if isinstance(resultat, str) else json.dumps(resultat, ensure_ascii=False)


class Cerveau:
    def __init__(self) -> None:
        moteur = os.getenv("JARVIS_MOTEUR", "ollama").lower()
        self.moteur = MoteurClaude() if moteur == "claude" else MoteurOllama()
        self.outils = charger_outils(self.moteur.completer)
        self.historique: list[dict] = []
        print(f"🧠 Moteur : {moteur} — {len(self.outils)} outils : "
              + ", ".join(o.nom for o in self.outils))

    def repondre(self, demande: str) -> str:
        self.historique.append({"role": "user", "content": demande})
        self.historique = self.historique[-(MAX_TOURS_HISTORIQUE * 2):]
        while self.historique and self.historique[0]["role"] != "user":
            self.historique.pop(0)
        try:
            texte = self.moteur.tour(self.historique, self.outils)
        except Exception as e:
            print(f"⚠️  Erreur du cerveau : {e}")
            self.historique.pop()
            return "Désolé, j'ai eu un problème de connexion avec mon cerveau."
        texte = texte or "C'est fait."
        # On ne garde que le texte final dans l'historique (léger et portable).
        self.historique.append({"role": "assistant", "content": texte})
        return texte
