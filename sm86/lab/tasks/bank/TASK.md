# Refactor the bank module

Refactor `bank.py`:

1. Add a class `Bank` that holds its own accounts, with methods `open_account(name, initial=0)`, `deposit(name,
   amount)`, `withdraw(name, amount)`, `balance(name)` and `transfer(src, dst, amount)`. Two `Bank` instances never
   share accounts.
2. Amounts are integers (cents). `deposit`, `withdraw` and `transfer` need `amount > 0`, else `ValueError`. `initial`
   must be `>= 0`, else `ValueError`. An unknown account raises `KeyError`. Opening an existing account raises
   `ValueError`. `transfer` to the same account raises `ValueError`.
3. Add `class InsufficientFunds(ValueError)`. `withdraw` and `transfer` raise it when the source balance is smaller
   than `amount`. A call that raises leaves every balance unchanged.
4. Keep the module-level functions `open_account`, `deposit`, `withdraw` and `balance` working for existing callers,
   now delegating to a module-level `Bank` instance named `default_bank`, and add a module-level `transfer` the same
   way.

Run `python -m pytest -q` in this folder to check your work, and keep going until every test passes. Do not change anything under `tests/`. Use only the Python standard library.
