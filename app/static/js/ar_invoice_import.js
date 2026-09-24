import {t} from "./i18n/i18n.js";
// AR archive and persisted invoice data; independent of AP entry selection.
import {initializeTableSort, reorderTableRows} from "./table_sort.js";
import {initializeArPayments} from "./ar_payments.js";
import {initializeArAllocations} from "./ar_allocations.js";
import {initializeArRecognition} from "./ar_recognition.js";
export function initializeArPanel() {
    // Retain presentation renderers only; language changes must not refill forms
    // or run selection/allocation logic. All translations still come from t().
    const localizedText = new Map();
    function setText(element, render) {
        localizedText.set(element, render);
        element.textContent = render();
    }
    document.addEventListener('accounting:language-changed', () => {
        for (const [element, render] of localizedText) {
            if (element.isConnected) element.textContent = render();
            else localizedText.delete(element);
        }
    });
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

    // Sorting creates functional buttons inside headers. Move each marker to
    // its button so applyTranslations never replaces the sort control.
    for (const header of dbBody.closest("table").querySelectorAll("th[data-i18n]")) {
        const button = header.querySelector("button");
        button.dataset.i18n = header.dataset.i18n;
        header.removeAttribute("data-i18n");
    }

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
        setText(editorStatus, () => invoice ? t("ar.loadedInvoice").replace("{number}", () => invoice.invoice_number) : t("ar.selectInvoice"));
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
        setText(item, message);
        fileList.replaceChildren(item);
    }

    function dbState(message) {
        const row = document.createElement("tr");
        const cell = document.createElement("td");
        cell.colSpan = 11;
        cell.className = "muted";
        setText(cell, message);
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
        setText(fileCount, () => t("ar.loading"));
        fileState(() => t("ar.loadingPdfs"));
        try {
            const payload = await request("/source-files");
            if (!Array.isArray(payload.files) || !payload.files.every(name => typeof name === "string")) {
                throw new Error(t("ar.invalidPdfList"));
            }
            directory.textContent = payload.directory;
            setText(fileCount, () => `${payload.files.length} ${t(payload.files.length === 1 ? "ar.pdf" : "ar.pdfs")}`);
            if (!payload.files.length) return fileState(() => t("ar.noPdfs"));
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
                    else setText(editorStatus, () => matches.length ? t("ar.multipleMatches")
                        : t("ar.noMatch"));
                });
                item.appendChild(button);
                return item;
            }));
            updateSelection();
        } catch {
            setText(fileCount, () => t("ar.unavailable"));
            fileState(() => t("ar.pdfLoadFailed"));
        }
    }

    async function loadOutgoingInvoices(preserveDraft = false, suppliedInvoices) {
        setText(dbCount, () => t("ar.loading"));
        dbState(() => t("ar.loadingInvoices"));
        try {
            const response = suppliedInvoices ?? await request("");
            if (!Array.isArray(response)) throw new Error(t("ar.invalidInvoiceList"));
            invoices = sortInvoices(response);
            setText(dbCount, () => `${invoices.length} ${t(invoices.length === 1 ? "ar.record" : "ar.records")}`);
            if (!invoices.length) {
                selectInvoice(null);
                dbState(() => t("ar.noInvoices"));
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
                    if (key === "amount_common" && invoice[key] == null) {
                        setText(cell, () => t("ar.pending"));
                    } else cell.textContent = invoice[key] ?? "—";
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
            setText(dbCount, () => t("ar.unavailable"));
            dbState(() => t("ar.invoiceLoadFailed"));
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
            setText(editorStatus, () => t("ar.noChanges"));
            return;
        }
        setBusy(true);
        setText(editorStatus, () => t("ar.saving"));
        try {
            const updated = await request(`/${encodeURIComponent(selectedInvoice.id)}`, "PATCH", payload);
            selectInvoice(updated);
            const refreshed = await loadOutgoingInvoices();
            setText(editorStatus, () => refreshed ? t("ar.savedInvoice").replace("{number}", () => updated.invoice_number)
                : t("ar.savedRefreshFailed"));
        } catch (error) {
            setText(editorStatus, () => t("ar.saveFailed").replace("{error}", () => error.translationKey ? t(error.translationKey) : error.message));
        } finally {
            setBusy(false);
        }
    }

    unlock.addEventListener("click", () => { editing = true; updateSelection(); });
    cancel.addEventListener("click", () => {
        selectInvoice(selectedInvoice);
        setText(editorStatus, () => t("ar.editCancelled"));
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
        setText(status, () => t("ar.processingStatus"));
        setText(processButton, () => t("ar.processingStatus"));
        try {
            const report = await request("/process-directory", "POST");
            if (!Array.isArray(report.files)) throw Object.assign(new Error(t("ar.invalidProcessing")), {translationKey: "ar.invalidProcessing"});
            setText(status, () => report.files.length ? report.files.map(file => {
                const labels = {imported: t("ar.imported"), already_imported: t("ar.alreadyImported"), failed: t("ar.failed")};
                const error = file.status === "failed" ? `: ${errorText(file.error ?? file.error_code ?? t("ar.unknownError"))}` : "";
                return `${file.filename} — ${labels[file.status] ?? file.status}${error}`;
            }).join("\n") : t("ar.noPdfs"));
        } catch (error) {
            setText(status, () => t("ar.directoryFailed").replace("{error}", () => error.translationKey ? t(error.translationKey) : error.message));
        } finally {
            // Refresh even after a request failure: some per-file commits may have completed.
            await reloadDatasets();
            setText(processButton, () => t("ar.updateFromDirectory"));
            setBusy(false);
        }
    }

    refreshButton.addEventListener("click", refreshArPanel);
    processEntry.addEventListener("click", async () => {
        if (busy || editing || !selectedInvoice) return;
        setBusy(true);
        setText(editorStatus, () => t("ar.processingStatus"));
        try {
            const result = await request(`/${encodeURIComponent(selectedInvoice.id)}/process`, "POST");
            if (result.status === "processed") {
                selectInvoice(result.entry);
                const refreshed = await loadOutgoingInvoices();
                setText(editorStatus, () => t("ar.processedInvoice").replace(/\{(number|message)\}/g, (_, key) =>
                    key === "number" ? result.invoice_number : result.message)
                    + (refreshed ? "" : t("ar.listRefreshFailed")));
            } else setText(editorStatus, () => t("ar.processingFailed").replace("{error}", () => result.message));
        } catch (error) {
            setText(editorStatus, () => t("ar.processingFailed").replace("{error}", () => error.translationKey ? t(error.translationKey) : error.message));
        } finally { setBusy(false); }
    });
    normalize.addEventListener("click", async () => {
        if (busy || editing) return;
        setBusy(true);
        setText(normalize, () => t("ar.processingStatus"));
        setText(conversionStatus, () => t("ar.processingStatus"));
        try {
            const report = await request("/process-entries", "POST");
            setText(conversionStatus, () => `${report.processed} ${t("ar.processed")}; ${report.failed} ${t("ar.failed")}.\n`
                + report.invoices.map(invoice => `${invoice.invoice_number} — ${invoice.status}: ${invoice.message}`).join("\n"));
        } catch (error) {
            setText(conversionStatus, () => t("ar.processFailed").replace("{error}", () => error.translationKey ? t(error.translationKey) : error.message));
        } finally {
            await loadOutgoingInvoices();
            setText(normalize, () => t("ar.processEntries"));
            setBusy(false);
        }
    });
    processButton.addEventListener("click", processArInvoiceDirectory);
    setText(editorStatus, () => t("ar.selectInvoice"));
    setText(processButton, () => t("ar.updateFromDirectory"));
    setText(normalize, () => t("ar.processEntries"));
    void refreshArPanel();
    async function refreshInvoiceFacts() {
        if (busy) return false;
        setBusy(true);
        try { return await loadOutgoingInvoices(true); }
        finally { setBusy(false); }
    }
    async function deletePaymentAndRefresh(mutate, fetchPayments, renderPayments) {
        if (busy || allocations.isBusy()) throw new Error('AR data is busy; retry the deletion.');
        setBusy(true);
        allocations.setBlocked(true);
        try {
            // A rejected DELETE leaves all currently displayed data intact.
            await mutate();
            try {
                // Stage both lists before publishing either; never show a mixed refresh.
                const results = await Promise.allSettled([request(''), fetchPayments()]);
                if (results.some(result => result.status !== 'fulfilled' || !Array.isArray(result.value)))
                    throw new Error('AR refresh failed');
                if (!await loadOutgoingInvoices(true, results[0].value)
                    || !await renderPayments(results[1].value)) throw new Error('AR rendering failed');
                return true;
            } catch {
                invoices = [];
                selectInvoice(null);
                setText(dbCount, () => t('ar.unavailable'));
                dbState(() => t('ar.invoiceLoadFailed'));
                allocations.setPayments([]);
                return false;
            }
        } finally {
            allocations.setBlocked(false);
            setBusy(false);
        }
    }
    const payments = initializeArPayments(refreshInvoiceFacts, data => allocations?.setPayments(data), deletePaymentAndRefresh);
    allocations = initializeArAllocations(async () => {
        const results = await Promise.all([refreshInvoiceFacts(), payments.refresh()]);
        return results.every(Boolean);
    });
}
