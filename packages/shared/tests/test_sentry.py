from cp_shared.sentry import scrub_event


class TestScrubEvent:
    def test_redacts_a_sensitive_field_in_request_headers(self) -> None:
        event = {
            "request": {
                "headers": {"Authorization": "Bearer abc.def-123_xyz", "Accept": "application/json"}
            }
        }

        scrubbed = scrub_event(event, {})

        assert scrubbed["request"]["headers"]["Authorization"] == "[REDACTED]"
        assert scrubbed["request"]["headers"]["Accept"] == "application/json"

    def test_redacts_a_sensitive_field_in_extra(self) -> None:
        event = {"extra": {"access_token": "some-real-token", "tenant_id": "abc-123"}}

        scrubbed = scrub_event(event, {})

        assert scrubbed["extra"]["access_token"] == "[REDACTED]"
        assert scrubbed["extra"]["tenant_id"] == "abc-123"

    def test_redacts_a_secret_shaped_string_inside_a_stack_frame_variable(self) -> None:
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl"
        event = {
            "exception": {
                "values": [
                    {
                        "stacktrace": {
                            "frames": [{"vars": {"raw_header": f"Authorization: Bearer {jwt}"}}]
                        }
                    }
                ]
            }
        }

        scrubbed = scrub_event(event, {})

        frame_vars = scrubbed["exception"]["values"][0]["stacktrace"]["frames"][0]["vars"]
        assert jwt not in frame_vars["raw_header"]
        assert "[REDACTED]" in frame_vars["raw_header"]

    def test_leaves_ordinary_metadata_untouched(self) -> None:
        event = {"event_id": "abc123", "platform": "python", "level": "error"}

        scrubbed = scrub_event(event, {})

        assert scrubbed == event

    def test_redacts_within_a_list(self) -> None:
        event = {"tags": [{"secret": "shhh"}, {"name": "ok"}]}

        scrubbed = scrub_event(event, {})

        assert scrubbed["tags"][0]["secret"] == "[REDACTED]"
        assert scrubbed["tags"][1]["name"] == "ok"
