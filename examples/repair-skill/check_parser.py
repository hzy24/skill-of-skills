"""Synthetic fixture: validate the supplied artifact, without modifying it."""
import importlib.util,sys,unittest
spec=importlib.util.spec_from_file_location('target',sys.argv.pop(1))
target=importlib.util.module_from_spec(spec);spec.loader.exec_module(target)
class ParserTest(unittest.TestCase):
    def test_empty(self):self.assertEqual(target.parse(''),[])
    def test_whitespace(self):self.assertEqual(target.parse('  '),[])
    def test_existing_integers(self):self.assertEqual(target.parse('1, -2, 3'),[1,-2,3])
if __name__=='__main__':unittest.main()
