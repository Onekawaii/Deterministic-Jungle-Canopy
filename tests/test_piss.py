import tempfile, unittest
from pathlib import Path
from piss.parser import parse_text
from piss.runner import run_program

class PissTests(unittest.TestCase):
    def test_parser(self):
        self.assertEqual(parse_text("WANT x\nBURY y\n")[0].op,"WANT")

    def test_unknown(self):
        with self.assertRaises(ValueError):
            parse_text("WANT x\nDANCE wildly\n")

    def test_receipt(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td); p=d/'a.piss'
            p.write_text('WANT pass\nDO echo hello\nRECKON last_do_passed\nBURY r\n')
            s,r,_=run_program(str(p),str(d/'receipts'))
            self.assertEqual(s,'PASS')
            self.assertTrue(r.exists())

    def test_fail(self):
        with tempfile.TemporaryDirectory() as td:
            d=Path(td); p=d/'a.piss'
            p.write_text('WANT fail\nDO python -c "import sys;sys.exit(2)"\nRECKON last_do_passed\nBURY r\n')
            s,r,_=run_program(str(p),str(d/'receipts'))
            self.assertEqual(s,'FAIL')
            self.assertTrue(r.exists())

if __name__=='__main__':
    unittest.main()
