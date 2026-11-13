"""
Agents emploi : chercheur d'offres, rédacteur de CV et de lettres.

1. L'agent chercheur parcourt le web (Welcome to the Jungle, LinkedIn, Indeed,
   APEC, HelloWork, pages carrières…) et sélectionne les offres qui collent
   au profil (profil.md) et aux cibles (cibles.md).
2. Pour chaque offre retenue, l'agent rédacteur prépare un dossier complet :
   CV adapté, lettre de motivation, fiche de l'offre (lien, contact, arguments,
   points à préparer, message court pour le recruteur).
3. JARVIS te prévient : tu n'as plus qu'à postuler.

Les dossiers sont dans candidatures/, le suivi dans donnees/offres.json.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime

from . import DONNEES, RACINE, Outil, missions
from .documents import balisage_vers_docx
from .memoire import lire_cibles, lire_memoire, lire_profil

FICHIER_OFFRES = DONNEES / "offres.json"
DOSSIER_CANDIDATURES = RACINE / "candidatures"

STATUTS = ("trouvée", "dossier prêt", "postulée", "entretien", "refusée", "écartée")


# --------------------------------------------------------------------------- #
# Suivi des offres
# --------------------------------------------------------------------------- #

def _charger() -> dict[str, dict]:
    if FICHIER_OFFRES.exists():
        return json.loads(FICHIER_OFFRES.read_text(encoding="utf-8"))
    return {}


def _sauver(offres: dict[str, dict]) -> None:
    FICHIER_OFFRES.write_text(json.dumps(offres, ensure_ascii=False, indent=1), encoding="utf-8")


def _cle(offre: dict) -> str:
    base = f"{offre.get('entreprise', '')}-{offre.get('titre', '')}".lower()
    return re.sub(r"[^a-z0-9]+", "-", base).strip("-")[:90]


def _extraire_json(texte: str):
    """Récupère le premier tableau JSON présent dans une réponse."""
    bloc = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", texte, re.S)
    brut = bloc.group(1) if bloc else texte[texte.find("["): texte.rfind("]") + 1]
    try:
        return json.loads(brut)
    except json.JSONDecodeError:
        return []


def _verifier_profil() -> str | None:
    if not lire_profil():
        return ("Le fichier profil.md est vide. Colle ton CV dedans pour que les agents "
                "puissent travailler.")
    return None


# --------------------------------------------------------------------------- #
# Agent chercheur
# --------------------------------------------------------------------------- #

SYSTEME_CHERCHEUR = """Tu es un chasseur d'offres d'emploi expert du marché français, \
méticuleux et exigeant. Tu travailles pour un candidat précis et tu ne retiens que des \
offres réelles, actuelles et pertinentes pour lui."""


def chercher_offres(ia, nombre: int = 8, focus: str = "") -> list[dict]:
    deja_vues = [f"{o['entreprise']} — {o['titre']}" for o in _charger().values()]
    consigne = f"""Nous sommes le {date.today():%d/%m/%Y}. Trouve les {nombre} meilleures \
offres d'emploi pour ce candidat.

PROFIL ET CV :
{lire_profil()}

POSTES CIBLÉS, PRIORITÉS ET POSTES À ÉVITER :
{lire_cibles()}

INFORMATIONS COMPLÉMENTAIRES (préférences, lieu, salaire…) :
{lire_memoire() or "aucune"}

{"CONSIGNE PARTICULIÈRE POUR CETTE RECHERCHE : " + focus if focus else ""}

MÉTHODE :
- Cherche partout : Welcome to the Jungle, LinkedIn Jobs, Indeed, APEC, HelloWork, \
Jobteaser, France Travail, Glassdoor, les pages carrières d'entreprises (notamment SaaS, \
fintech, scale-ups). Varie les intitulés, en français et en anglais, en commençant par la \
priorité 1.
- Ne garde que des offres publiées il y a moins de 30 jours et encore ouvertes. Ouvre la \
page de l'offre pour vérifier qu'elle existe et lire les missions et les exigences.
- Respecte la localisation et les préférences du candidat si elles sont connues.
- Écarte les postes de la liste « à éviter » et les offres trop éloignées du profil.
- Ignore ces offres déjà traitées : {"; ".join(deja_vues[-150:]) or "aucune"}.

