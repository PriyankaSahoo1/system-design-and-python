"""Splitwise-style ledger. History is append-only. Balances are a sum."""

from __future__ import annotations

from dataclasses import dataclass, field


class Unbalanced(Exception):
    pass


@dataclass
class Expense:
    expense_id: str
    payer_id: str
    shares: dict[str, int]


@dataclass
class Settlement:
    from_user: str
    to_user: str
    amount: int


@dataclass
class GroupLedger:
    expenses: list[Expense] = field(default_factory=list)
    settlements: list[Settlement] = field(default_factory=list)
    _seq: int = 0

    def add_expense(self, payer_id: str, shares: dict[str, int]) -> Expense:
        if sum(shares.values()) <= 0:
            raise Unbalanced("empty")
        if any(amount < 0 for amount in shares.values()):
            raise Unbalanced("negative share")
        self._seq += 1
        expense = Expense(f"E{self._seq}", payer_id, dict(shares))
        self.expenses.append(expense)
        return expense

    def settle(self, from_user: str, to_user: str, amount: int) -> None:
        if amount <= 0:
            raise Unbalanced("amount")
        self.settlements.append(Settlement(from_user, to_user, amount))

    def nets(self) -> dict[str, int]:
        """Positive means the group owes this person. Negative means they owe the group."""
        net: dict[str, int] = {}
        for expense in self.expenses:
            total = sum(expense.shares.values())
            net[expense.payer_id] = net.get(expense.payer_id, 0) + total
            for user, amount in expense.shares.items():
                net[user] = net.get(user, 0) - amount
        for settlement in self.settlements:
            net[settlement.from_user] = net.get(settlement.from_user, 0) + settlement.amount
            net[settlement.to_user] = net.get(settlement.to_user, 0) - settlement.amount
        return {user: amount for user, amount in net.items() if amount != 0}

    def simplified(self) -> list[tuple[str, str, int]]:
        """Display only. Same nets, fewer edges. Does not delete history."""
        debtors: list[list] = []
        creditors: list[list] = []
        for user, amount in self.nets().items():
            if amount < 0:
                debtors.append([user, -amount])
            elif amount > 0:
                creditors.append([user, amount])
        payments: list[tuple[str, str, int]] = []
        i = j = 0
        while i < len(debtors) and j < len(creditors):
            pay = min(debtors[i][1], creditors[j][1])
            payments.append((debtors[i][0], creditors[j][0], pay))
            debtors[i][1] -= pay
            creditors[j][1] -= pay
            if debtors[i][1] == 0:
                i += 1
            if creditors[j][1] == 0:
                j += 1
        return payments
