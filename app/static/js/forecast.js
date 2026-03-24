const forecastForm = document.getElementById("forecastForm");
const forecastProduct = document.getElementById("forecastProduct");
const forecastMessage = document.getElementById("forecastMessage");
const forecastResult = document.getElementById("forecastResult");

function showForecastMessage(message, type = "success") {
    forecastMessage.innerHTML = `<div class="alert alert-${type} py-2">${message}</div>`;
    setTimeout(() => {
        forecastMessage.innerHTML = "";
    }, 3000);
}

async function loadForecastProducts() {
    try {
        const response = await fetch("/products");
        const data = await response.json();

        forecastProduct.innerHTML = `<option value="">Select product</option>`;
        data.forEach(product => {
            forecastProduct.innerHTML += `
                <option value="${product.id}">
                    ${product.name} (${product.category || "No category"})
                </option>
            `;
        });
    } catch (error) {
        showForecastMessage("Failed to load products", "danger");
    }
}

function renderForecastResult(result) {
    forecastResult.innerHTML = `
        <div class="row g-3">
            <div class="col-md-6">
                <div class="mini-stat-card">
                    <div class="mini-stat-label">Product</div>
                    <div class="mini-stat-value small-value">${result.product_name}</div>
                </div>
            </div>

            <div class="col-md-6">
                <div class="mini-stat-card">
                    <div class="mini-stat-label">Current Inventory</div>
                    <div class="mini-stat-value">${result.current_inventory}</div>
                </div>
            </div>

            <div class="col-12">
                <div class="forecast-highlight">
                    <div class="forecast-label">Predicted Demand</div>
                    <div class="forecast-value">${Number(result.predicted_demand).toFixed(2)}</div>
                </div>
            </div>

            <div class="col-md-6">
                <div class="mini-stat-card">
                    <div class="mini-stat-label">Latest Historical Date</div>
                    <div class="mini-stat-value small-value">${result.latest_date}</div>
                </div>
            </div>

            <div class="col-md-6">
                <div class="mini-stat-card">
                    <div class="mini-stat-label">Forecast Date</div>
                    <div class="mini-stat-value small-value">${result.forecast_date}</div>
                </div>
            </div>

            <div class="col-md-6">
                <div class="mini-stat-card">
                    <div class="mini-stat-label">History Rows Used</div>
                    <div class="mini-stat-value">${result.history_rows}</div>
                </div>
            </div>

            <div class="col-md-6">
                <div class="mini-stat-card">
                    <div class="mini-stat-label">Restock Decision</div>
                    <div class="mini-stat-value small-value">
                        ${result.restock_needed ? "Restock Needed" : "Stock OK"}
                    </div>
                </div>
            </div>
        </div>
    `;
}

forecastForm.addEventListener("submit", async function (e) {
    e.preventDefault();

    const productId = parseInt(forecastProduct.value);

    if (!productId) {
        showForecastMessage("Please select a product", "danger");
        return;
    }

    try {
        const response = await fetch("/forecast-demand", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ product_id: productId })
        });

        const data = await response.json();

        if (!response.ok) {
            showForecastMessage(data.error || "Failed to forecast demand", "danger");
            return;
        }

        renderForecastResult(data);
        showForecastMessage("Demand forecast generated successfully", "success");
    } catch (error) {
        showForecastMessage("Something went wrong while forecasting demand", "danger");
    }
});

loadForecastProducts();