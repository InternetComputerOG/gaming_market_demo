import pytest
from typing import Any, Dict, List
from typing_extensions import TypedDict

from app.engine.state import (
    BinaryState,
    EngineState,
    deserialize_state,
    get_binary,
    get_p_no,
    get_p_yes,
    init_state,
    serialize_state,
    update_subsidies,
)
from app.config import get_default_engine_params


@pytest.fixture
def default_params() -> Dict[str, Any]:
    return get_default_engine_params()


@pytest.fixture
def initial_state(default_params: Dict[str, Any]) -> EngineState:
    return init_state(default_params)


def test_init_state_defaults(initial_state: EngineState, default_params: Dict[str, Any]):
    n = default_params["n_outcomes"]
    z = default_params["z"]
    q0 = default_params["q0"]
    subsidy_per = z / n

    assert len(initial_state["binaries"]) == n
    assert initial_state["pre_sum_yes"] == pytest.approx(n * (q0 / subsidy_per))

    for i, binary in enumerate(initial_state["binaries"]):
        assert binary["outcome_i"] == i
        assert binary["V"] == 0.0
        assert binary["subsidy"] == pytest.approx(subsidy_per)
        assert binary["L"] == pytest.approx(subsidy_per)
        assert binary["q_yes"] == q0
        assert binary["q_no"] == q0
        assert binary["virtual_yes"] == 0.0
        assert binary["seigniorage"] == 0.0
        assert binary["active"] is True
        assert binary["lob_pools"] == {"YES": {"buy": {}, "sell": {}}, "NO": {"buy": {}, "sell": {}}}

        # Initial prices
        assert get_p_yes(binary) == pytest.approx(0.5)
        assert get_p_no(binary) == pytest.approx(0.5)

        # Invariants
        assert binary["subsidy"] > 0
        assert binary["L"] == pytest.approx(binary["V"] + binary["subsidy"])
        assert binary["q_yes"] + binary["q_no"] < 2 * binary["L"]
        assert binary["q_yes"] + binary["virtual_yes"] < binary["L"]


@pytest.mark.parametrize("n_outcomes", [3, 10])
def test_init_state_varying_n(n_outcomes: int, default_params: Dict[str, Any]):
    params = {**default_params, "n_outcomes": n_outcomes}
    state = init_state(params)
    assert len(state["binaries"]) == n_outcomes
    subsidy_per = params["z"] / n_outcomes
    assert state["pre_sum_yes"] == pytest.approx(n_outcomes * (params["q0"] / subsidy_per))


def test_serialize_deserialize_round_trip(initial_state: EngineState):
    # Add sample lob_pools with int keys
    binary = initial_state["binaries"][0]
    binary["lob_pools"]["YES"]["buy"][10] = {"volume": 100.0, "shares": {"user1": 50.0, "user2": 50.0}}
    binary["lob_pools"]["NO"]["sell"][20] = {"volume": 200.0, "shares": {}}

    serialized = serialize_state(initial_state)
    assert isinstance(serialized, Dict)
    assert "binaries" in serialized
    assert "pre_sum_yes" in serialized

    # Check stringified keys
    assert "10" in serialized["binaries"][0]["lob_pools"]["YES"]["buy"]
    assert "20" in serialized["binaries"][0]["lob_pools"]["NO"]["sell"]

    deserialized = deserialize_state(serialized)
    assert deserialized == initial_state
    # Check int keys restored
    assert 10 in deserialized["binaries"][0]["lob_pools"]["YES"]["buy"]
    assert 20 in deserialized["binaries"][0]["lob_pools"]["NO"]["sell"]


def test_get_binary_valid(initial_state: EngineState):
    for i in range(len(initial_state["binaries"])):
        binary = get_binary(initial_state, i)
        assert binary["outcome_i"] == i


def test_get_binary_invalid(initial_state: EngineState):
    with pytest.raises(ValueError, match="Binary not found for outcome"):
        get_binary(initial_state, -1)
    with pytest.raises(ValueError, match="Binary not found for outcome"):
        get_binary(initial_state, len(initial_state["binaries"]))


def test_get_p_yes_no(initial_state: EngineState):
    binary = initial_state["binaries"][0]
    assert get_p_yes(binary) == pytest.approx((binary["q_yes"] + binary["virtual_yes"]) / binary["L"])
    assert get_p_no(binary) == pytest.approx(binary["q_no"] / binary["L"])

    # Test with virtual_yes >0
    binary["virtual_yes"] = 100.0
    assert get_p_yes(binary) == pytest.approx((binary["q_yes"] + 100.0) / binary["L"])


@pytest.mark.parametrize("v_multiplier", [0.0, 0.5, 1.5])  # V from 0 to beyond phase-out
def test_update_subsidies(initial_state: EngineState, default_params: Dict[str, Any], v_multiplier: float):
    z_per = default_params["z"] / default_params["n_outcomes"]
    gamma = default_params["gamma"]

    for binary in initial_state["binaries"]:
        binary["V"] = v_multiplier * (z_per / gamma)

    update_subsidies(initial_state, default_params)

    for binary in initial_state["binaries"]:
        expected_subsidy = max(0.0, z_per - gamma * binary["V"])
        assert binary["subsidy"] == pytest.approx(expected_subsidy)
        assert binary["L"] == pytest.approx(binary["V"] + expected_subsidy)
        assert binary["L"] > 0
        if v_multiplier >= 1.0:
            assert binary["subsidy"] == 0.0
        else:
            assert binary["subsidy"] > 0


def test_update_subsidies_invariants(initial_state: EngineState, default_params: Dict[str, Any]):
    # Set some virtual_yes and check invariants hold post-update
    initial_state["binaries"][0]["virtual_yes"] = 50.0
    initial_state["binaries"][0]["V"] = 10000.0  # Force phase-out

    update_subsidies(initial_state, default_params)

    binary = initial_state["binaries"][0]
    assert binary["q_yes"] + binary["virtual_yes"] < binary["L"]
    assert binary["q_no"] < binary["L"]


def test_active_flags(initial_state: EngineState):
    # Indirectly test via get_binary, but ensure init sets active=True
    for binary in initial_state["binaries"]:
        assert binary["active"] is True

    # Manual set inactive, check p computations still work (though not used in inactive)
    initial_state["binaries"][0]["active"] = False
    binary = get_binary(initial_state, 0)
    assert get_p_yes(binary) > 0