"""Runtime secret resolution for `DataSource.secret_reference` (and any other key pointer).

A reference like "datasource/<org>/<source>/mqtt_password" is mapped to the environment variable
`KOTA_SECRET_DATASOURCE_<ORG>_<SOURCE>_MQTT_PASSWORD` (upper-cased, every non-alphanumeric character -> "_").
This is the minimum "platform secrets layer" the models already assume: deployments populate the environment from
their secret manager (Kubernetes secret, Vault agent, cloud secret store). To use a different backend, replace
`resolve` - callers never see where a value came from and must never log it.
"""
from __future__ import annotations

import os
import re

PREFIX = "KOTA_SECRET_"


def env_name(reference: str) -> str:
    return PREFIX + re.sub(r"[^A-Za-z0-9]+", "_", reference.strip()).strip("_").upper()


def resolve(reference: str | None) -> str | None:
    """The secret value, or None when the reference is empty or unset. Never raises, never logs the value."""
    if not reference or not reference.strip():
        return None
    value = os.environ.get(env_name(reference))
    return value if value else None
