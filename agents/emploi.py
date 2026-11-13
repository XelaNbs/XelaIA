"""
Agent emploi : cherche des offres et prépare des candidatures sur mesure.

Source des offres : l'API officielle et gratuite de France Travail
(inscription sur https://francetravail.io, API « Offres d'emploi v2 »).
Les offres sont stockées dans donnees/offres.json, les candidatures
rédigées dans le dossier candidatures/.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from . import DONNEES, RACINE, Outil
from .memoire import lire_memoire, lire_profil

URL_JETON = ("https://entreprise.francetravail.fr/connexion/oauth2/access_token"
             "?realm=%2Fpartenaire")
URL_RECHERCHE = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"
FICHIER_OFFRES = DONNEES / "offres.json"
DOSSIER_CANDIDATURES = RACINE / "candidatures"

_jeton = {"valeur": None, "expire": 0.0}


# --------------------------------------------------------------------------- #
# Accès à l'API France Travail
# --------------------------------------------------------------------------- #

def _obtenir_jeton() -> str:
    if _jeton["valeur"] and time.time() < _jeton["expire"] - 60:
        return _jeton["valeur"]
    client_id = os.getenv("FRANCE_TRAVAIL_CLIENT_ID")
    secret = os.getenv("FRANCE_TRAVAIL_CLIENT_SECRET")
    if not client_id or not secret:
        raise RuntimeError(
            "identifiants France Travail absents. Il faut créer une application gratuite "
            "sur francetravail.io et renseigner FRANCE_TRAVAIL_CLIENT_ID et "
            "FRANCE_TRAVAIL_CLIENT_SECRET dans le fichier .env"
        )
    corps = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": secret,
        "scope": "api_offresdemploiv2 o2dsoffre",
    }).encode()
    req = urllib.request.Request(
        URL_JETON, data=corps,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        donnees = json.load(r)
    _jeton["valeur"] = donnees["access_token"]
    _jeton["expire"] = time.time() + int(donnees.get("expires_in", 1499))
    return _jeton["valeur"]


def _rechercher_api(params: dict) -> list[dict]:
    url = URL_RECHERCHE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {_obtenir_jeton()}",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            brut = r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"France Travail a répondu {e.code} : {e.read()[:200]!r}")
    if not brut:  # 204 : aucune offre
        return []
    return json.loads(brut).get("resultats", [])


# --------------------------------------------------------------------------- #
# Stockage local des offres
# --------------------------------------------------------------------------- #

def _charger_offres() -> dict[str, dict]:
    if FICHIER_OFFRES.exists():
        return json.loads(FICHIER_OFFRES.read_text(encoding="utf-8"))
    return {}


def _sauver_offres(offres: dict[str, dict]) -> None:
    FICHIER_OFFRES.write_text(json.dumps(offres, ensure_ascii=False, indent=1), encoding="utf-8")


def _resumer(o: dict) -> dict:
    return {
        "id": o.get("id"),
        "titre": o.get("intitule"),
        "entreprise": (o.get("entreprise") or {}).get("nom", "non précisée"),
        "lieu": (o.get("lieuTravail") or {}).get("libelle"),
        "contrat": o.get("typeContratLibelle") or o.get("typeContrat"),
        "salaire": (o.get("salaire") or {}).get("libelle"),
        "date": (o.get("dateCreation") or "")[:10],
        "lien": (o.get("origineOffre") or {}).get("urlOrigine")
                or f"https://candidat.francetravail.fr/offres/recherche/detail/{o.get('id')}",
        "contact": o.get("contact") or {},
        "description": (o.get("description") or "")[:1500],
    }


# --------------------------------------------------------------------------- #
# Outils exposés à JARVIS
# --------------------------------------------------------------------------- #

def chercher_offres(mots_cles: str, departement: str = "", contrat: str = "",
                    nombre: int = 10) -> str:
    params = {"motsCles": mots_cles, "range": f"0-{max(1, min(int(nombre), 50)) - 1}",
              "sort": "1"}  # 1 = les plus récentes d'abord
    if departement:
        params["departement"] = departement
    if contrat:
        params["typeContrat"] = contrat.upper()
    resultats = [_resumer(o) for o in _rechercher_api(params)]

    stock = _charger_offres()
    nouvelles = 0
    for r in resultats:
        if r["id"] not in stock:
            nouvelles += 1
            r["statut"] = "trouvée"
            stock[r["id"]] = r
    _sauver_offres(stock)

    if not resultats:
        return "Aucune offre trouvée pour cette recherche."
    lignes = [f"{len(resultats)} offres ({nouvelles} nouvelles). Juge leur pertinence "
              "par rapport au profil de l'utilisateur :"]
    for r in resultats:
        lignes.append(f"- [{r['id']}] {r['titre']} chez {r['entreprise']}, {r['lieu']}, "
                      f"{r['contrat']}, {r['salaire'] or 'salaire non précisé'}. "
                      f"Extrait : {r['description'][:300]}")
    return "\n".join(lignes)


def rediger_candidature(offre_id: str, angle: str = "", _completer=None) -> str:
    stock = _charger_offres()
    offre = stock.get(offre_id)
    if not offre:
        return f"Offre {offre_id} inconnue : lance d'abord chercher_offres."
    profil = lire_profil()
    if not profil:
        return ("Le fichier profil.md est vide : il faut y coller le CV de l'utilisateur "
                "pour rédiger une vraie candidature.")

    consigne = f"""Rédige une candidature pour cette offre, au nom du candidat.

