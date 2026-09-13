from app.core.crypto import decrypt_credentials, encrypt_credentials


def test_round_trip() -> None:
    data = {"consumer_key": "ck_abc123", "consumer_secret": "cs_xyz789"}
    token = encrypt_credentials(data)
    assert decrypt_credentials(token) == data


def test_ciphertext_never_contains_plaintext_secrets() -> None:
    data = {"api_key": "super-secret-value-do-not-leak"}
    token = encrypt_credentials(data)
    assert "super-secret-value-do-not-leak" not in token


def test_encrypting_the_same_data_twice_yields_different_ciphertext() -> None:
    """Fernet includes a random IV, so credentials rotation/rewriting
    doesn't produce a predictable, comparable ciphertext."""
    data = {"token": "same-value"}
    assert encrypt_credentials(data) != encrypt_credentials(data)
