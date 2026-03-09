# app/restock.py


def calculate_restock(
    predicted_demand: float,
    inventory_level: float,
    safety_factor: float = 0.15,
    reorder_threshold: float = 0.9,
    min_order: int = 0,
    max_order: int | None = None
) -> dict:
    """
    Converts predicted demand into a restocking decision.

    Parameters
    ----------
    predicted_demand : float
        Model-predicted units expected to be sold.
    inventory_level : float
        Current stock on hand.
    safety_factor : float
        Extra buffer stock percentage (e.g., 0.15 = 15%).
    reorder_threshold : float
        Trigger point: restock if inventory <= predicted_demand * reorder_threshold.
    min_order : int
        Minimum order quantity if restocking happens (optional).
    max_order : int | None
        Maximum order cap (optional).

    Returns
    -------
    dict with:
      - restock_needed (bool)
      - reorder_point (float)
      - target_stock (float)
      - restock_quantity (int)
    """

    # Guard against negative values
    predicted_demand = max(0.0, float(predicted_demand))
    inventory_level = max(0.0, float(inventory_level))

    # Reorder point (WHEN to restock)
    reorder_point = predicted_demand * float(reorder_threshold)

    if inventory_level > reorder_point:
        return {
            "restock_needed": False,
            "reorder_point": float(reorder_point),
            "target_stock": float(predicted_demand * (1 + safety_factor)),
            "restock_quantity": 0
        }

    # Target stock (HOW MUCH stock we want to have)
    target_stock = predicted_demand * (1 + float(safety_factor))

    # Restock quantity
    restock_qty = target_stock - inventory_level
    restock_qty = max(0, int(round(restock_qty)))

    # Apply min/max business rules (optional)
    if restock_qty > 0 and min_order:
        restock_qty = max(restock_qty, int(min_order))

    if max_order is not None:
        restock_qty = min(restock_qty, int(max_order))

    return {
        "restock_needed": restock_qty > 0,
        "reorder_point": float(reorder_point),
        "target_stock": float(target_stock),
        "restock_quantity": int(restock_qty)
    }