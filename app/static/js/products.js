const tableBody = document.getElementById("productsTableBody");
const searchInput = document.getElementById("searchInput");

const productForm = document.getElementById("productForm");
const productIdInput = document.getElementById("productId");
const nameInput = document.getElementById("name");
const categoryInput = document.getElementById("category");
const priceInput = document.getElementById("price");
const productMessage = document.getElementById("productMessage");
const formTitle = document.getElementById("formTitle");
const submitBtn = document.getElementById("submitBtn");
const cancelEditBtn = document.getElementById("cancelEditBtn");

let allProducts = [];

async function fetchProducts() {
    try {
        const response = await fetch("/products");
        const data = await response.json();
        allProducts = data;
        renderProducts(allProducts);
    } catch (error) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="${window.USER_ROLE === 'Administrator' ? 5 : 4}" class="text-center text-danger">
                    Failed to load products.
                </td>
            </tr>
        `;
    }
}

function renderProducts(products) {
    if (!products.length) {
        tableBody.innerHTML = `
            <tr>
                <td colspan="${window.USER_ROLE === 'Administrator' ? 5 : 4}" class="text-center text-muted">
                    No products found.
                </td>
            </tr>
        `;
        return;
    }

    tableBody.innerHTML = products.map(product => `
        <tr>
            <td>${product.id}</td>
            <td>${product.name}</td>
            <td>${product.category || "-"}</td>
            <td>₦${Number(product.price || 0).toLocaleString()}</td>
            ${window.USER_ROLE === "Administrator" ? `
            <td>
                <button class="btn btn-sm btn-outline-primary me-2" onclick="editProduct(${product.id})">Edit</button>
                <button class="btn btn-sm btn-outline-danger" onclick="deleteProduct(${product.id})">Delete</button>
            </td>` : ""}
        </tr>
    `).join("");
}

function showMessage(message, type = "success") {
    productMessage.innerHTML = `<div class="alert alert-${type} py-2">${message}</div>`;
    setTimeout(() => {
        productMessage.innerHTML = "";
    }, 3000);
}

if (productForm) {
    productForm.addEventListener("submit", async function (e) {
        e.preventDefault();

        const productId = productIdInput.value;
        const payload = {
            name: nameInput.value.trim(),
            category: categoryInput.value.trim(),
            price: parseFloat(priceInput.value || 0)
        };

        try {
            let response;

            if (productId) {
                response = await fetch(`/products/${productId}`, {
                    method: "PUT",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify(payload)
                });
            } else {
                response = await fetch("/products", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify(payload)
                });
            }

            const data = await response.json();

            if (!response.ok) {
                showMessage(data.error || "Operation failed", "danger");
                return;
            }

            showMessage(productId ? "Product updated successfully" : "Product added successfully");
            resetForm();
            fetchProducts();
        } catch (error) {
            showMessage("Something went wrong", "danger");
        }
    });
}

function resetForm() {
    if (!productForm) return;

    productIdInput.value = "";
    nameInput.value = "";
    categoryInput.value = "";
    priceInput.value = "";
    formTitle.textContent = "Add Product";
    submitBtn.textContent = "Add Product";
    cancelEditBtn.classList.add("d-none");
}

if (cancelEditBtn) {
    cancelEditBtn.addEventListener("click", resetForm);
}

async function editProduct(productId) {
    try {
        const response = await fetch(`/products/${productId}`);
        const product = await response.json();

        if (!response.ok) {
            showMessage(product.error || "Failed to fetch product", "danger");
            return;
        }

        productIdInput.value = product.id;
        nameInput.value = product.name;
        categoryInput.value = product.category || "";
        priceInput.value = product.price || "";

        formTitle.textContent = "Edit Product";
        submitBtn.textContent = "Update Product";
        cancelEditBtn.classList.remove("d-none");

        window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (error) {
        showMessage("Failed to load product for editing", "danger");
    }
}

async function deleteProduct(productId) {
    const confirmed = confirm("Are you sure you want to delete this product?");
    if (!confirmed) return;

    try {
        const response = await fetch(`/products/${productId}`, {
            method: "DELETE"
        });

        const data = await response.json();

        if (!response.ok) {
            showMessage(data.error || "Delete failed", "danger");
            return;
        }

        showMessage("Product deleted successfully");
        fetchProducts();
    } catch (error) {
        showMessage("Something went wrong while deleting", "danger");
    }
}

if (searchInput) {
    searchInput.addEventListener("input", function () {
        const term = this.value.toLowerCase().trim();

        const filtered = allProducts.filter(product =>
            product.name.toLowerCase().includes(term) ||
            (product.category || "").toLowerCase().includes(term)
        );

        renderProducts(filtered);
    });
}

fetchProducts();