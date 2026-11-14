# Pilote de l’interface et du moteur

Branche isolée `codex/integration-interface-moteur`, fondée sur `97dfdb1`.
L’installation antérieure sur 8765 est conservée. Le pilote s’ouvre sur 8767 ;
son moteur HTTP authentifié écoute uniquement sur 127.0.0.1:8766.

## Cerveau et voix

La conversation et tous les agents utilisent explicitement Claude Code, modèle
`claude-sonnet-5-5`, via l’abonnement Claude connecté. Aucun basculement API ou
Ollama. Les alias de modèles auxiliaires sont également fixés sur ce modèle.
Les métadonnées des appels réels sont conservées localement dans `engine_calls`.
Le lanceur retire les identifiants API du processus et ajoute `~/.local/bin` au
PATH. `--setting-sources ""`, outils limités et configuration MCP vide empêchent
les outils de développement du CLI de devenir les outils de l’assistant.

La transcription utilise Whisper sur le Mac et la synthèse utilise la voix
macOS. Aucun compte ElevenLabs n’est requis. Un clic sur « Démarrer la
conversation vocale » autorise le micro ; « Interrompre » coupe la lecture et
« Arrêter » coupe le micro. Le passage de l’onglet en arrière-plan coupe le micro. La détection de parole
utilise une sortie d’analyse silencieuse, indépendante des haut-parleurs.

## Stockage et missions

SQLite est la source des offres, de la mémoire, du CV extrait et du journal.
Chaque appel de stockage ouvre et ferme sa propre connexion : aucune connexion
partagée entre threads. WAL, transactions et fusion des champs modifiés évitent
l’écrasement des changements concurrents. Le cache du CV dépend du SHA-256 du PDF.
L’import historique est idempotent et conserve les fichiers d’origine.

Les noms et paramètres des fonctions des agents sont conservés. Les changements
dans emploi, memoire et missions concernent leurs accès au stockage. Des tests
AST comparent les autres fonctions à la branche de départ. Le pont remplace les
callbacks de lancement par une file durable ; il appelle les fonctions existantes.
Les corrections Claude Code et les contrôles documentaires sont dans des commits
séparés. Les missions sont exécutées successivement ; la conversation peut rester
active. La file reprend après redémarrage, au maximum trois tentatives. Une
interruption pendant une génération peut conduire à régénérer son dossier.

La routine du pilote est désactivée. Le fichier LaunchAgent Claude recherché
n’était pas présent lors de la vérification. La programmation de l’installation
8765 reste donc la seule routine active pendant le pilote. Le remplacement de
8765 et le transfert de cette routine ne sont pas effectués par ce pilote.

## Documents et limites

Les dossiers contiennent de vrais CV et lettres PDF, plus des fiches Markdown.
Les chiffres générés d’un CV sont comparés au PDF de référence avant rendu,
puis dans le PDF final ; le CV doit tenir sur une page. Ce contrôle vérifie la
présence des valeurs, pas la pertinence de leur association à chaque affirmation.
La relecture des faits reste nécessaire. Les descriptions d’offres doivent
conserver leur langue originale pour déterminer celle du dossier.

Les annonces et scores proviennent du moteur web ; l’interface indique que leurs
preuves restent à vérifier. La date de publication peut manquer dans le stockage
historique du moteur. Aucune candidature ou publication sur un réseau social
n’est envoyée automatiquement dans ce pilote. Gmail n’est pas connecté ici.

## Démarrage et retour arrière

Ouvrir `Lancer le pilote.command` relance les services arrêtés et ouvre la session
locale sans afficher le jeton. Si Claude est déconnecté, ouvrir
`Connecter Claude.command` dans Terminal et suivre la connexion officielle. Aucun
code ni secret ne doit être copié dans le chat ou dans le dépôt.

Fermer l’onglet ne supprime pas les données. Pour arrêter le pilote, arrêter les
processus qui écoutent sur 8766 et 8767, après vérification de leurs PID ; conserver
le processus 8765. La version antérieure reste accessible sur son port habituel.

## Vérification et confidentialité

17 tests automatisés passent : concurrence SQLite, import, signatures et logique
des agents, refus des autres cerveaux/clés API, authentification HTTP, séparation
des PDF entre missions, chiffres et déduplication. Le test navigateur vérifie la
séparation des cookies entre 8765 et 8767, les pages et l’affichage mobile.
Le test vocal utilise une entrée synthétique, les vraies routes de transcription,
de conversation et de synthèse, puis décode les fichiers reçus sur une sortie
silencieuse. Ce contrôle ne certifie pas le microphone ni les haut-parleurs
physiques : aucun périphérique audio matériel n’était exposé par le système.

Un dossier réel en anglais à Lisbonne a passé les contrôles des deux PDF,
numériques pour le CV et visuels pour les deux documents. Les preuves détaillées
et les documents personnels restent dans les dossiers ignorés.

Avant chaque commit, `scripts/check_public_tree.py` contrôle les chemins suivis.
Le hook local `.githooks/pre-commit` exécute ce contrôle. `.env`, le CV original,
le profil, les données, les candidatures, les contenus, SQLite, les jetons et les
fichiers audio sont exclus. Un clone neuf doit activer le hook avec
`git config core.hooksPath .githooks` avant de travailler avec des données réelles.
