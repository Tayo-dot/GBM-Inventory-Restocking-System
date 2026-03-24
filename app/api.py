# app/api.py

import os
from dotenv import load_dotenv
from sympy import product

load_dotenv()

import io
from flask import send_file

from flask import Flask, request, jsonify, render_template, redirect, url_for, session, flash
import pandas as pd
import joblib
from xgboost import XGBRegressor

from app.restock import calculate_restock
from app.db import init_db, db
from app.models import User, Product, Inventory, RestockLog, SalesData
from functools import wraps

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key")
init_db(app)

MODELS_PATH = os.getenv("MODEL_PATH")
FEATURES_PATH = os.getenv("FEATURES_PATH")

model = XGBRegressor()
model.load_model(MODELS_PATH)

features = joblib.load(FEATURES_PATH)

def get_category_code(category_value):
    categories = db.session.query(SalesData.category).distinct().all()
    category_list = sorted([c[0] for c in categories if c[0] is not None])
    category_map = {cat: idx for idx, cat in enumerate(category_list)}
    return category_map.get(category_value, 0)


def build_features_from_sales_data(product_name):
    rows = (
        SalesData.query
        .filter_by(name=product_name)
        .order_by(SalesData.date.asc())
        .all()
    )

    if not rows:
        raise ValueError("No historical sales data found for this product")

    df = pd.DataFrame([{
        "date": r.date,
        "name": r.name,
        "category": r.category,
        "price": r.price,
        "inventory_level": r.inventory_level,
        "units_sold": r.units_sold
    } for r in rows])

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date").reset_index(drop=True)

    sales = df["units_sold"].astype(float)

    if len(sales) < 2:
        raise ValueError("At least 2 historical rows are needed for forecasting")

    latest_row = df.iloc[-1]
    next_date = latest_row["date"] + pd.Timedelta(days=1)

    def safe_lag(n):
        if len(sales) >= n:
            return float(sales.iloc[-n])
        return float(sales.iloc[-1])

    def safe_mean(window):
        return float(sales.tail(min(window, len(sales))).mean())

    def safe_std(window):
        std_val = sales.tail(min(window, len(sales))).std(ddof=0)
        return float(0 if pd.isna(std_val) else std_val)

    category_code = get_category_code(latest_row["category"])

    feature_row = {
        "price": float(latest_row["price"]),
        "inventory_level": int(latest_row["inventory_level"]),
        "category": category_code,

        # defaulted features for now
        "discount": 0.0,
        "region": 0,
        "weather_condition": 0,
        "holiday_promotion": 0,
        "competitor_pricing": float(latest_row["price"]),
        "seasonality": int(next_date.month),

        # lag features
        "lag_1": safe_lag(1),
        "lag_3": safe_lag(3),
        "lag_7": safe_lag(7),
        "lag_14": safe_lag(14),

        # rolling features
        "roll_mean_7": safe_mean(7),
        "roll_mean_14": safe_mean(14),
        "roll_mean_30": safe_mean(30),
        "roll_std_7": safe_std(7),
        "roll_std_14": safe_std(14),

        # date-derived features
        "month": int(next_date.month),
        "day_of_week": int(next_date.dayofweek),
        "day": int(next_date.day),
    }

    # ensure exact feature alignment with trained model
    for col in features:
        if col not in feature_row:
            feature_row[col] = 0

    X_input = pd.DataFrame([feature_row])[features]

    return X_input, {
        "history_rows": len(df),
        "latest_date": str(latest_row["date"].date()),
        "forecast_date": str(next_date.date()),
        "latest_units_sold": float(sales.iloc[-1]),
        "category_code": category_code
    }

