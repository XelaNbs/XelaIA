"""
Génération des PDF : CV (mise en page à deux colonnes, comme le CV d'origine)
et lettre de motivation assortie.

Les agents produisent des données structurées (JSON) ; ce module s'occupe
uniquement de la mise en page, avec ReportLab.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Frame, FrameBreak, KeepTogether,
                                PageTemplate, Paragraph, Spacer)
from reportlab.platypus.flowables import HRFlowable

MARINE = HexColor("#1B2A4A")
BLEU = HexColor("#2C4A7C")
GRIS = HexColor("#555555")
FOND = HexColor("#DCE3EF")

LARGEUR, HAUTEUR = A4
COLONNE = 68 * mm

# --------------------------------------------------------------------------- #
# Polices : Arial du Mac si disponible (accents, €, tirets…), sinon Helvetica
# --------------------------------------------------------------------------- #

_POLICES = [
    ("/System/Library/Fonts/Supplemental/Arial.ttf",
     "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
     "/System/Library/Fonts/Supplemental/Arial Italic.ttf",
     "/System/Library/Fonts/Supplemental/Arial Bold Italic.ttf"),
    ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf"),
]


def _enregistrer_police() -> str:
    for chemins in _POLICES:
        if all(Path(c).exists() for c in chemins):
            noms = ["CV", "CV-Gras", "CV-Italique", "CV-GrasItalique"]
            for nom, chemin in zip(noms, chemins):
                pdfmetrics.registerFont(TTFont(nom, chemin))
            pdfmetrics.registerFontFamily("CV", normal="CV", bold="CV-Gras",
                                          italic="CV-Italique", boldItalic="CV-GrasItalique")
            return "CV"
    return "Helvetica"


POLICE = _enregistrer_police()
GRAS = "CV-Gras" if POLICE == "CV" else "Helvetica-Bold"
ITALIQUE = "CV-Italique" if POLICE == "CV" else "Helvetica-Oblique"
GRAS_ITALIQUE = "CV-GrasItalique" if POLICE == "CV" else "Helvetica-BoldOblique"


def _style(nom, **kw) -> ParagraphStyle:
    base = dict(fontName=POLICE, fontSize=9.2, leading=12, textColor=HexColor("#222222"))
    base.update(kw)
    return ParagraphStyle(nom, **base)


S = {
    "contact_gras": _style("cg", fontName=GRAS, fontSize=9.2, leading=12.5),
    "contact": _style("c", textColor=GRIS, fontSize=8.8, leading=12.5),
    "titre_g": _style("tg", fontName=GRAS, fontSize=10.5, textColor=MARINE,
                      spaceBefore=12, spaceAfter=5),
    "item_g": _style("ig", fontName=GRAS, fontSize=9, leading=11),
    "sous_g": _style("sg", textColor=GRIS, fontSize=8.6, leading=11, spaceAfter=4),
    "liste_g": _style("lg", textColor=GRIS, fontSize=8.6, leading=11.5),
    "nom": _style("nom", fontName=GRAS, fontSize=21, leading=25, textColor=HexColor("#111111")),
    "poste_vise": _style("pv", fontName=GRAS_ITALIQUE, fontSize=12.5, leading=16, textColor=BLEU,
                         spaceAfter=6),
    "accroche": _style("acc", fontSize=9.2, leading=12.6),
    "section": _style("sec", fontName=GRAS, fontSize=12.5, leading=15, textColor=MARINE,
                      spaceBefore=11, spaceAfter=2),
    "poste": _style("po", fontName=GRAS, fontSize=9.8, leading=12.5, spaceBefore=6),
    "ligne_dates": _style("ld", fontSize=8.6, leading=11, textColor=GRIS, spaceAfter=2),
    "puce": _style("pu", fontSize=8.9, leading=11.6, leftIndent=9, bulletIndent=1,
                   spaceAfter=1.5),
    "lettre": _style("le", fontSize=10.5, leading=15, alignment=TA_JUSTIFY, spaceAfter=9),
    "lettre_g": _style("lg2", fontSize=10.5, leading=15, alignment=TA_LEFT),
}

LIBELLES = {
    "fr": dict(langues="LANGUES", competences="COMPÉTENCES", informatique="INFORMATIQUE",
               interets="CENTRES D’INTÉRÊT", experience="Expérience professionnelle",
               formation="Formation", objet="Objet", le="le"),
    "en": dict(langues="LANGUAGES", competences="SKILLS", informatique="TOOLS",
               interets="INTERESTS", experience="Professional experience",
               formation="Education", objet="Subject", le=""),
    "es": dict(langues="IDIOMAS", competences="COMPETENCIAS", informatique="HERRAMIENTAS",
               interets="INTERESES", experience="Experiencia profesional",
               formation="Formación", objet="Asunto", le=""),
    "pt": dict(langues="IDIOMAS", competences="COMPETÊNCIAS", informatique="FERRAMENTAS",
               interets="INTERESSES", experience="Experiência profissional",
               formation="Formação", objet="Assunto", le=""),
}


def _txt(texte: str) -> str:
    """Échappe le texte et convertit **gras** en balises ReportLab."""
    texte = escape(str(texte or ""))
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", texte)


# --------------------------------------------------------------------------- #
# CV
# --------------------------------------------------------------------------- #

def _fond_colonne(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFillColor(FOND)
    canvas.rect(0, 0, COLONNE, HAUTEUR, stroke=0, fill=1)
    canvas.restoreState()


def _ligne_section() -> HRFlowable:
    return HRFlowable(width="100%", thickness=1.1, color=MARINE, spaceBefore=1, spaceAfter=4)


def generer_cv_pdf(cv: dict, chemin: Path) -> int:
    """
    cv = {
      "langue": "fr", "nom": ..., "titre": ..., "accroche": ...,
      "contact": {"email", "telephone", "localisation", "linkedin", "permis"},
      "langues": [{"langue", "niveau"}], "competences": [...],
      "informatique": [{"categorie", "outils"}], "centres_interet": [...],
      "experiences": [{"poste", "dates", "entreprise", "lieu", "puces": [...]}],
      "formation": [{"diplome", "dates", "ecole", "lieu"}]
    }
    """
    lib = LIBELLES.get(cv.get("langue", "fr"), LIBELLES["fr"])
    chemin.parent.mkdir(parents=True, exist_ok=True)

    marge = 9 * mm
    gauche = Frame(marge * 0.9, marge, COLONNE - 1.8 * marge, HAUTEUR - 2 * marge,
                   leftPadding=0, rightPadding=0, topPadding=4 * mm, bottomPadding=0, id="g")
    droite = Frame(COLONNE + 7 * mm, marge, LARGEUR - COLONNE - 7 * mm - marge,
                   HAUTEUR - 2 * marge, leftPadding=0, rightPadding=0,
                   topPadding=1 * mm, bottomPadding=0, id="d")
    suite = Frame(COLONNE + 7 * mm, marge, LARGEUR - COLONNE - 7 * mm - marge,
                  HAUTEUR - 2 * marge, id="suite")
    doc = BaseDocTemplate(str(chemin), pagesize=A4, title=f"CV {cv.get('nom', '')}",
                          author=cv.get("nom", ""))
    doc.addPageTemplates([
        PageTemplate("premiere", [gauche, droite], onPage=_fond_colonne,
                     autoNextPageTemplate="suite"),
        PageTemplate("suite", [suite]),
    ])

    h = []
    # --- Colonne de gauche ---
    c = cv.get("contact", {})
    for cle, style in (("email", "contact_gras"), ("telephone", "contact_gras"),
                       ("localisation", "contact"), ("linkedin", "contact"),
                       ("permis", "contact")):
        if c.get(cle):
            h.append(Paragraph(_txt(c[cle]), S[style]))

    if cv.get("langues"):
        h.append(Paragraph(lib["langues"], S["titre_g"]))
        for l in cv["langues"]:
            h.append(Paragraph(_txt(l.get("langue")), S["item_g"]))
            h.append(Paragraph(_txt(l.get("niveau")), S["sous_g"]))
    if cv.get("competences"):
        h.append(Paragraph(lib["competences"], S["titre_g"]))
        for comp in cv["competences"]:
            h.append(Paragraph(_txt(comp), S["liste_g"]))
    if cv.get("informatique"):
        h.append(Paragraph(lib["informatique"], S["titre_g"]))
        for i in cv["informatique"]:
            h.append(Paragraph(_txt(i.get("categorie")), S["item_g"]))
            h.append(Paragraph(_txt(i.get("outils")), S["sous_g"]))
    if cv.get("centres_interet"):
        h.append(Paragraph(lib["interets"], S["titre_g"]))
        for ci in cv["centres_interet"]:
            h.append(Paragraph(_txt(ci), S["liste_g"]))
    h.append(FrameBreak())

    # --- Colonne principale ---
    h.append(Paragraph(_txt(cv.get("nom")), S["nom"]))
    h.append(Paragraph(_txt(cv.get("titre")), S["poste_vise"]))
    if cv.get("accroche"):
        h.append(Paragraph(_txt(cv["accroche"]), S["accroche"]))

    h.append(Paragraph(lib["experience"], S["section"]))
    h.append(_ligne_section())
    for e in cv.get("experiences", []):
        bloc = [
            Paragraph(_txt(e.get("poste")), S["poste"]),
            Paragraph(f"<i>{_txt(e.get('dates'))}</i>&nbsp;&nbsp;"
                      f"<font color='#2C4A7C'><b>{_txt(e.get('entreprise'))}</b></font>"
                      + (f"&nbsp;&nbsp;<i>({_txt(e['lieu'])})</i>" if e.get("lieu") else ""),
                      S["ligne_dates"]),
        ]
        puces = [Paragraph(_txt(p), S["puce"], bulletText="•") for p in e.get("puces", [])]
        h.append(KeepTogether(bloc + puces[:1]))
        h.extend(puces[1:])

    if cv.get("formation"):
        h.append(Paragraph(lib["formation"], S["section"]))
        h.append(_ligne_section())
        for f in cv["formation"]:
            h.append(KeepTogether([
                Paragraph(_txt(f.get("diplome")), S["poste"]),
                Paragraph(f"<i>{_txt(f.get('dates'))}</i>&nbsp;&nbsp;"
                          f"<font color='#2C4A7C'><b>{_txt(f.get('ecole'))}</b></font>"
                          + (f"&nbsp;&nbsp;<i>({_txt(f['lieu'])})</i>" if f.get("lieu") else ""),
                          S["ligne_dates"]),
            ]))

    doc.build(h)
    return doc.page  # nombre de pages (le CV doit tenir sur une seule)


# --------------------------------------------------------------------------- #
# Lettre de motivation
# --------------------------------------------------------------------------- #

def generer_lettre_pdf(lettre: dict, cv: dict, chemin: Path) -> Path:
    """
    lettre = {"langue", "ville_date", "destinataire": [lignes], "objet",
              "salutation", "paragraphes": [...], "formule_finale"}
    """
    lib = LIBELLES.get(lettre.get("langue", "fr"), LIBELLES["fr"])
    chemin.parent.mkdir(parents=True, exist_ok=True)
    marge = 20 * mm

    def entete(canvas, doc):
        canvas.saveState()
        canvas.setFillColor(FOND)
        canvas.rect(0, HAUTEUR - 30 * mm, LARGEUR, 30 * mm, stroke=0, fill=1)
        canvas.setFillColor(HexColor("#111111"))
        canvas.setFont(GRAS, 18)
        canvas.drawString(marge, HAUTEUR - 14 * mm, cv.get("nom", ""))
        canvas.setFillColor(BLEU)
        canvas.setFont(ITALIQUE, 11)
        canvas.drawString(marge, HAUTEUR - 20.5 * mm, cv.get("titre", ""))
        c = cv.get("contact", {})
        infos = "  •  ".join(x for x in (c.get("email"), c.get("telephone"),
                                          c.get("localisation")) if x)
        canvas.setFillColor(GRIS)
        canvas.setFont(POLICE, 8.8)
        canvas.drawString(marge, HAUTEUR - 26 * mm, infos)
        canvas.restoreState()

    doc = BaseDocTemplate(str(chemin), pagesize=A4, title=f"Lettre {cv.get('nom', '')}",
                          author=cv.get("nom", ""))
    cadre = Frame(marge, marge, LARGEUR - 2 * marge, HAUTEUR - 30 * mm - marge - 4 * mm,
                  leftPadding=0, rightPadding=0, topPadding=6 * mm, id="l")
    doc.addPageTemplates([PageTemplate("lettre", [cadre], onPage=entete)])

    h = []
    for ligne in lettre.get("destinataire", []):
        h.append(Paragraph(_txt(ligne), _style("dest", fontSize=10.5, leading=14,
                                                alignment=2)))
    h.append(Spacer(1, 6 * mm))
    h.append(Paragraph(_txt(lettre.get("ville_date") or f"Paris, {date.today():%d/%m/%Y}"),
                       _style("vd", fontSize=10.5, alignment=2, textColor=GRIS)))
    h.append(Spacer(1, 8 * mm))
    h.append(Paragraph(f"<b>{lib['objet']} :</b> {_txt(lettre.get('objet'))}", S["lettre_g"]))
    h.append(Spacer(1, 7 * mm))
    if lettre.get("salutation"):
        h.append(Paragraph(_txt(lettre["salutation"]), S["lettre"]))
    for p in lettre.get("paragraphes", []):
        h.append(Paragraph(_txt(p), S["lettre"]))
    if lettre.get("formule_finale"):
        h.append(Paragraph(_txt(lettre["formule_finale"]), S["lettre"]))
    h.append(Spacer(1, 4 * mm))
    h.append(Paragraph(f"<b>{_txt(cv.get('nom'))}</b>", S["lettre_g"]))
    doc.build(h)
    return chemin
