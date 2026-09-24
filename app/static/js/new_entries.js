import {t} from "./i18n/i18n.js";

const API_BASE = "/acct/v0";


function formatApiError(error) {
    if (error instanceof Error && error.renderMessage) {
        return error.renderMessage();
    }

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


function requestError(method, path) {
    const renderMessage = () => t("newEntries.status.requestFailed")
        .replace(/\{(method|path)\}/g, (_, key) => key === "method" ? method : path);
    return Object.assign(new Error(renderMessage()), {renderMessage});
}


async function apiGet(path) {
    const response = await fetch(`${API_BASE}${path}`);

    if (!response.ok) {
        throw requestError("GET", path);
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
        throw body || requestError("POST", path);
    }

    return body;
}


function fillSelect(selectId, values, translationPrefix = null) {
    const select = document.getElementById(selectId);

    if (!select) {
        console.warn(`Missing select element: ${selectId}`);
        return;
    }

    const selectedIndex = select.selectedIndex;
    const selectedValue = select.value;
    const hadOptions = select.options.length > 0;
    select.innerHTML = "";

    for (const value of values) {
        const option = document.createElement("option");
        option.value = value;
        option.textContent = translationPrefix
            ? t(`${translationPrefix}.${value}`, value)
            : value;
        select.appendChild(option);
    }

    // Preserve the draft, including an explicitly cleared selection.
    if (hadOptions) {
        if (selectedIndex === -1) select.selectedIndex = -1;
        else select.value = selectedValue;
    }
}


function fillCategorySelect(categories) {
    const select = document.getElementById("category_code");

    if (!select) {
        console.warn("Missing select element: category_code");
        return;
    }

    const selectedIndex = select.selectedIndex;
    const selectedValue = select.value;
    const hadOptions = select.options.length > 0;
    select.innerHTML = "";

    for (const category of categories) {
        const option = document.createElement("option");
        option.value = category.code;
        option.textContent = `${category.code} — ${t(`metadata.category.${category.code}`, category.label)}`;
        select.appendChild(option);
    }

    // Preserve the draft, including an explicitly cleared selection.
    if (hadOptions) {
        if (selectedIndex === -1) select.selectedIndex = -1;
        else select.value = selectedValue;
    }
}


function validatePayloadClientSide(payload) {
    const errors = [];

    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
        errors.push(t("newEntries.validation.payloadObject"));
        return errors;
    }

    if (!payload.entry_type) {
        errors.push(t("newEntries.validation.entryTypeRequired"));
    }

    if (!payload.category_code) {
        errors.push(t("newEntries.validation.categoryRequired"));
    }

    if (!payload.tax_scope) {
        errors.push(t("newEntries.validation.taxScopeRequired"));
    }

    if (!payload.counterparty_name) {
        errors.push(t("newEntries.validation.counterpartyRequired"));
    }

    if (!payload.payment_method) {
        errors.push(t("newEntries.validation.paymentMethodRequired"));
    }

    if (!payload.payment_date) {
        errors.push(t("newEntries.validation.paymentDateRequired"));
    }

    if (!payload.amount_original || Number(payload.amount_original) <= 0) {
        errors.push(t("newEntries.validation.amountPositive"));
    }

    if (!payload.currency_original) {
        errors.push(t("newEntries.validation.currencyRequired"));
    }

    if (payload.has_invoice) {
        if (!payload.invoice_date) {
            errors.push(t("newEntries.validation.invoiceDateRequired"));
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
        const renderMessage = () => t("newEntries.validation.pastedShape");
        throw Object.assign(new Error(renderMessage()), {renderMessage});
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
        errors.push(t("newEntries.validation.batchObject"));
        return errors;
    }

    if (!Array.isArray(batchPayload.entries)) {
        errors.push(t("newEntries.validation.batchEntries"));
        return errors;
    }

    if (batchPayload.entries.length === 0) {
        errors.push(t("newEntries.validation.batchNotEmpty"));
        return errors;
    }

    batchPayload.entries.forEach((entry, index) => {
        const entryErrors = validatePayloadClientSide(entry);

        for (const error of entryErrors) {
            errors.push(`${t("newEntries.validation.entry")} ${index + 1}: ${error}`);
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

    let renderMessage = null;
    function showMessage(text) {
        // Keep a renderer for frontend messages and raw text for external data.
        renderMessage = typeof text === "function" ? text : () => text;
        message.textContent = renderMessage();
    }

    function populateMetadata({includeCurrency = true} = {}) {
        if (!metadata) {
            const renderMessage = () => t("newEntries.status.metadataRequired");
            throw Object.assign(new Error(renderMessage()), {renderMessage});
        }

        fillSelect("entry_type", metadata.entry_types, "metadata.entryType");
        fillSelect("tax_scope", metadata.tax_scopes, "metadata.taxScope");
        fillSelect("payment_method", metadata.payment_methods, "metadata.paymentMethod");
        if (includeCurrency) fillSelect("currency_original", metadata.currencies);
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
            showMessage(() => validatePayloadClientSide(payload).join("\n"));
            return false;
        }

        try {
            const result = await apiPost("/entries", payload);

            showMessage(
                () => `${t(successPrefix)}: ${result.id}; `
                + `${t("newEntries.field.invoiceNumber")}=${result.invoice_number ?? t("newEntries.status.missing")}`
            );

            await onEntriesCreated();

            return true;
        } catch (error) {
            showMessage(() => formatApiError(error));
            return false;
        }
    }

    async function submitBatchPayload(batchPayload, successPrefix) {
        const errors = validateBatchPayloadClientSide(batchPayload);

        if (errors.length > 0) {
            showMessage(() => validateBatchPayloadClientSide(batchPayload).join("\n"));
            return false;
        }

        try {
            const result = await apiPost("/entries/batch", batchPayload);
            const count = Array.isArray(result) ? result.length : 0;

            showMessage(
                () => `${t(successPrefix)}: ${count} ${t(count === 1
                    ? "newEntries.status.entrySaved" : "newEntries.status.entriesSaved")}`
            );

            await onEntriesCreated();

            return true;
        } catch (error) {
            showMessage(() => formatApiError(error));
            return false;
        }
    }

    async function fetchEntryCreateContract() {
        if (!contractJsonArea) {
            showMessage(() => t("newEntries.status.contractAreaMissing"));
            return;
        }

        try {
            const contract = await apiGet("/entry-create-contract");
            contractJsonArea.value = JSON.stringify(contract, null, 2);
            showMessage(() => t("newEntries.status.contractLoaded"));
        } catch (error) {
            showMessage(() => error instanceof Error && error.renderMessage
                ? error.renderMessage() : JSON.stringify(error, null, 2));
        }
    }

    async function copyContractJsonToClipboard() {
        if (!contractJsonArea) {
            showMessage(() => t("newEntries.status.contractAreaMissing"));
            return;
        }

        if (!contractJsonArea.value.trim()) {
            showMessage(
                () => t("newEntries.status.noContract")
            );
            return;
        }

        try {
            await navigator.clipboard.writeText(contractJsonArea.value);
            showMessage(() => t("newEntries.status.contractCopied"));
        } catch (error) {
            contractJsonArea.select();
            document.execCommand("copy");
            showMessage(() => t("newEntries.status.contractCopyFallback"));
        }
    }

    form.addEventListener("submit", async (event) => {
        event.preventDefault();

        const payload = collectPayload();
        const saved = await submitPayload(payload, "newEntries.status.savedEntry");

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
                () => t("newEntries.status.exampleLoaded")
            );
        });
    }

    if (submitJsonButton && jsonPasteArea) {
        submitJsonButton.addEventListener("click", async () => {
            showMessage(() => t("newEntries.status.submittingJson"));

            let rawPayload;

            try {
                rawPayload = JSON.parse(jsonPasteArea.value);
            } catch (error) {
                showMessage(() => `${t("newEntries.validation.invalidJson")}\n${error.message}`);
                return;
            }

            let batchPayload;

            try {
                batchPayload = normalizeToBatchPayload(rawPayload);
            } catch (error) {
                showMessage(() => formatApiError(error));
                return;
            }

            const saved = await submitBatchPayload(
                batchPayload,
                "newEntries.status.savedBatch"
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

    document.addEventListener("accounting:language-changed", () => {
        populateMetadata({includeCurrency: false});
        if (renderMessage) message.textContent = renderMessage();
    });

    return {
        showMessage,
    };
}
