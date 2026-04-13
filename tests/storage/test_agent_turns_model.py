def test_agent_turn_model_columns():
    from agentlabx.providers.storage.models import AgentTurn

    cols = {c.name for c in AgentTurn.__table__.columns}
    assert cols >= {
        "id", "session_id", "turn_id", "parent_turn_id",
        "agent", "stage", "kind", "payload_json",
        "system_prompt_hash", "tokens_in", "tokens_out",
        "cost_usd", "is_mock", "ts",
    }


def test_agent_turn_indexes():
    from agentlabx.providers.storage.models import AgentTurn

    idx_names = {idx.name for idx in AgentTurn.__table__.indexes}
    assert "ix_agent_turns_session_agent_ts" in idx_names
    assert "ix_agent_turns_session_stage_ts" in idx_names
