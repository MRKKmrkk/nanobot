"""Default extension registry."""

from __future__ import annotations

from importlib import import_module

from loguru import logger

from nanobot.config.schema import Config, GatewayExtensionConfig
from nanobot.extensions.base import NanobotExtension


def default_gateway_extension_specs() -> list[GatewayExtensionConfig]:
    """Return built-in default extension declarations."""
    return [
        GatewayExtensionConfig(
            extension_id="expert",
            class_path="nanobot.extensions.expert_extension.ExpertExtension",
            enabled=True,
        ),
        GatewayExtensionConfig(
            extension_id="hook",
            class_path="nanobot.extensions.hook_extension.HookExtension",
            enabled=True,
        ),
    ]


def load_gateway_extensions(config: Config) -> list[NanobotExtension]:
    """Load gateway extensions from config declarations."""
    specs = default_gateway_extension_specs() if config.gateway.extensions is None else config.gateway.extensions
    loaded: list[NanobotExtension] = []

    for spec in specs:
        if not spec.enabled:
            logger.info("Gateway extension disabled: {}", spec.extension_id)
            continue

        try:
            module_name, class_name = spec.class_path.rsplit(".", 1)
            ext_cls = getattr(import_module(module_name), class_name)
            ext = ext_cls()
            if not isinstance(ext, NanobotExtension):
                raise TypeError(f"{spec.class_path} is not a NanobotExtension")
            if ext.extension_id != spec.extension_id:
                logger.warning(
                    "Gateway extension id mismatch: declared={}, actual={}",
                    spec.extension_id,
                    ext.extension_id,
                )
            loaded.append(ext)
        except Exception as e:
            logger.error("Failed to load extension {} ({}): {}", spec.extension_id, spec.class_path, e)

    return loaded
