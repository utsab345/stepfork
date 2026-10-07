from stepfork.trace import event_json_schema, manifest_json_schema, trace_json_schema


def test_event_json_schema_contains_discriminator_and_variants() -> None:
    schema = event_json_schema()

    assert schema["discriminator"]["propertyName"] == "type"
    mapping = schema["discriminator"]["mapping"]
    for event_type in [
        "run_start",
        "llm_request",
        "llm_response",
        "tool_call",
        "tool_result",
        "state_change",
        "error",
        "run_end",
    ]:
        assert event_type in mapping

    assert len(schema["oneOf"]) == 8


def test_manifest_json_schema_contains_contract_fields() -> None:
    schema = manifest_json_schema()
    properties = schema["properties"]

    for field in [
        "schema_version",
        "run_id",
        "agent_name",
        "created_at",
        "status",
    ]:
        assert field in properties


def test_trace_json_schema_can_be_generated() -> None:
    schema = trace_json_schema()

    assert schema["title"] == "Trace"
    assert "events" in schema["properties"]
