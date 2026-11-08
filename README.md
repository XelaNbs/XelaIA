# JARVIS — assistant vocal en français

Il écoute le micro et se déclenche quand tu dis « Jarvis ». Ta demande part à l'API Claude (`claude-sonnet-5-5`), puis la réponse est lue à voix haute avec edge-tts.

| Fichier | Rôle |
|---|---|
| `jarvis.py` | le programme |
| `requirements.txt` | modules Python |
| `install.sh` | installation guidée sur macOS, avec confirmation à chaque étape sensible |
| `.env.example` | modèle pour ta clé API (copié en `.env`, qui n'est jamais commité) |

## Installation (MacBook, Apple Silicon)

```bash
git clone https://github.com/XelaNbs/XelaIA.git
cd XelaIA
git checkout claude/exciting-goldberg-ivamp4
./install.sh
```

Le script :
1. vérifie Python 3 ;
2. installe Homebrew s'il manque, **après ta confirmation** ;
3. installe `portaudio`, dont pyaudio a besoin, **après ta confirmation** ;
4. crée l'environnement virtuel `.venv` ;
5. installe les modules dans `.venv` (rien n'est installé globalement), **après ta confirmation** ;
6. crée `.env`.

Ouvre ensuite `.env` et colle ta clé : `ANTHROPIC_API_KEY=sk-ant-...` (à créer sur https://console.anthropic.com).

## Lancement

```bash
source .venv/bin/activate
python jarvis.py --texte    # 1er test : au clavier, avec la voix
python jarvis.py            # mode vocal
```

Exemples : « Jarvis, quel temps fait-il à Paris en novembre ? », ou dis « Jarvis », attends « Oui ? », puis pose ta question.
Pour quitter : « Jarvis, au revoir » ou `Ctrl+C`.

Options : `--muet` (texte seulement), `--micros` (liste les micros), `--micro N` (choisit un micro).
Pour une voix féminine : `JARVIS_VOIX=fr-FR-DeniseNeural` dans `.env`.

## Dépannage

- **Le micro n'entend rien** : au 1er lancement, macOS demande l'accès au micro pour le Terminal. Sinon, va dans Réglages Système → Confidentialité et sécurité → Micro et active Terminal (ou iTerm, ou VS Code).
- **Erreur `CERTIFICATE_VERIFY_FAILED`** (Python installé depuis python.org) : lance `/Applications/Python 3.x/Install Certificates.command`.
- **pyaudio ne compile pas** : vérifie `brew install portaudio`, puis relance `./install.sh`.
- **pygame ne s'installe pas** (Python très récent) : `pip install pygame-ce`, c'est le même module `pygame`.

## Limites actuelles

- La reconnaissance vocale passe par le service gratuit de Google : Internet est requis et l'audio est envoyé à Google tant que JARVIS écoute.
- La mémoire de conversation (10 échanges) est perdue à chaque redémarrage.

## Feuille de route

- [ ] Mot d'activation local avec **openWakeWord** : plus d'envoi audio permanent, déclenchement plus rapide.
- [ ] Accès à **Google Agenda** (API Google Calendar + OAuth, exposé à Claude via le *tool use*).
- [ ] **Rappels** (planificateur local + notifications macOS + annonce vocale).
