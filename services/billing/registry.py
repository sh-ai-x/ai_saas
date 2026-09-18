"""Composition-root provider registry and one-provider-per-environment rule."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from .adapters.lemon_squeezy import LemonSqueezyAdapter
from .adapters.mock import MockPaymentAdapter
from .adapters.toss import TossPaymentsAdapter
from .errors import ProviderConfigurationError, UnknownProvider
from .ports import PaymentProvider

LIVE_PROVIDERS = frozenset({"toss", "lemon-squeezy"})
KNOWN_PROVIDERS = frozenset({"mock", *LIVE_PROVIDERS})


class ProviderRegistry(Mapping[str, PaymentProvider]):
    def __init__(self, providers: Mapping[str, PaymentProvider] | None = None) -> None:
        self._providers = dict(providers or {})
        unknown = set(self._providers) - KNOWN_PROVIDERS
        if unknown:
            raise ProviderConfigurationError(f"unknown providers: {sorted(unknown)}")

    def __getitem__(self, key: str) -> PaymentProvider:
        try:
            return self._providers[key]
        except KeyError as exc:
            raise UnknownProvider(key) from exc

    def __iter__(self) -> Iterator[str]:
        return iter(self._providers)

    def __len__(self) -> int:
        return len(self._providers)

    def require(self, provider_id: str, capability: str | None = None) -> PaymentProvider:
        provider = self[provider_id]
        if capability and capability not in provider.capabilities:
            raise ProviderConfigurationError(f"{provider_id} does not support {capability}")
        return provider


def build_registry(
    *,
    environment: str,
    selected_provider: str,
    mock: PaymentProvider | None = None,
    toss: PaymentProvider | None = None,
    lemon_squeezy: PaymentProvider | None = None,
) -> ProviderRegistry:
    if selected_provider not in KNOWN_PROVIDERS:
        raise ProviderConfigurationError("selected provider is not supported")
    live = [name for name, adapter in (("toss", toss), ("lemon-squeezy", lemon_squeezy)) if adapter is not None]
    if len(live) > 1:
        raise ProviderConfigurationError("at most one live payment provider may be configured")
    if selected_provider == "mock" and live:
        raise ProviderConfigurationError("a live adapter cannot be configured while mock is selected")
    if environment == "production" and selected_provider == "mock":
        raise ProviderConfigurationError("mock payments are not allowed in production")
    if selected_provider in LIVE_PROVIDERS and selected_provider not in live:
        raise ProviderConfigurationError(f"selected live provider is not configured: {selected_provider}")
    if selected_provider == "mock" and mock is None:
        mock = MockPaymentAdapter()
    providers: dict[str, PaymentProvider] = {}
    if mock is not None:
        providers["mock"] = mock
    if toss is not None:
        providers["toss"] = toss
    if lemon_squeezy is not None:
        providers["lemon-squeezy"] = lemon_squeezy
    return ProviderRegistry(providers)


def build_registry_from_environment(values: Mapping[str, str]) -> ProviderRegistry:
    """Construct only the adapter selected by the validated environment."""

    environment = values.get("APP_ENV", "").strip().lower()
    selected = values.get("PAYMENT_PROVIDER", "").strip().lower()
    toss_configured = any(values.get(key, "").strip() for key in ("TOSS_SECRET_KEY", "TOSS_WEBHOOK_SECRET"))
    lemon_configured = any(
        values.get(key, "").strip()
        for key in ("LEMONSQUEEZY_API_KEY", "LEMONSQUEEZY_WEBHOOK_SECRET")
    )
    if toss_configured and lemon_configured:
        raise ProviderConfigurationError("only one live payment provider may be configured")
    if selected == "mock":
        if toss_configured or lemon_configured:
            raise ProviderConfigurationError("live credentials are present while mock is selected")
        return build_registry(environment=environment, selected_provider=selected, mock=MockPaymentAdapter())
    if selected == "toss":
        return build_registry(
            environment=environment,
            selected_provider=selected,
            toss=TossPaymentsAdapter(
                secret_key=values.get("TOSS_SECRET_KEY"),
                webhook_secret=values.get("TOSS_WEBHOOK_SECRET"),
                test_mode=environment != "production",
            ),
        )
    if selected == "lemon-squeezy":
        return build_registry(
            environment=environment,
            selected_provider=selected,
            lemon_squeezy=LemonSqueezyAdapter(
                api_key=values.get("LEMONSQUEEZY_API_KEY"),
                webhook_secret=values.get("LEMONSQUEEZY_WEBHOOK_SECRET") or values.get("LEMONSQUEEZY_API_KEY", ""),
                test_mode=environment != "production",
            ),
        )
    raise ProviderConfigurationError("selected provider is not supported")

