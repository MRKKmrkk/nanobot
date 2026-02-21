"""Gateway extensions."""

from nanobot.extensions.base import GatewayExtensionContext, NanobotExtension
from nanobot.extensions.manager import ExtensionManager
from nanobot.extensions.registry import (
    default_gateway_extension_specs,
    load_gateway_extensions,
)

__all__ = [
    "GatewayExtensionContext",
    "NanobotExtension",
    "ExtensionManager",
    "default_gateway_extension_specs",
    "load_gateway_extensions",
]
