"""
Agents emploi : chercheur d'offres, rédacteur de CV et de lettres.

1. L'agent chercheur parcourt le web (Welcome to the Jungle, LinkedIn, Indeed,
   APEC, HelloWork, pages carrières…) et sélectionne les offres qui collent
   au profil (profil.md) et aux cibles (cibles.md).
2. Pour chaque offre retenue, l'agent rédacteur prépare un dossier complet, à
   partir de ton CV d'origine (mon_cv.pdf) : CV adapté en PDF (même mise en
   page), lettre de motivation en PDF, fiche de l'offre (lien, contact,
   arguments, message court pour le recruteur).
3. JARVIS te prévient : tu n'as plus qu'à postuler.

Les dossiers sont dans candidatures/, le suivi dans donnees/offres.json.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime

from . import DONNEES, RACINE, Outil, missions
from .memoire import lire_cibles, lire_memoire, lire_profil
from . import stockage

FICHIER_OFFRES = DONNEES / "offres.json"
DOSSIER_CANDIDATURES = RACINE / "candidatures"

STATUTS = ("trouvée", "dossier prêt", "postulée", "entretien", "refusée", "écartée")


# --------------------------------------------------------------------------- #
# Suivi des offres
# --------------------------------------------------------------------------- #

def _charger() -> dict[str, dict]:
    return stockage.charger_offres()


def _sauver(offres: dict[str, dict]) -> None:
    stockage.sauver_offres(offres)


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


def _verifier_profil(ia) -> str | None:
    cv_maitre(ia)
    if not lire_profil():
        return ("Je n'ai pas ton CV. Dépose-le en PDF dans le dossier de JARVIS sous le nom "
                "mon_cv.pdf, et je m'occupe du reste.")
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
# CV d'origine : mon_cv.pdf (ou le premier PDF du dossier mon_cv/)
# --------------------------------------------------------------------------- #

def _chaine(description: str) -> dict:
    return {"type": "string", "description": description}


def _objet(proprietes: dict) -> dict:
    return {"type": "object", "properties": proprietes,
            "required": list(proprietes), "additionalProperties": False}


def _liste(element: dict) -> dict:
    return {"type": "array", "items": element}


SCHEMA_CV = _objet({
    "langue": {"type": "string", "enum": ["fr", "en", "es", "pt"]},
    "nom": _chaine("Prénom NOM"),
    "titre": _chaine("Intitulé affiché sous le nom"),
    "accroche": _chaine("3 lignes ; **gras** autorisé sur les chiffres clés"),
    "contact": _objet({k: _chaine(k) for k in
                       ("email", "telephone", "localisation", "linkedin", "permis")}),
    "langues": _liste(_objet({"langue": _chaine("langue"), "niveau": _chaine("niveau")})),
    "competences": _liste(_chaine("compétence")),
    "informatique": _liste(_objet({"categorie": _chaine("catégorie"),
                                   "outils": _chaine("outils, séparés par des virgules")})),
    "centres_interet": _liste(_chaine("centre d'intérêt")),
    "experiences": _liste(_objet({
        "poste": _chaine("intitulé du poste"), "dates": _chaine("dates"),
        "entreprise": _chaine("entreprise"), "lieu": _chaine("ville, précision"),
        "puces": _liste(_chaine("réalisation ; **gras** sur les chiffres clés")),
    })),
    "formation": _liste(_objet({"diplome": _chaine("diplôme"), "dates": _chaine("dates"),
                                "ecole": _chaine("école"), "lieu": _chaine("ville")})),
})

SCHEMA_LETTRE = _objet({
    "langue": {"type": "string", "enum": ["fr", "en", "es", "pt"]},
    "destinataire": _liste(_chaine("ligne d'adresse : entreprise, service ou personne, ville")),
    "ville_date": _chaine("ex : Paris, le 13 novembre 2026"),
    "objet": _chaine("objet de la lettre"),
    "salutation": _chaine("ex : Madame, Monsieur,"),
    "paragraphes": _liste(_chaine("paragraphe")),
    "formule_finale": _chaine("formule de politesse"),
})

FICHIER_CV_MAITRE = DONNEES / "cv_maitre.json"


def _source_cv():
    if (RACINE / "mon_cv.pdf").exists():
        return RACINE / "mon_cv.pdf"
    dossier = RACINE / "mon_cv"
    pdfs = sorted(dossier.glob("*.pdf"), key=lambda p: p.stat().st_mtime) if dossier.exists() else []
    return pdfs[-1] if pdfs else None


def cv_maitre(ia) -> dict | None:
    """Transcrit ton CV PDF en données (une fois ; refait si le PDF change)."""
    source = _source_cv()
    cache = stockage.charger_cv(source)
    if cache is not None:
        return cache
    if source is None:
        return None
    print(f"📄 Lecture de ton CV ({source.name})…")
    cv = ia.completer_json(
        "Retranscris ce CV fidèlement et intégralement dans le format demandé : chaque "
        "expérience avec toutes ses puces, chaque chiffre, chaque formation, compétence, "
        "outil, langue et centre d'intérêt, sans rien résumer ni inventer. Mets en **gras** "
        "les mêmes éléments que dans l'original.",
        SCHEMA_CV, "Tu es un assistant de saisie extrêmement précis.", pdf=source)
    stockage.sauver_cv(cv, source)
    print("✅ CV d'origine enregistré.")
    return cv


# --------------------------------------------------------------------------- #
# Agent rédacteur : CV adapté + lettre en PDF, fiche de candidature
# --------------------------------------------------------------------------- #

SYSTEME_REDACTEUR = """Tu es un expert du recrutement commercial (sales, account \
management, business development) en France et à l'international, qui adapte des CV et \
écrit des lettres qui décrochent des entretiens. Style : concret, chiffré, sobre, sans \
formules creuses. Tu n'inventes JAMAIS une expérience, un diplôme, un chiffre, un outil ou \
une compétence absents du CV d'origine : tu reformules, sélectionnes, ordonnes et traduis \
ce qui existe."""


