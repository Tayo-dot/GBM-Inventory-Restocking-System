# app/api.py

import os
from dotenv import load_dotenv

load_dotenv()

import io
from flask import send_file

from flask import Flask, request, jsonify
import pandas as pd
import joblib
from xgboost import XGBRegressor

from app.restock import calculate_restock
from app.db import init_db, db
from app.models import Product, Inventory, RestockLog

app = Flask(__name__)
init_db(app)

MODELS_PATH = os.getenv("MODEL_PATH")
FEATURES_PATH = os.getenv("FEATURES_PATH")

model = XGBRegressor()
model.load_model(MODELS_PATH)

features = joblib.load(FEATURES_PATH)


def make_input_row(payload: dict) -> pd.DataFrame:
    """
    Converts incoming JSON payload into a 1-row DataFrame
    with the exact columns the model expects.
    Missing columns are filled with 0.
    Extra columns are ignored.
    """
    row = pd.DataFrame([payload])
    row = row.reindex(columns=features, fill_value=0)
    return row


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200

@app.route("/routes", methods=["GET"])
def routes():
    return jsonify(sorted([str(r) for r in app.url_map.iter_rules()])), 200


@app.route("/predict", methods=["POST"])
def predict():
    # Ensure JSON
    payload = request.get_json(silent=True)
    if payload is None:
        return jsonify({"error": "Request body must be JSON"}), 400

    # inventory_level is needed for restocking logic
    if "inventory_level" not in payload:
        return jsonify({"error": "Missing required field: inventory_level"}), 400

    try:
        X_input = make_input_row(payload)
        predicted_demand = float(model.predict(X_input)[0])

        inv = float(payload.get("inventory_level", 0))

        restock_info = calculate_restock(
            predicted_demand=predicted_demand,
            inventory_level=inv,
            safety_factor=0.15,
            reorder_threshold=0.7
        )

        result = {
            "predicted_demand": predicted_demand,
            "inventory_level": inv,
            **restock_info
        }

        return jsonify(result), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    

@app.route("/predict-csv", methods=["POST"])
def predict_csv_download():
    """
    Upload a CSV file and download a CSV with predictions + restock decisions.
    Expected: multipart/form-data with key 'file'
    """
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded. Use form-data key: 'file'"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    try:
        # Read uploaded CSV
        df_upload = pd.read_csv(file)

        # Must have inventory_level for restocking logic
        if "inventory_level" not in df_upload.columns:
            return jsonify({"error": "CSV must contain 'inventory_level' column"}), 400

        # Align features for the model (missing -> 0, extra ignored)
        X_batch = df_upload.reindex(columns=features, fill_value=0)

        # Predict
        preds = model.predict(X_batch).astype(float)

        # Add prediction column
        df_out = df_upload.copy()
        df_out["predicted_demand"] = preds

        # Apply restock logic row-by-row
        restock_needed_list = []
        reorder_point_list = []
        target_stock_list = []
        restock_qty_list = []

        for i, pred in enumerate(preds):
            inv = float(df_upload.loc[i, "inventory_level"])

            restock_info = calculate_restock(
                predicted_demand=float(pred),
                inventory_level=inv,
                safety_factor=0.15,
                reorder_threshold=0.7
            )

            restock_needed_list.append(restock_info["restock_needed"])
            reorder_point_list.append(restock_info["reorder_point"])
            target_stock_list.append(restock_info["target_stock"])
            restock_qty_list.append(restock_info["restock_quantity"])

        df_out["restock_needed"] = restock_needed_list
        df_out["reorder_point"] = reorder_point_list
        df_out["target_stock"] = target_stock_list
        df_out["restock_quantity"] = restock_qty_list

        # Convert output to CSV in-memory
        buffer = io.StringIO()
        df_out.to_csv(buffer, index=False)
        buffer.seek(0)

        # Send as downloadable file
        return send_file(
            io.BytesIO(buffer.getvalue().encode("utf-8")),
            mimetype="text/csv",
            as_attachment=True,
            download_name="restock_predictions.csv"
        )

    except Exception as e:
        return jsonify({"error": str(e)}), 500

with app.app_context():
    db.create_all()
    print("Tables created successfully")


@app.route("/products", methods=["POST"])
def add_product():
    data = request.json

    name = data.get("name")
    category = data.get("category")
    price = data.get("price")

    if not name:
        return jsonify({"error": "Product name is required"}), 400

    product = Product(
        name=name,
        category=category,
        price=price
    )

    db.session.add(product)
    db.session.commit()

    return jsonify({
        "message": "Product added successfully",
        "product_id": product.id
    }), 201

@app.route("/products", methods=["GET"])
def get_products():
    products = Product.query.all()

    result = []

    for p in products:
        result.append({
            "id": p.id,
            "name": p.name,
            "category": p.category,
            "price": p.price
        })

    return jsonify(result), 200

@app.route("/stock/update", methods=["POST"])
def update_stock():
    data = request.json

    product_id = data.get("product_id")
    inventory_level = data.get("inventory_level")

    if product_id is None or inventory_level is None:
        return jsonify({
            "error": "product_id and inventory_level are required"
        }), 400

    product = Product.query.get(product_id)
    if not product:
        return jsonify({"error": "Product not found"}), 404

    stock = Inventory.query.filter_by(product_id=product_id).first()

    if stock:
        stock.inventory_level = inventory_level
    else:
        stock = Inventory(
            product_id=product_id,
            inventory_level=inventory_level
        )
        db.session.add(stock)

    db.session.commit()

    return jsonify({
        "message": "Stock updated successfully",
        "product_id": product_id,
        "inventory_level": inventory_level
    }), 200

