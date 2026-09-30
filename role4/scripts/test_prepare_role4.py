import unittest
from decimal import Decimal
from prepare_role4 import number,period,resolve_hours,text

class PreparationTests(unittest.TestCase):
    def test_missing_is_not_zero(self):
        self.assertEqual(number('0'),(Decimal(0),None))
        self.assertEqual(number('Division by zero!'),(None,'source_division_by_zero'))
        self.assertEqual(number('-2'),(None,'negative'))
        self.assertEqual(number('1,23'),(None,'invalid_numeric'))
    def test_period_and_xlsx_identifiers(self):
        self.assertEqual(text(2025.0),'2025')
        self.assertEqual(period(2025.0),(2025,'2025-01-01','2025-12-31'))
        self.assertEqual(period('2025 (1/1 - 13/9)'),(2025,'2025-01-01','2025-09-13'))
        self.assertEqual(period('2025 (31/2 - 13/9)'),(2025,None,None))
    def test_hours_recovery_and_conflict(self):
        n,p=resolve_hours({'annual_time_at_sea_h_reported':'','raw__Total time spent at sea [hours]':'123'})
        self.assertEqual(n,Decimal(123));self.assertTrue(p['recovered_from_raw'])
        n,p=resolve_hours({'annual_time_at_sea_h_reported':'125','raw__Total time spent at sea [hours]':'123'})
        self.assertIsNone(n);self.assertEqual(p['reason'],'conflicting_source_values')

if __name__=='__main__':unittest.main()