def _consigne_offre(offre: dict) -> str:
    return f"""OFFRE : {offre['titre']} chez {offre['entreprise']} ({offre.get('lieu')}, \
{offre.get('contrat')})
Lien : {offre.get('lien')}
{offre.get('description', '')}

PROFIL DU CANDIDAT :
{lire_profil()}

INFORMATIONS COMPLÉMENTAIRES :
{lire_memoire() or "aucune"}"""


def _nom_fichier(texte: str) -> str:
    return re.sub(r"[^\w-]+", "_", texte).strip("_")[:60]


CONSIGNE_CV = """Adapte le CV d'origine du candidat à cette offre.
- Rédige dans la langue de l'offre (langue = fr, en, es ou pt) ; traduis si besoin.
- Même structure et mêmes informations de contact que le CV d'origine.
- titre : intitulé proche du poste visé, crédible pour ce candidat.
- accroche : 3 lignes ciblées sur l'offre, avec ses résultats les plus parlants.
- experiences : toutes les expériences pertinentes, dans l'ordre chronologique inverse, avec \
les dates et entreprises exactes ; reformule et réordonne les puces pour faire ressortir ce \
que l'offre demande (mots-clés de l'offre) ; garde les chiffres exacts en **gras**.
- competences : 6 à 8, choisies et formulées selon l'offre, toutes justifiées par le parcours.
- Le CV doit tenir sur UNE page : 3 à 4 puces pour les postes récents, 1 à 2 pour les anciens."""


def preparer_dossier(ia, offre: dict) -> str:
    from .documents import generer_cv_pdf, generer_lettre_pdf

    contexte = _consigne_offre(offre)
    nom_offre = _nom_fichier(f"{offre['entreprise']}_{offre['titre']}")
    dossier = DOSSIER_CANDIDATURES / f"{date.today():%Y-%m-%d}_{nom_offre}"

    cv = ia.completer_json(f"{contexte}\n\n{CONSIGNE_CV}", SCHEMA_CV, SYSTEME_REDACTEUR)
    nom = _nom_fichier(cv.get("nom", "Candidat").title().replace(" ", "-"))
    entreprise = _nom_fichier(offre["entreprise"])
    chemin_cv = dossier / f"CV_{nom}_{entreprise}.pdf"
    if generer_cv_pdf(cv, chemin_cv) > 1:  # trop long : on demande une version plus courte
        cv = ia.completer_json(
            f"{contexte}\n\n{CONSIGNE_CV}\n\nVoici ta première version, qui dépasse une page. "
            f"Raccourcis-la (moins de puces, puces plus courtes, accroche plus brève) :\n"
            f"{json.dumps(cv, ensure_ascii=False)}", SCHEMA_CV, SYSTEME_REDACTEUR)
        generer_cv_pdf(cv, chemin_cv)

    lettre = ia.completer_json(f"""{contexte}

Rédige la lettre de motivation, dans la même langue que le CV adapté ({cv.get('langue', 'fr')}).
- ville_date : ville du candidat et date du jour ({date.today():%d/%m/%Y}), écrite en toutes lettres.
- destinataire : l'entreprise (et le contact s'il est connu : {offre.get('contact') or 'inconnu'}).
- 4 paragraphes, 250 à 330 mots au total : une accroche liée à l'entreprise ou au poste ; \
deux paragraphes reliant 2 ou 3 réalisations chiffrées du CV aux besoins de l'offre ; une \
conclusion qui propose un échange. Si le profil a un manque évident par rapport à l'offre, \
assume-le en une phrase et montre comment il le compense (comme le candidat le fait \
naturellement dans ses candidatures).""", SCHEMA_LETTRE, SYSTEME_REDACTEUR)
    generer_lettre_pdf(lettre, cv, dossier / f"LM_{nom}_{entreprise}.pdf")

    fiche = ia.completer(f"""{contexte}

Prépare la fiche de candidature, en Markdown, avec ces sections :
## Pourquoi postuler
## Points à défendre en entretien (3 à 5, avec les exemples du profil à raconter)
## Points faibles possibles et réponses
## Questions à poser au recruteur
## Message LinkedIn au recruteur (300 caractères maximum)
## Mail de candidature (objet + 100 à 150 mots, prêt à copier si la candidature se fait par mail)""",
                         SYSTEME_REDACTEUR)
    contact = offre.get("contact") or "non trouvé"
    (dossier / "Fiche_offre.md").write_text(
        f"# {offre['titre']} — {offre['entreprise']}\n\n"
        f"- **Lien pour postuler** : {offre.get('lien')}\n"
        f"- **Lieu / contrat / salaire** : {offre.get('lieu')} / {offre.get('contrat')} / "
        f"{offre.get('salaire') or 'non précisé'}\n"
        f"- **Contact** : {contact if isinstance(contact, str) else json.dumps(contact, ensure_ascii=False)}\n"
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
    if (erreur := _verifier_profil(ia)):
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
    if (erreur := _verifier_profil(ia)):
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
