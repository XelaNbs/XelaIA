"""
Cerveau de JARVIS : le modèle de langage et la boucle d'outils.

Moteurs (variable JARVIS_MOTEUR dans .env) :
  - "claude-code" (par défaut) : ton abonnement Claude Pro/Max via Claude Code,
                                 avec recherche web, sans aucun coût en plus.
  - "api"                      : API Claude payante (clé console.anthropic.com).
  - "ollama"                   : modèle local gratuit (sans recherche web).

JARVIS ne fait pas tout lui-même : il délègue aux agents (dossier agents/),
qui travaillent en arrière-plan, puis il te rend compte.
"""

from __future__ import annotations

import base64
import json
import os
import re
from datetime import datetime
from pathlib import Path

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


def extraire_objet_json(texte: str) -> dict:
    """Lit un objet JSON dans une réponse, même entourée de texte."""
    try:
        return json.loads(texte)
    except json.JSONDecodeError:
        debut, fin = texte.find("{"), texte.rfind("}")
        if debut == -1 or fin == -1:
            raise ValueError("pas de JSON dans la réponse")
        return json.loads(texte[debut:fin + 1])


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
            raise SystemExit("❌ Moteur « api » choisi mais ANTHROPIC_API_KEY manquante dans .env. "
                             "Sans clé, mets JARVIS_MOTEUR=claude-code (ton abonnement).")
        self.client = anthropic.Anthropic()
        self.modele = os.getenv("JARVIS_MODELE", "claude-sonnet-5-5")
        self.effort = os.getenv("JARVIS_EFFORT", "low")
        self.web = True

    def _creer(self, messages, outils=(), systeme="", effort=None, max_tokens=8000,
               schema=None):
        output_config = {"effort": effort or self.effort}
        if schema:  # sorties structurées : la réponse respecte exactement ce schéma JSON
            output_config["format"] = {"type": "json_schema", "schema": schema}
        rep = self.client.beta.messages.create(
            model=self.modele,
            max_tokens=max_tokens,
            system=systeme,
            messages=messages,
            tools=list(outils),
            output_config=output_config,
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

    def completer_json(self, consigne: str, schema: dict, systeme: str = "",
                       pdf: Path | None = None, effort: str = "medium") -> dict:
        """Une rédaction qui renvoie des données structurées (CV, lettre…)."""
        import anthropic

        contenu = [{"type": "text", "text": consigne}]
        if pdf:
            donnees = base64.standard_b64encode(Path(pdf).read_bytes()).decode()
            contenu.insert(0, {"type": "document", "source": {
                "type": "base64", "media_type": "application/pdf", "data": donnees}})
        messages = [{"role": "user", "content": contenu}]
        try:
            rep = self._creer(messages, systeme=systeme, effort=effort, max_tokens=16000,
                              schema=schema)
        except anthropic.BadRequestError as e:  # repli : JSON demandé dans la consigne
            print(f"⚠️  Sortie structurée refusée ({e}), repli sur JSON libre.")
            rep = self._creer(messages, effort=effort, max_tokens=16000,
                              systeme=systeme + "\nRéponds uniquement avec un objet JSON valide "
                              f"respectant ce schéma : {json.dumps(schema)}")
        if rep.stop_reason == "refusal":
            raise RuntimeError("le modèle a refusé cette rédaction")
        return extraire_objet_json(self._texte(rep))

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
# Moteur Claude Code : utilise TON abonnement Claude (Pro/Max), sans clé API
# --------------------------------------------------------------------------- #

class MoteurClaudeCode:
    """
    Passe par le programme `claude` (Claude Code) en mode non interactif.
    Claude Code est inclus dans les abonnements Claude Pro et Max : aucun coût en
    plus, mais les limites d'usage de l'abonnement s'appliquent.
    """

    INTERDITS = "Bash,Edit,Write,MultiEdit,NotebookEdit,Task"

    def __init__(self) -> None:
        import shutil
        from integration.environment import claude_binary

        self.binaire = claude_binary()
        if not Path(self.binaire).exists():
            raise SystemExit(
                "❌ Claude Code n'est pas installé. Lance ./install.sh, ou dans le Terminal :\n"
                "   curl -fsSL https://claude.ai/install.sh | bash\n"
                "   puis tape « claude » une fois pour te connecter avec ton compte Claude."
            )
        self.modele = os.getenv("JARVIS_MODELE_CC", "sonnet")
        self.web = True

    def _lancer(self, consigne: str, outils: str = "", delai: int = 900) -> str:
        import subprocess

        from integration.environment import subscription_environment
        env = subscription_environment()
        commande = [self.binaire, "-p", "--output-format", "json", "--model", self.modele,
                    "--restricted", "--setting-sources", "",
                    "--tools", outils, "--disallowedTools", self.INTERDITS + ",mcp__*",
                    "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}']
        if outils:
            commande += ["--allowedTools", outils]
        res = subprocess.run(commande, input=consigne, capture_output=True, text=True,
                             timeout=delai, env=env, cwd=str(Path(__file__).resolve().parent))
        try:
            donnees = json.loads(res.stdout)
        except json.JSONDecodeError:
            raise RuntimeError(f"Claude Code a échoué : {(res.stderr or res.stdout)[:300]}")
        if donnees.get("is_error"):
            raise RuntimeError(f"Claude Code : {str(donnees.get('result'))[:300]}")
        if res.returncode:
            raise RuntimeError(f"Claude Code a quitté avec le code {res.returncode}")
        from agents.stockage import connexion
        import time
        with connexion(True) as c:
            c.execute('INSERT INTO engine_calls(kind,result,created) VALUES(?,?,?)',('claude-code',json.dumps({'modelUsage':donnees.get('modelUsage',{}),'session_id':donnees.get('session_id'),'duration_ms':donnees.get('duration_ms')},ensure_ascii=False),time.time()))
        return (donnees.get("result") or "").strip()

    def completer(self, consigne: str, systeme: str = "", effort: str = "") -> str:
        return self._lancer(f"{systeme}\n\n{consigne}".strip())

    def completer_json(self, consigne: str, schema: dict, systeme: str = "",
                       pdf: Path | None = None, effort: str = "") -> dict:
        outils = ""
        is_cv='experiences' in schema.get('properties',{})
        if is_cv:
            consigne += "\nConserve exactement les noms d'employeurs, d'écoles, les dates et chiffres du CV d'origine. N'ajoute aucun chiffre, même pour décrire une durée."
        if pdf:
            consigne = f"Lis le fichier PDF {Path(pdf).resolve()} avec l'outil Read.\n\n{consigne}"
            outils = "Read"
        texte = self._lancer(
            f"{systeme}\n\n{consigne}\n\nRéponds UNIQUEMENT avec un objet JSON valide, sans "
            f"texte autour, respectant ce schéma JSON :\n{json.dumps(schema, ensure_ascii=False)}",
            outils)
        value=extraire_objet_json(texte)
        if is_cv:
            from integration.document_validation import validate_cv_numbers
            validate_cv_numbers(value,pdf)
        return value

    def rechercher_web(self, consigne: str, systeme: str = "", max_recherches: int = 15) -> str:
        return self._lancer(
            f"{systeme}\n\nTu peux faire jusqu'à {max_recherches} recherches web (WebSearch) "
            f"et lire des pages (WebFetch).\n\n{consigne}", "WebSearch,WebFetch")

    def tour(self, historique: list[dict], outils: list[Outil]) -> str:
        index = {o.nom: o for o in outils}
        catalogue = "\n".join(
            f"- {o.nom}({', '.join(o.parametres)}) : {o.description}" for o in outils)
        conversation = "\n".join(
            f"{'UTILISATEUR' if m['role'] == 'user' else 'JARVIS'} : {m['content']}"
            for m in historique if isinstance(m.get("content"), str))
        resultats = ""
        for _ in range(MAX_ETAPES_OUTILS):
            consigne = f"""{prompt_systeme()}

TES OUTILS (tu les déclenches via le champ "actions") :
{catalogue}
Tu as aussi la recherche web (WebSearch, WebFetch) pour les questions d'actualité.

CONVERSATION :
{conversation}
{("RÉSULTATS DE TES ACTIONS PRÉCÉDENTES :" + resultats) if resultats else ""}

Réponds UNIQUEMENT avec un objet JSON, sans texte autour :
{{"actions": [{{"outil": "nom", "arguments": {{...}}}}], "reponse": "ce que tu dis à l'utilisateur"}}
Si tu as besoin du résultat d'une action avant de répondre, mets les actions et laisse \
"reponse" vide : tu recevras les résultats. Sinon, "actions" est une liste vide."""
            try:
                sortie = extraire_objet_json(self._lancer(consigne, "WebSearch,WebFetch", 300))
            except ValueError:
                return "Désolé, je me suis embrouillé. Tu peux répéter ?"
            actions = sortie.get("actions") or []
            for a in actions:
                nom = a.get("outil", "")
                r = executer(index, nom, a.get("arguments") or {})
                resultats += f"\n- {nom} → {r}"
            if sortie.get("reponse") or not actions:
                return nettoyer(sortie.get("reponse") or "C'est fait.")
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

    def completer_json(self, consigne: str, schema: dict, systeme: str = "",
                       pdf: Path | None = None, effort: str = "") -> dict:
        if pdf:
            from pypdf import PdfReader

            texte = "\n".join(p.extract_text() or "" for p in PdfReader(str(pdf)).pages)
            consigne = f"CONTENU DU PDF :\n{texte}\n\n{consigne}"
        messages = [{"role": "system", "content": systeme}] if systeme else []
        messages.append({"role": "user", "content": consigne})
        rep = self.client.chat(model=self.modele, messages=messages, format=schema, think=False)
        return extraire_objet_json(rep.message.content or "{}")

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
    """
    auto (défaut) : ton abonnement Claude via Claude Code, sauf si une clé API est fournie.
    claude-code   : abonnement Claude Pro/Max (aucun coût en plus).
    api           : API Claude payante (console.anthropic.com).
    ollama        : modèle local gratuit.
    """
    nom = os.getenv("JARVIS_MOTEUR", "claude-code").lower()
    if nom != 'claude-code':
        raise RuntimeError('Pilote : seul JARVIS_MOTEUR=claude-code est autorisé. Aucun repli API ou Ollama.')
    if 'ANTHROPIC_API_KEY' in os.environ:
        raise RuntimeError('ANTHROPIC_API_KEY est interdite dans le processus moteur')
    return MoteurClaudeCode(), nom


class Cerveau:
    def __init__(self) -> None:
        self.moteur, nom = creer_moteur()
        from agents.emploi import cv_maitre

        try:
            cv_maitre(self.moteur)  # lit ton CV d'origine (une seule fois, puis cache)
        except Exception as e:
            print(f"⚠️  Lecture du CV impossible : {e}")
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
