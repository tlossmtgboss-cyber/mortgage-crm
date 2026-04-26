"""Tests for URLA voice input validators."""
import pytest
from decimal import Decimal
from datetime import date

from agents.urla.validators import (
    URLAInputError,
    parse_ssn,
    parse_date,
    parse_currency,
    parse_state,
    parse_phone,
    parse_yes_no,
)


class TestParseSSN:
    def test_standard_format(self):
        assert parse_ssn("219-09-9999") == "219-09-9999"

    def test_spaces(self):
        assert parse_ssn("219 09 9999") == "219-09-9999"

    def test_no_separators(self):
        assert parse_ssn("219099999") == "219-09-9999"

    def test_rejects_sequential(self):
        with pytest.raises(URLAInputError):
            parse_ssn("123-45-6789")

    def test_rejects_all_same_digit(self):
        with pytest.raises(URLAInputError):
            parse_ssn("111-11-1111")

    def test_rejects_area_000(self):
        with pytest.raises(URLAInputError):
            parse_ssn("000-12-3456")

    def test_rejects_area_666(self):
        with pytest.raises(URLAInputError):
            parse_ssn("666-12-3456")

    def test_rejects_area_900_plus(self):
        with pytest.raises(URLAInputError):
            parse_ssn("900-12-3456")

    def test_rejects_group_00(self):
        with pytest.raises(URLAInputError):
            parse_ssn("219-00-3456")

    def test_rejects_serial_0000(self):
        with pytest.raises(URLAInputError):
            parse_ssn("219-09-0000")

    def test_rejects_too_few_digits(self):
        with pytest.raises(URLAInputError):
            parse_ssn("219-09-999")

    def test_empty(self):
        with pytest.raises(URLAInputError):
            parse_ssn("")


class TestParseCurrency:
    def test_plain_number(self):
        assert parse_currency("425000") == Decimal("425000")

    def test_dollar_sign_commas(self):
        assert parse_currency("$425,000") == Decimal("425000")

    def test_with_cents(self):
        assert parse_currency("$1,234.56") == Decimal("1234.56")

    def test_spoken_thousand(self):
        assert parse_currency("four hundred twenty five thousand") == Decimal("425000")

    def test_spoken_hundred(self):
        assert parse_currency("three hundred") == Decimal("300")

    def test_negative_parsed_as_decimal(self):
        assert parse_currency("-100") == Decimal("-100")

    def test_rejects_empty(self):
        with pytest.raises(URLAInputError):
            parse_currency("")


class TestParseDate:
    def test_us_format_dots(self):
        assert parse_date("01.15.1990") == date(1990, 1, 15)

    def test_us_format_slashes(self):
        assert parse_date("01/15/1990") == date(1990, 1, 15)

    def test_us_format_dashes(self):
        assert parse_date("01-15-1990") == date(1990, 1, 15)

    def test_spoken_month(self):
        result = parse_date("January 15, 1990")
        assert result == date(1990, 1, 15)

    def test_spoken_month_no_comma(self):
        result = parse_date("January 15 1990")
        assert result == date(1990, 1, 15)

    def test_rejects_empty(self):
        with pytest.raises(URLAInputError):
            parse_date("")


class TestParseState:
    def test_abbreviation(self):
        assert parse_state("SC") == "SC"

    def test_full_name(self):
        assert parse_state("South Carolina") == "SC"

    def test_lowercase(self):
        assert parse_state("south carolina") == "SC"

    def test_rejects_invalid(self):
        with pytest.raises(URLAInputError):
            parse_state("Atlantis")


class TestParsePhone:
    def test_e164(self):
        assert parse_phone("+18435551212") == "+18435551212"

    def test_us_ten_digit(self):
        assert parse_phone("843-555-1212") == "+18435551212"

    def test_with_parens(self):
        assert parse_phone("(843) 555-1212") == "+18435551212"

    def test_rejects_too_short(self):
        with pytest.raises(URLAInputError):
            parse_phone("555-12")


class TestParseYesNo:
    def test_yes_variants(self):
        assert parse_yes_no("yes") is True
        assert parse_yes_no("Yeah") is True
        assert parse_yes_no("correct") is True
        assert parse_yes_no("that's right") is True

    def test_no_variants(self):
        assert parse_yes_no("no") is False
        assert parse_yes_no("Nope") is False
        assert parse_yes_no("negative") is False

    def test_rejects_ambiguous(self):
        with pytest.raises(URLAInputError):
            parse_yes_no("maybe")
