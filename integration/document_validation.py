"""Checks source facts at the model boundary, leaving agent workflows intact."""
import json
from pathlib import Path
import re
import unicodedata
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parents[1]

def numbers(text):
    result=set()
    for m in re.finditer(r'\d+(?:[.,]\d+)?',str(text)):
        raw=m.group().replace(',','.')
        if re.fullmatch(r'\d+[.]\d{3}',raw):raw=raw.replace('.','')
        value=float(raw);result.add(str(int(value)) if value.is_integer() else str(value))
        tail=str(text)[m.end():m.end()+4].lstrip()
        if tail.lower().startswith('k'):
            scaled=value*1000;result.add(str(int(scaled)) if scaled.is_integer() else str(scaled))
    return result

def source_text(source=None):
    return '\n'.join(p.extract_text() or '' for p in PdfReader(source or ROOT/'mon_cv.pdf').pages)

def validate_cv_numbers(value,source=None):
    text=json.dumps(value,ensure_ascii=False) if not isinstance(value,str) else value
    extra=numbers(text)-numbers(source_text(source))
    if extra:raise ValueError('Chiffres absents du CV de référence : '+', '.join(sorted(extra)))
    return {'numbers_verified':True,'extra_numbers':[]}

def validate_generated_pdf(path,expected_language=None):
    path=Path(path);reader=PdfReader(path);text='\n'.join(p.extract_text() or '' for p in reader.pages)
    cv=path.name.startswith('CV_')
    if cv:
        validate_cv_numbers(text)
        if len(reader.pages)!=1:raise ValueError('CV PDF non conforme : il doit tenir sur une page')
    if expected_language=='en':
        if cv and ('Professional experience' not in text or 'Education' not in text):raise ValueError('CV attendu en anglais')
        if not cv and ('Subject' not in text or any(x in text for x in ('Madame, Monsieur','Veuillez agréer'))):raise ValueError('Lettre attendue en anglais')
    return {'file':path.name,'pages':len(reader.pages),'cv_numbers_verified':cv,'language_checked':expected_language,'sha256':__import__('hashlib').sha256(path.read_bytes()).hexdigest()}
