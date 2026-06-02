"""
Payment gateway router — maps gateway name to its module.

Each gateway module must expose:
  - create_checkout_session(order) -> dict  (returns {'checkout_url': str})
  - verify_webhook(headers, body) -> dict
  - process_webhook_event(event) -> dict | None
"""
import importlib

_GATEWAY_MODULES = {
    'stub': 'payments.services.stub_gateway',
    'stripe': 'payments.services.stripe_gateway',
    'alipay': 'payments.services.alipay_gateway',
    'wechat': 'payments.services.wechat_gateway',
    'airwallex': 'payments.services.airwallex_gateway',
}


def get_gateway(name: str):
    """Return the gateway module for the given name. Raises ValueError if unknown."""
    module_path = _GATEWAY_MODULES.get(name)
    if module_path is None:
        raise ValueError(f'Unknown payment gateway: {name}')
    return importlib.import_module(module_path)
