const importForm = document.getElementById("importForm");
const importFile = document.getElementById("importFile");
const importMessage = document.getElementById("importMessage");

console.log("IMPORT JS LOADED");
console.log("importForm:", importForm);

function showImportMessage(message, type = "success") {
    importMessage.innerHTML = `<div class="alert alert-${type} py-2">${message}</div>`;
}

if (importForm) {
    importForm.addEventListener("submit", async function (e) {
        e.preventDefault();

        const file = importFile.files[0];

        if (!file) {
            showImportMessage("Please choose a CSV file.", "danger");
            return;
        }

        const formData = new FormData();
        formData.append("file", file);

        try {
            showImportMessage("Uploading dataset, please wait...", "info");

            const response = await fetch("/import-data", {
                method: "POST",
                body: formData
            });

            const data = await response.json();

            if (!response.ok) {
                showImportMessage(data.error || "Import failed.", "danger");
                return;
            }

            showImportMessage(
                `✔ Dataset uploaded successfully.<br>
                <b>${data.sales_rows_imported}</b> historical sales rows imported<br>
                <b>${data.new_products}</b> new products added<br>
                <b>${data.updated_products}</b> products updated`,
                "success"
            );

            importForm.reset();
        } catch (error) {
            console.error(error);
            showImportMessage("Something went wrong during import.", "danger");
        }
    });
}