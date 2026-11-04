"""Operating-system credential storage. Secrets never enter the JSON manifest."""

from __future__ import annotations

from dataclasses import dataclass

SERVICE_NAME = "forge-mcp"


class CredentialError(RuntimeError):
    """A credential could not be accessed securely."""


@dataclass
class CredentialVault:
    """Thin wrapper around the operating-system keyring.

    There is deliberately no plaintext-file fallback. If no secure keyring is
    available, setup fails and asks the operator to configure one.
    """

    service_name: str = SERVICE_NAME

    @staticmethod
    def _keyring():
        try:
            import keyring
            from keyring.errors import NoKeyringError
        except ImportError as exc:
            raise CredentialError("Install the keyring dependency to manage credentials.") from exc
        try:
            backend = keyring.get_keyring()
            priority = getattr(backend, "priority", 0)
            if callable(priority):
                priority = priority()
            if priority <= 0:
                raise CredentialError(
                    "No secure OS credential store is available. Configure macOS Keychain, "
                    "Windows Credential Manager, or a Linux Secret Service backend."
                )
        except NoKeyringError as exc:
            raise CredentialError("No secure OS credential store is available.") from exc
        return keyring

    def set(self, reference: str, secret: str) -> None:
        if not reference or len(reference) > 192:
            raise ValueError("Credential reference must contain 1–192 characters.")
        if not secret or "\n" in secret or "\r" in secret:
            raise ValueError("Credential values must be non-empty and single-line.")
        try:
            self._keyring().set_password(self.service_name, reference, secret)
        except Exception as exc:
            raise CredentialError(f"Could not save credential {reference!r} in the OS keyring.") from exc

    def get(self, reference: str) -> str:
        try:
            secret = self._keyring().get_password(self.service_name, reference)
        except Exception as exc:
            raise CredentialError(f"Could not read credential {reference!r} from the OS keyring.") from exc
        if secret is None:
            raise CredentialError(
                f"Credential {reference!r} is missing. Run forge-mcp credential set."
            )
        return secret

    def delete(self, reference: str) -> None:
        try:
            self._keyring().delete_password(self.service_name, reference)
        except Exception as exc:
            raise CredentialError(f"Could not delete credential {reference!r}.") from exc

    def exists(self, reference: str) -> bool:
        try:
            return self._keyring().get_password(self.service_name, reference) is not None
        except Exception as exc:
            raise CredentialError("Could not inspect the OS keyring.") from exc
