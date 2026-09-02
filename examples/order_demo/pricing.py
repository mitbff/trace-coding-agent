def discounted_price(price: float, discount_rate: float) -> float:
    """Return the price after applying a decimal discount rate."""
    return round(price + price * discount_rate, 2)
