from backend.agent.llm import extract_json


def test_extract_json_from_fenced_block():
    text = 'Thoughts...\n```json\n{"a":1,"b":"x"}\n```\n'
    out = extract_json(text)
    assert out == {"a": 1, "b": "x"}


def test_extract_json_from_trailing_object():
    text = 'plan result: {"picked":[1,2], "ok": true}'
    out = extract_json(text)
    assert out["picked"] == [1, 2]
    assert out["ok"] is True
