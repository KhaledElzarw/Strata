class InsufficientFunds(ValueError):
    pass


class Bank:
    def __init__(self):
        self._accounts = {}

    def _need(self, name):
        if name not in self._accounts:
            raise KeyError(name)

    @staticmethod
    def _positive(amount):
        if amount <= 0:
            raise ValueError("amount must be positive")

    def open_account(self, name, initial=0):
        if name in self._accounts:
            raise ValueError("account exists: " + name)
        if initial < 0:
            raise ValueError("initial balance must be >= 0")
        self._accounts[name] = initial

    def deposit(self, name, amount):
        self._need(name)
        self._positive(amount)
        self._accounts[name] += amount

    def withdraw(self, name, amount):
        self._need(name)
        self._positive(amount)
        if self._accounts[name] < amount:
            raise InsufficientFunds(name)
        self._accounts[name] -= amount

    def balance(self, name):
        self._need(name)
        return self._accounts[name]

    def transfer(self, src, dst, amount):
        self._need(src)
        self._need(dst)
        self._positive(amount)
        if src == dst:
            raise ValueError("same account")
        if self._accounts[src] < amount:
            raise InsufficientFunds(src)
        self._accounts[src] -= amount
        self._accounts[dst] += amount


default_bank = Bank()


def open_account(name, initial=0):
    default_bank.open_account(name, initial)


def deposit(name, amount):
    default_bank.deposit(name, amount)


def withdraw(name, amount):
    default_bank.withdraw(name, amount)


def balance(name):
    return default_bank.balance(name)


def transfer(src, dst, amount):
    default_bank.transfer(src, dst, amount)
