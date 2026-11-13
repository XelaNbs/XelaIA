#!/bin/zsh
set -eu
cd "${0:A:h}"
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
print "Connexion officielle Claude Code à votre abonnement."
print "Si un code est demandé, collez-le uniquement dans cette fenêtre Terminal, jamais dans le chat."
env -u ANTHROPIC_API_KEY -u ANTHROPIC_AUTH_TOKEN -u CLAUDE_CODE_OAUTH_TOKEN claude auth login
print "Connexion terminée. Vous pouvez revenir dans Codex."
read -r "?Appuyez sur Entrée pour fermer."
