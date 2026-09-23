const API_BASE = "/acct/v0";


function formatApiError(error) {
    if (error && typeof error === "object" && "detail" in error) {
        return typeof error.detail === "string"
            ? error.detail
            : JSON.stringify(error.detail, null, 2);
    }

    if (error instanceof Error) {
        return error.message;
    }

    return JSON.stringify(error, null, 2);
}


async function apiGet(path) {
    const response = await fetch(`${API_BASE}${path}`);

    if (!response.ok) {
        throw new Error(`GET ${path} failed`);
    }

    return await response.json();
}


async function apiPost(path, payload) {
    const response = await fetch(`${API_BASE}${path}`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
    });

    const body = await response.json().catch(() => null);

    if (!response.ok) {
        throw body || new Error(`POST ${path} failed`);
    }

    return body;
}


function fillSelect(selectId, values) {
    const select = document.getElementById(selectId);

    if (!select) {
        console.warn(`Missing select element: ${selectId}`);
        return;
    }

    select.innerHTML = "";

    for (const value of values) {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = value;
        select.appendChild(option);
    }
}


function fillCategorySelect(categories) {
    const select = document.getElementById("category_code");

    if (!select) {
        console.warn("Missing select element: category_code");
        return;
    }

    select.innerHTML = "";

    for (const category of categories) {
        const option = document.createElement("option");
        option.value = category.code;
        option.textContent = `${category.code} — ${category.label}`;
        select.appendChild(option);
    }
}


function validatePayloadClientSide(payload) {
    const errors = [];

    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
        errors.push("Payload must be one JSON object.");
        return errors;
    }

    if (!payload.entry_type) {
        errors.push("Entry type is required.");
    }

    if (!payload.category_code) {
        errors.push("Category is required.");
    }

    if (!payload.tax_scope) {
        errors.push("Tax scope is required.");
    }

    if (!payload.counterparty_name) {
        errors.push("Counterparty is required.");
    }

    if (!payload.payment_method) {
        errors.push("Payment method is required.");
    }

    if (!payload.payment_date) {
        errors.push("Payment date is required.");
    }

    if (!payload.amount_original || Number(payload.amount_original) <= 0) {
        errors.push("Amount must be greater than zero.");
    }

    if (!payload.currency_original) {
        errors.push("Currency is required.");
    }

    if (payload.has_invoice) {
        if (!payload.invoice_date) {
            errors.push("Invoice date is required when invoice exists.");
        }
    }

    return errors;
}


function normalizeToBatchPayload(rawPayload) {
    if (Array.isArray(rawPayload)) {
        return {
            entries: rawPayload,
        };
    }

    if (!rawPayload || typeof rawPayload !== "object") {
        throw new Error(
            "Pasted JSON must be one object, a list of objects, or an object with an entries list."
        );
    }

    if (Array.isArray(rawPayload.entries)) {
        return rawPayload;
    }

    return {
        entries: [rawPayload],
    };
}


function validateBatchPayloadClientSide(batchPayload) {
    const errors = [];

    if (
        !batchPayload
        || typeof batchPayload !== "object"
        || Array.isArray(batchPayload)
    ) {
        errors.push("Batch payload must be one JSON object.");
        return errors;
    }

    if (!Array.isArray(batchPayload.entries)) {
        errors.push("Batch payload must contain an entries list.");
        return errors;
    }

    if (batchPayload.entries.length === 0) {
        errors.push("Batch payload must contain at least one entry.");
        return errors;
    }

    batchPayload.entries.forEach((entry, index) => {
        const entryErrors = validatePayloadClientSide(entry);

        for (const error of entryErrors) {
            errors.push(`Entry ${index + 1}: ${error}`);
        }
    });

    return errors;
}


function exampleBatchJsonPayload() {
    return {
        entries: [
            {
                entry_type: "expense",
                category_code: "buro",
                tax_scope: "domestic",
                counterparty_name: "Batch JSON Vendor One GmbH",
                payment_method: "bank_transfer",
                payment_date: "2026-05-25",
                has_invoice: true,
                invoice_number: "BATCH-JSON-001",
                invoice_date: "2026-05-25",
                amount_original: "49.90",
                currency_original: "EUR",
                remarks: "Manual batch JSON submission, invoice 1.",
                tags: ["batch-json", "invoice"],
                source_filename: "IMG_4821.JPG",
            },
            {
                entry_type: "expense",
                category_code: "betriebsbedarf",
                tax_scope: "domestic",
                counterparty_name: "Batch JSON Vendor Two GmbH",
                payment_method: "unknown",
                payment_date: "2026-05-25",
                has_invoice: true,
                invoice_number: "BATCH-JSON-002",
                invoice_date: "2026-05-25",
                amount_original: "89.00",
                currency_original: "EUR",
                remarks: "Manual batch JSON submission, invoice 2.",
                tags: ["batch-json", "invoice"],
                source_filename: "IMG_4821.JPG",
            },
        ],
    };
}


