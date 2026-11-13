# JARVIS : ton assistant vocal et le chef de ton équipe d'agents IA

Tu parles à JARVIS. Il comprend ce que tu veux, fait travailler les agents spécialisés et te rend compte à voix haute, avec un peu d'humour. Il agit sans te demander la permission à chaque étape, et il retient ce que tu lui apprends sur toi.

> ⚠️ Ce dépôt GitHub est **public**. Ton CV (`profil.md`), tes données et tes dossiers sont exclus de git et restent sur ton Mac. Pour plus de tranquillité, passe le dépôt en privé (GitHub → Settings → Danger Zone → Change visibility).

```
            Toi  ⇄  JARVIS (voix, mémoire, personnalité)
                       │
     ┌─────────────┬───┴──────────┬───────────────┬──────────────┐
  Mémoire      Agent emploi   Agent candidature  Agent mails*  Agent réseaux
 (souvenirs)   (tout le web)   (CV, lettres)      (Gmail)     (TikTok, Insta)
                                                   * prochaine étape
```

## Ce dont tu as besoin

| Brique | Outil | Coût |
|---|---|---|
| Cerveau et recherche web | **API Claude** (`claude-sonnet-5-5`) | paiement à l'usage, **à part** des abonnements Claude.ai / ChatGPT |
| Voix | **ElevenLabs** (voix au choix), avec edge-tts gratuit en secours | offre gratuite limitée, puis abonnement |
| Écoute | SpeechRecognition | gratuit |
| CV et lettres | python-docx (fichiers Word) | gratuit |

Mode 100 % gratuit possible : `JARVIS_MOTEUR=ollama` (modèle local, sans recherche web).

## Installation (MacBook, Apple Silicon)

```bash
git clone https://github.com/XelaNbs/XelaIA.git
cd XelaIA
git checkout claude/exciting-goldberg-ivamp4
./install.sh
```

Le script demande ta confirmation à chaque étape. Il peut aussi programmer la **routine du matin**.

Ensuite :
1. **`.env`** : colle ta clé API Claude (https://console.anthropic.com, rubrique « API Keys », ajoute quelques euros de crédit).
2. **`profil.md`** : colle ton CV complet, ta ville, ta mobilité, ton salaire souhaité. Les agents n'inventent rien : tout ce qu'ils écrivent vient de là. Ce fichier ne quitte pas ton Mac.
3. **`cibles.md`** : les postes visés, par priorité, et les postes à éviter. Tu peux le modifier quand tu veux.
4. **Voix ElevenLabs** (facultatif) :
   - copie ta clé (Profil → API Keys) dans `ELEVENLABS_API_KEY` ;
   - dans la Voice Library, ajoute à « My Voices » une voix qui te plaît (cherche « butler » ou « British » pour un vrai style Jarvis, ou une voix française grave) ;
   - lance `python jarvis.py --voix` et copie l'ID choisi dans `ELEVENLABS_VOICE_ID`.

## Lancement

```bash
source .venv/bin/activate
python jarvis.py            # à la voix
python jarvis.py --texte    # au clavier
python jarvis.py --routine  # lance la routine emploi tout de suite
```

Ce que tu peux lui dire :
- « Jarvis, trouve-moi les meilleures offres et prépare les dossiers. »
- « Jarvis, concentre-toi sur les Account Executive en fintech à Paris. »
- « Jarvis, prépare un dossier pour cette offre : <lien> » (au clavier).
- « Jarvis, j'ai postulé chez Qonto. » / « J'ai un entretien chez Pennylane ! »
- « Jarvis, où en sont mes candidatures ? »
- « Jarvis, prépare les contenus TikTok et Instagram de la semaine pour Padel'Prog. »

Les missions tournent **en arrière-plan** : tu continues à parler à Jarvis, puis il t'annonce à voix haute (et par notification macOS) que tout est prêt.

## Où sont les résultats

| Dossier | Contenu |
|---|---|
| `candidatures/<date>_<entreprise>_<poste>/` | `CV_….docx` adapté à l'offre, `Lettre_motivation_….docx`, `Fiche_offre.md` (lien pour postuler, contact, arguments d'entretien, message LinkedIn, mail) |
| `contenus/` | plans de publications TikTok / Instagram prêts à tourner |
| `donnees/offres.json` | suivi des offres et des statuts |
| `donnees/journal.md` | historique des missions |

Pour envoyer en PDF : ouvre le .docx, puis Fichier → Exporter en PDF.

## Ajouter un agent

Crée `agents/mon_agent.py` avec une fonction `outils(ia)` qui renvoie une liste d'`Outil`, puis ajoute-le dans `agents/__init__.py`. Jarvis saura l'utiliser tout seul.

## Feuille de route

- [x] Cerveau Claude avec recherche web (Ollama gratuit en option)
- [x] Voix ElevenLabs au choix
- [x] Mémoire durable
- [x] Équipe emploi : recherche sur tout le web, CV adapté, lettre, fiche d'entretien
- [x] Missions en arrière-plan et routine du matin
- [x] Agent réseaux : contenus TikTok et Instagram pour Padel'Prog
- [ ] Agent mails : tri de la boîte Gmail, relances de candidatures
- [ ] Publication automatique sur TikTok et Instagram
- [ ] Mot d'activation local (openWakeWord) et Google Agenda

## Dépannage

- **Micro muet** : Réglages Système → Confidentialité et sécurité → Micro → active Terminal.
- **« ANTHROPIC_API_KEY manquante »** : l'abonnement Claude.ai ne suffit pas, il faut une clé sur console.anthropic.com.
- **Voix trop lente** : mets `ELEVENLABS_MODELE=eleven_flash_v2_5` dans `.env`.
- **La routine ne s'est pas lancée** : regarde `donnees/routine.log`.
- **`CERTIFICATE_VERIFY_FAILED`** : lance `/Applications/Python 3.x/Install Certificates.command`.
