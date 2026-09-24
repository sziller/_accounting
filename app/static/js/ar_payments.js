import {t} from "./i18n/i18n.js";
// Payment state is independent of the selected outgoing invoice.
export function initializeArPayments(refreshInvoices, onPayments = () => {}) {
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
    const form = document.getElementById('ar-payment-form');
    if (!form) return;
    const body = document.getElementById('ar-payment-body');
    const status = document.getElementById('ar-payment-status');
    const fresh = document.getElementById('new-ar-payment');
    const refresh = document.getElementById('refresh-ar-payments');
    const save = document.getElementById('save-ar-payment');
    const cancel = document.getElementById('cancel-ar-payment');
    const fields = ['payment_date', 'amount', 'currency', 'payer_name', 'bank_reference', 'payment_method', 'remarks'];
    const optional = new Set(['payer_name', 'bank_reference', 'payment_method', 'remarks']);
    const input = key => form.elements.namedItem(key);
    let selected = null;
    let active = false;
    let busy = false;
    function controls() {
        fresh.disabled = refresh.disabled = busy;
        save.disabled = cancel.disabled = busy || !active;
        for (const key of fields) input(key).disabled = busy || !active;
        for (const row of body.querySelectorAll('[data-payment-id]')) {
            const chosen = row.dataset.paymentId === selected?.id;
            row.classList.toggle('is-selected', chosen);
            row.setAttribute('aria-selected', String(chosen));
        }
    }
    function select(payment, creating = false) {
        selected = payment;
        active = Boolean(payment) || creating;
        for (const key of fields) input(key).value = payment?.[key] ?? '';
        for (const key of ['allocated_amount', 'unallocated_amount']) input(key).value = payment?.[key] ?? '';
        setText(save, () => creating ? t("payments.create") : t("common.save"));
        controls();
    }
    async function request(path = '', method = 'GET', payload) {
        const response = await fetch(`/acct/v0/incoming-payments${path}`, {
            method, cache: 'no-store', ...(payload === undefined ? {} : {
                headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)})});
        const data = await response.json();
        if (!response.ok) {
            const detail = data.detail;
            throw new Error(typeof detail === 'string' ? detail : Array.isArray(detail)
                ? detail.map(item => `${(item.loc ?? []).join('.')}: ${item.msg}`).join('\n')
                : JSON.stringify(detail ?? `HTTP ${response.status}`));
        }
        return data;
    }
    function tableMessage(message) {
        const row = document.createElement('tr');
        const cell = document.createElement('td');
        cell.colSpan = 8;
        setText(cell, message);
        row.append(cell);
        body.replaceChildren(row);
    }
    async function load(preserveDraft = false) {
        tableMessage(() => t("payments.loading"));
        try {
            const payments = await request();
            if (!Array.isArray(payments)) throw Object.assign(new Error(t("payments.invalidList")), {translationKey: "payments.invalidList"});
            body.replaceChildren(...payments.map(payment => {
                const row = document.createElement('tr');
                row.dataset.paymentId = payment.id;
                row.tabIndex = 0;
                for (const key of ['payment_date', 'amount', 'currency', 'payer_name', 'bank_reference',
                                   'payment_method', 'allocated_amount', 'unallocated_amount']) {
                    const cell = document.createElement('td');
                    cell.textContent = payment[key] ?? '—';
                    row.append(cell);
                }
                const choose = () => { if (!busy) { select(payment); setText(status, () => t("payments.selected")); } };
                row.addEventListener('click', choose);
                row.addEventListener('keydown', event => {
                    if (['Enter', ' '].includes(event.key)) { event.preventDefault(); choose(); }
                });
                return row;
            }));
            if (!payments.length) tableMessage(() => t("payments.empty"));
            const updated = payments.find(payment => payment.id === selected?.id) ?? null;
            if (preserveDraft && active) {
                if (selected) selected = updated;
                for (const key of ['allocated_amount', 'unallocated_amount']) input(key).value = updated?.[key] ?? '';
                controls();
            } else select(updated);
            onPayments(payments);
            return true;
        } catch (error) {
            tableMessage(() => t("payments.loadFailed"));
            setText(status, () => error.translationKey ? t(error.translationKey) : error.message);
            return false;
        }
    }
    async function reload() {
        if (busy) return;
        busy = true; controls();
        try { await load(); } finally { busy = false; controls(); }
    }
    fresh.addEventListener('click', () => { select(null, true); setText(status, () => t("payments.enterDetails")); });
    cancel.addEventListener('click', () => { select(selected); setText(status, () => t("ar.editCancelled")); });
    refresh.addEventListener('click', reload);
    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (busy || !active || !form.reportValidity()) return;
        const payload = {};
        for (const key of fields) {
            const value = input(key).value;
            if (!selected || value !== String(selected[key] ?? '')) payload[key] = value === '' && optional.has(key) ? null : value;
        }
        if (!Object.keys(payload).length) { setText(status, () => t("ar.noChanges")); return; }
        busy = true; controls(); setText(status, () => t("payments.saving"));
        try {
            const saved = await request(selected ? `/${encodeURIComponent(selected.id)}` : '', selected ? 'PATCH' : 'POST', payload);
            select(saved);
            const loaded = await load();
            const invoicesRefreshed = await refreshInvoices();
            setText(status, () => t("payments.saved") + (loaded ? '' : t("payments.refreshFailed"))
                + (invoicesRefreshed ? '' : t("payments.invoiceRefreshFailed")));
        } catch (error) { setText(status, () => t("payments.saveFailed").replace("{error}", () => error.translationKey ? t(error.translationKey) : error.message)); }
        finally { busy = false; controls(); }
    });
    setText(save, () => t("common.save"));
    controls();
    void reload();
    return {async refresh() {
        if (busy) return false;
        busy = true; controls();
        try { return await load(true); } finally { busy = false; controls(); }
    }};
}
