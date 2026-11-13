"""
Mise en page des documents (CV, lettre) au format Word (.docx).

Les agents écrivent dans un balisage simple :
    # Titre principal       ## Section       ### Sous-section
    - puce                  **gras**         ligne vide = nouveau paragraphe
"""

from __future__ import annotations

import re
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt, RGBColor

BLEU = RGBColor(0x1F, 0x3A, 0x5F)


def _ajouter_texte(paragraphe, texte: str) -> None:
    """Ajoute du texte en gérant le **gras**."""
    for i, morceau in enumerate(re.split(r"\*\*(.+?)\*\*", texte)):
        if morceau:
            paragraphe.add_run(morceau).bold = i % 2 == 1


def _document() -> Document:
    doc = Document()
    for section in doc.sections:
        section.top_margin = section.bottom_margin = Cm(1.6)
        section.left_margin = section.right_margin = Cm(1.8)
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10.5)
    style.paragraph_format.space_after = Pt(3)
    return doc


def balisage_vers_docx(texte: str, chemin: Path, lettre: bool = False) -> Path:
    doc = _document()
    if lettre:
        doc.styles["Normal"].font.size = Pt(11)
        doc.styles["Normal"].paragraph_format.space_after = Pt(10)

    entete = False  # lignes juste sous le nom : centrées (titre, coordonnées)
    for ligne in texte.strip().splitlines():
        ligne = ligne.rstrip()
        if not ligne.strip():
            continue
        if ligne.startswith("### "):
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(6)
            run = p.add_run(ligne[4:].replace("**", ""))
            run.bold = True
        elif ligne.startswith("## "):
            entete = False
            p = doc.add_paragraph()
            p.paragraph_format.space_before = Pt(10)
            run = p.add_run(ligne[3:].replace("**", "").upper())
            run.bold = True
            run.font.size = Pt(11.5)
            run.font.color.rgb = BLEU
        elif ligne.startswith("# "):
            p = doc.add_paragraph()
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = p.add_run(ligne[2:].replace("**", ""))
            run.bold = True
            run.font.size = Pt(18)
            run.font.color.rgb = BLEU
            entete = not lettre
        elif re.match(r"^\s*[-•]\s+", ligne):
            p = doc.add_paragraph(style="List Bullet")
            p.paragraph_format.space_after = Pt(1)
            _ajouter_texte(p, re.sub(r"^\s*[-•]\s+", "", ligne))
        else:
            p = doc.add_paragraph()
            if lettre:
                p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            elif entete:
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            _ajouter_texte(p, ligne)

    chemin.parent.mkdir(parents=True, exist_ok=True)
    doc.save(chemin)
    return chemin
