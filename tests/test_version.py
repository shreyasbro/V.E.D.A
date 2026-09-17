import unittest
from veda.version import VERSION, BUILD, parse_semver, compare_versions, is_newer_version

class TestVersionSystem(unittest.TestCase):
    def test_authoritative_constants(self):
        self.assertEqual(VERSION, "1.0.0")
        self.assertEqual(BUILD, 1000)

    def test_parse_semver(self):
        self.assertEqual(parse_semver("1.0.0"), (1, 0, 0))
        self.assertEqual(parse_semver("v2.4.1"), (2, 4, 1))
        self.assertEqual(parse_semver("1.2"), (1, 2, 0))
        self.assertEqual(parse_semver("1.2.3-beta.1"), (1, 2, 3))

    def test_compare_versions(self):
        self.assertEqual(compare_versions("1.1.0", "1.0.0"), 1)
        self.assertEqual(compare_versions("1.0.0", "1.0.0"), 0)
        self.assertEqual(compare_versions("0.9.9", "1.0.0"), -1)
        self.assertEqual(compare_versions("1.0.1", "1.0.0"), 1)
        self.assertEqual(compare_versions("2.0.0", "1.9.9"), 1)

    def test_is_newer_version(self):
        self.assertTrue(is_newer_version("1.0.1", "1.0.0"))
        self.assertTrue(is_newer_version("1.1.0", "1.0.0"))
        self.assertFalse(is_newer_version("1.0.0", "1.0.0"))
        self.assertFalse(is_newer_version("0.9.0", "1.0.0"))

if __name__ == '__main__':
    unittest.main()
