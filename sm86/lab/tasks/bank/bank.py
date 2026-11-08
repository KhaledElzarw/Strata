"""Account helpers. Balances are integer cents."""
_accounts = {}


def open_account(name, initial=0):
    if name in _accounts:
        raise ValueError("account exists: " + name)
    _accounts[name] = initial


def deposit(name, amount):
    _accounts[name] += amount


def withdraw(name, amount):
    _accounts[name] -= amount


def balance(name):
    return _accounts[name]