def get_dashboard_insights():
    products = Product.query.all()

    restock_needed_count = 0
    highest_demand_product = None
    highest_demand_value = 0
    lowest_stock_product = None
    lowest_stock_value = None

    for product in products:
        stock = Inventory.query.filter_by(product_id=product.id).first()
        if not stock:
            continue

        try:
            X_input, _ = build_features_from_sales_data(product.name)
            X_input.loc[0, "inventory_level"] = stock.inventory_level

            predicted_demand = float(model.predict(X_input)[0])
            
            restock_info = calculate_restock(
                predicted_demand=predicted_demand,
                inventory_level=stock.inventory_level,
                safety_factor=0.15,
                reorder_threshold=0.7
            )

            if restock_info["restock_needed"]:
                restock_needed_count += 1

            if predicted_demand > highest_demand_value:
                highest_demand_value = predicted_demand
                highest_demand_product = product.name

            if lowest_stock_value is None or stock.inventory_level < lowest_stock_value:
                lowest_stock_value = stock.inventory_level
                lowest_stock_product = product.name

        except Exception:
            continue

    return {
        "restock_needed_count": restock_needed_count,
        "highest_demand_product": highest_demand_product,
        "highest_demand_value": highest_demand_value,
        "lowest_stock_product": lowest_stock_product,
        "lowest_stock_value": lowest_stock_value
    }

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login_page"))
        return f(*args, **kwargs)
    return wrapper

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login_page"))

        if session.get("role") != "Administrator":
            flash("Access denied: Admin only", "danger")
            return redirect(url_for("dashboard_page"))

        return f(*args, **kwargs)
    return wrapper

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

def sales_data_exists ():
    return SalesData.query.first() is not None

def admin_exists():
    return User.query.filter_by(role="Administrator").first() is not None

from functools import wraps

def admin_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "username" not in session:
            return redirect(url_for("login_page"))

        if session.get("role") != "Administrator":
            flash("Access denied: Admin only", "danger")
            return redirect(url_for("dashboard_page"))

        return f(*args, **kwargs)
    return wrapper


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
        
        if "name" not in df_out.columns and "product_id" in df_out.columns:
            product_ids = df_out["product_id"].dropna().unique().tolist()
            products = Product.query.filter(Product.id.in_(product_ids)).all()
            product_map = {p.id: p.name for p in products}
            df_out["product_name"] = df_out["product_id"].map(product_map)
        
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

@app.route("/check-admin")
def check_admin():
    admin = User.query.filter_by(role="Administrator").first()
    return {
        "admin_exists": admin is not None,
        "admin_username": admin.username if admin else None
    }
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
@login_required
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
@login_required
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
@login_required
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
@login_required
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
        return jsonify({"error": "No inventory record found for this product"}), 404

    try:
        X_input, meta = build_features_from_sales_data(product.name)

        X_input.loc[0, "inventory_level"] = stock.inventory_level

        predicted_demand = float(model.predict(X_input)[0])

        restock_info = calculate_restock(
            predicted_demand=predicted_demand,
            inventory_level=stock.inventory_level,
            safety_factor=0.15,
            reorder_threshold=0.7
        )

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
            "reorder_point": restock_info.get("reorder_point"),
            "target_stock": restock_info["target_stock"],
            "restock_needed": restock_info["restock_needed"],
            "restock_quantity": restock_info["restock_quantity"],
            "history_rows": meta["history_rows"],
            "latest_date": meta["latest_date"],
            "forecast_date": meta["forecast_date"]
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
    
@app.route("/restock/history", methods=["GET"])
@login_required
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
@login_required
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
@admin_required
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
@admin_required
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
@login_required
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

@app.route("/")
def home():
    if "username" in session:
        if not admin_exists():
            return redirect(url_for("setup_admin"))
        return redirect(url_for("login_page"))

    if not sales_data_exists() and session.get("role") == "Administrator":
        return redirect(url_for("import_page"))

    return redirect(url_for("dashboard_page"))

@app.route("/login", methods=["GET", "POST"])
def login_page():
    if not admin_exists():
        return redirect(url_for("setup_admin"))

    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "").strip()

        user = User.query.filter_by(username=username).first()

        if user is None or user.password != password:
            flash("Invalid username or password", "danger")
            return render_template("login.html")

        session["username"] = user.username
        session["role"] = user.role
        session["user_id"] = user.id

        flash("Login successful", "success")
        if not sales_data_exists() and user.role == "Administrator":
            return redirect(url_for("import_page"))
        
        return redirect(url_for("dashboard_page"))

    return render_template("login.html")

