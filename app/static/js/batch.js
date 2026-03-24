const batchForm = document.getElementById("batchForm");
const csvFileInput = document.getElementById("csvFile");
const batchMessage = document.getElementById("batchMessage");
const downloadBtn = document.getElementById("downloadBtn");
const batchResultsBody = document.getElementById("batchResultsBody");
const batchSearch = document.getElementById("batchSearch");

let previewRows = [];
let currentFile = null;

function showBatchMessage(message, type = "success") {
    batchMessage.innerHTML = `<div class="alert alert-${type} py-2">${message}</div>`;
}

function renderBatchResults(rows) {
    if (!rows.length) {
        batchResultsBody.innerHTML = `
            <tr>
                <td colspan="6" class="text-center text-muted">
                    No matching results found.
                </td>
            </tr>
        `;
        return;
    }

    batchResultsBody.innerHTML = rows.map(row => {
        const restockNeeded = row.restock_needed;

        return `
        <tr class="${restockNeeded ? 'restock-alert' : 'restock-ok'}">
            <td>${row.name ?? row.product_name ?? "-"}</td>
            <td>${row.inventory_level ?? "-"}</td>
            <td>${Number(row.predicted_demand || 0).toFixed(2)}</td>
            <td>
                ${restockNeeded
                    ? '<span class="badge bg-danger">Restock Needed</span>'
                    : '<span class="badge bg-success">Stock OK</span>'}
            </td>
            <td>${row.restock_quantity ?? 0}</td>
            <td>${Number(row.target_stock || 0).toFixed(2)}</td>
        </tr>
        `;
    }).join("");
}

batchForm.addEventListener("submit", async function (e) {
    e.preventDefault();

    const file = csvFileInput.files[0];

    if (!file) {
        showBatchMessage("Please choose a CSV file.", "danger");
        return;
    }

    currentFile = file;

    const formData = new FormData();
    formData.append("file", file);

    try {
        showBatchMessage("Processing file, please wait...", "info");

        const response = await fetch("/predict-csv-preview", {
            method: "POST",
            body: formData
        });

        const data = await response.json();

        if (!response.ok) {
            showBatchMessage(data.error || "Failed to process CSV file.", "danger");
            return;
        }

        previewRows = data.rows || [];
        renderBatchResults(previewRows);

        showBatchMessage("Preview generated successfully.", "success");
        downloadBtn.classList.remove("d-none");

    } catch (error) {
        showBatchMessage("Something went wrong while uploading the file.", "danger");
        console.error(error);
    }
});

downloadBtn.addEventListener("click", async function () {
    if (!currentFile) {
        showBatchMessage("No file available for download processing.", "danger");
        return;
    }

    const formData = new FormData();
    formData.append("file", currentFile);

    try {
        const response = await fetch("/predict-csv", {
            method: "POST",
            body: formData
        });

        if (!response.ok) {
            showBatchMessage("Failed to download processed CSV.", "danger");
            return;
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);

        const a = document.createElement("a");
        a.href = url;
        a.download = "restock_predictions.csv";
        document.body.appendChild(a);
        a.click();
        a.remove();

        window.URL.revokeObjectURL(url);

        showBatchMessage("Processed CSV downloaded successfully.", "success");
    } catch (error) {
        showBatchMessage("Something went wrong while downloading the file.", "danger");
        console.error(error);
    }
});

batchSearch.addEventListener("input", function () {
    const term = this.value.toLowerCase().trim();

    const filtered = previewRows.filter(row =>
        String(row.name ?? row.product_name ?? "").toLowerCase().includes(term) ||
        String(row.inventory_level ?? "").toLowerCase().includes(term) ||
        String(row.restock_quantity ?? "").toLowerCase().includes(term) ||
        String(row.predicted_demand ?? "").toLowerCase().includes(term) ||
        String(row.target_stock ?? "").toLowerCase().includes(term) ||
        String(row.restock_needed ?? "").toLowerCase().includes(term)
    );

    renderBatchResults(filtered);
});