from pricing import discounted_price


def order_total(prices: list[float], discount_rate: float = 0.0) -> float:
    return round(sum(discounted_price(price, discount_rate) for price in prices), 2)
