#!/usr/bin/env python3
"""
JARVIS — assistant vocal en français.

Écoute le micro, se déclenche sur le mot « Jarvis », confie la demande au
cerveau (API Claude) qui pilote l'équipe d'agents, et répond à voix haute
(ElevenLabs, ou edge-tts gratuit en secours).

Usage :
    python jarvis.py            # mode vocal (micro + haut-parleurs)
    python jarvis.py --texte    # mode clavier (pour tester sans micro)
    python jarvis.py --micros   # liste les micros disponibles
    python jarvis.py --voix     # liste tes voix ElevenLabs
    python jarvis.py --routine  # routine du matin (offres + dossiers), sans intervention
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

VOIX = os.getenv("JARVIS_VOIX", "fr-FR-HenriNeural")  # ou fr-FR-DeniseNeural
LANGUE = "fr-FR"
MOT_ACTIVATION = "jarvis"
MOTS_SORTIE = ("au revoir", "arrête-toi", "arrete-toi", "éteins-toi", "eteins-toi")


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
# Voix : ElevenLabs (si une clé est configurée), sinon edge-tts (gratuit)
# --------------------------------------------------------------------------- #

URL_ELEVENLABS = "https://api.elevenlabs.io/v1"


class Voix:
    def __init__(self, muet: bool = False) -> None:
        self.muet = muet
        self.voix_edge = os.getenv("JARVIS_VOIX", VOIX)
        self.cle_eleven = os.getenv("ELEVENLABS_API_KEY", "").strip()
        self.voix_eleven = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
        self.modele_eleven = os.getenv("ELEVENLABS_MODELE", "eleven_multilingual_v2")
        moteur = "ElevenLabs" if self.cle_eleven and self.voix_eleven else "edge-tts"
        print(f"🔊 Voix : {moteur}")
        if not muet:
            os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
            import pygame  # import tardif : pas nécessaire en mode muet

            pygame.mixer.init()
            self._pygame = pygame

    def _elevenlabs(self, texte: str, chemin: str) -> None:
        import json
        import urllib.request

        req = urllib.request.Request(
            f"{URL_ELEVENLABS}/text-to-speech/{self.voix_eleven}"
            "?output_format=mp3_44100_128",
            data=json.dumps({
                "text": texte,
                "model_id": self.modele_eleven,
                "voice_settings": {"stability": 0.45, "similarity_boost": 0.8, "style": 0.2},
            }).encode(),
            headers={"xi-api-key": self.cle_eleven, "Content-Type": "application/json",
                     "Accept": "audio/mpeg"},
        )
        with urllib.request.urlopen(req, timeout=30) as r, open(chemin, "wb") as f:
            f.write(r.read())

    def _edge(self, texte: str, chemin: str) -> None:
        import edge_tts

        asyncio.run(edge_tts.Communicate(texte, self.voix_edge).save(chemin))

    def _generer(self, texte: str, chemin: str) -> None:
        if self.cle_eleven and self.voix_eleven:
            try:
                return self._elevenlabs(texte, chemin)
            except Exception as e:  # quota épuisé, réseau… : on bascule sur edge-tts
                print(f"⚠️  ElevenLabs indisponible ({e}), voix de secours.")
        self._edge(texte, chemin)

    def dire(self, texte: str) -> None:
        print(f"🤖 JARVIS : {texte}")
        if self.muet or not texte.strip():
            return
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            chemin = f.name
        try:
            self._generer(texte, chemin)
            self._pygame.mixer.music.load(chemin)
            self._pygame.mixer.music.play()
            while self._pygame.mixer.music.get_busy():
                time.sleep(0.05)
            self._pygame.mixer.music.unload()
        except Exception as e:  # on garde au moins le texte
            print(f"⚠️  Synthèse vocale impossible : {e}")
        finally:
            try:
                os.remove(chemin)
            except OSError:
                pass


def lister_voix_elevenlabs() -> None:
    import json
    import urllib.request

    cle = os.getenv("ELEVENLABS_API_KEY", "").strip()
    if not cle:
        sys.exit("❌ Ajoute ELEVENLABS_API_KEY dans .env d'abord.")
    req = urllib.request.Request(f"{URL_ELEVENLABS}/voices", headers={"xi-api-key": cle})
    with urllib.request.urlopen(req, timeout=20) as r:
        voix = json.load(r).get("voices", [])
    print("Voix disponibles dans ton compte ElevenLabs (copie l'ID dans ELEVENLABS_VOICE_ID) :")
    for v in voix:
        labels = ", ".join(f"{k}: {val}" for k, val in (v.get("labels") or {}).items())
        print(f"  {v['voice_id']}  {v['name']:<25} {labels}")


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


def annoncer_rapports(voix: Voix, cerveau) -> None:
    """Lit à voix haute les rapports des missions terminées."""
    from agents.missions import rapports_en_attente

    for rapport in rapports_en_attente():
        cerveau.noter_rapport(rapport)
        voix.dire("Rapport de mission. " + rapport)


def boucle_vocale(voix: Voix, cerveau, index_micro: int | None) -> None:
    oreille = Oreille(index_micro)
    voix.dire("Bonjour. JARVIS à ton service, et toute l'équipe est prête.")

    while True:
        annoncer_rapports(voix, cerveau)
        # Délai court pour pouvoir annoncer les rapports de mission entre deux écoutes.
        entendu = oreille.ecouter(delai=4, duree_max=10)
        if not entendu:
            continue
        print(f"   (entendu : {entendu})")

        commande = extraire_commande(entendu)
        if commande is None:
            continue  # pas le mot d'activation → on ignore

        if not commande:  # juste « Jarvis » → on attend la demande
            voix.dire("Oui ?")
            commande = oreille.ecouter(delai=6, duree_max=25)
            if not commande:
                voix.dire("Je n'ai rien entendu.")
                continue

        print(f"🧑 Toi : {commande}")
        if veut_quitter(commande):
            voix.dire("À plus tard. Je garde un œil sur tout.")
            return
        voix.dire(cerveau.repondre(commande))


def boucle_texte(voix: Voix, cerveau) -> None:
    print("Mode texte — tape ta demande (Entrée vide = voir les rapports, « au revoir » pour quitter).")
    while True:
        annoncer_rapports(voix, cerveau)
        try:
            demande = input("🧑 Toi : ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            return
        if not demande:
            continue
        if veut_quitter(demande):
            voix.dire("À plus tard. Je garde un œil sur tout.")
            return
        voix.dire(cerveau.repondre(demande))


def routine(muet: bool) -> None:
    """Routine du matin : recherche d'offres + dossiers, sans intervention."""
    from agents.emploi import mission_emploi
    from agents.missions import executer_mission
    from cerveau import creer_moteur

    moteur, _ = creer_moteur()
    nombre = int(os.getenv("JARVIS_ROUTINE_OFFRES", "5"))
    rapport = executer_mission("routine emploi", lambda: mission_emploi(moteur, nombre))
    print(rapport)
    if not muet:
        Voix().dire("Bonjour. " + rapport)


def main() -> None:
    parser = argparse.ArgumentParser(description="JARVIS, assistant vocal.")
    parser.add_argument("--texte", action="store_true", help="saisie au clavier au lieu du micro")
    parser.add_argument("--muet", action="store_true", help="n'affiche que le texte, sans voix")
    parser.add_argument("--micro", type=int, default=None, help="index du micro à utiliser")
    parser.add_argument("--micros", action="store_true", help="liste les micros et quitte")
    parser.add_argument("--voix", action="store_true", help="liste les voix ElevenLabs et quitte")
    parser.add_argument("--routine", action="store_true",
                        help="routine du matin : cherche les offres et prépare les dossiers")
    args = parser.parse_args()

    charger_env(Path(__file__).with_name(".env"))
    os.chdir(Path(__file__).resolve().parent)

    if args.micros:
        lister_micros()
        return
    if args.voix:
        lister_voix_elevenlabs()
        return
    if args.routine:
        routine(args.muet)
        return

    from cerveau import Cerveau

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
