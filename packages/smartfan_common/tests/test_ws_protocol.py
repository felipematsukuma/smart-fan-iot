import json
from pathlib import Path

import pytest

from smartfan_common.ws_protocol import CLIENT_PACKET, SERVER_CONTROL

CASES = json.loads((Path(__file__).parents[1] / "fixtures/ws.v1.json").read_text())


@pytest.mark.parametrize("case", CASES, ids=lambda case: case["name"])
def test_shared_websocket_contract(case):
    adapter = CLIENT_PACKET if case["kind"] == "client" else SERVER_CONTROL
    if case["valid"]:
        adapter.validate_json(json.dumps(case["value"]))
    else:
        with pytest.raises(ValueError):
            adapter.validate_json(json.dumps(case["value"]))
