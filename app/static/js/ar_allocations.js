import {t} from "./i18n/i18n.js";
// Allocation facts come from the backend; no recognition/balance calculations.
export function initializeArAllocations(refresh) {
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
    const form = document.getElementById('ar-allocation-form');
    const list = document.getElementById('ar-allocation-list');
    const select = document.getElementById('ar-allocation-payment');
    const amount = document.getElementById('ar-allocation-amount');
    const submit = document.getElementById('allocate-ar-payment');
    const status = document.getElementById('ar-allocation-status');
    const remaining = document.getElementById('ar-allocation-remaining');
    let invoice = null, payments = [], busy = false;
    // Only compare exact API decimal strings for the suggested minimum.
    const units = value => { const [a,b=''] = String(value).split('.'); return BigInt(a) * 1000000n + BigInt(b.padEnd(6,'0')); };
    function suggest() {
        const payment = payments.find(p => p.id === select.value);
        setText(remaining, () => payment ? t("allocations.available").replace("{amount}", () => payment.unallocated_amount).replace("{currency}", () => payment.currency) : t("allocations.noCompatible"));
        amount.value = payment && invoice ? (units(payment.unallocated_amount) < units(invoice.outstanding_amount)
            ? payment.unallocated_amount : invoice.outstanding_amount) : '';
    }
    async function request(path, method, payload) {
        const response = await fetch(`/acct/v0/invoice-payment-allocations${path}`, {
            method, ...(payload ? {headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)} : {})});
        if (response.status === 204) return;
        const result = await response.json();
        if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : JSON.stringify(result.detail));
        return result;
    }
    async function mutate(path, method, payload) {
        if (busy) return;
        busy = true; render(); setText(status, () => t("allocations.saving"));
        try {
            await request(path, method, payload);
            const refreshed = await refresh();
            setText(status, () => t("allocations.saved") + (refreshed ? '' : t("allocations.refreshFailed")));
        } catch (error) { setText(status, () => t("allocations.failed").replace("{error}", () => error.message)); }
        finally { busy = false; render(); }
    }
    function render() {
        const selectedPayment = select.value;
        const compatible = invoice ? payments.filter(p => p.currency === invoice.currency && units(p.unallocated_amount) > 0n) : [];
        select.replaceChildren(...compatible.map(p => {
            const option = document.createElement('option'); option.value = p.id;
            setText(option, () => `${p.payment_date} — ${p.payer_name ?? ''} / ${p.bank_reference ?? ''} — ${p.amount} ${p.currency} — ${t("allocations.availableLabel")} ${p.unallocated_amount} (${p.id})`);
            return option;
        }));
        if (compatible.some(p => p.id === selectedPayment)) select.value = selectedPayment;
        const closed = !invoice || units(invoice.outstanding_amount) <= 0n;
        select.disabled = amount.disabled = submit.disabled = busy || closed || !compatible.length;
        suggest();
        localizedText.delete(list);
        list.replaceChildren();
        if (!invoice || !invoice.allocations?.length) {
            setText(list, () => invoice ? t("allocations.noAllocations") : t("ar.selectInvoice"));
            return;
        }
        for (const allocation of invoice.allocations) {
            const payment = payments.find(p => p.id === allocation.payment_id);
            const row = document.createElement('li'); row.dataset.allocationId = allocation.id;
            const text = document.createElement('span');
            setText(text, () => `${allocation.payment_date} — ${allocation.amount_allocated} ${invoice.currency} — ${payment?.payer_name ?? ''} / ${payment?.bank_reference ?? ''} — ${t("allocations.paymentLabel")} ${allocation.payment_id} `);
            const remove = document.createElement('button'); remove.type = 'button'; setText(remove, () => t("allocations.unallocate")); remove.disabled = busy;
            remove.addEventListener('click', () => {
                if (window.confirm(t("allocations.confirmRemoval").replace("{amount}", () => allocation.amount_allocated).replace("{currency}", () => invoice.currency)))
                    void mutate(`/${encodeURIComponent(allocation.id)}`, 'DELETE');
            });
            row.append(text, remove); list.append(row);
        }
    }
    select.addEventListener('change', suggest);
    form.addEventListener('submit', event => {
        event.preventDefault();
        if (submit.disabled || !form.reportValidity()) return;
        void mutate('', 'POST', {invoice_id:invoice.id, payment_id:select.value, amount_allocated:amount.value});
    });
    render();
    return {setInvoice(value) { invoice=value; render(); }, setPayments(value) { payments=value; render(); }};
}
