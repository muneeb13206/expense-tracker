"""Tests for helper functions.  Run: python -m unittest tests.test_utils -v"""
import unittest

from utils import format_inr


class TestFormatInr(unittest.TestCase):
    def test_formats(self):
        cases = {
            0: "₹0.00",
            5: "₹5.00",
            999.5: "₹999.50",
            1000: "₹1,000.00",
            1234.5: "₹1,234.50",
            125000: "₹1,25,000.00",
            12345678.9: "₹1,23,45,678.90",
            -2500: "-₹2,500.00",
        }
        for value, expected in cases.items():
            with self.subTest(value=value):
                self.assertEqual(format_inr(value), expected)

    def test_bad_input_does_not_crash(self):
        self.assertEqual(format_inr(None), "₹0.00")
        self.assertEqual(format_inr("abc"), "₹0.00")


if __name__ == "__main__":
    unittest.main()