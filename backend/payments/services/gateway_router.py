"""
Payment gateway router — maps gateway name to its module.

Each gateway module must expose (one-time payments):
  - create_checkout_session(order) -> dict  (returns {'checkout_url': str})
  - verify_webhook(headers, body) -> dict
  - process_webhook_event(event) -> dict | None

Subscription-capable gateways may also expose:
  - create_subscription_checkout(order) -> dict
  - cancel_subscription(subscription) -> dict
  - get_subscription_status(subscription) -> dict
"""
import importlib

_GATEWAY_MODULES = {
    'stub': 'payments.services.stub_gateway',
    'alipay': 'payments.services.alipay_gateway',
    'wechat': 'payments.services.wechat_gateway',
}


def get_gateway(name: str):
    """Return the gateway module for the given name. Raises ValueError if unknown."""
    module_path = _GATEWAY_MODULES.get(name)
    if module_path is None:
        raise ValueError(f'Unknown payment gateway: {name}')
    return importlib.import_module(module_path)


def gateway_supports_subscriptions(name: str) -> bool:
    """Check if a gateway implements the subscription interface."""
    try:
        gw = get_gateway(name)
        return hasattr(gw, 'create_subscription_checkout')
    except ValueError:
        return False
