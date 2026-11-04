"""Persistent MCP OAuth token storage backed by the operating-system keyring."""

from __future__ import annotations

import json

from forge_mcp.vault import CredentialVault
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken


class KeyringOAuthStorage:
    """Implements the MCP SDK TokenStorage protocol without plaintext files."""

    def __init__(self, server_name: str, vault: CredentialVault | None = None) -> None:
        self.vault = vault or CredentialVault()
        self.token_ref = f"oauth/{server_name}/tokens"
        self.client_ref = f"oauth/{server_name}/client-info"

    async def get_tokens(self) -> OAuthToken | None:
        try:
            value = self.vault.get(self.token_ref)
        except Exception:
            return None
        return OAuthToken.model_validate(json.loads(value))

    async def set_tokens(self, tokens: OAuthToken) -> None:
        self.vault.set(self.token_ref, tokens.model_dump_json())

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        try:
            value = self.vault.get(self.client_ref)
        except Exception:
            return None
        return OAuthClientInformationFull.model_validate(json.loads(value))

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        self.vault.set(self.client_ref, client_info.model_dump_json())
