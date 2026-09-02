from pricing import discounted_price


def test_discounted_price_reduces_price():
    assert discounted_price(100, 0.2) == 80


def test_zero_discount_keeps_price():
    assert discounted_price(49.9, 0) == 49.9
