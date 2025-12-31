"""
MinIO Tenant Manager

Manages multiple MinIO tenant connections.
"""

import os
from typing import Optional, Dict

from minio import Minio
from pydantic import BaseModel, Field


class MinioTenantConfig(BaseModel):
    """Configuration for a single MinIO tenant."""

    tenant_id: str = Field(..., description="Unique identifier for this tenant")
    endpoint: str = Field(..., description="MinIO endpoint (e.g., 'minio.example.com:9000')")
    access_key: str = Field(..., description="MinIO access key")
    secret_key: str = Field(..., description="MinIO secret key")
    secure: bool = Field(default=True, description="Use HTTPS/TLS")
    region: Optional[str] = Field(default=None, description="S3 region")


class MinioTenantManager:
    """Manages multiple MinIO tenant connections."""

    def __init__(self):
        self.clients: Dict[str, Minio] = {}
        self.configs: Dict[str, MinioTenantConfig] = {}

    def load_tenant_from_env(self, tenant_id: str) -> Optional[MinioTenantConfig]:
        """Load tenant configuration from environment variables."""
        prefix = f"MINIO_TENANT_{tenant_id.upper()}"
        endpoint = os.getenv(f"{prefix}_ENDPOINT")
        if not endpoint:
            return None

        return MinioTenantConfig(
            tenant_id=tenant_id,
            endpoint=endpoint,
            access_key=os.getenv(f"{prefix}_ACCESS_KEY", ""),
            secret_key=os.getenv(f"{prefix}_SECRET_KEY", ""),
            secure=os.getenv(f"{prefix}_SECURE", "true").lower() == "true",
            region=os.getenv(f"{prefix}_REGION"),
        )

    def register_tenant(self, config: MinioTenantConfig) -> None:
        """Register a tenant and create a MinIO client."""
        client = Minio(
            config.endpoint,
            access_key=config.access_key,
            secret_key=config.secret_key,
            secure=config.secure,
            region=config.region,
        )
        self.clients[config.tenant_id] = client
        self.configs[config.tenant_id] = config

    def get_client(self, tenant_id: str) -> Minio:
        """Get MinIO client for a tenant."""
        if tenant_id not in self.clients:
            # Try to load from environment
            config = self.load_tenant_from_env(tenant_id)
            if config:
                self.register_tenant(config)
            else:
                raise ValueError(
                    f"Tenant '{tenant_id}' not found. Configure it via environment variables."
                )

        return self.clients[tenant_id]

