from order import order_total


def test_order_total_applies_discount_to_every_item():
    assert order_total([100, 50], 0.1) == 135
