"""Unit tests for payments.py's pure logic: admission/renewal/due_payment
classification and the due_amount decrement math."""

from payments import apply_due_payment, classify_admission_or_renewal


class TestClassifyAdmissionOrRenewal:
    def test_first_ever_subscription_is_admission(self):
        assert classify_admission_or_renewal("sub-1", "sub-1") == "admission"

    def test_later_subscription_is_renewal(self):
        assert classify_admission_or_renewal("sub-1", "sub-2") == "renewal"

    def test_member_with_no_subscriptions_at_all_is_renewal(self):
        # Shouldn't happen in practice (a payment implies a subscription
        # exists), but earliest_subscription_id=None must never accidentally
        # equal a real id and classify as admission.
        assert classify_admission_or_renewal(None, "sub-1") == "renewal"


class TestApplyDuePayment:
    def test_partial_payment_reduces_due_amount(self):
        assert apply_due_payment(due_amount=3000, payment_amount=1000) == 2000

    def test_exact_payment_zeroes_due_amount(self):
        assert apply_due_payment(due_amount=3000, payment_amount=3000) == 0

    def test_overpayment_floors_at_zero_not_negative(self):
        assert apply_due_payment(due_amount=1000, payment_amount=1500) == 0

    def test_zero_due_amount_stays_zero(self):
        assert apply_due_payment(due_amount=0, payment_amount=500) == 0
