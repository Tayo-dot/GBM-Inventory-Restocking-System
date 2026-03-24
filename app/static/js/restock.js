const restockProduct = document.getElementById("restockProduct");
const restockForm = document.getElementById("restockForm");
const restockMessage = document.getElementById("restockMessage");
const resultCard = document.getElementById("resultCard");
const historyTableBody = document.getElementById("historyTableBody");
const historySearch = document.getElementById("historySearch");

let historyData = [];

function showRestockMessage(message, type = "success") {
    restockMessage.innerHTML = `<div class="alert alert-${type} py-2">${message}</div>`;
    setTimeout(() => {
        restockMessage.innerHTML = "";
    }, 3000);
}

async function loadProducts() {
    try {
        const response = await fetch("/products");
        const data = await response.json();

        restockProduct.innerHTML = `<option value="">Select product</option>`;
        data.forEach(product => {
            restockProduct.innerHTML += `
                <option value="${product.id}">
                    ${product.name} (${product.category || "No category"})
                </option>
            `;
        });
    } catch (error) {
        showRestockMessage("Failed to load products", "danger");
    }
}

async function loadHistory() {
    try {
        const response = await fetch("/restock/history");
        const data = await response.json();

        historyData = data;
        renderHistory(historyData);
    } catch (error) {
        historyTableBody.innerHTML = `
            <tr>
                <td colspan="6" class="text-center text-danger">
                    Failed to load restock history.
                </td>
            </tr>
        `;
    }
}

function renderHistory(data) {
    if (!data.length) {
        historyTableBody.innerHTML = `
            <tr>
                <td colspan="6" class="text-center text-muted">
                    No restock history available.
                </td>
            </tr>
        `;
        return;
    }

    historyTableBody.innerHTML = data.map(item => `
        <tr>
            <td>${item.product_name || "-"}</td>
            <td>${item.current_inventory}</td>
            <td>${Number(item.predicted_demand).toFixed(2)}</td>
            <td>
                ${item.restock_needed
                    ? '<span class="badge bg-danger">Yes</span>'
                    : '<span class="badge bg-success">No</span>'}
            </td>
            <td>${item.restock_quantity}</td>
            <td>${item.created_at || "-"}</td>
        </tr>
    `).join("");
}

function renderRecommendation(result) {
    resultCard.innerHTML = `
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
            <div class="col-md-6">
                <div class="mini-stat-card">
                    <div class="mini-stat-label">Predicted Demand</div>
                    <div class="mini-stat-value">${Number(result.predicted_demand).toFixed(2)}</div>
                </div>
            </div>
            <div class="col-md-6">
                <div class="mini-stat-card">
                    <div class="mini-stat-label">Reorder Point</div>
                    <div class="mini-stat-value">${Number(result.reorder_point || 0).toFixed(2)}</div>
                </div>
            </div>
            <div class="col-md-6">
                <div class="mini-stat-card">
                    <div class="mini-stat-label">Target Stock</div>
                    <div class="mini-stat-value">${Number(result.target_stock).toFixed(2)}</div>
                </div>
            </div>
            <div class="col-md-6">
                <div class="mini-stat-card">
                    <div class="mini-stat-label">Restock Quantity</div>
                    <div class="mini-stat-value">${result.restock_quantity}</div>
                </div>
            </div>
            <div class="col-12">
                <div class="status-banner ${result.restock_needed ? 'danger' : 'success'}">
                    ${result.restock_needed
                        ? 'Restock is required for this product.'
                        : 'No restock needed at the moment.'}
                </div>
            </div>
        </div>
    `;
}

restockForm.addEventListener("submit", async function (e) {
    e.preventDefault();

    const productId = parseInt(restockProduct.value);

    if (!productId) {
        showRestockMessage("Please select a product", "danger");
        return;
    }

    try {
        const response = await fetch("/restock/recommend", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({ product_id: productId })
        });

        const data = await response.json();

        if (!response.ok) {
            showRestockMessage(data.error || "Failed to generate recommendation", "danger");
            return;
        }

        renderRecommendation(data);
        showRestockMessage("Recommendation generated successfully");
        loadHistory();
    } catch (error) {
        showRestockMessage("Something went wrong while generating recommendation", "danger");
    }
});

historySearch.addEventListener("input", function () {
    const term = this.value.toLowerCase().trim();

    const filtered = historyData.filter(item =>
        (item.product_name || "").toLowerCase().includes(term) ||
        String(item.product_id).includes(term)
    );

    renderHistory(filtered);
});

loadProducts();
loadHistory();