import uuid

from app.core.config import get_settings
from app.core.security import InvalidTokenError, create_access_token, decode_access_token
from app.db.models.membership import MembershipRole


def _make_token() -> str:
    return create_access_token(
        user_id=uuid.uuid4(), tenant_id=uuid.uuid4(), role=MembershipRole.OWNER
    )


class TestDecodeAccessToken:
    def test_round_trips_a_freshly_issued_token(self) -> None:
        token = _make_token()

        payload = decode_access_token(token)

        assert payload["type"] == "access"

    def test_rejects_a_garbage_token(self) -> None:
        try:
            decode_access_token("not-a-real-token")
            raised = False
        except InvalidTokenError:
            raised = True
        assert raised is True


class TestSecretKeyRotation:
    """Phase 21: `secret_key_previous` lets a token signed under the
    OLD key keep verifying during a rotation window, without forcing
    every logged-in user to re-login the instant `secret_key` changes."""

    def test_a_token_signed_before_rotation_still_verifies_after(self, monkeypatch) -> None:
        settings = get_settings()
        old_key = settings.secret_key
        token = _make_token()  # signed under the current (soon to be "old") key

        # Simulate rotation: secret_key becomes new, old one moves to
        # secret_key_previous.
        monkeypatch.setattr(settings, "secret_key", "brand-new-rotated-secret")
        monkeypatch.setattr(settings, "secret_key_previous", old_key)

        payload = decode_access_token(token)

        assert payload["type"] == "access"

    def test_a_token_is_rejected_once_its_old_key_is_no_longer_listed(self, monkeypatch) -> None:
        settings = get_settings()
        old_key = settings.secret_key
        token = _make_token()

        monkeypatch.setattr(settings, "secret_key", "brand-new-rotated-secret")
        monkeypatch.setattr(settings, "secret_key_previous", None)

        try:
            decode_access_token(token)
            raised = False
        except InvalidTokenError:
            raised = True

        assert raised is True
        assert old_key != settings.secret_key  # sanity: rotation actually happened

    def test_new_tokens_are_always_signed_with_the_current_key_only(self, monkeypatch) -> None:
        settings = get_settings()
        monkeypatch.setattr(settings, "secret_key_previous", "some-old-key")

        token = _make_token()

        # Decodable with just the current key - never depends on
        # secret_key_previous for a token issued *after* rotation.
        monkeypatch.setattr(settings, "secret_key_previous", None)
        payload = decode_access_token(token)
        assert payload["type"] == "access"
