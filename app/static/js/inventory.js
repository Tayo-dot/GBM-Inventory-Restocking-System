const productSelect = document.getElementById("productSelect");
const inventoryLevelInput = document.getElementById("inventoryLevel");
const stockForm = document.getElementById("stockForm");
const stockMessage = document.getElementById("stockMessage");
const inventoryTableBody = document.getElementById("inventoryTableBody");
const inventorySearch = document.getElementById("inventorySearch");

let inventoryData = [];
let productsData = [];

async function fetchProductsForDropdown() {
    try {
        const response = await fetch("/products");
        const data = await response.json();

        productsData = data;

        productSelect.innerHTML = `<option value="">Select product</option>`;

        data.forEach(product => {
            productSelect.innerHTML += `
                <option value="${product.id}">
                    ${product.name} (${product.category || "No category"})
                </option>
            `;
        });
    } catch (error) {
        showMessage("Failed to load products", "danger");
    }
}

async function fetchInventory() {
    try {
        const response = await fetch("/stock");
        const data = await response.json();

        inventoryData = data;
        renderInventory(inventoryData);
    } catch (error) {
        inventoryTableBody.innerHTML = `
            <tr>
                <td colspan="3" class="text-center text-danger">
                    Failed to load inventory.
                </td>
            </tr>
        `;
    }
}

function renderInventory(data) {
    if (!data.length) {
        inventoryTableBody.innerHTML = `
            <tr>
                <td colspan="3" class="text-center text-muted">
                    No inventory records found.
                </td>
            </tr>
        `;
        return;
    }

    inventoryTableBody.innerHTML = data.map(item => `
        <tr>
            <td>${item.product_id}</td>
            <td>${item.product_name}</td>
            <td>${item.inventory_level}</td>
        </tr>
    `).join("");
}

function showMessage(message, type = "success") {
    stockMessage.innerHTML = `<div class="alert alert-${type} py-2">${message}</div>`;
    setTimeout(() => {
        stockMessage.innerHTML = "";
    }, 3000);
}

stockForm.addEventListener("submit", async function (e) {
    e.preventDefault();

    const payload = {
        product_id: parseInt(productSelect.value),
        inventory_level: parseInt(inventoryLevelInput.value)
    };

    if (!payload.product_id || isNaN(payload.inventory_level)) {
        showMessage("Please select a product and enter inventory level", "danger");
        return;
    }

    try {
        const response = await fetch("/stock/update", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (!response.ok) {
            showMessage(data.error || "Failed to update stock", "danger");
            return;
        }

        showMessage("Stock updated successfully");
        stockForm.reset();
        fetchInventory();
    } catch (error) {
        showMessage("Something went wrong while updating stock", "danger");
    }
});

inventorySearch.addEventListener("input", function () {
    const term = this.value.toLowerCase().trim();

    const filtered = inventoryData.filter(item =>
        item.product_name.toLowerCase().includes(term) ||
        String(item.product_id).includes(term)
    );

    renderInventory(filtered);
});

fetchProductsForDropdown();
fetchInventory();