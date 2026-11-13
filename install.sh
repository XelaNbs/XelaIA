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
if confirmer "Installer les modules Python (anthropic, python-docx, SpeechRecognition, pyaudio, edge-tts, pygame) dans .venv ?"; then
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
  echo "📝 Fichier .env créé : colle ta clé ANTHROPIC_API_KEY (et ElevenLabs si tu veux)."
fi
if [ ! -f profil.md ]; then
  cp profil.exemple.md profil.md
  echo "📝 Fichier profil.md créé : colle ton CV dedans pour que les agents te connaissent."
fi

# 7. Routine du matin (optionnelle) : launchd lance « jarvis.py --routine » chaque jour
PLIST="$HOME/Library/LaunchAgents/com.jarvis.routine.plist"
HEURE="${JARVIS_ROUTINE_HEURE:-8}"
if [ ! -f "$PLIST" ] && confirmer "Programmer la routine emploi chaque matin à ${HEURE}h (recherche + dossiers prêts) ?"; then
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.jarvis.routine</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PWD/.venv/bin/python</string>
    <string>$PWD/jarvis.py</string>
    <string>--routine</string>
  </array>
  <key>WorkingDirectory</key><string>$PWD</string>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>$HEURE</integer><key>Minute</key><integer>0</integer></dict>
  <key>StandardOutPath</key><string>$PWD/donnees/routine.log</string>
  <key>StandardErrorPath</key><string>$PWD/donnees/routine.log</string>
</dict>
</plist>
PLIST
  mkdir -p donnees
  launchctl load "$PLIST"
  echo "✅ Routine programmée (si le Mac dort à ${HEURE}h, elle se lance à son réveil)."
  echo "   Pour l'arrêter : launchctl unload \"$PLIST\" && rm \"$PLIST\""
fi

echo
echo "🎉 Installation terminée. Pour lancer JARVIS :"
echo "   source .venv/bin/activate"
echo "   python jarvis.py --texte   # test au clavier"
echo "   python jarvis.py           # mode vocal"
