// Payment state is independent of the selected outgoing invoice.
export function initializeArPayments(refreshInvoices, onPayments = () => {}) {
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
        save.textContent = creating ? 'Create Payment' : 'Save Changes';
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
        cell.textContent = message;
        row.append(cell);
        body.replaceChildren(row);
    }
    async function load(preserveDraft = false) {
        tableMessage('Loading incoming payments…');
        try {
            const payments = await request();
            if (!Array.isArray(payments)) throw new Error('Invalid payment list response');
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
                const choose = () => { if (!busy) { select(payment); status.textContent = 'Payment selected.'; } };
                row.addEventListener('click', choose);
                row.addEventListener('keydown', event => {
                    if (['Enter', ' '].includes(event.key)) { event.preventDefault(); choose(); }
                });
                return row;
            }));
            if (!payments.length) tableMessage('No incoming payments stored yet.');
            const updated = payments.find(payment => payment.id === selected?.id) ?? null;
            if (preserveDraft && active) {
                if (selected) selected = updated;
                for (const key of ['allocated_amount', 'unallocated_amount']) input(key).value = updated?.[key] ?? '';
                controls();
            } else select(updated);
            onPayments(payments);
            return true;
        } catch (error) {
            tableMessage('Could not load incoming payments.');
            status.textContent = error.message;
            return false;
        }
    }
    async function reload() {
        if (busy) return;
        busy = true; controls();
        try { await load(); } finally { busy = false; controls(); }
    }
    fresh.addEventListener('click', () => { select(null, true); status.textContent = 'Enter payment details.'; });
    cancel.addEventListener('click', () => { select(selected); status.textContent = 'Edit cancelled.'; });
    refresh.addEventListener('click', reload);
    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (busy || !active || !form.reportValidity()) return;
        const payload = {};
        for (const key of fields) {
            const value = input(key).value;
            if (!selected || value !== String(selected[key] ?? '')) payload[key] = value === '' && optional.has(key) ? null : value;
        }
        if (!Object.keys(payload).length) { status.textContent = 'No changes to save.'; return; }
        busy = true; controls(); status.textContent = 'Saving payment…';
        try {
            const saved = await request(selected ? `/${encodeURIComponent(selected.id)}` : '', selected ? 'PATCH' : 'POST', payload);
            select(saved);
            const loaded = await load();
            const invoicesRefreshed = await refreshInvoices();
            status.textContent = 'Payment saved.' + (loaded ? '' : ' Payment list refresh failed; click Refresh.')
                + (invoicesRefreshed ? '' : ' Invoice refresh deferred or failed; use invoice Refresh after finishing edits.');
        } catch (error) { status.textContent = `Could not save payment: ${error.message}`; }
        finally { busy = false; controls(); }
    });
    controls();
    void reload();
    return {async refresh() {
        if (busy) return false;
        busy = true; controls();
        try { return await load(true); } finally { busy = false; controls(); }
    }};
}
