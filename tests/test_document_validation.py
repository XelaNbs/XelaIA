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

if __name__=='__main__':unittest.main()