@app.route("/dashboard-page")
@login_required
def dashboard_page():
    total_products = Product.query.count()
    total_stock_items = Inventory.query.count()
    total_restock_logs = RestockLog.query.count()
    total_sales_rows = SalesData.query.count()

    insights = get_dashboard_insights()

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
            "created_at": log.created_at.strftime("%Y-%m-%d %H:%M") if log.created_at else None
        })
        restock_items = RestockLog.query.filter_by(restock_needed=True).all()
        
        restock_products = []
        for item in restock_items:
            if item.product:
                restock_products.append(item.product.name)

    return render_template(
        "dashboard.html",
        username=session.get("username"),
        role=session.get("role"),
        total_products=total_products,
        total_stock_items=total_stock_items,
        total_restock_logs=total_restock_logs,
        total_sales_rows=total_sales_rows,
        restock_needed_count=insights["restock_needed_count"],
        highest_demand_product=insights["highest_demand_product"],
        highest_demand_value=insights["highest_demand_value"],
        lowest_stock_product=insights["lowest_stock_product"],
        lowest_stock_value=insights["lowest_stock_value"],
        recent_activity=recent_activity,
        restock_products=restock_products
    )

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out", "info")
    return redirect(url_for("login_page"))

@app.route("/users", methods=["POST"])
@admin_required
def create_user():
    data = request.get_json(silent=True)

    if data is None:
        return jsonify({"error": "Request body must be JSON"}), 400

    username = data.get("username", "").strip().lower()
    password = data.get("password", "").strip()
    role = data.get("role", "").strip()

    if not username or not password or not role:
        return jsonify({"error": "username, password, and role are required"}), 400

    existing_user = User.query.filter_by(username=username).first()
    if existing_user:
        return jsonify({"error": "Username already exists"}), 400

    user = User(
        username=username,
        password=password,
        role=role
    )

    db.session.add(user)
    db.session.commit()

    return jsonify({
        "message": "User created successfully",
        "user_id": user.id,
        "username": user.username,
        "role": user.role
    }), 201

@app.route("/users", methods=["GET"])
def get_users():
    users = User.query.all()

    result = []
    for user in users:
        result.append({
            "id": user.id,
            "username": user.username,
            "role": user.role
        })

    return jsonify(result), 200

@app.route("/admin/create-user", methods=["GET", "POST"])
@admin_required
def create_user_page():
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "").strip()
        role = request.form.get("role", "").strip()

        if not username or not password or not role:
            flash("All fields are required", "danger")
            return render_template("create_user.html")

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            flash("Username already exists", "danger")
            return render_template("create_user.html")

        user = User(
            username=username,
            password=password,
            role=role
        )

        db.session.add(user)
        db.session.commit()

        flash("User created successfully", "success")
        return redirect(url_for("create_user_page"))

    return render_template("create_user.html")

@app.route("/products-page")
@login_required
def products_page():
    return render_template(
        "products.html",
        username=session.get("username"),
        role=session.get("role")
    )

@app.route("/inventory-page")
@login_required
def inventory_page():
    return render_template(
        "inventory.html",
        username=session.get("username"),
        role=session.get("role")
)

@app.route("/restock-page")
@login_required
def restock_page():
    return render_template(
        "restock.html",
        username=session.get("username"),
        role=session.get("role")
    )

@app.route("/batch-page")
@login_required
def batch_page():
    return render_template(
        "batch.html",
        username=session.get("username"),
        role=session.get("role")
    )

@app.route("/all-routes")
def all_routes():
    return {
        "routes": sorted([str(rule) + "->" + rule.endpoint for rule in app.url_map.iter_rules()])
    }