OFFRE : {offre['titre']} chez {offre['entreprise']} ({offre['lieu']}, {offre['contrat']})
{offre['description']}

PROFIL DU CANDIDAT :
{profil}

INFOS COMPLÉMENTAIRES :
{lire_memoire()}

{('ANGLE À METTRE EN AVANT : ' + angle) if angle else ''}

Produis exactement trois parties, avec ces titres :
## Objet du mail
(une ligne)
## Mail de candidature
(court, 120 mots max, direct, personnalisé, se termine par la signature du candidat)
## Lettre de motivation
(250 à 350 mots, concrète, reliant 2 ou 3 expériences du profil aux besoins de l'offre)

N'invente aucune expérience ni diplôme absent du profil."""
    texte = _completer(consigne, "Tu es un expert du recrutement en France.")

    DOSSIER_CANDIDATURES.mkdir(exist_ok=True)
    nom = re.sub(r"[^\w-]+", "_", f"{offre['entreprise']}_{offre['titre']}")[:80]
    chemin = DOSSIER_CANDIDATURES / f"{offre_id}_{nom}.md"
    entete = (f"# {offre['titre']} — {offre['entreprise']}\n\n"
              f"Lien : {offre['lien']}\nContact : {json.dumps(offre['contact'], ensure_ascii=False)}\n\n")
    chemin.write_text(entete + texte, encoding="utf-8")

    offre["statut"] = "candidature rédigée"
    _sauver_offres(stock)
    return (f"Candidature rédigée et enregistrée dans {chemin.relative_to(RACINE)}. "
            f"Contact connu dans l'offre : {offre['contact'] or 'aucun'}.")


def suivi_candidatures() -> str:
    stock = _charger_offres()
    if not stock:
        return "Aucune offre suivie pour l'instant."
    par_statut: dict[str, list[str]] = {}
    for o in stock.values():
        par_statut.setdefault(o.get("statut", "trouvée"), []).append(
            f"{o['titre']} chez {o['entreprise']}")
    return "\n".join(f"{s} ({len(l)}) : " + " ; ".join(l[:10]) for s, l in par_statut.items())


def outils(completer) -> list[Outil]:
    return [
        Outil(
            "chercher_offres",
            "Agent emploi : cherche des offres d'emploi récentes en France (France Travail). "
            "Après l'appel, sélectionne les plus pertinentes pour le profil de l'utilisateur.",
            chercher_offres,
            {
                "mots_cles": {"type": "string", "description": "Métier ou compétences, ex : 'développeur python'."},
                "departement": {"type": "string", "description": "Numéro de département, ex : '75'. Vide = toute la France."},
                "contrat": {"type": "string", "description": "CDI, CDD, MIS (intérim) ou vide."},
                "nombre": {"type": "integer", "description": "Nombre d'offres (1 à 50, défaut 10)."},
            },
            ["mots_cles"],
        ),
        Outil(
            "rediger_candidature",
            "Agent candidature : rédige le mail et la lettre de motivation personnalisés pour "
            "une offre déjà trouvée, et les enregistre. À utiliser sans demander pour chaque "
            "offre jugée pertinente.",
            lambda offre_id, angle="": rediger_candidature(offre_id, angle, completer),
            {
                "offre_id": {"type": "string", "description": "Identifiant de l'offre (entre crochets)."},
                "angle": {"type": "string", "description": "Point fort à mettre en avant (optionnel)."},
            },
            ["offre_id"],
        ),
        Outil(
            "suivi_candidatures",
            "Fait le point sur toutes les offres suivies et leur statut.",
            suivi_candidatures,
        ),
    ]
