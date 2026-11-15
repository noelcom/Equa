"""Kandidatens identitet: krypterad i databasen, läsbar bara efter ett avslöjande.

Identiteten krypteras med en egen nyckel (`identity_key`) innan den skrivs till databasen,
så varken en databasdump, Supabase-konsolen eller en felaktig fråga visar namn
(ADR 0009). Försvinner nyckeln går sparade identiteter inte att läsa.
"""

from cryptography.fernet import Fernet, InvalidToken
from pydantic import BaseModel


class Identity(BaseModel):
    # False: ingen identitet sparades (t.ex. CV:n som laddades upp före avslöjandet).
    # True: den lästes ut, men enskilda fält kan ändå saknas i CV:t och är då None.
    extracted: bool = False
    name: str | None = None
    email: str | None = None
    phone: str | None = None


def encrypt_identity(key: str, identity: Identity) -> str:
    stored = identity.model_copy(update={"extracted": True})
    return Fernet(key).encrypt(stored.model_dump_json().encode()).decode()


def decrypt_identity(key: str, token: str | None) -> Identity:
    """Saknad eller oläsbar identitet ger en tom `Identity`, aldrig ett fel."""
    if not token:
        return Identity()
    try:
        stored = Identity.model_validate_json(Fernet(key).decrypt(token.encode()))
        return stored.model_copy(update={"extracted": True})
    except InvalidToken:
        return Identity()


def is_valid_key(key: str) -> bool:
    try:
        Fernet(key)
    except ValueError:
        return False
    return True