export function initializeNewEntries({
    metadata,
    onEntriesCreated = async () => {},
} = {}) {
    const form = document.getElementById("entry-form");
    const message = document.getElementById("message");

    const jsonPasteArea = document.getElementById("json-paste-area");
    const submitJsonButton = document.getElementById("submit-json");
    const loadExampleJsonButton = document.getElementById("load-example-json");

    const contractJsonArea = document.getElementById("contract-json-area");
    const fetchContractJsonButton = document.getElementById("fetch-contract-json");
    const copyContractJsonButton = document.getElementById("copy-contract-json");

    function showMessage(text) {
        message.textContent = text;
    }

    function populateMetadata() {
        if (!metadata) {
            throw new Error("New Entries metadata is required.");
        }

        fillSelect("entry_type", metadata.entry_types);
        fillSelect("tax_scope", metadata.tax_scopes);
        fillSelect("payment_method", metadata.payment_methods);
        fillSelect("currency_original", metadata.currencies);
        fillCategorySelect(metadata.categories);
    }

    function collectPayload() {
        const data = new FormData(form);
        const hasInvoice = data.get("has_invoice") === "on";

        return {
            entry_type: data.get("entry_type"),
            category_code: data.get("category_code"),
            tax_scope: data.get("tax_scope"),
            counterparty_name: data.get("counterparty_name"),
            payment_method: data.get("payment_method"),
            payment_date: data.get("payment_date"),
            has_invoice: hasInvoice,
            invoice_number: data.get("invoice_number"),
            invoice_date: hasInvoice
                ? data.get("invoice_date") || null
                : null,
            amount_original: data.get("amount_original"),
            currency_original: data.get("currency_original"),
            remarks: data.get("remarks") || null,
            tags: String(data.get("tags") || "")
                .split(",")
                .map(x => x.trim())
                .filter(Boolean),
            source_filename: null,
        };
    }

    async function submitPayload(payload, successPrefix) {
        const errors = validatePayloadClientSide(payload);

        if (errors.length > 0) {
            showMessage(errors.join("\n"));
            return false;
        }

        try {
            const result = await apiPost("/entries", payload);

            showMessage(
                `${successPrefix}: ${result.id}; `
                + `invoice_number=${result.invoice_number ?? "missing"}`
            );

            await onEntriesCreated();

            return true;
        } catch (error) {
            showMessage(formatApiError(error));
            return false;
        }
    }

    async function submitBatchPayload(batchPayload, successPrefix) {
        const errors = validateBatchPayloadClientSide(batchPayload);

        if (errors.length > 0) {
            showMessage(errors.join("\n"));
            return false;
        }

        try {
            const result = await apiPost("/entries/batch", batchPayload);
            const count = Array.isArray(result) ? result.length : 0;

            showMessage(
                `${successPrefix}: ${count} entr${count === 1 ? "y" : "ies"} saved.`
            );

            await onEntriesCreated();

            return true;
        } catch (error) {
            showMessage(formatApiError(error));
            return false;
        }
    }

    async function fetchEntryCreateContract() {
        if (!contractJsonArea) {
            showMessage("Contract display area is missing.");
            return;
        }

        try {
            const contract = await apiGet("/entry-create-contract");
            contractJsonArea.value = JSON.stringify(contract, null, 2);
            showMessage("Current AI invoice recognition contract loaded.");
        } catch (error) {
            showMessage(JSON.stringify(error, null, 2));
        }
    }

    async function copyContractJsonToClipboard() {
        if (!contractJsonArea) {
            showMessage("Contract display area is missing.");
            return;
        }

        if (!contractJsonArea.value.trim()) {
            showMessage(
                "No contract JSON loaded yet. Click 'Fetch Current Contract' first."
            );
            return;
        }

        try {
            await navigator.clipboard.writeText(contractJsonArea.value);
            showMessage("Contract JSON copied to clipboard.");
        } catch (error) {
            contractJsonArea.select();
            document.execCommand("copy");
            showMessage("Contract JSON selected/copied using fallback.");
        }
    }

    form.addEventListener("submit", async (event) => {
        event.preventDefault();

        const payload = collectPayload();
        const saved = await submitPayload(payload, "Saved entry");

        if (saved) {
            form.reset();
        }
    });

    if (loadExampleJsonButton && jsonPasteArea) {
        loadExampleJsonButton.addEventListener("click", () => {
            jsonPasteArea.value = JSON.stringify(
                exampleBatchJsonPayload(),
                null,
                2
            );

            showMessage(
                "Batch example JSON loaded. Review and submit when ready."
            );
        });
    }

    if (submitJsonButton && jsonPasteArea) {
        submitJsonButton.addEventListener("click", async () => {
            showMessage("Submitting pasted JSON...");

            let rawPayload;

            try {
                rawPayload = JSON.parse(jsonPasteArea.value);
            } catch (error) {
                showMessage(`Invalid JSON:\n${error.message}`);
                return;
            }

            let batchPayload;

            try {
                batchPayload = normalizeToBatchPayload(rawPayload);
            } catch (error) {
                showMessage(error.message);
                return;
            }

            const saved = await submitBatchPayload(
                batchPayload,
                "Saved pasted JSON batch"
            );

            if (saved) {
                jsonPasteArea.value = "";
            }
        });
    }

    if (fetchContractJsonButton) {
        fetchContractJsonButton.addEventListener("click", async () => {
            await fetchEntryCreateContract();
        });
    }

    if (copyContractJsonButton) {
        copyContractJsonButton.addEventListener("click", async () => {
            await copyContractJsonToClipboard();
        });
    }

    populateMetadata();

    return {
        showMessage,
    };
}