RENDU : uniquement un tableau JSON (dans un bloc ```json), trié du meilleur au moins bon, \
chaque élément avec ces clés :
"titre", "entreprise", "lieu", "contrat", "salaire" (ou null), "teletravail" (ou null),
"lien" (URL directe de l'offre), "source", "date_publication",
"priorite" (1, 2 ou 3 selon les cibles), "score" (0 à 100, adéquation réelle),
"pourquoi" (2 phrases : pourquoi ce poste lui va),
"points_faibles" (ce qui pourrait coincer et comment le compenser),
"contact" (nom, rôle et email ou profil LinkedIn du recruteur ou manager s'ils sont publics, sinon null),
"description" (missions et exigences de l'offre, 1500 caractères maximum)."""
    texte = ia.rechercher_web(consigne, SYSTEME_CHERCHEUR, max_recherches=25)
    offres = [o for o in _extraire_json(texte) if isinstance(o, dict) and o.get("titre")]
    return offres[:nombre]


# --------------------------------------------------------------------------- #
# Agent rédacteur
# --------------------------------------------------------------------------- #

SYSTEME_REDACTEUR = """Tu es un expert du recrutement commercial (sales, account \
management, business development) en France, qui écrit des CV et des lettres qui \
décrochent des entretiens. Style : concret, chiffré, sobre, sans formules creuses. \
Tu n'inventes JAMAIS une expérience, un diplôme, un chiffre ou une compétence absents \
du profil : tu reformules, sélectionnes et ordonnes ce qui existe."""


def _consigne_offre(offre: dict) -> str:
    return f"""OFFRE : {offre['titre']} chez {offre['entreprise']} ({offre.get('lieu')}, \
{offre.get('contrat')})
Lien : {offre.get('lien')}
{offre.get('description', '')}

PROFIL ET CV DU CANDIDAT :
{lire_profil()}

INFORMATIONS COMPLÉMENTAIRES :
{lire_memoire() or "aucune"}"""


def _nom_dossier(offre: dict) -> str:
    base = f"{date.today():%Y-%m-%d}_{offre['entreprise']}_{offre['titre']}"
    return re.sub(r"[^\w-]+", "_", base)[:90].strip("_")


def preparer_dossier(ia, offre: dict) -> str:
    dossier = DOSSIER_CANDIDATURES / _nom_dossier(offre)
    contexte = _consigne_offre(offre)

    cv = ia.completer(f"""{contexte}

Rédige le CV du candidat, adapté à cette offre (une page, compatible avec les logiciels \
de tri des recruteurs). Titre du CV = intitulé proche du poste visé. Mets en avant les \
expériences, résultats chiffrés et mots-clés qui correspondent à l'offre.
Utilise exactement ce balisage, sans rien d'autre avant ni après :
# Prénom Nom
Titre du CV
Téléphone | Email | Ville | LinkedIn (seulement ceux présents dans le profil)
## Profil
(3 lignes d'accroche ciblées sur l'offre)
## Expériences professionnelles
### Poste — Entreprise, Ville (dates)
- réalisation concrète et chiffrée
## Formation
## Compétences
## Langues
(ajoute ## Centres d'intérêt seulement si utile au poste)""", SYSTEME_REDACTEUR)

    lettre = ia.completer(f"""{contexte}

Rédige la lettre de motivation (250 à 330 mots) : une accroche liée à l'entreprise ou au \
poste, deux paragraphes reliant 2 ou 3 réalisations du profil aux besoins de l'offre, une \
conclusion qui propose un échange. Commence par le bloc coordonnées du candidat, puis \
l'objet. Texte simple, paragraphes séparés par une ligne vide, pas de titre Markdown.""",
                          SYSTEME_REDACTEUR)

    fiche = ia.completer(f"""{contexte}

Prépare la fiche de candidature, en Markdown, avec ces sections :
## Pourquoi postuler
## Points à défendre en entretien (3 à 5, avec les exemples du profil à raconter)
## Points faibles possibles et réponses
## Questions à poser au recruteur
## Message LinkedIn au recruteur (300 caractères maximum)
## Mail de candidature (si la candidature se fait par mail : objet + 100 mots)""",
                         SYSTEME_REDACTEUR)

    prenom_nom = (cv.splitlines()[0].lstrip("# ").strip() if cv else "Candidat") or "Candidat"
    nom_fichier = re.sub(r"[^\w-]+", "_", prenom_nom)
    balisage_vers_docx(cv, dossier / f"CV_{nom_fichier}.docx")
    balisage_vers_docx(lettre, dossier / f"Lettre_motivation_{nom_fichier}.docx", lettre=True)
    contact = offre.get("contact") or "non trouvé"
    (dossier / "Fiche_offre.md").write_text(
        f"# {offre['titre']} — {offre['entreprise']}\n\n"
        f"- **Lien pour postuler** : {offre.get('lien')}\n"
        f"- **Lieu / contrat / salaire** : {offre.get('lieu')} / {offre.get('contrat')} / "
        f"{offre.get('salaire') or 'non précisé'}\n"
        f"- **Contact** : {json.dumps(contact, ensure_ascii=False) if not isinstance(contact, str) else contact}\n"
        f"- **Score** : {offre.get('score', '?')}/100 — priorité {offre.get('priorite', '?')}\n\n"
        f"{fiche}\n\n---\n## Offre\n{offre.get('description', '')}\n",
        encoding="utf-8",
    )
    return str(dossier.relative_to(RACINE))


def _enregistrer(offre: dict, statut: str, dossier: str | None = None) -> None:
    stock = _charger()
    cle = _cle(offre)
    fiche = stock.get(cle, {})
    fiche.update({k: offre.get(k) for k in ("titre", "entreprise", "lieu", "contrat", "lien",
                                            "score", "priorite", "contact")})
    fiche["statut"] = statut
    fiche["maj"] = f"{datetime.now():%d/%m/%Y}"
    if dossier:
        fiche["dossier"] = dossier
    stock[cle] = fiche
    _sauver(stock)


# --------------------------------------------------------------------------- #
# Missions complètes
# --------------------------------------------------------------------------- #

def mission_emploi(ia, nombre: int = 5, focus: str = "") -> str:
    if (erreur := _verifier_profil()):
        return erreur
    offres = chercher_offres(ia, nombre, focus)
    if not offres:
        return "L'agent chercheur n'a trouvé aucune nouvelle offre pertinente cette fois-ci."
    prets = []
    for offre in offres:
        try:
            dossier = preparer_dossier(ia, offre)
            _enregistrer(offre, "dossier prêt", dossier)
            prets.append(f"{offre['titre']} chez {offre['entreprise']}")
        except Exception as e:
            print(f"⚠️  Dossier {offre.get('entreprise')} : {e}")
            _enregistrer(offre, "trouvée")
    return (f"{len(prets)} dossiers de candidature sont prêts : " + " ; ".join(prets)
            + ". CV, lettres et fiches sont dans le dossier candidatures. Il ne reste qu'à postuler.")


def mission_offre_precise(ia, offre_texte: str) -> str:
    """Prépare un dossier pour une offre donnée par l'utilisateur (lien ou description)."""
    if (erreur := _verifier_profil()):
        return erreur
    texte = ia.rechercher_web(
        f"""Voici une offre d'emploi (lien ou texte) : {offre_texte}
Si c'est un lien, ouvre la page. Rends uniquement un tableau JSON d'un seul élément avec
les clés "titre", "entreprise", "lieu", "contrat", "salaire", "lien", "contact" (recruteur
public ou null) et "description" (missions et exigences, 1500 caractères maximum).""",
        SYSTEME_CHERCHEUR, max_recherches=5)
    offres = _extraire_json(texte)
    if not offres:
        return "Je n'ai pas réussi à lire cette offre. Copie-moi son texte directement."
    offre = offres[0]
    dossier = preparer_dossier(ia, offre)
    _enregistrer(offre, "dossier prêt", dossier)
    return f"Le dossier pour {offre['titre']} chez {offre['entreprise']} est prêt. Tu peux postuler."


# --------------------------------------------------------------------------- #
# Outils exposés à JARVIS
# --------------------------------------------------------------------------- #

def suivi_candidatures() -> str:
    stock = _charger()
    if not stock:
        return "Aucune offre suivie pour l'instant."
    par_statut: dict[str, list[str]] = {}
    for o in stock.values():
        par_statut.setdefault(o.get("statut", "trouvée"), []).append(
            f"{o['titre']} chez {o['entreprise']} ({o.get('maj', '')})")
    return "\n".join(f"{s} ({len(l)}) : " + " ; ".join(l[-12:]) for s, l in par_statut.items())


def changer_statut(entreprise: str, statut: str, poste: str = "") -> str:
    statut = statut.lower().strip()
    if statut not in STATUTS:
        return f"Statut inconnu. Choisis parmi : {', '.join(STATUTS)}."
    stock = _charger()
    touchees = [o for o in stock.values()
                if entreprise.lower() in o["entreprise"].lower()
                and poste.lower() in o["titre"].lower()]
    if not touchees:
        return f"Aucune offre suivie chez « {entreprise} »."
    for o in touchees:
        o["statut"] = statut
        o["maj"] = f"{datetime.now():%d/%m/%Y}"
    _sauver(stock)
    return f"{len(touchees)} offre(s) chez {entreprise} passée(s) en « {statut} »."


def outils(ia) -> list[Outil]:
    return [
        Outil(
            "lancer_recherche_emploi",
            "Lance en arrière-plan l'équipe emploi : l'agent chercheur trouve les meilleures "
            "offres sur tout le web selon le profil et les cibles, puis l'agent rédacteur "
            "prépare pour chacune un CV adapté, une lettre de motivation et une fiche. "
            "L'utilisateur postule ensuite lui-même.",
            lambda nombre=5, focus="": missions.lancer(
                "recherche emploi", lambda: mission_emploi(ia, max(1, min(int(nombre), 15)), focus)),
            {
                "nombre": {"type": "integer", "description": "Nombre de dossiers à préparer (défaut 5, max 15)."},
                "focus": {"type": "string", "description": "Consigne particulière : intitulé, ville, secteur, entreprise… (optionnel)."},
            },
        ),
        Outil(
            "preparer_candidature_offre",
            "Prépare en arrière-plan le dossier complet (CV adapté, lettre, fiche) pour une "
            "offre précise que l'utilisateur a trouvée lui-même (lien ou description).",
            lambda offre: missions.lancer(
                f"dossier {offre[:30]}", lambda: mission_offre_precise(ia, offre)),
            {"offre": {"type": "string", "description": "Lien de l'offre ou son texte."}},
            ["offre"],
        ),
        Outil(
            "suivi_candidatures",
            "Fait le point sur les offres suivies et leur statut.",
            suivi_candidatures,
        ),
        Outil(
            "changer_statut_candidature",
            "Met à jour le statut d'une candidature quand l'utilisateur dit qu'il a postulé, "
            "obtenu un entretien, reçu un refus ou qu'une offre ne l'intéresse pas.",
            changer_statut,
            {
                "entreprise": {"type": "string", "description": "Nom (ou partie du nom) de l'entreprise."},
                "statut": {"type": "string", "enum": list(STATUTS)},
                "poste": {"type": "string", "description": "Partie de l'intitulé, si plusieurs offres dans la même entreprise."},
            },
            ["entreprise", "statut"],
        ),
    ]