@app.route("/stock", methods=["GET"])
def get_stock():
    stock_items = Inventory.query.all()

    result = []

    for item in stock_items:
        result.append({
            "product_id": item.product_id,
            "product_name": item.product.name,
            "inventory_level": item.inventory_level
        })

    return jsonify(result), 200

@app.route("/restock/recommend", methods=["POST"])
def recommend_restock():
    payload = request.get_json(silent=True)

    if payload is None:
        return jsonify({"error": "Request body must be JSON"}), 400

    product_id = payload.get("product_id")

    if product_id is None:
        return jsonify({"error": "product_id is required"}), 400

    product = Product.query.get(product_id)

    if not product:
        return jsonify({"error": "Product not found"}), 404

    stock = Inventory.query.filter_by(product_id=product_id).first()

    if not stock:
        return jsonify({"error": "No inventory record found"}), 404

    try:
        payload["inventory_level"] = stock.inventory_level

        X_input = make_input_row(payload)

        predicted_demand = float(model.predict(X_input)[0])

        restock_info = calculate_restock(
            predicted_demand=predicted_demand,
            inventory_level=stock.inventory_level
        )

        # SAVE RESTOCK HISTORY
        log = RestockLog(
            product_id=product.id,
            current_inventory=stock.inventory_level,
            predicted_demand=predicted_demand,
            reorder_point=restock_info.get("reorder_point"),
            target_stock=restock_info["target_stock"],
            restock_needed=restock_info["restock_needed"],
            restock_quantity=restock_info["restock_quantity"]
        )

        db.session.add(log)
        db.session.commit()

        return jsonify({
            "product_id": product.id,
            "product_name": product.name,
            "current_inventory": stock.inventory_level,
            "predicted_demand": predicted_demand,
            **restock_info
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route("/restock/history", methods=["GET"])
def get_restock_history():
    logs = RestockLog.query.order_by(RestockLog.created_at.desc()).all()

    result = []
    for log in logs:
        result.append({
            "id": log.id,
            "product_id": log.product_id,
            "product_name": log.product.name if log.product else None,
            "current_inventory": log.current_inventory,
            "predicted_demand": log.predicted_demand,
            "reorder_point": log.reorder_point,
            "target_stock": log.target_stock,
            "restock_needed": log.restock_needed,
            "restock_quantity": log.restock_quantity,
            "created_at": log.created_at.isoformat() if log.created_at else None
        })

    return jsonify(result), 200

@app.route("/products/<int:product_id>", methods=["GET"])
def get_product(product_id):
    product = Product.query.get(product_id)

    if not product:
        return jsonify({"error": "Product not found"}), 404

    stock = Inventory.query.filter_by(product_id=product_id).first()

    return jsonify({
        "id": product.id,
        "name": product.name,
        "category": product.category,
        "price": product.price,
        "inventory_level": stock.inventory_level if stock else None
    }), 200

@app.route("/products/<int:product_id>", methods=["PUT"])
def update_product(product_id):
    product = Product.query.get(product_id)

    if not product:
        return jsonify({"error": "Product not found"}), 404

    data = request.get_json(silent=True)

    if data is None:
        return jsonify({"error": "Request body must be JSON"}), 400

    product.name = data.get("name", product.name)
    product.category = data.get("category", product.category)
    product.price = data.get("price", product.price)

    db.session.commit()

    return jsonify({
        "message": "Product updated successfully",
        "product": {
            "id": product.id,
            "name": product.name,
            "category": product.category,
            "price": product.price
        }
    }), 200

@app.route("/products/<int:product_id>", methods=["DELETE"])
def delete_product(product_id):
    product = Product.query.get(product_id)

    if not product:
        return jsonify({"error": "Product not found"}), 404

    stock = Inventory.query.filter_by(product_id=product_id).first()
    if stock:
        db.session.delete(stock)

    logs = RestockLog.query.filter_by(product_id=product_id).all()
    for log in logs:
        db.session.delete(log)

    db.session.delete(product)
    db.session.commit()

    return jsonify({
        "message": "Product deleted successfully"
    }), 200

@app.route("/dashboard/summary", methods=["GET"])
def dashboard_summary():
    total_products = Product.query.count()
    total_stock_items = Inventory.query.count()
    total_restock_logs = RestockLog.query.count()

    low_stock_items = Inventory.query.filter(Inventory.inventory_level < 20).count()
    restock_needed_items = RestockLog.query.filter_by(restock_needed=True).count()

    recent_logs = RestockLog.query.order_by(RestockLog.created_at.desc()).limit(5).all()

    recent_activity = []
    for log in recent_logs:
        recent_activity.append({
            "product_id": log.product_id,
            "product_name": log.product.name if log.product else None,
            "predicted_demand": log.predicted_demand,
            "current_inventory": log.current_inventory,
            "restock_needed": log.restock_needed,
            "restock_quantity": log.restock_quantity,
            "created_at": log.created_at.isoformat() if log.created_at else None
        })

    return jsonify({
        "total_products": total_products,
        "total_stock_items": total_stock_items,
        "total_restock_logs": total_restock_logs,
        "low_stock_items": low_stock_items,
        "restock_needed_items": restock_needed_items,
        "recent_activity": recent_activity
    }), 200

if __name__ == "__main__":
    app.run(debug=True)

