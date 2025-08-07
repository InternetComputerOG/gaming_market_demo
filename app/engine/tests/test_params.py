import pytest
import numpy as np
from typing_extensions import TypedDict
from app.engine.params import Params, get_default_params, validate_params, solve_quadratic

def test_get_default_params():
    params = get_default_params()
    assert isinstance(params, dict)
    assert params['alpha'] == 1.0
    assert params['beta'] == 1.0
    assert params['trade_fee'] == 0.01
    assert params['liquidity_initial'] == 1000.0 / 3  # Now dynamically loaded from config: z/n_outcomes
    assert params['min_liquidity'] == 0.0
    assert params['max_imbalance_ratio'] == 0.99  # Now dynamically loaded from config: p_max
    assert params['min_auto_fill'] == 0.1  # Now dynamically loaded from config: af_cap_frac
    assert params['resolution_prob'] == 0.5  # Legacy parameter, no direct mapping
    # Ensure all keys present per TypedDict
    expected_keys = {'alpha', 'beta', 'trade_fee', 'liquidity_initial', 'min_liquidity',
                     'max_imbalance_ratio', 'min_auto_fill', 'resolution_prob'}
    assert set(params.keys()) == expected_keys

def test_validate_params_valid():
    params: Params = get_default_params()
    try:
        validate_params(params)
    except ValueError:
        pytest.fail("Valid params raised ValueError")

def test_validate_params_invalid_alpha():
    params: Params = get_default_params()
    params['alpha'] = 0.0
    with pytest.raises(ValueError, match="alpha must be >0"):
        validate_params(params)
    
    params['alpha'] = -1.0
    with pytest.raises(ValueError, match="alpha must be >0"):
        validate_params(params)

def test_validate_params_invalid_beta():
    params: Params = get_default_params()
    params['beta'] = 0.0
    with pytest.raises(ValueError, match="beta must be >0"):
        validate_params(params)

def test_validate_params_invalid_trade_fee():
    params: Params = get_default_params()
    params['trade_fee'] = -0.01
    with pytest.raises(ValueError, match="trade_fee must be in \\[0,1\\)"):
        validate_params(params)
    
    params['trade_fee'] = 1.0
    with pytest.raises(ValueError, match="trade_fee must be in \\[0,1\\)"):
        validate_params(params)

def test_validate_params_invalid_liquidity_initial():
    params: Params = get_default_params()
    params['liquidity_initial'] = 0.0
    with pytest.raises(ValueError, match="liquidity_initial must be >0"):
        validate_params(params)

# Additional validation tests for other fields based on TDD ranges
def test_validate_params_invalid_max_imbalance_ratio():
    params: Params = get_default_params()
    params['max_imbalance_ratio'] = 1.0
    with pytest.raises(ValueError, match="max_imbalance_ratio must be <1"):
        validate_params(params)

def test_solve_quadratic_simple_positive_roots():
    # Quadratic: x^2 - 3x + 2 = 0, roots 1 and 2, min positive=1
    result = solve_quadratic(1.0, -3.0, 2.0)
    assert np.allclose(result, 1.0)

def test_solve_quadratic_tdd_like():
    # Example coeffs from TDD derivation, assume positive discriminant
    # coeff_a = f_i=0.8, coeff_b=10-0.8*5=6, coeff_c=-5*10 -20=-70
    # disc=36 + 4*0.8*70=36+224=260, sqrt~16.12, X=(-6+16.12)/1.6~6.325
    result = solve_quadratic(0.8, 6.0, -70.0)
    expected = (-6 + np.sqrt(260)) / 1.6
    assert np.allclose(result, expected)
    assert result > 0

def test_solve_quadratic_single_positive_root():
    # x^2 - 2x +1=0, root 1 (double)
    result = solve_quadratic(1.0, -2.0, 1.0)
    assert np.allclose(result, 1.0)

def test_solve_quadratic_no_positive_roots():
    # x^2 + 2x +1=0, root -1 (double)
    with pytest.raises(ValueError, match="No positive root found"):
        solve_quadratic(1.0, 2.0, 1.0)

def test_solve_quadratic_negative_discriminant():
    # x^2 + x +1=0, disc=-3<0
    with pytest.raises(ValueError, match="No real roots"):
        solve_quadratic(1.0, 1.0, 1.0)

def test_solve_quadratic_zero_a():
    # Degenerate, but per TDD a=f_i>0 always
    with pytest.raises(ValueError, match="a must be >0"):
        solve_quadratic(0.0, 1.0, 1.0)

def test_solve_quadratic_min_positive_selection():
    # Roots -1 and 2, select 2 (only positive)
    result = solve_quadratic(1.0, -1.0, -2.0)
    assert np.allclose(result, 2.0)

    # Roots 3 and 1, select 1
    result = solve_quadratic(1.0, -4.0, 3.0)
    assert np.allclose(result, 1.0)