#!/usr/bin/env python3
"""
JARVIS — assistant vocal en français.

Écoute le micro, se déclenche sur le mot « Jarvis », envoie la demande à
l'API Claude et répond à voix haute avec edge-tts.

Usage :
    python jarvis.py            # mode vocal (micro + haut-parleurs)
    python jarvis.py --texte    # mode clavier (pour tester sans micro)
    python jarvis.py --micros   # liste les micros disponibles
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

# --------------------------------------------------------------------------- #
# Configuration
# --------------------------------------------------------------------------- #

MODELE = os.getenv("JARVIS_MODELE", "claude-sonnet-5-5")
VOIX = os.getenv("JARVIS_VOIX", "fr-FR-HenriNeural")  # ou fr-FR-DeniseNeural
LANGUE = "fr-FR"
MOT_ACTIVATION = "jarvis"
MOTS_SORTIE = ("au revoir", "arrête-toi", "arrete-toi", "éteins-toi", "eteins-toi")
MAX_TOURS_HISTORIQUE = 10  # nombre d'échanges gardés en mémoire
MAX_TOKENS = 2000  # inclut la réflexion interne du modèle
EFFORT = os.getenv("JARVIS_EFFORT", "low")  # low = rapide et économique, suffisant pour discuter

PROMPT_SYSTEME = (
    "Tu es JARVIS, l'assistant vocal personnel de l'utilisateur, sur son MacBook. "
    "Tu réponds toujours en français, de façon naturelle, chaleureuse et concise "
    "(2 à 4 phrases sauf si on te demande plus de détails). "
    "Tes réponses sont lues à voix haute : n'utilise jamais de Markdown, de listes "
    "à puces, d'emojis, de tableaux ni de blocs de code. Écris les nombres et "
    "symboles comme on les prononce quand c'est plus clair à l'oral. "
    "Si une demande est ambiguë, pose une courte question de clarification."
)


# --------------------------------------------------------------------------- #
# Utilitaires
# --------------------------------------------------------------------------- #

def charger_env(fichier: Path) -> None:
    """Charge un fichier .env simple (CLE=valeur) sans dépendance externe."""
    if not fichier.exists():
        return
    for ligne in fichier.read_text(encoding="utf-8").splitlines():
        ligne = ligne.strip()
        if not ligne or ligne.startswith("#") or "=" not in ligne:
            continue
        cle, valeur = ligne.split("=", 1)
        os.environ.setdefault(cle.strip(), valeur.strip().strip('"').strip("'"))


def normaliser(texte: str) -> str:
    """Minuscules, sans accents — pour comparer les mots-clés."""
    texte = unicodedata.normalize("NFD", texte.lower())
    return "".join(c for c in texte if unicodedata.category(c) != "Mn")


def extraire_commande(transcription: str) -> str | None:
    """
    Si la phrase contient « Jarvis », renvoie ce qui suit (éventuellement vide).
    Sinon renvoie None.
    """
    norm = normaliser(transcription)
    # Google transcrit parfois « jarvis » comme « jarvice », « djarvis »…
    for variante in (MOT_ACTIVATION, "jarvice", "djarvis", "jarviss"):
        idx = norm.find(variante)
        if idx != -1:
            reste = transcription[idx + len(variante):]
            return reste.strip(" ,.!?;:").strip()
    return None


# --------------------------------------------------------------------------- #
# Voix (edge-tts + pygame)
# --------------------------------------------------------------------------- #

class Voix:
    def __init__(self, voix: str = VOIX, muet: bool = False) -> None:
        self.voix = voix
        self.muet = muet
        if not muet:
            import pygame  # import tardif : pas nécessaire en mode muet

            os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
            pygame.mixer.init()
            self._pygame = pygame

    async def _generer(self, texte: str, chemin: str) -> None:
        import edge_tts

        await edge_tts.Communicate(texte, self.voix).save(chemin)

    def dire(self, texte: str) -> None:
        print(f"🤖 JARVIS : {texte}")
        if self.muet or not texte.strip():
            return
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            chemin = f.name
        try:
            asyncio.run(self._generer(texte, chemin))
            self._pygame.mixer.music.load(chemin)
            self._pygame.mixer.music.play()
            while self._pygame.mixer.music.get_busy():
                time.sleep(0.05)
            self._pygame.mixer.music.unload()
        except Exception as e:  # réseau coupé, etc. : on garde au moins le texte
            print(f"⚠️  Synthèse vocale impossible : {e}")
        finally:
            try:
                os.remove(chemin)
            except OSError:
                pass


# --------------------------------------------------------------------------- #
# Cerveau (API Claude)
# --------------------------------------------------------------------------- #

class Cerveau:
    def __init__(self) -> None:
        import anthropic

        if not os.getenv("ANTHROPIC_API_KEY"):
            sys.exit(
                "❌ ANTHROPIC_API_KEY manquante. Copie .env.example en .env et "
                "colle ta clé (https://console.anthropic.com)."
            )
        self._anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.historique: list[dict] = []

    def repondre(self, demande: str) -> str:
        self.historique.append({"role": "user", "content": demande})
        # On ne garde que les derniers échanges (le 1er message doit être "user").
        self.historique = self.historique[-(MAX_TOURS_HISTORIQUE * 2):]
        try:
            reponse = self.client.messages.create(
                model=MODELE,
                max_tokens=MAX_TOKENS,
                system=PROMPT_SYSTEME,
                output_config={"effort": EFFORT},
                messages=self.historique,
            )
            texte = "".join(
                bloc.text for bloc in reponse.content if bloc.type == "text"
            ).strip()
        except self._anthropic.AuthenticationError:
            self.historique.pop()
            return "Ma clé d'API semble invalide. Vérifie le fichier point env."
        except self._anthropic.APIConnectionError:
            self.historique.pop()
            return "Je n'arrive pas à joindre mes serveurs. Vérifie la connexion internet."
        except self._anthropic.APIError as e:
            self.historique.pop()
            print(f"⚠️  Erreur API : {e}")
            return "Désolé, j'ai rencontré une erreur en contactant Claude."

        texte = texte or "Je n'ai pas de réponse à ça."
        self.historique.append({"role": "assistant", "content": texte})
        return texte


# --------------------------------------------------------------------------- #
# Oreille (SpeechRecognition + PyAudio)
# --------------------------------------------------------------------------- #

class Oreille:
    def __init__(self, index_micro: int | None = None) -> None:
        import speech_recognition as sr

        self.sr = sr
        self.reco = sr.Recognizer()
        self.reco.pause_threshold = 0.8       # silence (s) qui termine une phrase
        self.reco.dynamic_energy_threshold = True
        self.micro = sr.Microphone(device_index=index_micro)
        print("🎙️  Calibrage du bruit ambiant (silence 1 s)…")
        with self.micro as source:
            self.reco.adjust_for_ambient_noise(source, duration=1)

    def ecouter(self, delai: float | None = None, duree_max: float = 15) -> str | None:
        """Écoute une phrase et renvoie sa transcription (ou None)."""
        sr = self.sr
        with self.micro as source:
            try:
                audio = self.reco.listen(
                    source, timeout=delai, phrase_time_limit=duree_max
                )
            except sr.WaitTimeoutError:
                return None
        try:
            return self.reco.recognize_google(audio, language=LANGUE)
        except sr.UnknownValueError:
            return None
        except sr.RequestError as e:
            print(f"⚠️  Service de reconnaissance indisponible : {e}")
            time.sleep(2)
            return None


def lister_micros() -> None:
    import speech_recognition as sr

    for i, nom in enumerate(sr.Microphone.list_microphone_names()):
        print(f"  [{i}] {nom}")


# --------------------------------------------------------------------------- #
# Boucles principales
# --------------------------------------------------------------------------- #

def veut_quitter(texte: str) -> bool:
    norm = normaliser(texte)
    return any(normaliser(m) in norm for m in MOTS_SORTIE)


def boucle_vocale(voix: Voix, cerveau: Cerveau, index_micro: int | None) -> None:
    oreille = Oreille(index_micro)
    voix.dire("Bonjour, je suis JARVIS. Dites Jarvis pour m'appeler.")

    while True:
        print("👂 En attente de « Jarvis »…")
        entendu = oreille.ecouter(duree_max=8)
        if not entendu:
            continue
        print(f"   (entendu : {entendu})")

        commande = extraire_commande(entendu)
        if commande is None:
            continue  # pas le mot d'activation → on ignore

        if not commande:  # juste « Jarvis » → on attend la demande
            voix.dire("Oui ?")
            commande = oreille.ecouter(delai=6, duree_max=20)
            if not commande:
                voix.dire("Je n'ai rien entendu.")
                continue

        print(f"🧑 Vous : {commande}")
        if veut_quitter(commande):
            voix.dire("Au revoir, à bientôt.")
            return
        voix.dire(cerveau.repondre(commande))


def boucle_texte(voix: Voix, cerveau: Cerveau) -> None:
    print("Mode texte — tape ta demande (ou « au revoir » pour quitter).")
    while True:
        try:
            demande = input("🧑 Vous : ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not demande:
            continue
        if veut_quitter(demande):
            voix.dire("Au revoir, à bientôt.")
            return
        voix.dire(cerveau.repondre(demande))


def main() -> None:
    parser = argparse.ArgumentParser(description="JARVIS, assistant vocal.")
    parser.add_argument("--texte", action="store_true", help="saisie au clavier au lieu du micro")
    parser.add_argument("--muet", action="store_true", help="n'affiche que le texte, sans voix")
    parser.add_argument("--micro", type=int, default=None, help="index du micro à utiliser")
    parser.add_argument("--micros", action="store_true", help="liste les micros et quitte")
    args = parser.parse_args()

    charger_env(Path(__file__).with_name(".env"))

    if args.micros:
        lister_micros()
        return

    cerveau = Cerveau()
    voix = Voix(muet=args.muet)
    try:
        if args.texte:
            boucle_texte(voix, cerveau)
        else:
            boucle_vocale(voix, cerveau, args.micro)
    except KeyboardInterrupt:
        print("\n👋 JARVIS arrêté.")


if __name__ == "__main__":
    main()
