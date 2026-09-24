import {t} from "./i18n/i18n.js";
// Backend events only: no recognition arithmetic, sorting, or date inference.
export function initializeArRecognition() {
    const localizedTitles = new Map();
    // Retain presentation renderers only; language changes must not refill forms
    // or run selection/allocation logic. All translations still come from t().
    const localizedText = new Map();
    function setText(element, render) {
        localizedText.set(element, render);
        element.textContent = render();
    }
    document.addEventListener('accounting:language-changed', () => {
        for (const [element, render] of localizedTitles) {
            if (element.isConnected) element.title = render();
            else localizedTitles.delete(element);
        }
        for (const [element, render] of localizedText) {
            if (element.isConnected) element.textContent = render();
            else localizedText.delete(element);
        }
    });
    const body = document.getElementById('ar-recognition-body');
    const note = document.getElementById('ar-recognition-note');
    let generation = 0;
    function message(text) {
        const row = document.createElement('tr'), cell = document.createElement('td');
        cell.colSpan = 7; setText(cell, text); row.append(cell); body.replaceChildren(row);
    }
    const money = (value, currency) => value == null ? '—' : `${value} ${currency}`;
    return async invoice => {
        const current = ++generation;
        setText(note, () => '');
        if (!invoice) { message(() => t("ar.selectInvoice")); return; }
        message(() => t("recognition.loading"));
        try {
            const response = await fetch(`/acct/v0/outgoing-invoices/${encodeURIComponent(invoice.id)}/recognition-events`, {cache:'no-store'});
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const events = await response.json();
            if (!Array.isArray(events)) throw Object.assign(new Error(t("recognition.invalidResponse")), {translationKey: "recognition.invalidResponse"});
            if (current !== generation) return;
            if (!events.length) { message(() => t("recognition.empty")); return; }
            setText(note, () => events.some(event => event.source === 'allocation')
                ? t("recognition.detailed")
                : t("recognition.manual"));
            body.replaceChildren(...events.map(event => {
                const row = document.createElement('tr');
                for (const value of [event.recognition_date, event.tax_year,
                    money(event.amount_original, event.currency_original),
                    money(event.net_amount_original, event.currency_original),
                    money(event.vat_amount_original, event.currency_original),
                    money(event.amount_common, invoice.currency_common)]) {
                    const cell = document.createElement('td'); cell.textContent = value; row.append(cell);
                }
                const source = document.createElement('td');
                setText(source, () => event.source === 'manual_invoice_payment'
                    ? t("recognition.manualSource") : t("recognition.allocationSource"));
                row.append(source);
                if (event.payment_id) {
                    const title = () => t("recognition.tooltip").replace("{payment}", () => event.payment_id)
                        .replace("{allocation}", () => event.allocation_id);
                    localizedTitles.set(row, title);
                    row.title = title();
                }
                return row;
            }));
        } catch (error) {
            if (current === generation) message(() => t("recognition.loadFailed").replace("{error}", () => error.translationKey ? t(error.translationKey) : error.message));
        }
    };
}
