from __future__ import annotations

from typing import Any

import stripe

from app.core.config import settings


def stripe_mode() -> str:
    if settings.self_funded_mode:
        return "self_funded"
    key = settings.stripe_secret_key or ""
    if key.startswith("sk_test_"):
        return "stripe_test"
    if key.startswith("sk_live_"):
        return "stripe_live"
    return "stripe_unconfigured"


def require_stripe() -> None:
    if not settings.stripe_secret_key:
        raise RuntimeError("Stripe is not configured. Set STRIPE_SECRET_KEY first.")
    stripe.api_key = settings.stripe_secret_key


def require_webhook_secret() -> str:
    if not settings.stripe_webhook_secret:
        raise RuntimeError("Stripe webhook signing secret is not configured.")
    return settings.stripe_webhook_secret


def create_checkout_session(campaign, user) -> dict[str, Any]:
    if settings.self_funded_mode:
        return {
            "id": f"self-funded-{campaign.id[:8]}",
            "url": None,
            "customer_id": user.stripe_customer_id,
            "subscription_id": None,
            "mode": stripe_mode(),
            "activated": True,
            "message": "Self-funded mode is active. Ever will use your configured API accounts and meter spend against the campaign budget.",
        }
    require_stripe()
    brand_name = (
        campaign.brand_voice_profile.get("brand_name")
        or campaign.merchant.name
        or campaign.merchant.domain.split(".")[0].title()
    )
    session_params: dict[str, Any] = {
        "mode": "subscription",
        "client_reference_id": campaign.id,
        "success_url": f"{settings.public_web_url}/onboarding?checkout=success&campaign_id={campaign.id}",
        "cancel_url": f"{settings.public_web_url}/onboarding?checkout=cancel&campaign_id={campaign.id}",
        "line_items": [
            {
                "quantity": 1,
                "price_data": {
                    "currency": "usd",
                    "unit_amount": int(round(campaign.budget_monthly * 100)),
                    "recurring": {"interval": "month"},
                    "product_data": {
                        "name": f"Ever compute budget for {brand_name}",
                        "description": (
                            "Propose-only real-money experiment. All agent actions require "
                            "human approval and manual execution."
                        ),
                    },
                },
            }
        ],
        "metadata": {
            "campaign_id": campaign.id,
            "user_id": user.id,
            "merchant_id": campaign.merchant_id,
        },
        "subscription_data": {
            "metadata": {
                "campaign_id": campaign.id,
                "user_id": user.id,
                "merchant_id": campaign.merchant_id,
            }
        },
    }
    if user.stripe_customer_id:
        session_params["customer"] = user.stripe_customer_id
    else:
        # Stripe creates the customer automatically for subscription-mode Checkout.
        # `customer_creation` is only valid for one-time payment sessions.
        session_params["customer_email"] = user.email
    session = stripe.checkout.Session.create(**session_params)
    return {
        "id": session.id,
        "url": session.url,
        "customer_id": session.customer,
        "subscription_id": session.subscription,
        "mode": stripe_mode(),
    }


def construct_webhook_event(payload: bytes, signature: str | None) -> Any:
    require_stripe()
    webhook_secret = require_webhook_secret()
    if not signature:
        raise RuntimeError("Missing Stripe signature header.")
    return stripe.Webhook.construct_event(payload, signature, webhook_secret)


def retrieve_checkout_session(session_id: str) -> Any:
    require_stripe()
    if not session_id:
        raise RuntimeError("Stripe checkout session id is missing.")
    return stripe.checkout.Session.retrieve(session_id)
