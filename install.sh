#!/usr/bin/env bash
# Installation de JARVIS sur macOS (Apple Silicon).
# Chaque étape sensible demande ta confirmation avant de s'exécuter.
set -euo pipefail
cd "$(dirname "$0")"

confirmer() {
  local reponse
  read -r -p "👉 $1 [o/N] " reponse
  [[ "$reponse" =~ ^[oOyY]$ ]]
}

echo "=== Installation de JARVIS ==="

# 1. Python 3
if ! command -v python3 >/dev/null; then
  echo "❌ python3 introuvable. Installe-le depuis https://www.python.org puis relance."
  exit 1
fi
echo "✅ $(python3 --version)"

# 2. Homebrew (nécessaire pour portaudio, dont pyaudio a besoin)
if ! command -v brew >/dev/null && [ -x /opt/homebrew/bin/brew ]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
fi
if ! command -v brew >/dev/null; then
  echo "Homebrew n'est pas installé. Il faut l'installer pour obtenir portaudio."
  echo "Commande officielle (demande ton mot de passe administrateur) :"
  echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
  if confirmer "Installer Homebrew maintenant ?"; then
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    eval "$(/opt/homebrew/bin/brew shellenv)"
    if confirmer "Ajouter Homebrew à ton PATH de façon permanente (~/.zprofile) ?"; then
      echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
    fi
  else
    echo "⏹  Installation interrompue (Homebrew requis)."
    exit 1
  fi
fi
echo "✅ Homebrew : $(brew --version | head -1)"

# 3. portaudio
if brew list portaudio >/dev/null 2>&1; then
  echo "✅ portaudio déjà installé"
elif confirmer "Installer portaudio avec Homebrew (brew install portaudio) ?"; then
  brew install portaudio
else
  echo "⏹  portaudio est requis pour pyaudio."
  exit 1
fi

# 4. Environnement virtuel
if [ ! -d .venv ]; then
  echo "Création de l'environnement virtuel .venv…"
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
echo "✅ venv actif : $(python --version)"

# 5. Dépendances Python (dans le venv uniquement)
if confirmer "Installer les modules Python (anthropic, SpeechRecognition, pyaudio, edge-tts, pygame) dans .venv ?"; then
  pip install --upgrade pip
  PA="$(brew --prefix portaudio)"
  CFLAGS="-I$PA/include" LDFLAGS="-L$PA/lib" pip install -r requirements.txt
else
  echo "⏹  Modules non installés."
  exit 1
fi

# 6. Clé API
if [ ! -f .env ]; then
  cp .env.example .env
  echo "📝 Fichier .env créé : ouvre-le et colle ta clé ANTHROPIC_API_KEY."
fi

echo
echo "🎉 Installation terminée. Pour lancer JARVIS :"
echo "   source .venv/bin/activate"
echo "   python jarvis.py --texte   # test au clavier"
echo "   python jarvis.py           # mode vocal"
