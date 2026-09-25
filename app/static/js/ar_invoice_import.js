import {t} from "./i18n/i18n.js";
// DB-backed AR workspace; recognition creation lives in New Entries.
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

    document.addEventListener(
        "accounting:language-changed",
        () => {
            for (const [element, render] of localizedText) {
                if (element.isConnected) {
                    element.textContent = render();
                } else {
                    localizedText.delete(element);
                }
            }
        }
    );

    if (!document.getElementById("ar-view")) {
        return;
    }

    const refreshButton =
        document.getElementById("refresh-ar-invoices");

    const dbCount =
        document.getElementById("ar-invoice-db-count");

    const dbBody =
        document.getElementById("ar-invoice-db-body");

    const deleteStatus =
        document.getElementById("ar-invoice-delete-status");

    const form =
        document.getElementById("ar-invoice-detail-form");

    const editorStatus =
        document.getElementById("ar-invoice-editor-status");

    const unlock =
        document.getElementById("unlock-ar-invoice-edit");

    const save =
        document.getElementById("save-ar-invoice-edit");

    const cancel =
        document.getElementById("cancel-ar-invoice-edit");

    const previous =
        document.getElementById("previous-ar-invoice");

    const next =
        document.getElementById("next-ar-invoice");

    const normalize =
        document.getElementById("normalize-ar-invoices");

    const processEntry =
        document.getElementById("process-ar-entry");

    const conversionStatus =
        document.getElementById(
            "ar-invoice-conversion-status"
        );

    const editableFields = [
        "invoice_number",
        "invoice_date",
        "payment_date",
        "due_date",
        "customer_name",
        "customer_reference",
        "currency_original",
        "currency_common",
        "net_amount",
        "vat_amount",
        "amount_original",
        "pdf_filename",
        "pdf_sha256",
        "remarks",
    ];

    const derivedFields = [
        "paid_amount",
        "outstanding_amount",
        "payment_status",
        "created_at",
        "updated_at",
        "amount_common",
    ];

    const nullableFields = new Set([
        "payment_date",
        "due_date",
        "customer_reference",
        "net_amount",
        "vat_amount",
        "pdf_filename",
        "pdf_sha256",
        "remarks",
    ]);


    /* ======================================================================
       OUTGOING-INVOICE TABLE CONFIGURATION
       ====================================================================== */

    const invoiceColumns = [
        {
            key: "invoice_number",
        },
        {
            key: "invoice_date",
        },
        {
            key: "customer_name",
        },
        {
            key: "currency_original",
        },
        {
            key: "amount_original",
            sortType: "decimal",
        },
        {
            key: "paid_amount",
            sortType: "decimal",
        },
        {
            key: "outstanding_amount",
            sortType: "decimal",
        },
        {
            key: "payment_status",
        },
        {
            key: "pdf_filename",
        },
        {
            key: "currency_common",
        },
        {
            key: "amount_common",
            sortType: "decimal",
        },
    ];

    const defaultInvoiceColumnOrder =
        invoiceColumns.map(
            column => column.key
        );

    const invoiceColumnOrderStorageKey =
        "bookkeeping-ar-invoice-column-order";

    const invoiceTable =
        dbBody.closest("table");

    let invoiceColumnOrder =
        loadInvoiceColumnOrder();

    let draggedInvoiceColumn = null;


    /* ======================================================================
       TABLE ENHANCEMENT STYLES

       Kept local to the AR module so these small UX additions do not require
       another accounting_layout.css modification.
       ====================================================================== */

    function ensureInvoiceTableEnhancementStyles() {
        if (
            document.getElementById(
                "ar-invoice-table-enhancement-styles"
            )
        ) {
            return;
        }

        const style =
            document.createElement("style");

        style.id =
            "ar-invoice-table-enhancement-styles";

        style.textContent = `
            :root {
                --ar-status-open-color: #b42318;
                --ar-status-partial-color: #b56a00;
                --ar-status-paid-color: #16803a;
            }

            :root[data-theme="dark"] {
                --ar-status-open-color: #ff8178;
                --ar-status-partial-color: #ffb34d;
                --ar-status-paid-color: #62d68b;
            }

            @media (prefers-color-scheme: dark) {
                :root:not([data-theme="light"]) {
                    --ar-status-open-color: #ff8178;
                    --ar-status-partial-color: #ffb34d;
                    --ar-status-paid-color: #62d68b;
                }
            }

            .ar-payment-status-open {
                color: var(--ar-status-open-color);
                font-weight: 700;
            }

            .ar-payment-status-partially-paid {
                color: var(--ar-status-partial-color);
                font-weight: 700;
            }

            .ar-payment-status-paid {
                color: var(--ar-status-paid-color);
                font-weight: 700;
            }

            #ar-invoice-db-body td[data-column-key="payment_status"] {
                white-space: nowrap;
            }

            .ar-db-table th[data-column-key] {
                position: relative;
                padding-right: 1.9rem;
            }

            .ar-column-drag-handle {
                position: absolute;
                right: 0.35rem;
                top: 50%;
                transform: translateY(-50%);
                z-index: 3;

                display: inline-flex;
                align-items: center;
                justify-content: center;

                width: 1.15rem;
                height: 1.5rem;

                border-radius: 0.25rem;

                cursor: grab;
                user-select: none;
                touch-action: none;

                opacity: 0.45;
                font-weight: 700;
                line-height: 1;
            }

            .ar-column-drag-handle:hover,
            .ar-column-drag-handle:focus-visible {
                opacity: 1;
                background: var(--surface-hover);
                outline: none;
            }

            .ar-column-drag-handle:active {
                cursor: grabbing;
            }

            .ar-db-table th.is-column-dragging {
                opacity: 0.55;
            }

            .ar-db-table th.is-column-drop-target {
                box-shadow:
                    inset 3px 0 0
                    var(--focus-color);
            }
        `;

        document.head.appendChild(style);
    }


    /* ======================================================================
       PERSISTENT COLUMN ORDER
       ====================================================================== */

    function loadInvoiceColumnOrder() {
        try {
            const stored = JSON.parse(
                localStorage.getItem(
                    invoiceColumnOrderStorageKey
                ) ?? "null"
            );

            if (!Array.isArray(stored)) {
                return [
                    ...defaultInvoiceColumnOrder,
                ];
            }

            const validStored =
                stored.filter(
                    (key, index) =>
                        defaultInvoiceColumnOrder.includes(
                            key
                        )
                        && stored.indexOf(key)
                        === index
                );

            return [
                ...validStored,
                ...defaultInvoiceColumnOrder.filter(
                    key =>
                        !validStored.includes(key)
                ),
            ];
        } catch {
            return [
                ...defaultInvoiceColumnOrder,
            ];
        }
    }


    function saveInvoiceColumnOrder() {
        try {
            localStorage.setItem(
                invoiceColumnOrderStorageKey,
                JSON.stringify(
                    invoiceColumnOrder
                )
            );
        } catch {
            /*
             * Column reordering remains functional for the current page
             * even if browser storage is unavailable.
             */
        }
    }


    function applyInvoiceColumnOrder() {
        const headerRow =
            invoiceTable.tHead?.rows?.[0];

        if (!headerRow) {
            return;
        }

        const headerByKey =
            new Map(
                Array.from(headerRow.cells)
                    .filter(
                        header =>
                            header.dataset.columnKey
                    )
                    .map(
                        header => [
                            header.dataset.columnKey,
                            header,
                        ]
                    )
            );

        const fixedHeader =
            Array.from(headerRow.cells)
                .find(
                    header =>
                        header.dataset.columnFixed
                        === "true"
                )
            ?? headerRow.lastElementChild;

        for (
            const key
            of invoiceColumnOrder
        ) {
            const header =
                headerByKey.get(key);

            if (header) {
                headerRow.insertBefore(
                    header,
                    fixedHeader
                );
            }
        }

        for (
            const row
            of dbBody.querySelectorAll(
                "tr[data-invoice-id]"
            )
        ) {
            const cellByKey =
                new Map(
                    Array.from(row.cells)
                        .filter(
                            cell =>
                                cell.dataset.columnKey
                        )
                        .map(
                            cell => [
                                cell.dataset.columnKey,
                                cell,
                            ]
                        )
                );

            const fixedCell =
                Array.from(row.cells)
                    .find(
                        cell =>
                            cell.dataset.columnFixed
                            === "true"
                    )
                ?? row.lastElementChild;

            for (
                const key
                of invoiceColumnOrder
            ) {
                const cell =
                    cellByKey.get(key);

                if (cell) {
                    row.insertBefore(
                        cell,
                        fixedCell
                    );
                }
            }
        }
    }


    function moveInvoiceColumn(
        draggedKey,
        targetKey,
        placeAfter
    ) {
        if (
            !draggedKey
            || !targetKey
            || draggedKey === targetKey
            || !invoiceColumnOrder.includes(
                draggedKey
            )
            || !invoiceColumnOrder.includes(
                targetKey
            )
        ) {
            return;
        }

        const nextOrder =
            invoiceColumnOrder.filter(
                key =>
                    key !== draggedKey
            );

        let targetIndex =
            nextOrder.indexOf(
                targetKey
            );

        if (placeAfter) {
            targetIndex += 1;
        }

        nextOrder.splice(
            targetIndex,
            0,
            draggedKey
        );

        invoiceColumnOrder =
            nextOrder;

        saveInvoiceColumnOrder();
        applyInvoiceColumnOrder();
    }


    function initializeInvoiceColumnReordering() {
        ensureInvoiceTableEnhancementStyles();

        const headerRow =
            invoiceTable.tHead?.rows?.[0];

        if (!headerRow) {
            return;
        }

        /*
         * initializeTableSort() keeps the original header-cell sequence;
         * therefore the first N headers correspond to invoiceColumns.
         */
        const headers =
            Array.from(
                headerRow.cells
            );

        defaultInvoiceColumnOrder.forEach(
            (key, index) => {
                const header =
                    headers[index];

                if (!header) {
                    return;
                }

                header.dataset.columnKey =
                    key;

                const handle =
                    document.createElement(
                        "span"
                    );

                handle.className =
                    "ar-column-drag-handle";

                handle.draggable = true;
                handle.tabIndex = 0;

                handle.textContent =
                    "⋮⋮";

                handle.title =
                    "Drag to reorder column";

                handle.setAttribute(
                    "aria-label",
                    "Drag to reorder column"
                );

                /*
                 * Clicking or beginning a drag on the handle must not
                 * activate the table's sorting button.
                 */
                handle.addEventListener(
                    "click",
                    event => {
                        event.preventDefault();
                        event.stopPropagation();
                    }
                );

                handle.addEventListener(
                    "mousedown",
                    event => {
                        event.stopPropagation();
                    }
                );

                handle.addEventListener(
                    "dragstart",
                    event => {
                        draggedInvoiceColumn =
                            key;

                        header.classList.add(
                            "is-column-dragging"
                        );

                        if (
                            event.dataTransfer
                        ) {
                            event.dataTransfer.effectAllowed =
                                "move";

                            event.dataTransfer.setData(
                                "text/plain",
                                key
                            );
                        }
                    }
                );

                handle.addEventListener(
                    "dragend",
                    () => {
                        draggedInvoiceColumn =
                            null;

                        header.classList.remove(
                            "is-column-dragging"
                        );

                        for (
                            const item
                            of headerRow.cells
                        ) {
                            item.classList.remove(
                                "is-column-drop-target"
                            );
                        }
                    }
                );

                header.addEventListener(
                    "dragover",
                    event => {
                        if (
                            !draggedInvoiceColumn
                            || draggedInvoiceColumn
                            === key
                        ) {
                            return;
                        }

                        event.preventDefault();

                        if (
                            event.dataTransfer
                        ) {
                            event.dataTransfer.dropEffect =
                                "move";
                        }

                        for (
                            const item
                            of headerRow.cells
                        ) {
                            item.classList.remove(
                                "is-column-drop-target"
                            );
                        }

                        header.classList.add(
                            "is-column-drop-target"
                        );
                    }
                );

                header.addEventListener(
                    "dragleave",
                    event => {
                        if (
                            !header.contains(
                                event.relatedTarget
                            )
                        ) {
                            header.classList.remove(
                                "is-column-drop-target"
                            );
                        }
                    }
                );

                header.addEventListener(
                    "drop",
                    event => {
                        if (
                            !draggedInvoiceColumn
                            || draggedInvoiceColumn
                            === key
                        ) {
                            return;
                        }

                        event.preventDefault();

                        header.classList.remove(
                            "is-column-drop-target"
                        );

                        const bounds =
                            header.getBoundingClientRect();

                        const placeAfter =
                            event.clientX
                            > bounds.left
                            + bounds.width / 2;

                        moveInvoiceColumn(
                            draggedInvoiceColumn,
                            key,
                            placeAfter
                        );
                    }
                );

                header.appendChild(
                    handle
                );
            }
        );

        /*
         * DELETE remains permanently fixed as the final column.
         */
        const fixedHeader =
            headers[
                defaultInvoiceColumnOrder.length
            ];

        if (fixedHeader) {
            fixedHeader.dataset.columnFixed =
                "true";
        }

        applyInvoiceColumnOrder();
    }


    /* ======================================================================
       STATUS CELL COLORING
       ====================================================================== */

    function applyPaymentStatusClass(
        cell,
        statusValue
    ) {
        const status =
            String(
                statusValue ?? ""
            ).toLowerCase();

        cell.classList.remove(
            "ar-payment-status-open",
            "ar-payment-status-partially-paid",
            "ar-payment-status-paid"
        );

        if (status === "open") {
            cell.classList.add(
                "ar-payment-status-open"
            );
        } else if (
            status === "partially_paid"
        ) {
            cell.classList.add(
                "ar-payment-status-partially-paid"
            );
        } else if (
            status === "paid"
        ) {
            cell.classList.add(
                "ar-payment-status-paid"
            );
        }
    }


    /* ======================================================================
       AR STATE
       ====================================================================== */

    let invoices = [];
    let selectedInvoice = null;
    let editing = false;
    let busy = false;
    let refreshPending = false;
    let invoiceDeleteRefreshPending = false;
    let allocations;

    const refreshRecognition =
        initializeArRecognition();


    /* ======================================================================
       TABLE SORTING
       ====================================================================== */

    const sortInvoices =
        initializeTableSort(
            invoiceTable,
            invoiceColumns.map(
                column =>
                    column.sortType
                        ? [
                            column.key,
                            column.sortType,
                        ]
                        : [
                            column.key,
                        ]
            ),
            () => {
                invoices =
                    sortInvoices(
                        invoices
                    );

                reorderTableRows(
                    dbBody,
                    invoices,
                    "invoiceId"
                );

                updateSelection();
            }
        );

    /*
     * Sorting creates functional buttons inside headers. Move each marker to
     * its button so applyTranslations never replaces the sort control.
     */
    for (
        const header
        of invoiceTable.querySelectorAll(
            "th[data-i18n]"
        )
    ) {
        const button =
            header.querySelector(
                "button"
            );

        if (!button) {
            continue;
        }

        button.dataset.i18n =
            header.dataset.i18n;

        header.removeAttribute(
            "data-i18n"
        );
    }

    initializeInvoiceColumnReordering();


    /* ======================================================================
       SELECTION
       ====================================================================== */

    function updateSelection() {
        const index =
            invoices.findIndex(
                invoice =>
                    invoice.id
                    === selectedInvoice?.id
            );

        for (
            const row
            of dbBody.querySelectorAll(
                "[data-invoice-id]"
            )
        ) {
            const selected =
                selectedInvoice !== null
                && row.dataset.invoiceId
                === String(
                    selectedInvoice.id
                );

            row.classList.toggle(
                "is-selected",
                selected
            );

            row.setAttribute(
                "aria-selected",
                String(selected)
            );
        }

        previous.disabled =
            busy
            || index <= 0;

        for (
            const button
            of dbBody.querySelectorAll(
                ".ar-invoice-delete"
            )
        ) {
            button.disabled =
                busy;
        }

        next.disabled =
            busy
            || index < 0
            || index
            >= invoices.length - 1;

        unlock.disabled =
            busy
            || !selectedInvoice
            || editing;

        save.disabled =
            busy
            || !selectedInvoice
            || !editing;

        cancel.disabled =
            busy
            || !selectedInvoice
            || !editing;

        normalize.disabled =
            busy
            || editing;

        processEntry.disabled =
            busy
            || editing
            || !selectedInvoice;

        allocations?.setInvoice(
            selectedInvoice
        );

        for (
            const key
            of editableFields
        ) {
            document.getElementById(
                `ar-invoice-${key}`
            ).disabled =
                busy
                || !editing;
        }
    }


    /* ======================================================================
       PDF VIEWER
       ====================================================================== */

    const pdfFrame =
        document.getElementById(
            "ar-source-pdf"
        );

    const pdfFilename =
        document.getElementById(
            "ar-source-pdf-filename"
        );

    const pdfState =
        document.getElementById(
            "ar-source-pdf-state"
        );

    const pdfLink =
        document.getElementById(
            "ar-source-pdf-link"
        );

    let pdfRequest = 0;
    let pdfObjectUrl = null;
    let pdfController;


    async function updateSourcePdf(invoice) {
        const token =
            ++pdfRequest;

        pdfController?.abort();

        pdfController =
            new AbortController();

        pdfFilename.textContent =
            invoice?.pdf_filename ?? "";

        /*
         * No selected invoice, or selected invoice has no PDF:
         * clear the viewer normally.
         */
        if (!invoice?.pdf_filename) {
            pdfFrame.hidden = true;

            pdfFrame.removeAttribute(
                "src"
            );

            pdfLink.hidden = true;

            pdfLink.removeAttribute(
                "href"
            );

            if (pdfObjectUrl) {
                URL.revokeObjectURL(
                    pdfObjectUrl
                );

                pdfObjectUrl = null;
            }

            pdfState.hidden = false;

            setText(
                pdfState,
                () =>
                    t(
                        !invoice
                            ? "ar.selectInvoice"
                            : "ar.noSourcePdf"
                    )
            );

            return;
        }

        /*
         * If a PDF is already visible, leave it visible while the next PDF is
         * fetched. This prevents the viewer from flashing/collapsing between
         * invoice selections.
         */
        const currentPdfVisible =
            !pdfFrame.hidden
            && Boolean(
                pdfFrame.getAttribute(
                    "src"
                )
            );

        if (currentPdfVisible) {
            pdfState.hidden =
                true;
        } else {
            pdfState.hidden =
                false;

            setText(
                pdfState,
                () =>
                    t(
                        "ar.loadingPdfs"
                    )
            );
        }

        /*
         * Do not leave the Open link pointing at the previous invoice while
         * the replacement PDF is loading.
         */
        pdfLink.hidden =
            true;

        try {
            const response =
                await fetch(
                    "/acct/v0/outgoing-invoices/"
                    + encodeURIComponent(
                        invoice.id
                    )
                    + "/source-pdf",
                    {
                        signal:
                            pdfController.signal,
                    }
                );

            if (!response.ok) {
                throw new Error(
                    "HTTP "
                    + response.status
                );
            }

            const blob =
                await response.blob();

            /*
             * A newer selection superseded this request.
             */
            if (
                token !== pdfRequest
            ) {
                return;
            }

            const nextObjectUrl =
                URL.createObjectURL(
                    blob
                );

            const previousObjectUrl =
                pdfObjectUrl;

            /*
             * Swap directly from the old PDF to the new PDF.
             */
            pdfObjectUrl =
                nextObjectUrl;

            pdfFrame.src =
                nextObjectUrl;

            pdfFrame.hidden =
                false;

            pdfLink.href =
                nextObjectUrl;

            pdfLink.hidden =
                false;

            pdfState.hidden =
                true;

            /*
             * Keep the previous blob alive until the browser has accepted
             * the new iframe source.
             */
            if (previousObjectUrl) {
                const releasePreviousUrl =
                    () => {
                        URL.revokeObjectURL(
                            previousObjectUrl
                        );

                        pdfFrame.removeEventListener(
                            "load",
                            releasePreviousUrl
                        );
                    };

                pdfFrame.addEventListener(
                    "load",
                    releasePreviousUrl
                );
            }
        } catch (error) {
            /*
             * Aborted requests are normal when the user changes selection
             * quickly.
             */
            if (
                token !== pdfRequest
                || error?.name
                === "AbortError"
            ) {
                return;
            }

            /*
             * A genuine failure must not leave the previous invoice's PDF
             * displayed underneath the newly selected invoice.
             */
            pdfFrame.hidden =
                true;

            pdfFrame.removeAttribute(
                "src"
            );

            pdfLink.hidden =
                true;

            pdfLink.removeAttribute(
                "href"
            );

            if (pdfObjectUrl) {
                URL.revokeObjectURL(
                    pdfObjectUrl
                );

                pdfObjectUrl =
                    null;
            }

            pdfState.hidden =
                false;

            setText(
                pdfState,
                () =>
                    t(
                        "ar.pdfLoadFailed"
                    )
            );
        }
    }


    /* ======================================================================
       INVOICE SELECTION / EDITOR
       ====================================================================== */

    function selectInvoice(
        invoice,
        refreshSource = true
    ) {
        /*
         * API data is JSON; copying it this way also supports older browsers.
         */
        selectedInvoice =
            invoice
                ? JSON.parse(
                    JSON.stringify(
                        invoice
                    )
                )
                : null;

        editing =
            false;

        for (
            const key
            of [
                ...editableFields,
                ...derivedFields,
            ]
        ) {
            document.getElementById(
                `ar-invoice-${key}`
            ).value =
                selectedInvoice?.[key]
                ?? "";
        }

        setText(
            editorStatus,
            () =>
                invoice
                    ? t(
                        "ar.loadedInvoice"
                    ).replace(
                        "{number}",
                        () =>
                            invoice.invoice_number
                    )
                    : t(
                        "ar.selectInvoice"
                    )
        );

        if (
            refreshSource
            || !selectedInvoice
        ) {
            updateSourcePdf(
                selectedInvoice
            );
        }

        void refreshRecognition(
            selectedInvoice
        );

        updateSelection();
    }


    function setBusy(value) {
        busy =
            value;

        refreshButton.disabled =
            value;

        updateSelection();

        if (
            !busy
            && refreshPending
        ) {
            queueMicrotask(
                () =>
                    void refreshArPanel()
            );
        }
    }


    /* ======================================================================
       TABLE / API HELPERS
       ====================================================================== */

    function dbState(message) {
        const row =
            document.createElement(
                "tr"
            );

        const cell =
            document.createElement(
                "td"
            );

        cell.colSpan =
            12;

        cell.className =
            "muted";

        setText(
            cell,
            message
        );

        row.appendChild(
            cell
        );

        dbBody.replaceChildren(
            row
        );
    }


    function errorText(detail) {
        return typeof detail
        === "string"
            ? detail
            : JSON.stringify(
                detail
            );
    }


    async function request(
        path,
        method = "GET",
        payload
    ) {
        const options = {
            method,
            cache: "no-store",
        };

        if (
            payload !== undefined
        ) {
            options.headers = {
                "Content-Type":
                    "application/json",
            };

            options.body =
                JSON.stringify(
                    payload
                );
        }

        const response =
            await fetch(
                `/acct/v0/outgoing-invoices${path}`,
                options
            );

        if (
            response.status
            === 204
        ) {
            return;
        }

        const body =
            await response
                .json()
                .catch(
                    () => ({})
                );

        if (!response.ok) {
            throw new Error(
                errorText(
                    body.detail
                    ?? `HTTP ${response.status}`
                )
            );
        }

        return body;
    }


    /* ======================================================================
       OUTGOING-INVOICE LIST RENDERING
       ====================================================================== */

    async function loadOutgoingInvoices(
        preserveDraft = false,
        suppliedInvoices,
        refreshSource = true
    ) {
        setText(
            dbCount,
            () =>
                t(
                    "ar.loading"
                )
        );

        dbState(
            () =>
                t(
                    "ar.loadingInvoices"
                )
        );

        try {
            const response =
                suppliedInvoices
                ?? await request("");

            if (
                !Array.isArray(
                    response
                )
            ) {
                throw new Error(
                    t(
                        "ar.invalidInvoiceList"
                    )
                );
            }

            invoices =
                sortInvoices(
                    response
                );

            setText(
                dbCount,
                () =>
                    `${invoices.length} ${
                        t(
                            invoices.length
                            === 1
                                ? "ar.record"
                                : "ar.records"
                        )
                    }`
            );

            if (!invoices.length) {
                selectInvoice(
                    null
                );

                dbState(
                    () =>
                        t(
                            "ar.noInvoices"
                        )
                );

                return true;
            }

            dbBody.replaceChildren(
                ...invoices.map(
                    invoice => {
                        const row =
                            document.createElement(
                                "tr"
                            );

                        row.dataset.invoiceId =
                            invoice.id;

                        row.tabIndex =
                            0;

                        row.addEventListener(
                            "click",
                            () => {
                                if (!busy) {
                                    selectInvoice(
                                        invoice
                                    );
                                }
                            }
                        );

                        row.addEventListener(
                            "keydown",
                            event => {
                                if (
                                    event.target
                                    !== row
                                ) {
                                    return;
                                }

                                if (
                                    !busy
                                    && [
                                        "Enter",
                                        " ",
                                    ].includes(
                                        event.key
                                    )
                                ) {
                                    event.preventDefault();

                                    selectInvoice(
                                        invoice
                                    );
                                }
                            }
                        );

                        /*
                         * Cells are created directly in the user's saved
                         * column order.
                         */
                        for (
                            const key
                            of invoiceColumnOrder
                        ) {
                            const cell =
                                document.createElement(
                                    "td"
                                );

                            cell.dataset.columnKey =
                                key;

                            if (
                                key
                                === "amount_common"
                                && invoice[key]
                                == null
                            ) {
                                setText(
                                    cell,
                                    () =>
                                        t(
                                            "ar.pending"
                                        )
                                );
                            } else {
                                cell.textContent =
                                    invoice[key]
                                    ?? "—";
                            }

                            if (
                                key
                                === "payment_status"
                            ) {
                                applyPaymentStatusClass(
                                    cell,
                                    invoice[key]
                                );
                            }

                            row.appendChild(
                                cell
                            );
                        }

                        /*
                         * DELETE stays permanently at the far right.
                         */
                        const actions =
                            document.createElement(
                                "td"
                            );

                        actions.dataset.columnFixed =
                            "true";

                        const remove =
                            document.createElement(
                                "button"
                            );

                        remove.type =
                            "button";

                        remove.className =
                            "ar-invoice-delete";

                        remove.disabled =
                            busy;

                        setText(
                            remove,
                            () =>
                                t(
                                    "ar.deleteAction"
                                )
                        );

                        remove.addEventListener(
                            "click",
                            event => {
                                event.stopPropagation();

                                void deleteInvoice(
                                    invoice
                                );
                            }
                        );

                        actions.append(
                            remove
                        );

                        row.append(
                            actions
                        );

                        return row;
                    }
                )
            );

            /*
             * Ensure the header follows the same persisted order after the
             * body has been rebuilt.
             */
            applyInvoiceColumnOrder();

            const updated =
                invoices.find(
                    invoice =>
                        invoice.id
                        === selectedInvoice?.id
                )
                ?? null;

            if (
                preserveDraft
                && editing
                && updated
            ) {
                selectedInvoice =
                    updated;

                void refreshRecognition(
                    updated
                );

                for (
                    const key
                    of derivedFields
                ) {
                    document.getElementById(
                        `ar-invoice-${key}`
                    ).value =
                        updated[key]
                        ?? "";
                }

                updateSelection();
            } else {
                selectInvoice(
                    updated,
                    refreshSource
                );
            }

            return true;
        } catch {
            setText(
                dbCount,
                () =>
                    t(
                        "ar.unavailable"
                    )
            );

            dbState(
                () =>
                    t(
                        "ar.invoiceLoadFailed"
                    )
            );

            return false;
        }
    }


    /* ======================================================================
       SAVE
       ====================================================================== */

    async function saveArInvoice() {
        if (
            busy
            || !editing
            || !selectedInvoice
            || !form.reportValidity()
        ) {
            return;
        }

        const payload = {};

        for (
            const key
            of editableFields
        ) {
            const value =
                document.getElementById(
                    `ar-invoice-${key}`
                ).value;

            if (
                value
                !== String(
                    selectedInvoice[key]
                    ?? ""
                )
            ) {
                payload[key] =
                    value === ""
                    && nullableFields.has(
                        key
                    )
                        ? null
                        : value;
            }
        }

        if (
            !Object.keys(
                payload
            ).length
        ) {
            selectInvoice(
                selectedInvoice
            );

            setText(
                editorStatus,
                () =>
                    t(
                        "ar.noChanges"
                    )
            );

            return;
        }

        setBusy(true);

        setText(
            editorStatus,
            () =>
                t(
                    "ar.saving"
                )
        );

        try {
            const updated =
                await request(
                    `/${
                        encodeURIComponent(
                            selectedInvoice.id
                        )
                    }`,
                    "PATCH",
                    payload
                );

            selectInvoice(
                updated
            );

            const refreshed =
                await loadOutgoingInvoices();

            setText(
                editorStatus,
                () =>
                    refreshed
                        ? t(
                            "ar.savedInvoice"
                        ).replace(
                            "{number}",
                            () =>
                                updated.invoice_number
                        )
                        : t(
                            "ar.savedRefreshFailed"
                        )
            );
        } catch (error) {
            setText(
                editorStatus,
                () =>
                    t(
                        "ar.saveFailed"
                    ).replace(
                        "{error}",
                        () =>
                            error.translationKey
                                ? t(
                                    error.translationKey
                                )
                                : error.message
                    )
            );
        } finally {
            setBusy(false);
        }
    }


    /* ======================================================================
       EDITOR / NAVIGATION EVENTS
       ====================================================================== */

    unlock.addEventListener(
        "click",
        () => {
            editing =
                true;

            updateSelection();
        }
    );

    cancel.addEventListener(
        "click",
        () => {
            selectInvoice(
                selectedInvoice
            );

            setText(
                editorStatus,
                () =>
                    t(
                        "ar.editCancelled"
                    )
            );
        }
    );

    save.addEventListener(
        "click",
        saveArInvoice
    );

    form.addEventListener(
        "submit",
        event => {
            event.preventDefault();

            void saveArInvoice();
        }
    );

    for (
        const [button, offset]
        of [
            [
                previous,
                -1,
            ],
            [
                next,
                1,
            ],
        ]
    ) {
        button.addEventListener(
            "click",
            () => {
                const index =
                    invoices.findIndex(
                        invoice =>
                            invoice.id
                            === selectedInvoice?.id
                    );

                if (
                    !busy
                    && index >= 0
                    && invoices[
                        index + offset
                    ]
                ) {
                    selectInvoice(
                        invoices[
                            index + offset
                        ]
                    );
                }
            }
        );
    }


    /* ======================================================================
       REFRESH
       ====================================================================== */

    async function reloadDatasets() {
        await loadOutgoingInvoices(
            true
        );
    }


    async function refreshArPanel() {
        if (busy) {
            return;
        }

        refreshPending =
            false;

        if (
            invoiceDeleteRefreshPending
        ) {
            return refreshAfterInvoiceDeletion();
        }

        setBusy(true);

        try {
            await reloadDatasets();
        } finally {
            setBusy(false);
        }
    }


    refreshButton.addEventListener(
        "click",
        refreshArPanel
    );


    /* ======================================================================
       PROCESS SELECTED INVOICE
       ====================================================================== */

    processEntry.addEventListener(
        "click",
        async () => {
            if (
                busy
                || editing
                || !selectedInvoice
            ) {
                return;
            }

            setBusy(true);

            setText(
                editorStatus,
                () =>
                    t(
                        "ar.processingStatus"
                    )
            );

            try {
                const result =
                    await request(
                        `/${
                            encodeURIComponent(
                                selectedInvoice.id
                            )
                        }/process`,
                        "POST"
                    );

                if (
                    result.status
                    === "processed"
                ) {
                    selectInvoice(
                        result.entry
                    );

                    const refreshed =
                        await loadOutgoingInvoices();

                    setText(
                        editorStatus,
                        () =>
                            t(
                                "ar.processedInvoice"
                            ).replace(
                                /\{(number|message)\}/g,
                                (_, key) =>
                                    key === "number"
                                        ? result.invoice_number
                                        : result.message
                            )
                            + (
                                refreshed
                                    ? ""
                                    : t(
                                        "ar.listRefreshFailed"
                                    )
                            )
                    );
                } else {
                    setText(
                        editorStatus,
                        () =>
                            t(
                                "ar.processingFailed"
                            ).replace(
                                "{error}",
                                () =>
                                    result.message
                            )
                    );
                }
            } catch (error) {
                setText(
                    editorStatus,
                    () =>
                        t(
                            "ar.processingFailed"
                        ).replace(
                            "{error}",
                            () =>
                                error.translationKey
                                    ? t(
                                        error.translationKey
                                    )
                                    : error.message
                        )
                );
            } finally {
                setBusy(false);
            }
        }
    );


    /* ======================================================================
       PROCESS / NORMALIZE ALL
       ====================================================================== */

    normalize.addEventListener(
        "click",
        async () => {
            if (
                busy
                || editing
            ) {
                return;
            }

            setBusy(true);

            setText(
                normalize,
                () =>
                    t(
                        "ar.processingStatus"
                    )
            );

            setText(
                conversionStatus,
                () =>
                    t(
                        "ar.processingStatus"
                    )
            );

            try {
                const report =
                    await request(
                        "/process-entries",
                        "POST"
                    );

                setText(
                    conversionStatus,
                    () =>
                        `${
                            report.processed
                        } ${
                            t(
                                "ar.processed"
                            )
                        }; ${
                            report.failed
                        } ${
                            t(
                                "ar.failed"
                            )
                        }.\n`
                        + report.invoices
                            .map(
                                invoice =>
                                    `${
                                        invoice.invoice_number
                                    } — ${
                                        invoice.status
                                    }: ${
                                        invoice.message
                                    }`
                            )
                            .join(
                                "\n"
                            )
                );
            } catch (error) {
                setText(
                    conversionStatus,
                    () =>
                        t(
                            "ar.processFailed"
                        ).replace(
                            "{error}",
                            () =>
                                error.translationKey
                                    ? t(
                                        error.translationKey
                                    )
                                    : error.message
                        )
                );
            } finally {
                await loadOutgoingInvoices();

                setText(
                    normalize,
                    () =>
                        t(
                            "ar.processEntries"
                        )
                );

                setBusy(false);
            }
        }
    );


    /* ======================================================================
       INITIALIZATION
       ====================================================================== */

    setText(
        editorStatus,
        () =>
            t(
                "ar.selectInvoice"
            )
    );

    setText(
        normalize,
        () =>
            t(
                "ar.processEntries"
            )
    );

    document.addEventListener(
        "accounting:outgoing-invoices-created",
        () => {
            refreshPending =
                true;

            if (!busy) {
                void refreshArPanel();
            }
        }
    );

    void refreshArPanel();


    /* ======================================================================
       PAYMENT / ALLOCATION SYNCHRONIZATION
       ====================================================================== */

    async function refreshInvoiceFacts() {
        if (busy) {
            return false;
        }

        setBusy(true);

        try {
            return await loadOutgoingInvoices(
                true
            );
        } finally {
            setBusy(false);
        }
    }


    async function deleteAndRefresh(
        mutate,
        fetchPayments,
        renderPayments
    ) {
        if (
            busy
            || allocations.isBusy()
        ) {
            throw new Error(
                t(
                    "ar.deleteBusy"
                )
            );
        }

        setBusy(true);

        allocations.setBlocked(
            true
        );

        try {
            /*
             * A rejected DELETE leaves all currently displayed data intact.
             */
            await mutate();

            try {
                /*
                 * Stage both lists before publishing either; never show
                 * a mixed refresh.
                 */
                const results =
                    await Promise.allSettled(
                        [
                            request(""),
                            fetchPayments(),
                        ]
                    );

                if (
                    results.some(
                        result =>
                            result.status
                            !== "fulfilled"
                            || !Array.isArray(
                                result.value
                            )
                    )
                ) {
                    throw new Error(
                        "AR refresh failed"
                    );
                }

                if (
                    !await loadOutgoingInvoices(
                        true,
                        results[0].value,
                        false
                    )
                    || !await renderPayments(
                        results[1].value
                    )
                ) {
                    throw new Error(
                        "AR rendering failed"
                    );
                }

                return true;
            } catch {
                invoices = [];

                selectInvoice(
                    null
                );

                setText(
                    dbCount,
                    () =>
                        t(
                            "ar.unavailable"
                        )
                );

                dbState(
                    () =>
                        t(
                            "ar.invoiceLoadFailed"
                        )
                );

                allocations.setPayments(
                    []
                );

                payments.invalidate();

                return false;
            }
        } finally {
            allocations.setBlocked(
                false
            );

            setBusy(false);
        }
    }


    /* ======================================================================
       INVOICE DELETION
       ====================================================================== */

    async function refreshAfterInvoiceDeletion(
        mutate = async () => {}
    ) {
        try {
            const refreshed =
                await payments.withRefreshLock(
                    (
                        fetchPayments,
                        renderPayments
                    ) =>
                        deleteAndRefresh(
                            mutate,
                            fetchPayments,
                            renderPayments
                        )
                );

            invoiceDeleteRefreshPending =
                !refreshed;

            setText(
                deleteStatus,
                () =>
                    t(
                        refreshed
                            ? "ar.deleted"
                            : "ar.deleteRefreshFailed"
                    )
            );
        } catch (error) {
            setText(
                deleteStatus,
                () =>
                    t(
                        "ar.deleteFailed"
                    ).replace(
                        "{error}",
                        () =>
                            error.message
                    )
            );
        }
    }


    async function deleteInvoice(
        invoice
    ) {
        if (busy) {
            return;
        }

        const message =
            invoice.allocations?.length
                ? "ar.confirmDeleteAllocated"
                : "ar.confirmDelete";

        if (
            !window.confirm(
                t(message)
            )
        ) {
            return;
        }

        await refreshAfterInvoiceDeletion(
            async () => {
                await request(
                    `/${
                        encodeURIComponent(
                            invoice.id
                        )
                    }`,
                    "DELETE"
                );

                if (
                    selectedInvoice?.id
                    === invoice.id
                ) {
                    selectInvoice(
                        null
                    );
                }
            }
        );
    }


    /* ======================================================================
       PAYMENTS / ALLOCATIONS
       ====================================================================== */

    const payments =
        initializeArPayments(
            refreshInvoiceFacts,
            data =>
                allocations?.setPayments(
                    data
                ),
            deleteAndRefresh
        );

    allocations =
        initializeArAllocations(
            async () => {
                const results =
                    await Promise.all(
                        [
                            refreshInvoiceFacts(),
                            payments.refresh(),
                        ]
                    );

                return results.every(
                    Boolean
                );
            }
        );
}