@app.route("/predict-csv-preview", methods=["POST"])
@login_required
def predict_csv_preview():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded. Use form-data key: 'file'"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    try:
        df_upload = pd.read_csv(file)

        if "inventory_level" not in df_upload.columns:
            return jsonify({"error": "CSV must contain 'inventory_level' column"}), 400

        X_batch = df_upload.reindex(columns=features, fill_value=0)
        preds = model.predict(X_batch).astype(float)

        df_out = df_upload.copy()
        if "name" not in df_out.columns and "product_id" in df_out.columns:
            product_ids = df_out["product_id"].dropna().unique().tolist()
            products = Product.query.filter(Product.id.in_(product_ids)).all()
            product_map = {p.id: p.name for p in products}
            
            df_out["product_name"] = df_out["product_id"].map(product_map)

        df_out["predicted_demand"] = preds

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

        preview_data = df_out.to_dict(orient="records")

        return jsonify({
            "message": "Preview generated successfully",
            "rows": preview_data
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/import-data", methods=["POST"])
@admin_required
def import_data():
    if "file" not in request.files:
        return jsonify({"error": "No file uploaded. Use form-data key: 'file'"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    try:
        df = pd.read_csv(file)

        db.session.query(SalesData).delete()

        required_columns = {"date", "name", "category", "price", "inventory_level", "units_sold"}
        missing = required_columns - set(df.columns)

        if missing:
            return jsonify({
                "error": f"Missing required columns: {', '.join(sorted(missing))}"
            }), 400

        # Parse dates safely
        df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date

        if df["date"].isnull().any():
            return jsonify({"error": "One or more date values are invalid"}), 400

        imported_sales_rows = 0
        new_products = 0
        updated_products = 0

        for _, row in df.iterrows():
            name = str(row["name"]).strip()
            category = str(row["category"]).strip()
            price = float(row["price"])
            inventory_level = int(row["inventory_level"])
            units_sold = int(row["units_sold"])
            date_value = row["date"]

            if not name:
                continue

            sales_row = SalesData(
                date=date_value,
                name=name,
                category=category,
                price=price,
                inventory_level=inventory_level,
                units_sold=units_sold
            )
            db.session.add(sales_row)
            imported_sales_rows += 1

            product = Product.query.filter_by(name=name).first()

            if product:
                product.category = category
                product.price = price
                updated_products += 1
            else:
                product = Product(
                    name=name,
                    category=category,
                    price=price
                )
                db.session.add(product)
                db.session.flush()
                new_products += 1

            # Update inventory to latest imported value
            stock = Inventory.query.filter_by(product_id=product.id).first()

            if stock:
                stock.inventory_level = inventory_level
            else:
                stock = Inventory(
                    product_id=product.id,
                    inventory_level=inventory_level
                )
                db.session.add(stock)

        db.session.commit()

        return jsonify({
            "message": "Dataset uploaded successfully",
            "sales_rows_imported": imported_sales_rows,
            "new_products": new_products,
            "updated_products": updated_products
        }), 200

    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 500
    
@app.route("/import-page")
@admin_required
def import_page():
    return render_template(
        "import_data.html",
        username=session.get("username"),
        role=session.get("role")
    )

@app.route("/forecast-demand", methods=["POST"])
@login_required
def forecast_demand():
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
        return jsonify({"error": "No inventory record found for this product"}), 404

    try:
        X_input, meta = build_features_from_sales_data(product.name)

        # force current inventory from inventory table
        X_input.loc[0, "inventory_level"] = stock.inventory_level

        predicted_demand = float(model.predict(X_input)[0])

        restock_info = calculate_restock(
            predicted_demand=predicted_demand,
            inventory_level=stock.inventory_level,
            safety_factor=0.15,
            reorder_threshold=0.7
        )

        return jsonify({
            "product_id": product.id,
            "product_name": product.name,
            "current_inventory": stock.inventory_level,
            "predicted_demand": predicted_demand,
            "reorder_point": restock_info.get("reorder_point"),
            "target_stock": restock_info["target_stock"],
            "restock_needed": restock_info["restock_needed"],
            "restock_quantity": restock_info["restock_quantity"],
            "history_rows": meta["history_rows"],
            "latest_date": meta["latest_date"],
            "forecast_date": meta["forecast_date"]
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
    
@app.route("/forecast-page")
@login_required
def forecast_page():
    return render_template(
        "forecast.html",
        username=session.get("username"),
        role=session.get("role")
    )

@app.route("/setup-admin", methods=["GET", "POST"])
def setup_admin():
    if admin_exists():
        return redirect(url_for("login_page"))
    if request.method == "POST":
        username = request.form.get("username", "").strip().lower()
        password = request.form.get("password", "").strip()
        confirm_password = request.form.get("confirm_password", "").strip()
        
        if not username or not password or not confirm_password:
            flash("All fields are required", "danger")
            return render_template("setup_admin.html")
        
        if password != confirm_password:
            flash("Passwords do not match", "danger")
            return render_template("setup_admin.html")
        
        existing_user = User.query.filter_by(username=username).first()
        
        if existing_user:
            flash("Username already exists", "danger")
            return render_template("setup_admin.html")
        
        admin_user = User(
            username=username,
            password=password,
            role="Administrator"
            )
        
        db.session.add(admin_user)
        db.session.commit()
        
        flash("Administrator account created successfully. Please log in.", "success")
        return redirect(url_for("login_page"))
    
    return render_template("setup_admin.html")

if __name__ == "__main__":
    app.run(debug=True)

