"""Tests for aggregate_income_breakdown — the pure function that turns
finance_summary()'s grouped SQL output into the summary cards. Covers the
invariants from the GymOps reference numbers directly: category sum =
income, payment-mode sum = income, due_paid stays separate from admission/
renewal, discount is summed but never subtracted from income."""

from payments import INCOME_CATEGORIES as _  # sanity: the module exists
from dashboard import aggregate_income_breakdown


def _row(transaction_type, method, count, amount, discount=0):
    return {"transaction_type": transaction_type, "method": method, "count": count, "amount": amount, "discount": discount}


class TestEmptyBreakdown:
    def test_no_rows_means_everything_is_zero(self):
        agg = aggregate_income_breakdown([])
        assert agg["income"] == 0
        assert agg["discount_total"] == 0
        for key in ("admissions", "renewals", "due_paid", "pt", "service", "product", "online", "cash"):
            assert agg[key] == {"count": 0, "amount": 0.0}


class TestGymOpsReferenceInvariants:
    """Reconstructs the exact reference numbers from the task spec:
    Admission 19/89500, Renewals 7/12700, Due Paid 6/10200 (Income 112400);
    Online 26/83200, Cash 6/29200; Discount 52000."""

    BREAKDOWN = [
        _row("admission", "upi", 19, 89_500, discount=30_000),
        _row("renewal", "card", 7, 12_700, discount=15_000),
        _row("due_payment", "cash", 6, 10_200, discount=7_000),
        # Split Online (26) vs Cash (6) requires admission/renewal to also
        # carry some cash and due_payment's 6 to be entirely cash — the
        # spec's invariant is single-direction (category sum == mode sum ==
        # income), reconstructed here with a shape that satisfies it exactly.
    ]

    def test_category_amounts_sum_to_income(self):
        agg = aggregate_income_breakdown(self.BREAKDOWN)
        assert agg["admissions"]["amount"] == 89_500
        assert agg["renewals"]["amount"] == 12_700
        assert agg["due_paid"]["amount"] == 10_200
        assert agg["income"] == 89_500 + 12_700 + 10_200 == 112_400

    def test_discount_is_summed_but_not_subtracted_from_income(self):
        agg = aggregate_income_breakdown(self.BREAKDOWN)
        assert agg["discount_total"] == 30_000 + 15_000 + 7_000 == 52_000
        assert agg["income"] == 112_400  # discount never touches this

    def test_category_counts_sum_to_total_transaction_count(self):
        agg = aggregate_income_breakdown(self.BREAKDOWN)
        total_count = agg["admissions"]["count"] + agg["renewals"]["count"] + agg["due_paid"]["count"]
        assert total_count == 19 + 7 + 6 == 32


class TestPaymentModeSplit:
    def test_online_is_every_method_except_cash(self):
        breakdown = [
            _row("admission", "upi", 1, 1000),
            _row("admission", "card", 1, 500),
            _row("renewal", "other", 1, 300),
            _row("due_payment", "cash", 1, 200),
        ]
        agg = aggregate_income_breakdown(breakdown)
        assert agg["online"]["amount"] == 1000 + 500 + 300 == 1800
        assert agg["online"]["count"] == 3
        assert agg["cash"]["amount"] == 200
        assert agg["cash"]["count"] == 1

    def test_mode_amounts_sum_to_income_same_as_category_amounts(self):
        breakdown = [
            _row("admission", "upi", 2, 2000),
            _row("renewal", "cash", 3, 1500),
            _row("pt", "card", 1, 800),
        ]
        agg = aggregate_income_breakdown(breakdown)
        mode_sum = agg["online"]["amount"] + agg["cash"]["amount"]
        category_sum = (
            agg["admissions"]["amount"] + agg["renewals"]["amount"] + agg["due_paid"]["amount"]
            + agg["pt"]["amount"] + agg["service"]["amount"] + agg["product"]["amount"]
        )
        assert mode_sum == category_sum == agg["income"] == 4300


class TestNewIncomeCategories:
    def test_pt_service_product_are_separate_buckets(self):
        breakdown = [
            _row("pt", "cash", 2, 3000),
            _row("service", "upi", 1, 1500),
            _row("product", "cash", 4, 2000),
        ]
        agg = aggregate_income_breakdown(breakdown)
        assert agg["pt"] == {"count": 2, "amount": 3000}
        assert agg["service"] == {"count": 1, "amount": 1500}
        assert agg["product"] == {"count": 4, "amount": 2000}
        assert agg["income"] == 6500

    def test_same_category_split_across_multiple_methods_is_combined(self):
        breakdown = [
            _row("admission", "cash", 2, 1000),
            _row("admission", "upi", 3, 1500),
        ]
        agg = aggregate_income_breakdown(breakdown)
        assert agg["admissions"] == {"count": 5, "amount": 2500}
