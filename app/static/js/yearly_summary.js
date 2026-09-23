// Read-only presentation: all accounting values and population decisions are server-owned.
const element = id => document.getElementById(id);
const year = element('summary-year');
const status = element('summary-status');
const results = element('summary-results');
let generation = 0;
year.value = String(new Date().getFullYear());

// Preserve exact decimal text, including legitimate sub-cent precision.
const money = (value, currency) => value == null ? 'Unavailable' : `${value}${currency ? ` ${currency}` : ''}`;
function table(bodyId, rows, emptyText, columns) {
    const body = element(bodyId);
    body.replaceChildren();
    if (!rows.length) {
        const row = body.insertRow(), cell = row.insertCell();
        cell.colSpan = columns; cell.textContent = emptyText;
    }
    for (const values of rows) {
        const row = body.insertRow();
        for (const value of values) row.insertCell().textContent = value ?? 'Unavailable';
    }
}
function render(summary) {
    const incomplete = summary.completeness === 'incomplete';
    element('summary-completeness').textContent = incomplete ? 'Incomplete preview' : 'Complete preview';
    element('summary-completeness').classList.toggle('summary-incomplete', incomplete);
    element('summary-currency').textContent = `Report currency: ${summary.report_currency ?? 'Unavailable'}`;
    element('summary-warnings').replaceChildren(...summary.warnings.map(warning => {
        const item = document.createElement('li');
        item.textContent = `${warning.message} (Count: ${warning.count})`;
        item.dataset.warningCode = warning.code;
        return item;
    }));
    const headlines = element('summary-headlines');
    headlines.replaceChildren();
    for (const [label, key] of [
        ['Recognized AR gross', 'recognized_ar_gross_common'],
        ['AP deductible gross', 'ap_expense_deductible_gross_common'],
        ['Gross-basis result', 'gross_basis_result'],
        ['AP deductible VAT', 'ap_deductible_vat_common'],
    ]) {
        const card = document.createElement('div'), title = document.createElement('dt'), value = document.createElement('dd');
        title.textContent = label; value.textContent = money(summary[key], summary.report_currency);
        value.dataset.summaryField = key;
        card.append(title, value); headlines.append(card);
    }
    element('summary-counts').textContent = `AP included: ${summary.ap_included_count} · AP excluded: ${summary.ap_excluded_count} · AP non-expense: ${summary.ap_non_expense_count} · AP unassigned year: ${summary.ap_unassigned_year_count} · AR recognition events: ${summary.ar_event_count} · AR common excluded: ${summary.ar_common_excluded_count}`;
    table('summary-ap-body', summary.ap_breakdown.map(group => [
        group.entry_type, group.category_code, group.tax_scope, group.currency_common,
        group.record_count, group.incomplete_count, money(group.amount_common), money(group.vat_amount),
        money(group.deductible_amount), money(group.deductible_vat_amount),
    ]), 'No AP records for this year.', 10);
    table('summary-ar-body', summary.ar_components_by_original_currency.map(group => [
        group.currency_original, group.event_count, money(group.recognized_gross_original),
        money(group.known_net_original), money(group.known_vat_original), group.missing_net_count, group.missing_vat_count,
    ]), 'No AR receipts recognized for this year.', 7);
}
async function loadSummary() {
    const current = ++generation;
    results.hidden = true;
    element('summary-view').setAttribute('aria-busy', 'false');
    if (!year.checkValidity()) {
        status.textContent = 'Enter a whole tax year from 1 to 9999.';
        return;
    }
    const requestedYear = year.value;
    status.textContent = `Loading ${requestedYear} summary…`;
    element('summary-view').setAttribute('aria-busy', 'true');
    try {
        const response = await fetch(`/acct/v0/yearly-accounting-summary/${encodeURIComponent(requestedYear)}`, {cache: 'no-store'});
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        const summary = await response.json();
        if (current !== generation) return;
        render(summary);
        results.hidden = false;
        status.textContent = `Summary for ${summary.tax_year}`;
    } catch (error) {
        if (current === generation) status.textContent = `Could not load yearly summary: ${error.message}. Use Refresh Summary to retry.`;
    } finally {
        if (current === generation) element('summary-view').setAttribute('aria-busy', 'false');
    }
}
year.addEventListener('change', loadSummary);
element('refresh-summary').addEventListener('click', loadSummary);
window.addEventListener('accounting-view-change', event => {
    if (event.detail === 'summary-view') loadSummary();
});
if (!element('summary-view').hidden) loadSummary();
