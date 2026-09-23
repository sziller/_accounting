// AR archive and persisted invoice data; independent of AP entry selection.
import {initializeTableSort, reorderTableRows} from "./table_sort.js";
import {initializeArPayments} from "./ar_payments.js";
import {initializeArAllocations} from "./ar_allocations.js";
import {initializeArRecognition} from "./ar_recognition.js";
export function initializeArPanel() {
    if (!document.getElementById("ar-invoice-import-panel")) return;
    const directory = document.getElementById("ar-invoice-directory-name");
    const refreshButton = document.getElementById("refresh-ar-invoice-files");
    const processButton = document.getElementById("process-ar-invoice-directory");
    const fileCount = document.getElementById("ar-invoice-file-count");
    const fileList = document.getElementById("ar-invoice-file-list");
    const dbCount = document.getElementById("ar-invoice-db-count");
    const dbBody = document.getElementById("ar-invoice-db-body");
    const status = document.getElementById("ar-invoice-import-status");
    const form = document.getElementById("ar-invoice-detail-form");
    const editorStatus = document.getElementById("ar-invoice-editor-status");
    const unlock = document.getElementById("unlock-ar-invoice-edit");
    const save = document.getElementById("save-ar-invoice-edit");
    const cancel = document.getElementById("cancel-ar-invoice-edit");
    const previous = document.getElementById("previous-ar-invoice");
    const next = document.getElementById("next-ar-invoice");
    const normalize = document.getElementById("normalize-ar-invoices");
    const processEntry = document.getElementById("process-ar-entry");
    const conversionStatus = document.getElementById("ar-invoice-conversion-status");
    const editableFields = ["invoice_number", "invoice_date", "payment_date", "due_date", "customer_name",
        "customer_reference", "currency_original", "currency_common", "net_amount", "vat_amount", "amount_original",
        "pdf_filename", "pdf_sha256", "remarks"];
    const derivedFields = ["paid_amount", "outstanding_amount", "payment_status", "created_at", "updated_at", "amount_common"];
    const nullableFields = new Set(["payment_date", "due_date", "customer_reference", "net_amount", "vat_amount",
        "pdf_filename", "pdf_sha256", "remarks"]);
    let invoices = [];
    let selectedInvoice = null;
    let editing = false;
    let busy = false;
    let allocations;
    const refreshRecognition = initializeArRecognition();
    const sortInvoices = initializeTableSort(dbBody.closest("table"), [
        ["invoice_number"], ["invoice_date"], ["customer_name"], ["currency_original"],
        ["amount_original", "decimal"], ["paid_amount", "decimal"], ["outstanding_amount", "decimal"],
        ["payment_status"], ["pdf_filename"],
        ["currency_common"], ["amount_common", "decimal"],
    ], () => {
        invoices = sortInvoices(invoices);
        reorderTableRows(dbBody, invoices, "invoiceId");
        updateSelection();
    });

    function updateSelection() {
        const index = invoices.findIndex(invoice => invoice.id === selectedInvoice?.id);
        for (const row of dbBody.querySelectorAll("[data-invoice-id]")) {
            const selected = selectedInvoice !== null && row.dataset.invoiceId === String(selectedInvoice.id);
            row.classList.toggle("is-selected", selected);
            row.setAttribute("aria-selected", String(selected));
        }
        for (const button of fileList.querySelectorAll("[data-pdf-filename]")) {
            button.classList.toggle("is-selected", button.dataset.pdfFilename === selectedInvoice?.pdf_filename);
        }
        previous.disabled = busy || index <= 0;
        next.disabled = busy || index < 0 || index >= invoices.length - 1;
        unlock.disabled = busy || !selectedInvoice || editing;
        save.disabled = busy || !selectedInvoice || !editing;
        cancel.disabled = busy || !selectedInvoice || !editing;
        normalize.disabled = busy || editing;
        processEntry.disabled = busy || editing || !selectedInvoice;
        allocations?.setInvoice(selectedInvoice);
        for (const key of editableFields) document.getElementById(`ar-invoice-${key}`).disabled = busy || !editing;
    }

    function selectInvoice(invoice) {
        // API data is JSON; copying it this way also supports older browsers.
        selectedInvoice = invoice ? JSON.parse(JSON.stringify(invoice)) : null;
        editing = false;
        for (const key of [...editableFields, ...derivedFields]) {
            document.getElementById(`ar-invoice-${key}`).value = selectedInvoice?.[key] ?? "";
        }
        editorStatus.textContent = invoice ? `Loaded invoice: ${invoice.invoice_number}` : "Select an outgoing invoice.";
        void refreshRecognition(selectedInvoice);
        updateSelection();
    }

    function setBusy(value) {
        busy = value;
        refreshButton.disabled = value;
        processButton.disabled = value;
        updateSelection();
    }

    function fileState(message) {
        const item = document.createElement("li");
        item.className = "muted";
        item.textContent = message;
        fileList.replaceChildren(item);
    }

    function dbState(message) {
        const row = document.createElement("tr");
        const cell = document.createElement("td");
        cell.colSpan = 11;
        cell.className = "muted";
        cell.textContent = message;
        row.appendChild(cell);
        dbBody.replaceChildren(row);
    }

    function errorText(detail) {
        return typeof detail === "string" ? detail : JSON.stringify(detail);
    }

    async function request(path, method = "GET", payload) {
        const options = {method, cache: "no-store"};
        if (payload !== undefined) {
            options.headers = {"Content-Type": "application/json"};
            options.body = JSON.stringify(payload);
        }
        const response = await fetch(`/acct/v0/outgoing-invoices${path}`, options);
        const body = await response.json();
        if (!response.ok) throw new Error(errorText(body.detail ?? `HTTP ${response.status}`));
        return body;
    }

    async function loadArSourceFiles() {
        fileCount.textContent = "Loading…";
        fileState("Loading PDFs…");
        try {
            const payload = await request("/source-files");
            if (!Array.isArray(payload.files) || !payload.files.every(name => typeof name === "string")) {
                throw new Error("Invalid PDF list response");
            }
            directory.textContent = payload.directory;
            fileCount.textContent = `${payload.files.length} PDF${payload.files.length === 1 ? "" : "s"}`;
            if (!payload.files.length) return fileState("No PDFs found.");
            fileList.replaceChildren(...payload.files.map(filename => {
                const item = document.createElement("li");
                const button = document.createElement("button");
                button.type = "button";
                button.className = "ar-pdf-button";
                button.dataset.pdfFilename = filename;
                button.textContent = filename;
                button.addEventListener("click", () => {
                    if (busy) return;
                    const matches = invoices.filter(invoice => invoice.pdf_filename === filename);
                    if (matches.length === 1) selectInvoice(matches[0]);
                    else editorStatus.textContent = matches.length ? "Multiple invoices reference this PDF; select a table row."
                        : "No persisted invoice matches this PDF. The current selection is unchanged.";
                });
                item.appendChild(button);
                return item;
            }));
            updateSelection();
        } catch {
            fileCount.textContent = "Unavailable";
            fileState("Could not load source PDFs.");
        }
    }

    async function loadOutgoingInvoices(preserveDraft = false) {
        dbCount.textContent = "Loading…";
        dbState("Loading outgoing invoices…");
        try {
            const response = await request("");
            if (!Array.isArray(response)) throw new Error("Invalid outgoing-invoice list response");
            invoices = sortInvoices(response);
            dbCount.textContent = `${invoices.length} record${invoices.length === 1 ? "" : "s"}`;
            if (!invoices.length) {
                selectInvoice(null);
                dbState("No outgoing invoices stored yet.");
                return true;
            }
            dbBody.replaceChildren(...invoices.map(invoice => {
                const row = document.createElement("tr");
                row.dataset.invoiceId = invoice.id;
                row.tabIndex = 0;
                row.addEventListener("click", () => { if (!busy) selectInvoice(invoice); });
                row.addEventListener("keydown", event => {
                    if (!busy && ["Enter", " "].includes(event.key)) {
                        event.preventDefault();
                        selectInvoice(invoice);
                    }
                });
                for (const key of ["invoice_number", "invoice_date", "customer_name", "currency_original",
                    "amount_original", "paid_amount", "outstanding_amount", "payment_status", "pdf_filename",
                    "currency_common", "amount_common"]) {
                    const cell = document.createElement("td");
                    cell.textContent = invoice[key] ?? (key === "amount_common" ? "pending" : "—");
                    row.appendChild(cell);
                }
                return row;
            }));
            const updated = invoices.find(invoice => invoice.id === selectedInvoice?.id) ?? null;
            if (preserveDraft && editing && updated) {
                selectedInvoice = updated;
                void refreshRecognition(updated);
                for (const key of derivedFields) document.getElementById(`ar-invoice-${key}`).value = updated[key] ?? '';
                updateSelection();
            } else selectInvoice(updated);
            return true;
        } catch {
            dbCount.textContent = "Unavailable";
            dbState("Could not load outgoing invoices.");
            return false;
        }
    }

    async function saveArInvoice() {
        if (busy || !editing || !selectedInvoice || !form.reportValidity()) return;
        const payload = {};
        for (const key of editableFields) {
            const value = document.getElementById(`ar-invoice-${key}`).value;
            if (value !== String(selectedInvoice[key] ?? "")) {
                payload[key] = value === "" && nullableFields.has(key) ? null : value;
            }
        }
        if (!Object.keys(payload).length) {
            selectInvoice(selectedInvoice);
            editorStatus.textContent = "No changes to save.";
            return;
        }
        setBusy(true);
        editorStatus.textContent = "Saving…";
        try {
            const updated = await request(`/${encodeURIComponent(selectedInvoice.id)}`, "PATCH", payload);
            selectInvoice(updated);
            const refreshed = await loadOutgoingInvoices();
            editorStatus.textContent = refreshed ? `Saved invoice: ${updated.invoice_number}`
                : "Invoice saved, but the list could not be refreshed. Click Refresh to retry.";
        } catch (error) {
            editorStatus.textContent = `Could not save invoice: ${error.message}`;
        } finally {
            setBusy(false);
        }
    }

    unlock.addEventListener("click", () => { editing = true; updateSelection(); });
    cancel.addEventListener("click", () => {
        selectInvoice(selectedInvoice);
        editorStatus.textContent = "Edit cancelled.";
    });
    save.addEventListener("click", saveArInvoice);
    form.addEventListener("submit", event => { event.preventDefault(); void saveArInvoice(); });
    for (const [button, offset] of [[previous, -1], [next, 1]]) {
        button.addEventListener("click", () => {
            const index = invoices.findIndex(invoice => invoice.id === selectedInvoice?.id);
            if (!busy && index >= 0 && invoices[index + offset]) selectInvoice(invoices[index + offset]);
        });
    }

    async function reloadDatasets() {
        await Promise.all([loadArSourceFiles(), loadOutgoingInvoices()]);
    }

    async function refreshArPanel() {
        if (busy) return;
        setBusy(true);
        try { await reloadDatasets(); }
        finally { setBusy(false); }
    }

    async function processArInvoiceDirectory() {
        if (busy) return;
        setBusy(true);
        status.textContent = "Processing…";
        processButton.textContent = "Processing…";
        try {
            const report = await request("/process-directory", "POST");
            if (!Array.isArray(report.files)) throw new Error("Invalid processing response");
            const labels = {imported: "imported", already_imported: "already imported", failed: "failed"};
            status.textContent = report.files.length ? report.files.map(file => {
                const error = file.status === "failed" ? `: ${errorText(file.error ?? file.error_code ?? "Unknown error")}` : "";
                return `${file.filename} — ${labels[file.status] ?? file.status}${error}`;
            }).join("\n") : "No PDFs found.";
        } catch (error) {
            status.textContent = `Could not process AR invoice directory: ${error.message}`;
        } finally {
            // Refresh even after a request failure: some per-file commits may have completed.
            await reloadDatasets();
            processButton.textContent = "Update DB from Directory";
            setBusy(false);
        }
    }

    refreshButton.addEventListener("click", refreshArPanel);
    processEntry.addEventListener("click", async () => {
        if (busy || editing || !selectedInvoice) return;
        setBusy(true);
        editorStatus.textContent = "Processing…";
        try {
            const result = await request(`/${encodeURIComponent(selectedInvoice.id)}/process`, "POST");
            if (result.status === "processed") {
                selectInvoice(result.entry);
                const refreshed = await loadOutgoingInvoices();
                editorStatus.textContent = `Processed invoice: ${result.invoice_number}. ${result.message}`
                    + (refreshed ? "" : " List refresh failed; click Refresh to retry.");
            } else editorStatus.textContent = `Processing failed: ${result.message}`;
        } catch (error) {
            editorStatus.textContent = `Processing failed: ${error.message}`;
        } finally { setBusy(false); }
    });
    normalize.addEventListener("click", async () => {
        if (busy || editing) return;
        setBusy(true);
        normalize.textContent = "Processing…";
        conversionStatus.textContent = "Processing…";
        try {
            const report = await request("/process-entries", "POST");
            conversionStatus.textContent = `${report.processed} processed; ${report.failed} failed.\n`
                + report.invoices.map(invoice => `${invoice.invoice_number} — ${invoice.status}: ${invoice.message}`).join("\n");
        } catch (error) {
            conversionStatus.textContent = `Could not process invoices: ${error.message}`;
        } finally {
            await loadOutgoingInvoices();
            normalize.textContent = "Process Entries";
            setBusy(false);
        }
    });
    processButton.addEventListener("click", processArInvoiceDirectory);
    void refreshArPanel();
    async function refreshInvoiceFacts() {
        if (busy) return false;
        setBusy(true);
        try { return await loadOutgoingInvoices(true); }
        finally { setBusy(false); }
    }
    const payments = initializeArPayments(refreshInvoiceFacts, data => allocations?.setPayments(data));
    allocations = initializeArAllocations(async () => {
        const results = await Promise.all([refreshInvoiceFacts(), payments.refresh()]);
        return results.every(Boolean);
    });
}
