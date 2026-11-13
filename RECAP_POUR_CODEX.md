# Récap du travail de Claude sur JARVIS, pour Codex

Bonjour Codex. Alexandre a deux versions de JARVIS :
- **la tienne** : une interface web sur `http://localhost:8765` qui lui plaît beaucoup ;
- **la mienne (Claude)** : le moteur d'agents, en Python, sans interface web.

Il veut savoir si on peut brancher mon moteur derrière ton interface **sans risque**. Voici tout ce qu'il faut savoir pour en juger.

---

## 1. Où est le code

- Dépôt : `https://github.com/XelaNbs/XelaIA` (**public**), branche `claude/exciting-goldberg-ivamp4`.
- Langage : Python 3, dans un venv `.venv/`.
- Aucun serveur web, aucun port ouvert. Pas de conflit possible avec le port 8765.

## 2. Ce que fait mon moteur

| Fonction | Détail |
|---|---|
| Conversation | Personnalité JARVIS (majordome high-tech, tutoiement, humour). Agit sans demander de permission. Mémoire durable. |
| Agent chercheur d'offres | Recherche web (Welcome to the Jungle, LinkedIn, Indeed, APEC, HelloWork, pages carrières…). Filtre selon `cibles.md` (postes par priorité, localisation, postes à éviter). Ignore les offres déjà traitées. |
| Agent rédacteur | Pour chaque offre : **CV adapté en PDF** (même mise en page que le CV d'origine d'Alexandre, une page, dans la langue de l'offre), **lettre de motivation en PDF**, **fiche** (lien pour postuler, contact, arguments d'entretien, message LinkedIn, mail). N'invente aucune donnée : tout part du CV d'origine. |
| Suivi | Statuts : trouvée, dossier prêt, postulée, entretien, refusée, écartée. |
| Missions en arrière-plan | Les tâches longues tournent dans des threads. Un rapport est déposé dans une file à la fin, et une notification macOS s'affiche. |
| Routine du matin | `python jarvis.py --routine`, programmable par launchd : recherche et dossiers sans intervention. **Aucun envoi automatique** de candidature : Alexandre postule lui-même. |
| Agent réseaux | Plans de contenus TikTok et Instagram pour son appli de padel Padel'Prog (`appli.md`). |
| Voix | ElevenLabs si configuré, sinon edge-tts. Écoute micro via SpeechRecognition, mot d'activation « Jarvis ». |

## 3. Le cerveau (important pour les coûts)

Fichier `cerveau.py`, variable `JARVIS_MOTEUR` dans `.env` :
- `claude-code` (**par défaut**) : lance `claude -p --output-format json` (Claude Code, inclus dans l'abonnement Claude d'Alexandre). Aucun coût en plus, dans les limites d'usage de l'abonnement.
  - Outils autorisés : `WebSearch`, `WebFetch`, et `Read` pour lire le CV.
  - Outils interdits : `Bash`, `Edit`, `Write`.
- `api` : API Claude payante (Alexandre n'a pas de compte, à ne pas utiliser).
- `ollama` : modèle local gratuit, sans recherche web.

## 4. Les points d'entrée à appeler depuis une interface

À exécuter avec le Python du venv, depuis la racine du dépôt :

```python
from jarvis import charger_env; from pathlib import Path
charger_env(Path(".env"))

from cerveau import Cerveau
cerveau = Cerveau()                      # charge le moteur, les agents et le CV d'origine
texte = cerveau.repondre("Trouve-moi 3 offres et prépare les dossiers")
# → réponse de JARVIS (texte court, prévu pour être lu à voix haute)
# Les missions longues partent en arrière-plan et la réponse revient tout de suite.

from agents.missions import rapports_en_attente, etat_missions
rapports_en_attente()   # list[str] : rapports des missions terminées (à interroger régulièrement)
cerveau.noter_rapport(r)  # pour que JARVIS se souvienne du rapport dans la conversation
etat_missions()         # missions en cours

from agents.emploi import suivi_candidatures, changer_statut
suivi_candidatures()    # texte : offres par statut
changer_statut("Qonto", "postulée")
```

Données lisibles directement :

| Fichier | Contenu |
|---|---|
| `donnees/offres.json` | offres suivies : titre, entreprise, lieu, lien, score, statut, dossier |
| `candidatures/<date>_<entreprise>_<poste>/` | `CV_….pdf`, `LM_….pdf`, `Fiche_offre.md` |
| `contenus/` | plans de publications réseaux |
| `donnees/memoire.md` | mémoire de JARVIS |
| `donnees/journal.md` | historique des missions |
| `donnees/cv_maitre.json` | CV d'origine transcrit depuis `mon_cv.pdf` |

## 5. Fichiers personnels : ne jamais les committer

Le dépôt est public. Ces fichiers sont dans `.gitignore` et doivent le rester : `.env`, `mon_cv.pdf`, `mon_cv/`, `profil.md`, `donnees/`, `candidatures/`, `contenus/`.

## 6. État des tests

- Testé dans un conteneur Linux, avec un **faux Claude** : boucle d'outils, missions en arrière-plan, rapports, suivi, génération des PDF (rendu vérifié visuellement avec le vrai contenu du CV).
- **Pas encore testé en réel** : le vrai Claude Code sur le Mac, la vraie recherche web, ElevenLabs, le micro.

## 7. Proposition d'intégration (à valider par toi)

Un seul responsable par partie, pour ne pas se marcher dessus :
- **Toi (Codex)** : l'interface web (port 8765), son style, son ergonomie.
- **Moi (Claude)** : le moteur d'agents (`cerveau.py`, `agents/`).
- **Le lien** : ton serveur appelle les points d'entrée de la section 4.
  - Si ton backend est en Python : import direct.
  - Sinon : je peux ajouter une petite API locale (par exemple `POST /message`, `GET /rapports`, `GET /candidatures`, `GET /fichiers/...`) sur un autre port, ou en ligne de commande avec sortie JSON.
- On travaille sur une branche séparée, et ta version actuelle reste intacte tant qu'Alexandre n'a pas validé.

## 8. Questions pour toi

1. Ton interface fait-elle déjà un vrai travail derrière (recherche d'offres réelles, fichiers PDF créés sur le disque), ou est-ce surtout l'interface ?
2. En quel langage est ton backend, et comment ta page communique-t-elle avec lui ?
3. Quel modèle d'IA utilises-tu (abonnement ChatGPT ?) ? Si on fusionne, il faudra un seul cerveau pour éviter deux mémoires et deux listes d'offres.
4. Vois-tu un risque à ce que ton interface appelle mon moteur comme décrit en section 4 ?
5. Préfères-tu un import Python direct, ou une API locale ?
