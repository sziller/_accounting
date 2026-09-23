// Allocation facts come from the backend; no recognition/balance calculations.
export function initializeArAllocations(refresh) {
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
        remaining.textContent = payment ? `Available: ${payment.unallocated_amount} ${payment.currency}` : 'No compatible payment available.';
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
        busy = true; render(); status.textContent = 'Saving allocation…';
        try {
            await request(path, method, payload);
            const refreshed = await refresh();
            status.textContent = 'Allocation saved.' + (refreshed ? '' : ' Refresh failed or deferred; use Refresh.');
        } catch (error) { status.textContent = `Allocation failed: ${error.message}`; }
        finally { busy = false; render(); }
    }
    function render() {
        const selectedPayment = select.value;
        const compatible = invoice ? payments.filter(p => p.currency === invoice.currency && units(p.unallocated_amount) > 0n) : [];
        select.replaceChildren(...compatible.map(p => {
            const option = document.createElement('option'); option.value = p.id;
            option.textContent = `${p.payment_date} — ${p.payer_name ?? ''} / ${p.bank_reference ?? ''} — ${p.amount} ${p.currency} — available ${p.unallocated_amount} (${p.id})`;
            return option;
        }));
        if (compatible.some(p => p.id === selectedPayment)) select.value = selectedPayment;
        const closed = !invoice || units(invoice.outstanding_amount) <= 0n;
        select.disabled = amount.disabled = submit.disabled = busy || closed || !compatible.length;
        suggest();
        list.replaceChildren();
        if (!invoice || !invoice.allocations?.length) {
            list.textContent = invoice ? 'No allocations.' : 'Select an outgoing invoice.';
            return;
        }
        for (const allocation of invoice.allocations) {
            const payment = payments.find(p => p.id === allocation.payment_id);
            const row = document.createElement('li'); row.dataset.allocationId = allocation.id;
            const text = document.createElement('span');
            text.textContent = `${allocation.payment_date} — ${allocation.amount_allocated} ${invoice.currency} — ${payment?.payer_name ?? ''} / ${payment?.bank_reference ?? ''} — payment ${allocation.payment_id} `;
            const remove = document.createElement('button'); remove.type = 'button'; remove.textContent = 'Unallocate'; remove.disabled = busy;
            remove.addEventListener('click', () => {
                if (window.confirm(`Remove allocation of ${allocation.amount_allocated} ${invoice.currency}? The payment will remain.`))
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
