from app.db import db


class Product(db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    category = db.Column(db.String(120))
    price = db.Column(db.Float)

    inventory = db.relationship("Inventory", backref="product", lazy=True)


class Inventory(db.Model):
    __tablename__ = "inventory"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    inventory_level = db.Column(db.Integer, nullable=False)

class RestockLog(db.Model):
    __tablename__ = "restock_logs"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id"), nullable=False)
    current_inventory = db.Column(db.Integer, nullable=False)
    predicted_demand = db.Column(db.Float, nullable=False)
    reorder_point = db.Column(db.Float, nullable=True)
    target_stock = db.Column(db.Float, nullable=False)
    restock_needed = db.Column(db.Boolean, nullable=False)
    restock_quantity = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())

    product = db.relationship("Product", backref="restock_logs")