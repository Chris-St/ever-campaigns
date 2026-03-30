from __future__ import annotations

import os
from types import SimpleNamespace


os.environ["STRIPE_SECRET_KEY"] = "sk_test_123"
os.environ["STRIPE_WEBHOOK_SECRET"] = "whsec_123"
os.environ["SELF_FUNDED_MODE"] = "false"

from app.services.billing import create_checkout_session  # noqa: E402


def test_subscription_checkout_uses_customer_email_not_customer_creation(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            id="cs_test_123",
            url="https://checkout.stripe.test/session/cs_test_123",
            customer="cus_test_123",
            subscription="sub_test_123",
        )

    monkeypatch.setattr("app.services.billing.stripe.checkout.Session.create", fake_create)

    campaign = SimpleNamespace(
        id="camp_test_123",
        budget_monthly=50,
        merchant_id="merchant_test_123",
        merchant=SimpleNamespace(name="Bia", domain="biaundies.com"),
        brand_voice_profile={},
    )
    user = SimpleNamespace(
        id="user_test_123",
        email="founder@ever.com",
        stripe_customer_id=None,
    )

    response = create_checkout_session(campaign, user)

    assert response["id"] == "cs_test_123"
    assert captured["mode"] == "subscription"
    assert captured["customer_email"] == "founder@ever.com"
    assert "customer_creation" not in captured


def test_self_funded_mode_skips_stripe_and_activates_immediately(monkeypatch) -> None:
    monkeypatch.setattr("app.services.billing.settings.self_funded_mode", True)

    campaign = SimpleNamespace(
        id="camp_test_456",
        budget_monthly=50,
        merchant_id="merchant_test_456",
        merchant=SimpleNamespace(name="Bia", domain="biaundies.com"),
        brand_voice_profile={},
    )
    user = SimpleNamespace(
        id="user_test_456",
        email="founder@ever.com",
        stripe_customer_id=None,
    )

    response = create_checkout_session(campaign, user)

    assert response["mode"] == "self_funded"
    assert response["activated"] is True
    assert response["url"] is None
