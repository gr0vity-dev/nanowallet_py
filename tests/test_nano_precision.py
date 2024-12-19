import unittest
from decimal import Decimal
from nanowallet.utils import raw_to_nano, nano_to_raw
from nanowallet.errors import InvalidAmountError


class TestNanoPrecision(unittest.TestCase):
    def test_very_small_amounts(self):
        # Test smallest possible amount (1 raw)
        self.assertEqual(raw_to_nano(1), Decimal(
            '0.000000000000000000000000000001'))

        # Test slightly larger small amounts
        self.assertEqual(raw_to_nano(10), Decimal(
            '0.00000000000000000000000000001'))
        self.assertEqual(raw_to_nano(100), Decimal(
            '0.0000000000000000000000000001'))

        # Test amounts near precision boundary
        self.assertEqual(raw_to_nano(999999999), Decimal(
            '0.000000000000000000000999999999'))

    def test_tuncated_precision(self):
        # Test precise decimal conversion
        nano = raw_to_nano('1234567890123456789012345678900', decimal_places=6)
        self.assertEqual(nano, Decimal('1.234567'))

    def test_precise_amounts(self):
        # Test precise decimal conversion
        raw = nano_to_raw('0.123456789123456789123456789123')
        self.assertEqual(raw_to_nano(raw), Decimal(
            '0.123456789123456789123456789123'))

        # Test maximum precision (30 decimal places)
        max_precision = '1.123456789123456789123456789123'
        raw = nano_to_raw(max_precision)
        self.assertEqual(raw_to_nano(raw), Decimal(max_precision))

    def test_rounding_behavior(self):
        # Test that amounts beyond 30 decimal places are truncated at 30 places
        self.assertEqual(raw_to_nano(nano_to_raw('0.1234567891234567891234567891234')),
                         Decimal('0.123456789123456789123456789123'))

        # Test that trailing zeros are handled correctly
        self.assertEqual(raw_to_nano(nano_to_raw('1.100000000000000000000000000000')),
                         Decimal('1.100000000000000000000000000000'))

    def test_large_amounts(self):
        # Test maximum possible amount (2^128 - 1 raw)
        max_raw = 2**128 - 1
        self.assertEqual(nano_to_raw(raw_to_nano(max_raw)), max_raw)

        # Test large round numbers
        self.assertEqual(raw_to_nano(10**30), Decimal('1'))
        self.assertEqual(raw_to_nano(10**33), Decimal('1000'))

    def test_edge_cases(self):
        # Test zero
        self.assertEqual(raw_to_nano(0), Decimal('0'))
        self.assertEqual(nano_to_raw('0'), 0)

        # Test one raw
        self.assertEqual(nano_to_raw('0.000000000000000000000000000001'), 1)

        # Test one nano
        self.assertEqual(nano_to_raw('1'), 10**30)

        # Test invalid inputs
        with self.assertRaises(InvalidAmountError):
            nano_to_raw('-1')
        with self.assertRaises(Exception):
            nano_to_raw('invalid')

    def test_conversion_roundtrip(self):
        # Test that converting from nano to raw and back preserves value
        test_values = [
            '0.000000000000000000000000000001',  # 1 raw
            '0.000000000000000000000000000123',  # Small amount
            '0.123456789123456789123456789123',  # Complex decimal
            '1.000000000000000000000000000000',  # 1 Nano
            '1234567.89',                        # Larger amount
        ]

        for value in test_values:
            raw = nano_to_raw(value)
            nano = raw_to_nano(raw)
            assert nano == Decimal(value)

    def test_precision_loss_prevention(self):
        # Test that no precision is lost in calculations
        original = '1234567.123456789123456789123456789'
        raw = nano_to_raw(original)
        result = raw_to_nano(raw)
        # Compare up to original precision
        self.assertEqual(str(result)[:35], original)
        self.assertEqual(str(result)[35:], "")
