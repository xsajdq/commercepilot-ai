from cryptography.fernet import Fernet, InvalidToken

from cp_shared.crypto import decrypt_credentials, encrypt_credentials


def _generate_key() -> str:
    return Fernet.generate_key().decode("utf-8")


class TestSingleKey:
    def test_round_trips(self) -> None:
        key = _generate_key()
        data = {"consumer_key": "ck_abc123", "consumer_secret": "cs_xyz789"}

        token = encrypt_credentials(data, key=key)

        assert decrypt_credentials(token, key=key) == data

    def test_ciphertext_never_contains_the_plaintext(self) -> None:
        key = _generate_key()
        token = encrypt_credentials({"api_key": "super-secret-value"}, key=key)

        assert "super-secret-value" not in token

    def test_a_wrong_key_fails_to_decrypt(self) -> None:
        token = encrypt_credentials({"token": "x"}, key=_generate_key())

        try:
            decrypt_credentials(token, key=_generate_key())
            raised = False
        except InvalidToken:
            raised = True
        assert raised is True


class TestKeyRotation:
    """Phase 21: a `key` list supports zero-downtime rotation - encrypt
    always uses the first (current) key; decrypt tries every key in the
    list, so data written under a key that has since become "previous"
    still decrypts during the rotation window."""

    def test_data_written_under_the_old_key_still_decrypts_with_new_plus_old(self) -> None:
        old_key = _generate_key()
        new_key = _generate_key()
        token = encrypt_credentials({"token": "written-before-rotation"}, key=old_key)

        result = decrypt_credentials(token, key=[new_key, old_key])

        assert result == {"token": "written-before-rotation"}

    def test_encrypting_with_a_key_list_always_uses_the_first_key(self) -> None:
        new_key = _generate_key()
        old_key = _generate_key()

        token = encrypt_credentials({"token": "written-after-rotation"}, key=[new_key, old_key])

        # Decryptable by the new key alone...
        assert decrypt_credentials(token, key=new_key) == {"token": "written-after-rotation"}
        # ...but not by the old key alone - proving it was encrypted
        # under the new (first) key, not the old one.
        try:
            decrypt_credentials(token, key=old_key)
            raised = False
        except InvalidToken:
            raised = True
        assert raised is True

    def test_a_key_absent_from_the_rotation_list_still_fails(self) -> None:
        token = encrypt_credentials({"token": "x"}, key=_generate_key())

        try:
            decrypt_credentials(token, key=[_generate_key(), _generate_key()])
            raised = False
        except InvalidToken:
            raised = True
        assert raised is True
