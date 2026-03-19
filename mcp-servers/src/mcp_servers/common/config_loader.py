"""
Shared tenant configuration file loader.

Reads tenant configs from a JSON file mounted as a K8s Secret volume.
Used by all multi-tenant MCP server tenant managers.
"""

import json
import os
from typing import Any, Dict, Optional

DEFAULT_CONFIG_PATH = "/etc/mcp/tenants.json"


def load_tenant_configs_from_file(
    config_path: Optional[str] = None,
) -> Dict[str, Dict[str, Any]]:
    """Load all tenant configurations from a JSON config file.

    The JSON file structure:
    {
        "tenant_id_1": { "host": "...", "port": 5432, "password": "..." },
        "tenant_id_2": { ... }
    }

    Args:
        config_path: Path to the JSON config file.
                     Defaults to TENANT_CONFIG_FILE env var or /etc/mcp/tenants.json.

    Returns:
        Dict mapping tenant_id -> config dict. Empty dict if file not found.
    """
    path = config_path or os.getenv("TENANT_CONFIG_FILE", DEFAULT_CONFIG_PATH)

    if not os.path.exists(path):
        return {}

    try:
        with open(path, "r") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            print(f"Warning: Config file {path} does not contain a JSON object")
            return {}
        return data
    except (json.JSONDecodeError, IOError) as e:
        print(f"Warning: Failed to read config file {path}: {e}")
        return {}
