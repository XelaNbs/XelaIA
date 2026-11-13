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
| Cerveau et recherche web | **Claude Code**, connecté à ton abonnement Claude Pro/Max | **inclus** dans ton abonnement (dans ses limites d'usage) |
| Voix | **ElevenLabs** (voix au choix), avec edge-tts gratuit en secours | offre gratuite limitée, puis abonnement |
| Écoute | SpeechRecognition | gratuit |
| CV et lettres | ReportLab (PDF, mise en page de ton CV) | gratuit |

Autres moteurs possibles : `JARVIS_MOTEUR=api` (API Claude payante, plus rapide, clé sur console.anthropic.com) ou `JARVIS_MOTEUR=ollama` (modèle local gratuit, sans recherche web).

## Installation (MacBook, Apple Silicon)

```bash
git clone https://github.com/XelaNbs/XelaIA.git
cd XelaIA
git checkout claude/exciting-goldberg-ivamp4
./install.sh
```

Le script demande ta confirmation à chaque étape. Il peut aussi programmer la **routine du matin**.

Ensuite :
1. **Connecte Claude Code à ton abonnement** (une seule fois) : dans le Terminal, tape `claude`, choisis la connexion avec ton compte Claude (celui de ton abonnement Pro ou Max), valide dans le navigateur, puis tape `/exit`. Aucune clé, aucun compte console.
2. **Ton CV** : dépose ton CV actuel en PDF dans le dossier XelaIA, sous le nom **`mon_cv.pdf`**. Au premier lancement, Jarvis le lit et le transcrit une fois pour toutes. Chaque CV adapté part de là, avec la même mise en page. Si tu changes ton CV, remplace le fichier et Jarvis le relit tout seul.
3. **`cibles.md`** : les postes visés, par priorité, la localisation et les postes à éviter. Tu peux le modifier quand tu veux.
4. **`profil.md`** (facultatif) : ce qui n'est pas dans ton CV (salaire souhaité, disponibilité…). Pars de `profil.exemple.md`.
5. **Voix ElevenLabs** (facultatif) :
   - copie ta clé (Profil → API Keys) dans `ELEVENLABS_API_KEY` ;
   - dans la Voice Library, ajoute à « My Voices » une voix qui te plaît (cherche « butler » ou « British » pour un vrai style Jarvis, ou une voix française grave) ;
   - lance `python jarvis.py --voix` et copie l'ID choisi dans `ELEVENLABS_VOICE_ID`.

Ton CV, ton profil, tes dossiers et ta clé ne sont jamais envoyés sur GitHub.

## Lancement

Le plus simple : **double-clique sur `Jarvis.command`** dans le Finder pour lui parler à la voix, ou sur **`Jarvis-clavier.command`** pour lui écrire. La première fois, macOS peut bloquer le fichier : clic droit → Ouvrir → Ouvrir.

À la voix, commence chaque phrase par « Jarvis » : « Jarvis, … ». Ou dis juste « Jarvis », attends « Oui ? » et parle.

Depuis le Terminal :

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
| `candidatures/<date>_<entreprise>_<poste>/` | `CV_<Nom>_<Entreprise>.pdf` adapté à l'offre (dans la langue de l'offre), `LM_<Nom>_<Entreprise>.pdf`, `Fiche_offre.md` (lien pour postuler, contact, arguments d'entretien, message LinkedIn, mail) |
| `contenus/` | plans de publications TikTok / Instagram prêts à tourner |
| `donnees/offres.json` | suivi des offres et des statuts |
| `donnees/journal.md` | historique des missions |

## Ajouter un agent

Crée `agents/mon_agent.py` avec une fonction `outils(ia)` qui renvoie une liste d'`Outil`, puis ajoute-le dans `agents/__init__.py`. Jarvis saura l'utiliser tout seul.

## Feuille de route

- [x] Cerveau Claude via ton abonnement (Claude Code), avec recherche web ; API ou Ollama en option
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
- **« Claude Code n'est pas installé »** : relance `./install.sh`, puis tape `claude` pour te connecter.
- **« Claude Code : … limit »** : tu as atteint la limite d'usage de ton abonnement. Elle se recharge au bout de quelques heures.
- **Réponses un peu lentes** : chaque réponse lance Claude Code (quelques secondes). C'est le prix de la gratuité ; le moteur `api` est plus rapide.
- **Voix trop lente** : mets `ELEVENLABS_MODELE=eleven_flash_v2_5` dans `.env`.
- **« Jarvis.command » ne peut pas être ouvert** : clic droit → Ouvrir → Ouvrir (une seule fois).
- **La routine ne s'est pas lancée** : regarde `donnees/routine.log`.
- **`CERTIFICATE_VERIFY_FAILED`** : lance `/Applications/Python 3.x/Install Certificates.command`.
