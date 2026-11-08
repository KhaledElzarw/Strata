import pytest

import bank
from bank import Bank, InsufficientFunds


def test_basic_flow():
    b = Bank()
    b.open_account("a", 100)
    b.deposit("a", 50)
    b.withdraw("a", 30)
    assert b.balance("a") == 120


def test_transfer():
    b = Bank()
    b.open_account("a", 100)
    b.open_account("b")
    b.transfer("a", "b", 40)
    assert (b.balance("a"), b.balance("b")) == (60, 40)


def test_insufficient_funds_leaves_balances():
    b = Bank()
    b.open_account("a", 10)
    b.open_account("b", 5)
    with pytest.raises(InsufficientFunds):
        b.transfer("a", "b", 11)
    with pytest.raises(InsufficientFunds):
        b.withdraw("b", 6)
    assert (b.balance("a"), b.balance("b")) == (10, 5)


def test_insufficient_is_value_error():
    assert issubclass(InsufficientFunds, ValueError)


@pytest.mark.parametrize("amount", [0, -5])
def test_non_positive_amounts(amount):
    b = Bank()
    b.open_account("a", 10)
    b.open_account("b")
    for call in (lambda: b.deposit("a", amount), lambda: b.withdraw("a", amount),
                 lambda: b.transfer("a", "b", amount)):
        with pytest.raises(ValueError):
            call()
    assert b.balance("a") == 10


def test_unknown_accounts():
    b = Bank()
    b.open_account("a", 10)
    with pytest.raises(KeyError):
        b.balance("zz")
    with pytest.raises(KeyError):
        b.deposit("zz", 1)
    with pytest.raises(KeyError):
        b.transfer("a", "zz", 1)
    assert b.balance("a") == 10


def test_duplicate_and_negative_initial():
    b = Bank()
    b.open_account("a")
    with pytest.raises(ValueError):
        b.open_account("a")
    with pytest.raises(ValueError):
        b.open_account("n", -1)


def test_self_transfer():
    b = Bank()
    b.open_account("a", 10)
    with pytest.raises(ValueError):
        b.transfer("a", "a", 1)


def test_instances_are_independent():
    b1, b2 = Bank(), Bank()
    b1.open_account("a", 1)
    with pytest.raises(KeyError):
        b2.balance("a")


def test_legacy_functions_use_default_bank():
    bank.open_account("legacy-x", 5)
    bank.deposit("legacy-x", 5)
    bank.withdraw("legacy-x", 3)
    assert bank.balance("legacy-x") == 7 and bank.default_bank.balance("legacy-x") == 7
    bank.open_account("legacy-y")
    bank.transfer("legacy-x", "legacy-y", 7)
    assert bank.balance("legacy-y") == 7
    with pytest.raises(InsufficientFunds):
        bank.withdraw("legacy-x", 1)
