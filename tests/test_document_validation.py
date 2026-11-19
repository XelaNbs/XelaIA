import unittest
from unittest.mock import patch
from integration.document_validation import numbers,validate_cv_numbers

class DocumentTests(unittest.TestCase):
    def test_exact_numbers_only(self):
        with patch('integration.document_validation.source_text',return_value='120 clients, 95% de rétention, 2023–2025'):
            self.assertTrue(validate_cv_numbers({'experience':'120 clients ; 95%, 2023–2025'})['numbers_verified'])
            with self.assertRaises(ValueError):validate_cv_numbers({'experience':'150 clients ; 99%'})
    def test_equivalent_thousands(self):
        self.assertIn('350000',numbers('350 k€'));self.assertIn('350000',numbers('350,000 EUR'))

    def test_tailoring_does_not_change_approved_language_levels(self):
        from integration.document_validation import preserve_reference_languages
        reference={'langues':[{'langue':'Anglais','niveau':'Niveau C1'},{'langue':'Français','niveau':'Langue maternelle'}]}
        generated={'langue':'en','langues':[{'langue':'English','niveau':'B2'}]}
        result=preserve_reference_languages(generated,reference)
        self.assertEqual(result['langues'][0],{'langue':'English','niveau':'C1'})
        self.assertEqual(result['langues'][1]['niveau'],'Native')
        self.assertEqual(generated['langues'][0]['niveau'],'B2')
    def test_letter_date_matches_its_language(self):
        import datetime
        from integration.document_validation import normalize_letter_date
        result=normalize_letter_date({'langue':'en','ville_date':'Paris, le dix-huit novembre'},datetime.date(2026,11,19))
        self.assertEqual(result['ville_date'],'Paris, 19 November 2026')

if __name__=='__main__':unittest.main()
