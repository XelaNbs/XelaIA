"""
Cerveau de JARVIS : le modèle de langage et la boucle d'outils.

Moteurs (variable JARVIS_MOTEUR dans .env) :
  - "claude" (par défaut) : API Claude, fluide et intelligent, avec recherche web.
  - "ollama"              : modèle local gratuit (sans recherche web).

JARVIS ne fait pas tout lui-même : il délègue aux agents (dossier agents/),
qui travaillent en arrière-plan, puis il te rend compte.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime

from agents import Outil, charger_outils
from agents.memoire import lire_memoire, lire_profil

MAX_TOURS_HISTORIQUE = 12   # échanges gardés en mémoire de conversation
MAX_ETAPES_OUTILS = 10      # appels d'outils enchaînés par demande

JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août",
        "septembre", "octobre", "novembre", "décembre"]

PERSONNALITE = """\
Tu es JARVIS, l'assistant personnel de l'utilisateur et le chef d'une équipe d'agents IA \
qui travaillent pour lui (recherche d'emploi, candidatures, réseaux sociaux de son appli). \
Tu es son porte-parole : il te parle, tu fais travailler les agents et tu lui rends compte.

Caractère : loyal, vif, élégant, avec l'humour pince-sans-rire d'un majordome britannique \
high-tech. Tu le tutoies. Tu peux plaisanter et le chambrer gentiment quand l'ambiance s'y \
prête, sans jamais ralentir le travail.

Règles de travail :
- Tu AGIS. Quand une demande est claire, lance directement les outils, sans demander de \
permission ni de confirmation. Ne pose une question que s'il manque une information \
vraiment indispensable, une seule à la fois.
- Les missions longues (recherche d'offres, préparation des dossiers, contenus) tournent en \
arrière-plan : lance-les, dis-le en une phrase, et continue la conversation. Tu seras prévenu \
quand elles sont terminées.
- Dès que l'utilisateur donne une information durable sur lui (compétence, préférence, \
décision, contact…), enregistre-la avec l'outil memoriser, sans le lui demander.
- Pour une question d'actualité ou factuelle récente, utilise la recherche web.
- Réponds toujours en français. Tes réponses sont lues à voix haute : pas de Markdown, pas \
de listes, pas d'emojis, pas d'URL. Phrases courtes et naturelles, 1 à 4 phrases en général.
"""


def maintenant_en_francais() -> str:
    m = datetime.now()
    return f"{JOURS[m.weekday()]} {m.day} {MOIS[m.month - 1]} {m.year}, {m:%H:%M}"


def prompt_systeme() -> str:
    morceaux = [PERSONNALITE, f"Nous sommes le {maintenant_en_francais()}."]
    profil = lire_profil()
    if profil:
        morceaux.append("Profil de l'utilisateur :\n" + profil)
    memoire = lire_memoire()
    if memoire:
        morceaux.append("Ce que tu sais déjà sur l'utilisateur :\n" + memoire)
    return "\n\n".join(morceaux)


def nettoyer(texte: str) -> str:
    """Retire balises de réflexion et Markdown résiduel avant la lecture à voix haute."""
    texte = re.sub(r"<think>.*?</think>", "", texte, flags=re.S)
    texte = re.sub(r"\*{1,3}|#{1,6} |`+", "", texte)
    return texte.strip()


def executer(index: dict[str, Outil], nom: str, args: dict) -> str:
    outil = index.get(nom)
    if outil is None:
        return f"Erreur : outil inconnu « {nom} »."
    print(f"   🛠️  {nom}({json.dumps(args, ensure_ascii=False)[:200]})")
    try:
        resultat = outil.fonction(**args)
    except TypeError as e:
        return f"Erreur d'arguments pour {nom} : {e}"
    except Exception as e:  # un agent qui plante ne doit pas tuer JARVIS
        return f"Erreur pendant {nom} : {e}"
    return resultat if isinstance(resultat, str) else json.dumps(resultat, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# Moteur Claude (par défaut)
# --------------------------------------------------------------------------- #

class MoteurClaude:
    """
    Utilise l'API Claude. Le repli automatique côté serveur (« fallbacks ») est
    activé : si le modèle refuse une demande par précaution, l'API la relance
    sur un autre modèle Claude dans le même appel.
    """

    RECHERCHE_WEB = {"type": "web_search_20260209", "name": "web_search"}
    LECTURE_WEB = {"type": "web_fetch_20260209", "name": "web_fetch"}

    def __init__(self) -> None:
        import anthropic

        if not os.getenv("ANTHROPIC_API_KEY"):
            raise SystemExit(
                "❌ ANTHROPIC_API_KEY manquante dans .env.\n"
                "   Les abonnements Claude.ai / ChatGPT n'incluent pas l'API : crée une clé "
                "sur https://console.anthropic.com (paiement à l'usage)."
            )
        self.client = anthropic.Anthropic()
        self.modele = os.getenv("JARVIS_MODELE", "claude-sonnet-5-5")
        self.effort = os.getenv("JARVIS_EFFORT", "low")
        self.web = True

    def _creer(self, messages, outils=(), systeme="", effort=None, max_tokens=8000):
        rep = self.client.beta.messages.create(
            model=self.modele,
            max_tokens=max_tokens,
            system=systeme,
            messages=messages,
            tools=list(outils),
            output_config={"effort": effort or self.effort},
            betas=["server-side-fallback-2026-07-01"],
            extra_body={"fallbacks": "default"},
        )
        return rep

    @staticmethod
    def _texte(rep) -> str:
        return "".join(b.text for b in rep.content if b.type == "text").strip()

    def completer(self, consigne: str, systeme: str = "", effort: str = "medium") -> str:
        """Une tâche de rédaction, sans outils (lettres, CV, posts…)."""
        rep = self._creer([{"role": "user", "content": consigne}], systeme=systeme,
                          effort=effort, max_tokens=16000)
        if rep.stop_reason == "refusal":
            raise RuntimeError("le modèle a refusé cette rédaction")
        return self._texte(rep)

    def rechercher_web(self, consigne: str, systeme: str = "", max_recherches: int = 15) -> str:
        """Un agent autonome qui cherche et lit sur le web, puis rend un texte final."""
        outils = [dict(self.RECHERCHE_WEB, max_uses=max_recherches),
                  dict(self.LECTURE_WEB, max_uses=max_recherches)]
        messages = [{"role": "user", "content": consigne}]
        for _ in range(6):  # relances en cas de pause du serveur (pause_turn)
            rep = self._creer(messages, outils, systeme, effort="medium", max_tokens=32000)
            if rep.stop_reason != "pause_turn":
                break
            messages.append({"role": "assistant", "content": rep.content})
        if rep.stop_reason == "refusal":
            raise RuntimeError("le modèle a refusé cette recherche")
        return self._texte(rep)

    def tour(self, historique: list[dict], outils: list[Outil]) -> str:
        index = {o.nom: o for o in outils}
        schemas = [o.schema_claude() for o in outils] + [dict(self.RECHERCHE_WEB, max_uses=3)]
        messages = list(historique)
        for _ in range(MAX_ETAPES_OUTILS):
            rep = self._creer(messages, schemas, prompt_systeme())
            if rep.stop_reason == "refusal":
                return "Je préfère ne pas répondre à ça. Demande-moi autre chose."
            if rep.stop_reason == "pause_turn":
                messages.append({"role": "assistant", "content": rep.content})
                continue
            if rep.stop_reason != "tool_use":
                return nettoyer(self._texte(rep))
            messages.append({"role": "assistant", "content": rep.content})
            messages.append({"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": b.id,
                 "content": executer(index, b.name, b.input)}
                for b in rep.content if b.type == "tool_use"
            ]})
        return "J'ai beaucoup travaillé sur cette demande sans conclure. Tu peux la préciser ?"


# --------------------------------------------------------------------------- #
# Moteur local gratuit : Ollama (optionnel)
# --------------------------------------------------------------------------- #

class MoteurOllama:
    def __init__(self) -> None:
        import ollama

        self.modele = os.getenv("JARVIS_MODELE_LOCAL", "qwen3:8b")
        self.client = ollama.Client(host=os.getenv("OLLAMA_HOST", "http://localhost:11434"))
        self.web = False
        try:
            self.client.show(self.modele)
        except Exception as e:
            raise SystemExit(f"❌ Ollama ou le modèle « {self.modele} » indisponible ({e}).\n"
                             f"   Lance Ollama puis : ollama pull {self.modele}")

    def _chat(self, messages, outils=None):
        kwargs = {"model": self.modele, "messages": messages, "think": False}
        if outils:
            kwargs["tools"] = [o.schema_ollama() for o in outils]
        return self.client.chat(**kwargs).message

    def completer(self, consigne: str, systeme: str = "", effort: str = "") -> str:
        messages = [{"role": "system", "content": systeme}] if systeme else []
        messages.append({"role": "user", "content": consigne})
        return nettoyer(self._chat(messages).content or "")

    def rechercher_web(self, consigne: str, systeme: str = "", max_recherches: int = 0) -> str:
        raise RuntimeError("la recherche web nécessite le moteur claude (JARVIS_MOTEUR=claude)")

    def tour(self, historique: list[dict], outils: list[Outil]) -> str:
        index = {o.nom: o for o in outils}
        messages = [{"role": "system", "content": prompt_systeme()}, *historique]
        for _ in range(MAX_ETAPES_OUTILS):
            msg = self._chat(messages, outils)
            if not msg.tool_calls:
                return nettoyer(msg.content or "")
            messages.append(msg)
            for appel in msg.tool_calls:
                nom = appel.function.name
                messages.append({"role": "tool", "tool_name": nom,
                                 "content": executer(index, nom, appel.function.arguments or {})})
        return "J'ai beaucoup travaillé sur cette demande sans conclure. Tu peux la préciser ?"


# --------------------------------------------------------------------------- #
# Façade
# --------------------------------------------------------------------------- #

def creer_moteur():
    nom = os.getenv("JARVIS_MOTEUR", "claude").lower()
    return (MoteurOllama() if nom == "ollama" else MoteurClaude()), nom


class Cerveau:
    def __init__(self) -> None:
        self.moteur, nom = creer_moteur()
        self.outils = charger_outils(self.moteur)
        self.historique: list[dict] = []
        print(f"🧠 Moteur : {nom} — outils : " + ", ".join(o.nom for o in self.outils))

    def noter_rapport(self, rapport: str) -> None:
        """Ajoute un rapport de mission à la conversation, pour que JARVIS s'en souvienne."""
        if self.historique:
            self.historique.append({"role": "user",
                                    "content": f"[Rapport automatique d'un agent] {rapport}"})
            self.historique.append({"role": "assistant", "content": "Bien noté."})

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
            return "Désolé, j'ai perdu le contact avec mon cerveau. Vérifie la connexion ou la clé API."
        texte = texte or "C'est fait."
        self.historique.append({"role": "assistant", "content": texte})
        return texte
