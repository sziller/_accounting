import {
    initializeTableSort,
    reorderTableRows,
} from "./table_sort.js";


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


async function apiPut(path, payload) {
    const response = await fetch(`${API_BASE}${path}`, {
        method: "PUT",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(payload),
    });

    const body = await response.json().catch(() => null);

    if (!response.ok) {
        throw body || new Error(`PUT ${path} failed`);
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


function fillDetailCategorySelect(categories) {
    const select = document.getElementById("detail_category_code");

    if (!select) {
        console.warn("Missing select element: detail_category_code");
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

    if (payload.has_invoice && !payload.invoice_date) {
        errors.push("Invoice date is required when invoice exists.");
    }

    return errors;
}


export async function initializeAccountsPayable({metadata} = {}) {
    if (!metadata) {
        throw new Error("Accounts Payable metadata is required.");
    }

    const entriesBody = document.getElementById("entries-body");

    const reprocessPendingConversionsButton = document.getElementById(
        "reprocess-pending-conversions"
    );

    const processEntryButton = document.getElementById("process-entry");
    const processingStatus = document.getElementById("entry-processing-status");

    const detailForm = document.getElementById("entry-detail-form");
    const unlockEntryEditButton = document.getElementById("unlock-entry-edit");
    const saveEntryEditButton = document.getElementById("save-entry-edit");
    const cancelEntryEditButton = document.getElementById("cancel-entry-edit");

    const sourceImage = document.getElementById("source-image");
    const sourceImageFilename = document.getElementById(
        "source-image-filename"
    );
    const sourceImageEmpty = document.getElementById("source-image-empty");

    const previousSourceImage = document.getElementById(
        "previous-source-image"
    );
    const nextSourceImage = document.getElementById("next-source-image");

    const sourceImageFrame = document.getElementById("source-image-frame");
    const zoomOut = document.getElementById("source-image-zoom-out");
    const zoomIn = document.getElementById("source-image-zoom-in");
    const zoomReset = document.getElementById("source-image-reset");

    let processingEntries = false;
    let selectedEntry = null;
    let detailEditUnlocked = false;
    let listedEntries = [];
    let detailRequestId = 0;

    const imageViewerState = {
        scale: 1,
        x: 0,
        y: 0,
        pointerId: null,
        lastX: 0,
        lastY: 0,
    };

    const ZOOM_STEP = 0.25;
    const MAX_ZOOM = 10;

    /*
     * AP now owns its own visible status output.
     *
     * Previously AP wrote status messages into #message, which belongs to
     * the New Entries view. Until a dedicated AP editor-status element is
     * introduced, the existing AP processing-status element is the local
     * status target.
     */
    function showMessage(text) {
        processingStatus.textContent = text;
    }


    function populateMetadata() {
        fillSelect("detail_entry_type", metadata.entry_types);
        fillSelect("detail_tax_scope", metadata.tax_scopes);
        fillSelect("detail_payment_method", metadata.payment_methods);
        fillSelect("detail_currency_original", metadata.currencies);
        fillDetailCategorySelect(metadata.categories);
    }


    function renderImageTransform() {
        const state = imageViewerState;
        const ready = !sourceImage.hidden && sourceImage.naturalWidth > 0;

        // Measure the contained JPEG, not the letterboxed <img> element.
        const width = sourceImage.clientWidth;
        const height = sourceImage.clientHeight;

        const fit = ready
            ? Math.min(
                width / sourceImage.naturalWidth,
                height / sourceImage.naturalHeight
            )
            : 0;

        const limitX = Math.max(
            0,
            (sourceImage.naturalWidth * fit * state.scale - width) / 2
        );

        const limitY = Math.max(
            0,
            (sourceImage.naturalHeight * fit * state.scale - height) / 2
        );

        state.x = Math.max(-limitX, Math.min(limitX, state.x));
        state.y = Math.max(-limitY, Math.min(limitY, state.y));

        sourceImage.style.transform =
            `translate(${state.x}px, ${state.y}px) scale(${state.scale})`;

        sourceImageFrame.classList.toggle(
            "is-pannable",
            ready && state.scale > 1
        );

        sourceImageFrame.classList.toggle(
            "is-dragging",
            state.pointerId !== null
        );

        zoomOut.disabled = !ready || state.scale <= 1;
        zoomIn.disabled = !ready || state.scale >= MAX_ZOOM;
        zoomReset.disabled = !ready;
    }


    function stopImagePan() {
        const id = imageViewerState.pointerId;
        imageViewerState.pointerId = null;

        if (
            id !== null
            && sourceImageFrame.hasPointerCapture(id)
        ) {
            sourceImageFrame.releasePointerCapture(id);
        }

        sourceImageFrame.classList.remove("is-dragging");
    }


    function resetImageTransform() {
        stopImagePan();

        Object.assign(imageViewerState, {
            scale: 1,
            x: 0,
            y: 0,
        });

        renderImageTransform();
    }


    function zoomImage(delta) {
        if (sourceImage.hidden) {
            return;
        }

        stopImagePan();

        imageViewerState.scale = Math.max(
            1,
            Math.min(
                MAX_ZOOM,
                imageViewerState.scale + delta
            )
        );

        renderImageTransform();
    }


    function updateSourceImage(entry) {
        const filename = entry.source_filename;

        sourceImage.hidden = true;
        resetImageTransform();

        sourceImage.onload = null;
        sourceImage.onerror = null;
        sourceImage.removeAttribute("src");

        sourceImageFilename.textContent =
            filename || "No source image";

        sourceImageEmpty.hidden = false;
        sourceImageEmpty.textContent =
            "No source image associated with this entry.";

        if (!filename) {
            return;
        }

        const url =
            `${API_BASE}/source-images/${encodeURIComponent(filename)}`;

        sourceImageEmpty.textContent = "Loading source image…";

        sourceImage.onload = () => {
            if (
                sourceImage.getAttribute("src") !== url
                || !sourceImage.naturalWidth
            ) {
                return;
            }

            sourceImage.hidden = false;
            sourceImageEmpty.hidden = true;
            resetImageTransform();
        };

        sourceImage.onerror = () => {
            if (sourceImage.getAttribute("src") !== url) {
                return;
            }

            sourceImage.hidden = true;
            resetImageTransform();

            sourceImageEmpty.hidden = false;
            sourceImageEmpty.textContent =
                "Unable to load source image.";
        };

        sourceImage.src = url;
    }


    function updateEntrySelection() {
        const index = listedEntries.findIndex(
            entry => entry.id === selectedEntry?.id
        );

        previousSourceImage.disabled = index <= 0;

        nextSourceImage.disabled =
            index < 0
            || index >= listedEntries.length - 1;

        for (
            const row
            of entriesBody.querySelectorAll(".entry-row")
        ) {
            const selected =
                row.dataset.entryId === selectedEntry?.id;

            row.classList.toggle("is-selected", selected);
            row.setAttribute("aria-selected", String(selected));
        }
    }


    async function selectAdjacentEntry(offset) {
        const index = listedEntries.findIndex(
            entry => entry.id === selectedEntry?.id
        );

        const entry =
            index >= 0
                ? listedEntries[index + offset]
                : null;

        if (entry) {
            await loadEntryDetail(entry.id);
        }
    }


    const sortEntries = initializeTableSort(
        entriesBody.closest("table"),
        [
            ["payment_date"],
            ["counterparty_name"],
            ["category_code"],
            ["amount_common", "decimal"],
            ["vat_amount", "decimal"],
            ["deductible_amount", "decimal"],
        ],
        () => {
            listedEntries = sortEntries(listedEntries);

            reorderTableRows(
                entriesBody,
                listedEntries,
                "entryId"
            );

            updateEntrySelection();
        }
    );


    async function loadEntries() {
        const entries = sortEntries(
            await apiGet("/entries")
        );

        listedEntries = entries;
        entriesBody.innerHTML = "";

        for (const entry of entries) {
            const tr = document.createElement("tr");

            tr.classList.add("entry-row");
            tr.dataset.entryId = entry.id;

            tr.innerHTML = `
                <td>${entry.payment_date}</td>
                <td>${entry.counterparty_name}</td>
                <td>${entry.category_code}</td>
                <td>${entry.amount_common ?? "pending"} ${entry.currency_common}</td>
                <td>${entry.vat_amount ?? "pending"}</td>
                <td>${entry.deductible_amount ?? "pending"}</td>
            `;

            tr.addEventListener("click", async () => {
                await loadEntryDetail(entry.id);
            });

            entriesBody.appendChild(tr);
        }

        updateEntrySelection();
    }


    function setValue(id, value) {
        const element = document.getElementById(id);

        if (!element) {
            console.warn(`Missing detail element: ${id}`);
            return;
        }

        element.value = value ?? "";
    }


    function setChecked(id, value) {
        const element = document.getElementById(id);

        if (!element) {
            console.warn(`Missing checkbox element: ${id}`);
            return;
        }

        element.checked = Boolean(value);
    }


    function setDetailEditable(enabled) {
        detailEditUnlocked = enabled;

        processEntryButton.disabled =
            processingEntries
            || enabled
            || !selectedEntry;

        reprocessPendingConversionsButton.disabled =
            processingEntries
            || enabled;

        const editableIds = [
            "detail_entry_type",
            "detail_category_code",
            "detail_tax_scope",
            "detail_counterparty_name",
            "detail_payment_method",
            "detail_payment_date",
            "detail_amount_original",
            "detail_currency_original",
            "detail_has_invoice",
            "detail_invoice_number",
            "detail_invoice_date",
            "detail_remarks",
            "detail_tags",
            "detail_source_filename",
        ];

        for (const id of editableIds) {
            const element = document.getElementById(id);

            if (element) {
                element.disabled = !enabled;
            }
        }

        unlockEntryEditButton.disabled =
            processingEntries
            || enabled
            || !selectedEntry;

        saveEntryEditButton.disabled =
            !enabled
            || !selectedEntry;

        cancelEntryEditButton.disabled =
            !enabled
            || !selectedEntry;
    }


    function populateDetailForm(entry) {
        selectedEntry = entry;

        updateSourceImage(entry);
        updateEntrySelection();

        setValue("detail_id", entry.id);

        setValue(
            "detail_entry_type",
            entry.entry_type
        );

        setValue(
            "detail_category_code",
            entry.category_code
        );

        setValue(
            "detail_tax_scope",
            entry.tax_scope
        );

        setValue(
            "detail_counterparty_name",
            entry.counterparty_name
        );

        setValue(
            "detail_payment_method",
            entry.payment_method
        );

        setValue(
            "detail_payment_date",
            entry.payment_date
        );

        setValue(
            "detail_amount_original",
            entry.amount_original
        );

        setValue(
            "detail_currency_original",
            entry.currency_original
        );

        setChecked(
            "detail_has_invoice",
            entry.has_invoice
        );

        setValue(
            "detail_invoice_number",
            entry.invoice_number
        );

        setValue(
            "detail_invoice_date",
            entry.invoice_date
        );

        setValue(
            "detail_remarks",
            entry.remarks
        );

        setValue(
            "detail_tags",
            Array.isArray(entry.tags)
                ? entry.tags.join(", ")
                : ""
        );

        setValue(
            "detail_source_filename",
            entry.source_filename
        );

        setValue(
            "detail_booking_year",
            entry.booking_year
        );

        setValue(
            "detail_amount_common",
            entry.amount_common
        );

        setValue(
            "detail_currency_common",
            entry.currency_common
        );

        setValue(
            "detail_exchange_rate",
            entry.exchange_rate
        );

        setValue(
            "detail_exchange_rate_date",
            entry.exchange_rate_date
        );

        setValue(
            "detail_vat_rate_percent",
            entry.vat_rate_percent
        );

        setValue(
            "detail_vat_amount",
            entry.vat_amount
        );

        setValue(
            "detail_deductible_percent",
            entry.deductible_percent
        );

        setValue(
            "detail_deductible_amount",
            entry.deductible_amount
        );

        setValue(
            "detail_deductible_vat_amount",
            entry.deductible_vat_amount
        );

        setValue(
            "detail_writeoff_method",
            entry.writeoff_method
        );

        setValue(
            "detail_conversion_status",
            entry.conversion_status
        );

        setValue(
            "detail_conversion_note",
            entry.conversion_note
        );

        setValue(
            "detail_created_at",
            entry.created_at
        );

        setValue(
            "detail_updated_at",
            entry.updated_at
        );

        setDetailEditable(false);

        showMessage(`Loaded entry: ${entry.id}`);
    }


    async function loadEntryDetail(entryId) {
        const requestId = ++detailRequestId;

        try {
            const entry = await apiGet(
                `/entries/${entryId}`
            );

            if (requestId !== detailRequestId) {
                return;
            }

            populateDetailForm(entry);
        } catch (error) {
            if (requestId !== detailRequestId) {
                return;
            }

            showMessage(formatApiError(error));
        }
    }


    function collectDetailPayload() {
        const hasInvoice = document.getElementById(
            "detail_has_invoice"
        ).checked;

        return {
            entry_type:
                document.getElementById(
                    "detail_entry_type"
                ).value,

            category_code:
                document.getElementById(
                    "detail_category_code"
                ).value,

            tax_scope:
                document.getElementById(
                    "detail_tax_scope"
                ).value,

            counterparty_name:
                document.getElementById(
                    "detail_counterparty_name"
                ).value,

            payment_method:
                document.getElementById(
                    "detail_payment_method"
                ).value,

            payment_date:
                document.getElementById(
                    "detail_payment_date"
                ).value,

            has_invoice: hasInvoice,

            invoice_number:
                document.getElementById(
                    "detail_invoice_number"
                ).value,

            invoice_date:
                hasInvoice
                    ? document.getElementById(
                        "detail_invoice_date"
                    ).value || null
                    : null,

            amount_original:
                document.getElementById(
                    "detail_amount_original"
                ).value,

            currency_original:
                document.getElementById(
                    "detail_currency_original"
                ).value,

            remarks:
                document.getElementById(
                    "detail_remarks"
                ).value || null,

            tags:
                String(
                    document.getElementById(
                        "detail_tags"
                    ).value || ""
                )
                    .split(",")
                    .map(x => x.trim())
                    .filter(Boolean),

            source_filename:
                document.getElementById(
                    "detail_source_filename"
                ).value || null,
        };
    }


    async function saveEntryDetail() {
        if (!selectedEntry) {
            showMessage("No entry selected.");
            return;
        }

        const payload = collectDetailPayload();
        const errors = validatePayloadClientSide(payload);

        if (errors.length > 0) {
            showMessage(errors.join("\n"));
            return;
        }

        try {
            const updated = await apiPut(
                `/entries/${selectedEntry.id}`,
                payload
            );

            populateDetailForm(updated);
            await loadEntries();

            showMessage(
                `Updated entry: ${updated.id}`
            );
        } catch (error) {
            showMessage(formatApiError(error));
        }
    }


    async function processAccountingEntries(all) {
        if (
            processingEntries
            || detailEditUnlocked
            || (!all && !selectedEntry)
        ) {
            return;
        }

        const id = selectedEntry?.id;

        processingEntries = true;
        setDetailEditable(false);

        processingStatus.textContent = "Processing…";

        try {
            const result = await apiPost(
                all
                    ? "/entries/process"
                    : `/entries/${id}/process`,
                {}
            );

            await loadEntries();

            if (
                selectedEntry?.id === id
                && id
            ) {
                await loadEntryDetail(id);
            }

            processingStatus.textContent = all
                ? `${result.processed} processed; ${result.failed} failed.\n`
                    + result.entries
                        .map(
                            item =>
                                `${item.invoice_number || item.id} — `
                                + `${item.status}: ${item.message}`
                        )
                        .join("\n")
                : `${result.invoice_number || result.id} — `
                    + `${result.status}: ${result.message}`;
        } catch (error) {
            processingStatus.textContent =
                formatApiError(error);
        } finally {
            processingEntries = false;
            setDetailEditable(false);
        }
    }


    async function reprocessPendingConversions() {
        await processAccountingEntries(true);
    }


    processEntryButton.addEventListener(
        "click",
        () => processAccountingEntries(false)
    );


    previousSourceImage.addEventListener(
        "click",
        () => selectAdjacentEntry(-1)
    );


    nextSourceImage.addEventListener(
        "click",
        () => selectAdjacentEntry(1)
    );


    zoomOut.addEventListener(
        "click",
        () => zoomImage(-ZOOM_STEP)
    );


    zoomIn.addEventListener(
        "click",
        () => zoomImage(ZOOM_STEP)
    );


    zoomReset.addEventListener(
        "click",
        resetImageTransform
    );


    sourceImageFrame.addEventListener(
        "wheel",
        event => {
            if (
                !event.ctrlKey
                || sourceImage.hidden
            ) {
                return;
            }

            event.preventDefault();

            if (event.deltaY) {
                zoomImage(
                    event.deltaY < 0
                        ? ZOOM_STEP
                        : -ZOOM_STEP
                );
            }
        },
        {passive: false}
    );


    sourceImageFrame.addEventListener(
        "keydown",
        event => {
            if (
                event.ctrlKey
                || event.metaKey
                || event.altKey
                || sourceImage.hidden
            ) {
                return;
            }

            if (!["+", "-", "0"].includes(event.key)) {
                return;
            }

            event.preventDefault();

            if (event.key === "0") {
                resetImageTransform();
            } else {
                zoomImage(
                    event.key === "+"
                        ? ZOOM_STEP
                        : -ZOOM_STEP
                );
            }
        }
    );


    sourceImageFrame.addEventListener(
        "pointerdown",
        event => {
            if (
                event.button !== 0
                || event.pointerType !== "mouse"
                || sourceImage.hidden
                || imageViewerState.scale <= 1
            ) {
                return;
            }

            event.preventDefault();

            sourceImageFrame.focus({
                preventScroll: true,
            });

            Object.assign(imageViewerState, {
                pointerId: event.pointerId,
                lastX: event.clientX,
                lastY: event.clientY,
            });

            sourceImageFrame.setPointerCapture(
                event.pointerId
            );

            renderImageTransform();
        }
    );


    sourceImageFrame.addEventListener(
        "pointermove",
        event => {
            const state = imageViewerState;

            if (event.pointerId !== state.pointerId) {
                return;
            }

            state.x += event.clientX - state.lastX;
            state.y += event.clientY - state.lastY;

            state.lastX = event.clientX;
            state.lastY = event.clientY;

            renderImageTransform();
        }
    );


    for (
        const event
        of [
            "pointerup",
            "pointercancel",
            "lostpointercapture",
        ]
    ) {
        sourceImageFrame.addEventListener(
            event,
            stopImagePan
        );
    }


    window.addEventListener(
        "blur",
        stopImagePan
    );


    new ResizeObserver(
        renderImageTransform
    ).observe(sourceImageFrame);


    if (reprocessPendingConversionsButton) {
        reprocessPendingConversionsButton.addEventListener(
            "click",
            async () => {
                showMessage(
                    "Reprocessing pending currency conversions..."
                );

                await reprocessPendingConversions();
            }
        );
    }


    if (unlockEntryEditButton) {
        unlockEntryEditButton.addEventListener(
            "click",
            () => {
                if (!selectedEntry) {
                    showMessage(
                        "Select an entry first."
                    );
                    return;
                }

                setDetailEditable(true);

                showMessage(
                    "Editing unlocked. Derived fields remain read-only."
                );
            }
        );
    }


    if (saveEntryEditButton) {
        saveEntryEditButton.addEventListener(
            "click",
            async () => {
                await saveEntryDetail();
            }
        );
    }


    if (cancelEntryEditButton) {
        cancelEntryEditButton.addEventListener(
            "click",
            () => {
                if (selectedEntry) {
                    populateDetailForm(
                        selectedEntry
                    );
                }

                setDetailEditable(false);
                showMessage("Edit cancelled.");
            }
        );
    }


    /*
     * Metadata supplied by app_bootstrap.js.
     */
    populateMetadata();

    /*
     * Initial AP dataset load.
     */
    await loadEntries();


    return {
        refreshEntries: loadEntries,

        getSelectedEntry() {
            return selectedEntry;
        },
    };
}
