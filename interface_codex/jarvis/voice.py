import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from .core import Blocked, now
from .network import api, request

def transcribe(store, audio):
    config = store.config()
    model = Path(config["whisper_model"])
    whisper = shutil.which("whisper-cli")
    ffmpeg = shutil.which("ffmpeg")
    if not whisper or not ffmpeg or not model.is_file():
        raise Blocked("Transcription locale indisponible : whisper-cli, ffmpeg ou modèle manquant")
    if not 100 < len(audio) <= 12_000_000:
        raise ValueError("Audio vide ou trop volumineux (12 Mo maximum)")
    with store.model_lock, tempfile.TemporaryDirectory(prefix="jarvis-audio-") as td:
        original = Path(td) / "capture.bin"; wav = Path(td) / "capture.wav"
        original.write_bytes(audio)
        subprocess.run([ffmpeg,"-hide_banner","-loglevel","error","-nostdin","-y","-i",str(original),"-t","45","-ar","16000","-ac","1","-c:a","pcm_s16le",str(wav)], check=True,capture_output=True,timeout=30)
        out = Path(td) / "result"
        subprocess.run([whisper,"-m",str(model),"-f",str(wav),"-l","auto","-nt","-otxt","-of",str(out),"-t","4"],check=True,capture_output=True,timeout=120)
        text = out.with_suffix(".txt").read_text().strip()
        text = re.sub(r"\[[^\]]*\]|\([^)]*(?:music|musique|silence)[^)]*\)", "", text, flags=re.I).strip()
        return {"text":text,"provider":"whisper.cpp local","pronunciation_assessed":False}

def quota(store):
    key_path = store.folder / "elevenlabs-key"
    if not key_path.exists():
        raise Blocked("ElevenLabs non connecté : aucune clé serveur. Aucun quota ou droit vérifiable.")
    response = api("https://api.elevenlabs.io/v1/user/subscription", headers={"xi-api-key":key_path.read_text().strip()})
    voices = api("https://api.elevenlabs.io/v1/voices", headers={"xi-api-key":key_path.read_text().strip()})
    return {"subscription":response,"voices":[{"voice_id":v["voice_id"],"name":v["name"]} for v in voices.get("voices",[])],
        "note":"Un quota disponible ne garantit pas l’accès à tous les modèles et voix. Aucun achat ni activation effectué."}

def speak(store, text):
    text = text[:6000].strip()
    if not text:
        raise ValueError("Texte vide")
    config = store.config()
    if config.get("voice_provider") == "elevenlabs":
        with store.model_lock:
            cap = int(config.get("elevenlabs_max_chars",0))
            if not config.get("elevenlabs_enabled") or not config.get("voice_id") or cap<=0:
                raise Blocked("Consommation ElevenLabs désactivée : activer explicitement une voix et un plafond local")
            used = sum(json.loads(x["detail"]).get("characters",0) for x in store.rows("SELECT detail FROM audit WHERE event='elevenlabs.reserved'"))
            info = quota(store)["subscription"]
            remaining = info.get("character_limit",0)-info.get("character_count",0)
            # Never opts into paid overage; holds local usage before network I/O.
            if used+len(text)>cap or len(text)>remaining or info.get("can_extend_character_limit",False):
                raise Blocked("Plafond local, quota ou dépassement payant : utilisation refusée")
            voice = config["voice_id"]
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,100}",voice):
                raise ValueError("voice_id invalide")
            store.audit("elevenlabs.reserved", {"characters":len(text)})
            key = (store.folder / "elevenlabs-key").read_text().strip()
            audio = request("https://api.elevenlabs.io/v1/text-to-speech/"+voice, {"text":text,"model_id":"eleven_multilingual_v2"}, {"xi-api-key":key},timeout=60)
            return audio,"audio/mpeg"
    voice = config.get("voice","Thomas")
    # say renders locally, including on requests from the iPhone. No browser TTS cloud.
    with tempfile.TemporaryDirectory(prefix="jarvis-tts-") as td:
        path = Path(td) / "voice.aiff"
        source = Path(td) / "text.txt"; source.write_text(text)
        subprocess.run(["/usr/bin/say","-v",voice,"-f",str(source),"-o",str(path)],check=True,capture_output=True,timeout=90)
        wav = Path(td) / "voice.wav"
        subprocess.run([shutil.which("ffmpeg") or "ffmpeg","-hide_banner","-loglevel","error","-nostdin","-y","-i",str(path),str(wav)],check=True,capture_output=True,timeout=30)
        return wav.read_bytes(),"audio/wav"
