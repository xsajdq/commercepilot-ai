import io
import json
import logging
import uuid

from cp_shared.logging import JsonFormatter, RedactingFilter, configure_logging


def _make_logger(name: str) -> tuple[logging.Logger, io.StringIO]:
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.handlers = []
    logger.propagate = False
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter(service_name="test-service"))
    handler.addFilter(RedactingFilter())
    logger.addHandler(handler)
    return logger, stream


class TestJsonFormatter:
    def test_emits_valid_json_with_expected_fields(self) -> None:
        logger, stream = _make_logger(f"t-{uuid.uuid4()}")

        logger.info("hello world")

        payload = json.loads(stream.getvalue())
        assert payload["message"] == "hello world"
        assert payload["level"] == "INFO"
        assert payload["service"] == "test-service"
        assert "timestamp" in payload

    def test_includes_extra_fields_for_filtering(self) -> None:
        logger, stream = _make_logger(f"t-{uuid.uuid4()}")
        tenant_id = uuid.uuid4()

        logger.info("synced connection", extra={"tenant_id": tenant_id, "offers": 3})

        payload = json.loads(stream.getvalue())
        assert payload["tenant_id"] == str(tenant_id)
        assert payload["offers"] == 3

    def test_includes_exception_traceback(self) -> None:
        logger, stream = _make_logger(f"t-{uuid.uuid4()}")

        try:
            raise ValueError("boom")
        except ValueError:
            logger.exception("task failed")

        payload = json.loads(stream.getvalue())
        assert "ValueError: boom" in payload["exception"]


class TestRedactingFilter:
    def test_redacts_a_jwt_access_token_in_a_message_arg(self) -> None:
        logger, stream = _make_logger(f"t-{uuid.uuid4()}")
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJlLWJ5dGVz"

        logger.info("issued token: %s", jwt)

        output = stream.getvalue()
        assert jwt not in output
        assert "[REDACTED]" in output

    def test_redacts_a_fernet_encrypted_credentials_blob(self) -> None:
        logger, stream = _make_logger(f"t-{uuid.uuid4()}")
        fernet_token = "gAAAAABlorem_ipsum_dolor_sit_amet_1234567890=="

        logger.info("stored credentials %s", fernet_token)

        output = stream.getvalue()
        assert fernet_token not in output
        assert "[REDACTED]" in output

    def test_redacts_an_authorization_bearer_header(self) -> None:
        logger, stream = _make_logger(f"t-{uuid.uuid4()}")

        logger.info("request header: Authorization: Bearer abc123.def-456_xyz")

        output = stream.getvalue()
        assert "abc123.def-456_xyz" not in output
        assert "[REDACTED]" in output

    def test_redacts_a_stripe_secret_key(self) -> None:
        logger, stream = _make_logger(f"t-{uuid.uuid4()}")

        logger.info("configured stripe key %s", "sk_test_" + "51ABCDEFGHIJKLMNOPQRSTUV")

        output = stream.getvalue()
        assert "51ABCDEFGHIJKLMNOPQRSTUV" not in output
        assert "[REDACTED]" in output

    def test_redacts_a_stripe_webhook_secret(self) -> None:
        logger, stream = _make_logger(f"t-{uuid.uuid4()}")

        logger.info("webhook secret %s", "whsec_abcdefghijklmnopqrstuvwxyz")

        output = stream.getvalue()
        assert "abcdefghijklmnopqrstuvwxyz" not in output
        assert "[REDACTED]" in output

    def test_redacts_a_sensitive_extra_field_by_name(self) -> None:
        logger, stream = _make_logger(f"t-{uuid.uuid4()}")

        logger.info("login attempt", extra={"access_token": "some-opaque-value"})

        payload = json.loads(stream.getvalue())
        assert payload["access_token"] == "[REDACTED]"
        assert "some-opaque-value" not in stream.getvalue()

    def test_ordinary_text_passes_through_unchanged(self) -> None:
        logger, stream = _make_logger(f"t-{uuid.uuid4()}")

        logger.info("synced 12 products for tenant %s", "Acme Shop")

        payload = json.loads(stream.getvalue())
        assert payload["message"] == "synced 12 products for tenant Acme Shop"


class TestConfigureLogging:
    def test_is_idempotent_per_service_name(self) -> None:
        root = logging.getLogger()
        original_handlers = root.handlers

        try:
            configure_logging(service_name="idempotency-test")
            first_handlers = root.handlers
            configure_logging(service_name="idempotency-test")

            assert root.handlers is first_handlers
        finally:
            root.handlers = original_handlers
