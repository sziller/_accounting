// Backend events only: no recognition arithmetic, sorting, or date inference.
export function initializeArRecognition() {
    const body = document.getElementById('ar-recognition-body');
    const note = document.getElementById('ar-recognition-note');
    let generation = 0;
    function message(text) {
        const row = document.createElement('tr'), cell = document.createElement('td');
        cell.colSpan = 7; cell.textContent = text; row.append(cell); body.replaceChildren(row);
    }
    const money = (value, currency) => value == null ? '—' : `${value} ${currency}`;
    return async invoice => {
        const current = ++generation;
        note.textContent = '';
        if (!invoice) { message('Select an outgoing invoice.'); return; }
        message('Loading recognition…');
        try {
            const response = await fetch(`/acct/v0/outgoing-invoices/${encodeURIComponent(invoice.id)}/recognition-events`, {cache:'no-store'});
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const events = await response.json();
            if (!Array.isArray(events)) throw new Error('Invalid recognition response');
            if (current !== generation) return;
            if (!events.length) { message('No receipt recognized yet'); return; }
            note.textContent = events.some(event => event.source === 'allocation')
                ? 'Detailed payment allocations are used for recognition.'
                : 'No detailed allocations exist. Payment Received Date recognizes the whole invoice.';
            body.replaceChildren(...events.map(event => {
                const row = document.createElement('tr');
                for (const value of [event.recognition_date, event.tax_year,
                    money(event.amount_original, event.currency_original),
                    money(event.net_amount_original, event.currency_original),
                    money(event.vat_amount_original, event.currency_original),
                    money(event.amount_common, invoice.currency_common),
                    event.source === 'manual_invoice_payment' ? 'Manual full-payment date' : 'Payment allocation']) {
                    const cell = document.createElement('td'); cell.textContent = value; row.append(cell);
                }
                if (event.payment_id) row.title = `Payment ${event.payment_id}; allocation ${event.allocation_id}`;
                return row;
            }));
        } catch (error) {
            if (current === generation) message(`Could not load recognition events: ${error.message}`);
        }
    };
}
