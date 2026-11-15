"""Kandidatens identitet: krypterad i databasen, läsbar bara efter ett avslöjande.

Identiteten krypteras med en egen nyckel (`identity_key`) innan den skrivs till databasen,
så varken en databasdump, Supabase-konsolen eller en felaktig fråga visar namn
(ADR 0009). Försvinner nyckeln går sparade identiteter inte att läsa.
"""

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel


class Identity(BaseModel):
    # None: namnet kunde inte läsas ut (t.ex. CV:n som laddades upp före avslöjandet).
    name: str | None = None


def encrypt_identity(key: str, identity: Identity) -> str:
    return Fernet(key).encrypt(identity.model_dump_json().encode()).decode()


def decrypt_identity(key: str, token: str | None) -> Identity:
    """Saknad eller oläsbar identitet ger en tom `Identity`, aldrig ett fel."""
    if not token:
        return Identity()
    try:
        return Identity.model_validate_json(Fernet(key).decrypt(token.encode()))
    except InvalidToken:
        return Identity()


def is_valid_key(key: str) -> bool:
    try:
        Fernet(key)
    except ValueError:
        return False
    return True
