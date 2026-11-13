# JARVIS : ton assistant vocal et le chef de ton équipe d'agents IA

Tu parles à JARVIS. Il comprend ce que tu veux, fait travailler les agents spécialisés et te rend compte à voix haute, avec un peu d'humour. Il agit sans te demander la permission à chaque étape, et il retient ce que tu lui apprends sur toi.

```
            Toi  ⇄  JARVIS (voix, mémoire, personnalité)
                       │
     ┌─────────────┬───┴──────────┬───────────────┬──────────────┐
  Mémoire      Agent emploi   Agent candidature  Agent mails*  Agent réseaux*
 (souvenirs)  (France Travail) (lettres, mails)   (Gmail)       (ton appli)
                                                   * prochaines étapes
```

## La solution 100 % gratuite (par défaut)

| Brique | Outil | Coût |
|---|---|---|
| Cerveau | **Ollama** + modèle `qwen3:8b`, qui tourne en local sur le Mac | gratuit, hors ligne, privé |
| Écoute | SpeechRecognition (service Google gratuit) | gratuit |
| Voix | edge-tts (voix neuronales Microsoft) | gratuit |
| Offres d'emploi | API officielle France Travail | gratuit (inscription) |

Pour plus d'intelligence, passe `JARVIS_MOTEUR=claude` dans `.env` (API Claude, payante). Le reste ne change pas.

## Installation (MacBook, Apple Silicon)

```bash
git clone https://github.com/XelaNbs/XelaIA.git
cd XelaIA
git checkout claude/exciting-goldberg-ivamp4
./install.sh
```

Le script installe Homebrew, portaudio, **Ollama** et son modèle (environ 5 Go), le venv et les modules. Il demande ta confirmation à chaque étape.

Ensuite :
1. **`profil.md`** : colle ton CV et ce que tu recherches. C'est ce qui permet aux agents de travailler pour toi. Ce fichier ne quitte jamais ton Mac et n'est pas envoyé sur GitHub.
2. **France Travail** (5 minutes, gratuit) : crée un compte sur https://francetravail.io, puis « Créer une application » et abonne-la à l'API **Offres d'emploi v2**. Copie l'identifiant et la clé secrète dans `.env`.

## Lancement

```bash
source .venv/bin/activate
python jarvis.py --texte    # au clavier
python jarvis.py            # à la voix
```

Exemples :
- « Jarvis, je cherche un CDI de développeur Python à Paris, trouve-moi les meilleures offres. »
- « Jarvis, prépare les candidatures pour les trois meilleures. »
- « Jarvis, retiens que je ne veux pas travailler dans la banque. »
- « Jarvis, où en sont mes candidatures ? »

Les candidatures rédigées (objet, mail, lettre de motivation) sont enregistrées dans `candidatures/`. Les offres suivies sont dans `donnees/offres.json`, et la mémoire de Jarvis dans `donnees/memoire.md`.

## Ajouter un agent

Crée `agents/mon_agent.py` avec une fonction `outils(completer)` qui renvoie une liste d'`Outil`, puis ajoute-le dans `agents/__init__.py`. Jarvis saura l'utiliser tout seul.

## Feuille de route

- [x] Cerveau gratuit local (Ollama) ou Claude au choix
- [x] Mémoire durable
- [x] Agent emploi : recherche France Travail et tri selon ton profil
- [x] Agent candidature : mail et lettre sur mesure
- [ ] Agent mails : envoi des candidatures depuis Gmail, avec un plafond quotidien, et tri de ta boîte
- [ ] Agent contacts : trouver le recruteur ou le manager et son email
- [ ] Mode autonome : recherche et candidatures chaque matin, puis un résumé vocal
- [ ] Agent réseaux sociaux pour ton appli
- [ ] Mot d'activation local (openWakeWord) et transcription locale (Whisper)
- [ ] Google Agenda et rappels

## Dépannage

- **Micro muet** : Réglages Système → Confidentialité et sécurité → Micro → active Terminal.
- **« Ollama indisponible »** : lance `brew services start ollama`, puis `ollama pull qwen3:8b`.
- **Jarvis lent ou peu malin** : avec 16 Go de RAM, essaie `qwen3:4b` (plus rapide). Avec 24 Go ou plus, `qwen3:14b` est plus intelligent. Change `JARVIS_MODELE_LOCAL` dans `.env`.
- **`CERTIFICATE_VERIFY_FAILED`** : lance `/Applications/Python 3.x/Install Certificates.command`.
