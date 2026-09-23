// Run with Node 22+ and an isolated Chromium browser listening on CDP port 9223:
// node tests/frontend/source_image_viewer.mjs
// Serves the real frontend with fixture API responses; never modifies the database.
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import {createServer} from "node:http";

const root = new URL("../../", import.meta.url);
const jpeg = await readFile(new URL("app/static/Accounting-LogoBitbucket.jpg", root));
let secondJpeg;
const entries = ["IMG_4821.JPG", "My Receipt #02.jpeg", null, "missing.jpg"].map(
    (source_filename, index) => ({
        id: String(index + 1), source_filename, counterparty_name: `Vendor ${index + 1}`,
        payment_date: "2026-09-21", category_code: "buro", currency_common: "EUR",
        tags: [], entry_type: "expense", tax_scope: "domestic", payment_method: "bank_transfer",
        currency_original: "EUR", amount_original: "10.00", has_invoice: true,
        invoice_date: "2026-09-21", invoice_number: `AP-${index + 1}`,
    }),
);
const requests = [];
let arMode = "normal";
let blockFeatureModule = false;
let arDelay = 0;
let arProcessFailure = false;
let arProcessCalls = 0;
let arNormalizeCalls = 0;
let arNormalizeFailure = false;
const arRequests = [];
const arPatches = [];
const paymentWrites = [];
let paymentReject = false;
let payments = [{id:'payment-1', payment_date:'2026-01-01', amount:'100.00', currency:'EUR',
    payer_name:'Payer', bank_reference:'REF', payment_method:'bank_transfer', remarks:null,
    allocated_amount:'40.00', unallocated_amount:'60.00', allocations:[]}];
let allocationFacts = [];
let allocationSequence = 0;
let recognitionFailure = false;
let summaryMode = 'normal';
const summaryRequests = [];
const summaryFixture = year => ({
    tax_year: year, report_currency: 'CHF', completeness: 'complete',
    ap_included_count: 7, ap_excluded_count: 2, ap_non_expense_count: 1, ap_unassigned_year_count: 0,
    ar_event_count: 4, ar_common_excluded_count: 0,
    recognized_ar_gross_common: '123456789012345678.123456', ap_expense_deductible_gross_common: '10.00',
    gross_basis_result: '987.006', ap_deductible_vat_common: '1.2300',
    warnings: [{code:'freshness',count:0,message:'Freshness cannot be proven.'}],
    ap_breakdown: ['expense','income'].map(entry_type => ({entry_type,category_code:'buro',tax_scope:'domestic',
        currency_common:'CHF',record_count:1,incomplete_count:0,amount_common:'10.00',vat_amount:'1.90',
        deductible_amount:'7.00',deductible_vat_amount:'1.33'})),
    ar_components_by_original_currency: ['EUR','USD'].map(currency_original => ({currency_original,event_count:2,
        recognized_gross_original:'100.00',known_net_original:currency_original==='USD'?null:'80.00',
        known_vat_original:'20.006',missing_net_count:currency_original==='USD'?2:0,missing_vat_count:1})),
});
function refreshAllocationFixtures() {
    for (const invoice of arInvoices.filter(i => i.id.startsWith('allocation-'))) {
        invoice.allocations = allocationFacts.filter(a=>a.invoice_id===invoice.id).map(a=>({...a,
            payment_date:payments.find(p=>p.id===a.payment_id).payment_date}));
        invoice.paid_amount = String(invoice.allocations.reduce((sum,a)=>sum+Number(a.amount_allocated),0));
        invoice.outstanding_amount = String(Number(invoice.gross_amount)-Number(invoice.paid_amount));
        invoice.payment_status = Number(invoice.outstanding_amount)===0 ? 'paid' : Number(invoice.paid_amount)>0 ? 'partially_paid' : 'open';
    }
    for (const payment of payments.filter(p=>p.id.startsWith('alloc-'))) {
        payment.allocated_amount=String(allocationFacts.filter(a=>a.payment_id===payment.id).reduce((sum,a)=>sum+Number(a.amount_allocated),0));
        payment.unallocated_amount=String(Number(payment.amount)-Number(payment.allocated_amount));
    }
}
let rejectArPatch = false;
const writes = [];
const arInvoice = {id: "ar-1", invoice_number: "2701", invoice_date: "2026-09-15", customer_name: "Customer <literal>",
    currency: "USD", gross_amount: "123456789012345678.123456",
    currency_original: "USD", amount_original: "123456789012345678.123456", currency_common: "EUR", amount_common: null, paid_amount: "1.00",
    outstanding_amount: "123456789012345677.123456", payment_status: "partially_paid", pdf_filename: "Source One.PDF"};
let arInvoices = [arInvoice];
const server = createServer(async (req, res) => {
    const path = new URL(req.url, "http://localhost").pathname;
    if (blockFeatureModule && path === "/static/js/accounting_entries.js") {
        res.writeHead(503);
        return res.end("Feature module unavailable");
    }
    const json = value => {res.setHeader("Content-Type", "application/json"); res.end(JSON.stringify(value));};
    if (path.startsWith('/acct/v0/yearly-accounting-summary/')) {
        summaryRequests.push({path,method:req.method});
        if (summaryMode==='error') {res.statusCode=503; return json({detail:'Unavailable'});}
        const data=summaryFixture(Number(path.split('/').at(-1)));
        if (summaryMode==='incomplete') Object.assign(data,{completeness:'incomplete',report_currency:null,
            gross_basis_result:null,recognized_ar_gross_common:null,
            warnings:[{code:'currency_mismatch',count:2,message:'Common currencies disagree: EUR, USD.'}]});
        if (summaryMode==='empty') Object.assign(data,{report_currency:null,ap_included_count:0,ap_excluded_count:0,
            ap_non_expense_count:0,ar_event_count:0,ap_breakdown:[],ar_components_by_original_currency:[],
            recognized_ar_gross_common:'0',ap_expense_deductible_gross_common:'0',gross_basis_result:'0',ap_deductible_vat_common:'0'});
        return json(data);
    }
    if (path.startsWith('/acct/v0/invoice-payment-allocations')) {
        if (req.method==='DELETE') {
            allocationFacts=allocationFacts.filter(a=>!path.endsWith('/'+a.id));
            refreshAllocationFixtures(); res.statusCode=204; return res.end();
        }
        let raw=''; for await (const chunk of req) raw+=chunk;
        const data=JSON.parse(raw);
        const invoice=arInvoices.find(i=>i.id===data.invoice_id), payment=payments.find(p=>p.id===data.payment_id);
        const fail = detail => {res.statusCode=400; return json({detail});};
        if (payment.currency!==invoice.currency) return fail('Invoice and payment currencies must match');
        if (Number(data.amount_allocated)>Number(invoice.outstanding_amount)) return fail('Allocation exceeds invoice outstanding amount');
        if (Number(data.amount_allocated)>Number(payment.unallocated_amount)) return fail('Allocation exceeds payment remaining amount');
        const allocation={...data,id:`allocation-${++allocationSequence}`};
        allocationFacts.push(allocation); refreshAllocationFixtures(); return json(allocation);
    }
    if (path.startsWith('/acct/v0/incoming-payments')) {
        if (req.method === 'GET') return json(payments);
        let raw = '';
        for await (const chunk of req) raw += chunk;
        const payload = JSON.parse(raw);
        paymentWrites.push({method:req.method, path, payload});
        if (paymentReject) {res.statusCode=400; return json({detail:'amount cannot be less than existing allocations'});}
        if (req.method === 'POST') {
            const payment = {...payload,id:'payment-2',allocated_amount:'0',unallocated_amount:payload.amount,allocations:[]};
            payments.push(payment); return json(payment);
        }
        const index = payments.findIndex(payment => path.endsWith('/'+payment.id));
        payments[index] = {...payments[index],...payload};
        refreshAllocationFixtures();
        return json(payments[index]);
    }
    if (path.startsWith("/acct/v0/outgoing-invoices")) {
        if (path.endsWith('/recognition-events')) {
            if (recognitionFailure) {res.statusCode=503; return json({detail:'Recognition unavailable'});}
            const invoice=arInvoices.find(i=>i.id===decodeURIComponent(path.split('/').at(-2)));
            if (!invoice) {res.statusCode=404; return json({detail:'Not found'});}
            const base={invoice_id:invoice.id,currency_original:invoice.currency_original,
                net_amount_original:null,vat_amount_original:'0.006',amount_common:'1.234567'};
            return json(invoice.allocations?.length ? invoice.allocations.map(a=>({...base,
                recognition_date:a.payment_date,tax_year:Number(a.payment_date.slice(0,4)),amount_original:a.amount_allocated,
                source:'allocation',payment_id:a.payment_id,allocation_id:a.id}))
                : invoice.payment_date ? [{...base,recognition_date:invoice.payment_date,
                    tax_year:Number(invoice.payment_date.slice(0,4)),amount_original:invoice.gross_amount,
                    source:'manual_invoice_payment',payment_id:null,allocation_id:null}] : []);
        }
        arRequests.push({path, method: req.method});
        if (path.endsWith("/process")) {
            assert.equal(req.method, "POST");
            const id = path.split("/").at(-2);
            const invoice = arInvoices.find(invoice => invoice.id === id);
            invoice.amount_common = invoice.amount_original;
            return json({id, invoice_number:invoice.invoice_number, status:"processed", message:"Recalculated", entry:invoice});
        }
        if (path.endsWith("/process-entries")) {
            arNormalizeCalls++;
            assert.equal(req.method, "POST");
            let body = "";
            for await (const chunk of req) body += chunk;
            assert.equal(body, "");
            await new Promise(resolve => setTimeout(resolve, 200));
            if (arNormalizeFailure) {res.statusCode=503; return json({detail:"Database is busy; retry the request"});}
            arInvoices = arInvoices.map(invoice => ({...invoice,
                amount_common: invoice.currency_original === invoice.currency_common ? invoice.amount_original : null}));
            const invoices = arInvoices.map(invoice => ({...invoice,
                status: invoice.amount_common === null ? "failed" : "processed",
                message: invoice.amount_common === null ? "Unsupported conversion: USD → EUR." : "Identical currencies."}));
            return json({processed:invoices.filter(i=>i.status === "processed").length,
                failed:invoices.filter(i=>i.status === "failed").length, invoices});
        }
        if (req.method === "PATCH") {
            let raw = "";
            for await (const chunk of req) raw += chunk;
            const payload = JSON.parse(raw);
            arPatches.push(payload);
            if (rejectArPatch) {res.statusCode = 400; return json({detail: "gross_amount cannot be less than existing allocations"});}
            const index = arInvoices.findIndex(invoice => path.endsWith(`/${invoice.id}`));
            arInvoices[index] = {...arInvoices[index], ...payload};
            return json(arInvoices[index]);
        }
        if (path.endsWith("/process-directory")) {
            arProcessCalls++;
            let body = "";
            for await (const chunk of req) body += chunk;
            assert.equal(body, "");
            assert.equal(req.method, "POST");
            await new Promise(resolve => setTimeout(resolve, 200));
            if (arProcessFailure) {res.statusCode = 503; return json({detail: "Import unavailable"});}
            arInvoices = [arInvoice, {...arInvoice, id: "ar-2", invoice_number: "2702", pdf_filename: "New.pdf"}];
            return json({imported: 1, already_imported: 1, failed: 1, files: [
                {filename: "Source One.PDF", status: "already_imported"},
                {filename: "New.pdf", status: "imported"},
                {filename: "Broken.pdf", status: "failed", error: "gross amount not found"},
            ]});
        }
        await new Promise(resolve => setTimeout(resolve, arDelay));
        if (arMode === "error") {res.statusCode = 503; return json({detail: "Unavailable"});}
        if (path.endsWith("/source-files")) return json({directory: "AR_invoice_pdf", files: arMode === "empty" ? [] : ["Source One.PDF", "New.pdf"]});
        return json(arMode === "empty" ? [] : arInvoices);
    }
    if (path === "/acct/v0/metadata") return json({entry_types: ["expense"], tax_scopes: ["domestic"], payment_methods: ["bank_transfer"], currencies: ["EUR"], categories: [{code:"buro",label:"Office"}]});
    if (req.method === "POST" || req.method === "PUT") {
        let raw = ""; for await (const chunk of req) raw += chunk;
        const payload = raw ? JSON.parse(raw) : null;
        writes.push({path, payload, method: req.method});
        if (path.endsWith("/process")) {
            const all = path === "/acct/v0/entries/process";
            const selected = all ? entries : entries.filter(entry => path === `/acct/v0/entries/${entry.id}/process`);
            for (const entry of selected) Object.assign(entry, {amount_common:"10.00", vat_amount:"1.60", deductible_amount:"10.00"});
            return json(all ? {processed:selected.length, failed:0, entries:selected.map(entry => ({id:entry.id,status:"processed",message:"Recalculated"}))}
                : {id:selected[0].id,status:"processed",message:"Recalculated",entry:selected[0]});
        }
        if (path.endsWith("/batch")) return json(payload.entries.map((entry, i) => ({...entry,id:`batch-${i}`})));
        return json({...payload, id: path.split("/").at(-1) === "entries" ? "created" : path.split("/").at(-1)});
    }
    if (path.endsWith("entry-create-contract")) return json({fixture_contract:true, entries:[]});
    if (path === "/acct/v0/entries") return json(entries);
    if (path.startsWith("/acct/v0/entries/")) return json(entries.find(entry => path.endsWith(`/${entry.id}`)));
    if (path.startsWith("/acct/v0/source-images/")) {
        requests.push(req.url);
        if (path.endsWith("missing.jpg")) {res.writeHead(404); return res.end();}
        res.setHeader("Content-Type", "image/jpeg");
        return res.end(path.endsWith(".jpeg") ? secondJpeg : jpeg);
    }
    const file = path === "/" ? "app/templates/index.html" : `app${path}`;
    if (path !== "/" && !path.startsWith("/static/")) {res.writeHead(404); return res.end();}
    try {
        const body = await readFile(new URL(file, root));
        res.setHeader("Content-Type", path.endsWith(".js") ? "text/javascript" : path.endsWith(".css") ? "text/css" : "text/html");
        res.end(body);
    } catch {res.writeHead(404); res.end();}
});
await new Promise(resolve => server.listen(0, "127.0.0.1", resolve));
const origin = `http://127.0.0.1:${server.address().port}`;
const target = await (await fetch("http://127.0.0.1:9223/json/new?about:blank", {method: "PUT"})).json();
const socket = new WebSocket(target.webSocketDebuggerUrl);
await new Promise(resolve => socket.addEventListener("open", resolve, {once: true}));
let sequence = 0;
const pending = new Map();
const responses = [];
const runtimeErrors = [];
socket.addEventListener("message", ({data}) => {
    const message = JSON.parse(data);
    if (message.id) {
        const {resolve, reject} = pending.get(message.id);
        pending.delete(message.id);
        if (message.error) reject(new Error(JSON.stringify(message.error)));
        else resolve(message.result);
    } else if (message.method === "Network.responseReceived") responses.push(message.params.response);
    else if (message.method === "Runtime.exceptionThrown") runtimeErrors.push(message.params.exceptionDetails);
});
function command(method, params = {}) {
    return new Promise((resolve, reject) => {
        const id = ++sequence;
        pending.set(id, {resolve, reject});
        socket.send(JSON.stringify({id, method, params}));
    });
}
async function evaluate(expression) {
    const result = await command("Runtime.evaluate", {expression, returnByValue: true, awaitPromise: true});
    assert.equal(result.exceptionDetails, undefined, JSON.stringify(result.exceptionDetails));
    return result.result.value;
}
async function waitFor(expression) {
    for (let attempt = 0; attempt < 100; attempt++) {
        if (await evaluate(expression)) return;
        await new Promise(resolve => setTimeout(resolve, 50));
    }
    throw new Error(`Timed out: ${expression}; message=${await evaluate('document.getElementById("message")?.textContent')}; errors=${JSON.stringify(runtimeErrors)}`);
}
const image = 'document.getElementById("source-image")';
const click = selector => evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`);
const transform = () => evaluate(`(() => {
    const m = new DOMMatrix(getComputedStyle(${image}).transform);
    return {scale: m.a, x: m.e, y: m.f};
})()`);
const assertFit = async () => assert.deepEqual(await transform(), {scale: 1, x: 0, y: 0});
try {
    secondJpeg = Buffer.from(await evaluate(`(() => {
        const canvas = document.createElement("canvas");
        canvas.width = 40; canvas.height = 80;
        const context = canvas.getContext("2d");
        context.fillStyle = "#cc3300"; context.fillRect(0, 0, 40, 80);
        return canvas.toDataURL("image/jpeg").split(",")[1];
    })()`), "base64");
    await command("Network.enable");
    await command("Runtime.enable");
    await command("Emulation.setDeviceMetricsOverride", {width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false});
    await command("Page.navigate", {url: origin});
    await waitFor('document.querySelectorAll(".entry-row").length === 4');
    assert.equal(await evaluate('location.hash'), "#ap");
    assert.deepEqual(await evaluate('Array.from(document.querySelectorAll(".view-nav-button"), e=>e.textContent.trim())'),
        ["Accounts Payable", "Accounts Receivable", "New Entries", "Gewinnermittlung"]);
    assert.equal(await evaluate('document.querySelector("#input-view #ar-invoice-import-panel")'), null);
    await waitFor('document.getElementById("ar-invoice-db-count").textContent === "1 record"');
    assert.equal(await evaluate('document.querySelectorAll("#ar-invoice-file-list li").length'), 2);
    assert.deepEqual(await evaluate('Array.from(document.querySelectorAll("#ar-invoice-db-body td"), cell => cell.textContent)'),
        [arInvoice.invoice_number, arInvoice.invoice_date, arInvoice.customer_name, arInvoice.currency,
            arInvoice.gross_amount, arInvoice.paid_amount, arInvoice.outstanding_amount, arInvoice.payment_status, arInvoice.pdf_filename, "EUR", "pending"]);
    assert.equal(arProcessCalls, 0);
    await click('.entry-row[data-entry-id="1"]');
    await waitFor(`${image}.naturalWidth > 0 && !${image}.hidden`);
    assert.equal(await evaluate(`${image}.src`), `${origin}/acct/v0/source-images/IMG_4821.JPG`);
    const dimensions = await evaluate(`(() => {
        const img = ${image}; const bounds = img.getBoundingClientRect();
        const frame = img.parentElement.getBoundingClientRect(); const css = getComputedStyle(img);
        return {width: bounds.width, height: bounds.height, frameWidth: frame.width, frameHeight: frame.height,
            inside: bounds.top >= frame.top && bounds.bottom <= frame.bottom && bounds.left >= frame.left && bounds.right <= frame.right,
            display: css.display, visibility: css.visibility, opacity: css.opacity, fit: css.objectFit};
    })()`);
    assert.ok(dimensions.width > 0 && dimensions.height > 0);
    assert.ok(dimensions.inside);
    assert.notEqual(dimensions.display, "none");
    assert.equal(dimensions.visibility, "visible");
    assert.equal(dimensions.opacity, "1");
    assert.equal(dimensions.fit, "contain");
    console.log("Rendered image:", dimensions);
    const response = responses.find(item => item.url.endsWith("/source-images/IMG_4821.JPG"));
    assert.equal(response.status, 200);
    assert.equal(response.mimeType, "image/jpeg");
    const screenshot = await command("Page.captureScreenshot", {format: "png"});
    const {writeFile} = await import("node:fs/promises");
    await writeFile("/tmp/accounting-source-viewer.png", Buffer.from(screenshot.data, "base64"));

    await assertFit();
    const layout = () => evaluate(`JSON.stringify([
        document.querySelector('.source-image-card').getBoundingClientRect().toJSON(),
        document.querySelector('.entries-card').getBoundingClientRect().toJSON(),
        document.documentElement.scrollWidth
    ])`);
    const beforeLayout = await layout();
    await click("#source-image-zoom-in");
    assert.equal((await transform()).scale, 1.25);
    await click("#source-image-zoom-out");
    await assertFit();
    await click("#source-image-zoom-out");
    await assertFit();
    for (let i = 0; i < 40; i++) await click("#source-image-zoom-in");
    assert.equal((await transform()).scale, 10);
    assert.equal(await evaluate('document.getElementById("source-image-zoom-in").disabled'), true);
    const center = await evaluate(`(() => {const r = document.getElementById('source-image-frame').getBoundingClientRect(); return {x:r.x+r.width/2,y:r.y+r.height/2};})()`);
    await command("Input.dispatchMouseEvent", {type: "mousePressed", ...center, button: "left", clickCount: 1});
    await command("Input.dispatchMouseEvent", {type: "mouseMoved", x: center.x + 350, y: center.y + 300, button: "left", buttons: 1});
    await waitFor(`new DOMMatrix(getComputedStyle(${image}).transform).f > 0`);
    assert.equal(await evaluate('getComputedStyle(document.getElementById("source-image-frame")).cursor'), "grabbing");
    await command("Input.dispatchMouseEvent", {type: "mouseReleased", x: center.x + 350, y: center.y + 300, button: "left", clickCount: 1});
    assert.ok((await transform()).y > 0);
    // Actual contained image must still cover the viewport on enlarged axes.
    assert.equal(await evaluate(`(() => {
        const img = ${image}; const m = new DOMMatrix(getComputedStyle(img).transform);
        const fit = Math.min(img.clientWidth/img.naturalWidth, img.clientHeight/img.naturalHeight);
        return Math.abs(m.e) <= Math.max(0,(img.naturalWidth*fit*m.a-img.clientWidth)/2)+0.01
            && Math.abs(m.f) <= Math.max(0,(img.naturalHeight*fit*m.a-img.clientHeight)/2)+0.01;
    })()`), true);
    assert.equal(await layout(), beforeLayout);
    await click("#source-image-reset");
    await assertFit();
    await command("Input.dispatchMouseEvent", {type: "mouseWheel", ...center, deltaX: 0, deltaY: -100, modifiers: 2});
    await waitFor(`new DOMMatrix(getComputedStyle(${image}).transform).a === 1.25`);
    const scrollBefore = await evaluate("window.scrollY");
    await command("Input.dispatchMouseEvent", {type: "mouseWheel", ...center, deltaX: 0, deltaY: 150});
    await waitFor(`window.scrollY > ${scrollBefore}`);
    assert.equal((await transform()).scale, 1.25);
    await evaluate('window.scrollTo(0,0); document.getElementById("source-image-frame").focus({preventScroll:true})');
    for (const [key, scale] of [["+", 1.5], ["-", 1.25], ["0", 1]]) {
        await command("Input.dispatchKeyEvent", {type: "keyDown", key});
        await command("Input.dispatchKeyEvent", {type: "keyUp", key});
        assert.equal((await transform()).scale, scale);
    }
    await click("#unlock-entry-edit");
    await evaluate('document.getElementById("detail_counterparty_name").focus()');
    await command("Input.dispatchKeyEvent", {type: "keyDown", key: "+", text: "+"});
    await command("Input.dispatchKeyEvent", {type: "keyUp", key: "+"});
    await assertFit();
    await click("#source-image-zoom-in");

    await click("#next-source-image");
    await waitFor(`${image}.getAttribute("src") === "/acct/v0/source-images/My%20Receipt%20%2302.jpeg" && !${image}.hidden`);
    assert.equal(await evaluate(`${image}.naturalWidth`), 40);
    assert.equal(await evaluate(`${image}.naturalHeight`), 80);
    await assertFit();
    assert.equal(await evaluate('document.getElementById("source-image-filename").textContent'), entries[1].source_filename);
    assert.equal(await evaluate('document.getElementById("detail_id").value'), "2");
    assert.equal(await evaluate('document.querySelector(".entry-row.is-selected").dataset.entryId'), "2");
    await click("#next-source-image");
    await waitFor('document.getElementById("detail_id").value === "3"');
    assert.equal(await evaluate(`${image}.hidden && !${image}.hasAttribute("src")`), true);
    await assertFit();
    assert.equal(await evaluate('document.getElementById("source-image-zoom-in").disabled && document.getElementById("source-image-reset").disabled'), true);
    await click("#previous-source-image");
    await waitFor('document.getElementById("detail_id").value === "2" && !document.getElementById("source-image").hidden');
    await assertFit();
    await click("#source-image-zoom-in");
    await click('.entry-row[data-entry-id="4"]');
    await waitFor('document.getElementById("source-image-empty").textContent === "Unable to load source image."');
    assert.equal(await evaluate(`${image}.hidden`), true);
    await assertFit();
    assert.equal(await evaluate('document.getElementById("source-image-zoom-in").disabled'), true);
    await click('.entry-row[data-entry-id="1"]');
    await waitFor('document.getElementById("detail_id").value === "1" && !document.getElementById("source-image").hidden');
    await click("#source-image-zoom-in");
    await click('.entry-row[data-entry-id="2"]');
    await waitFor('document.getElementById("detail_id").value === "2" && !document.getElementById("source-image").hidden');
    await assertFit();
    await click("#source-image-zoom-in");
    await click("#previous-source-image");
    await waitFor('document.getElementById("detail_id").value === "1" && !document.getElementById("source-image").hidden');
    await assertFit();
    await click("#show-input-view");
    assert.equal(await evaluate('document.getElementById("process-view").hidden && !document.getElementById("input-view").hidden'), true);
    await click("#show-process-view");
    assert.equal(await evaluate(`!document.getElementById("process-view").hidden && !${image}.hidden`), true);
    assert.ok(requests.includes("/acct/v0/source-images/My%20Receipt%20%2302.jpeg"));
    await click("#show-ar-view");
    assert.equal(await evaluate('location.hash'), "#ar");
    assert.equal(await evaluate(`(() => {
        const files = document.getElementById("ar-invoice-import-panel").getBoundingClientRect();
        const rows = document.querySelector(".ar-invoices-card").getBoundingClientRect();
        const editor = document.querySelector(".ar-editor-column").getBoundingClientRect();
        return editor.right <= files.left && editor.right <= rows.left && files.bottom <= rows.top;
    })()`), true, "AR editor sits left of PDFs and selectable invoices");
    await click('[data-invoice-id="ar-1"]');
    await waitFor('document.getElementById("ar-recognition-body").textContent.includes("No receipt recognized yet")');
    assert.equal(await evaluate('document.getElementById("ar-invoice-invoice_number").value'), "2701");
    assert.equal(await evaluate('document.querySelector(".ar-db-table .is-selected").dataset.invoiceId'), "ar-1");
    assert.equal(await evaluate('document.getElementById("ar-invoice-amount_original").disabled'), true);
    await click("#unlock-ar-invoice-edit");
    assert.equal(await evaluate('document.getElementById("ar-invoice-amount_original").disabled'), false);
    assert.equal(await evaluate('document.getElementById("ar-invoice-paid_amount").readOnly'), true);
    assert.equal(await evaluate('document.getElementById("ar-invoice-amount_common").readOnly'), true);
    assert.equal(await evaluate('document.getElementById("normalize-ar-invoices").disabled'), true);
    assert.equal(await evaluate('document.getElementById("process-ar-entry").disabled'), true);
    await evaluate('document.getElementById("ar-invoice-customer_name").value = "Discard me"');
    await click("#cancel-ar-invoice-edit");
    assert.equal(await evaluate('document.getElementById("ar-invoice-customer_name").value'), arInvoice.customer_name);
    assert.equal(arPatches.length, 0);
    await click("#unlock-ar-invoice-edit");
    await evaluate('document.getElementById("ar-invoice-remarks").value = "Reviewed"');
    await click("#save-ar-invoice-edit");
    await waitFor('document.getElementById("ar-invoice-editor-status").textContent.startsWith("Saved invoice:")');
    assert.deepEqual(arPatches[0], {remarks:"Reviewed"});
    assert.equal(await evaluate('document.getElementById("ar-invoice-remarks").value'), "Reviewed");
    assert.equal(await evaluate('document.getElementById("ar-invoice-remarks").disabled'), true);
    assert.equal(await evaluate('document.getElementById("ar-invoice-payment_date").value'), "");
    for (const value of ["2025-12-31", "2026-10-01", ""]) {
        await click("#unlock-ar-invoice-edit");
        await evaluate(`document.getElementById("ar-invoice-payment_date").value = ${JSON.stringify(value)}`);
        await click("#save-ar-invoice-edit");
        await waitFor('!document.getElementById("unlock-ar-invoice-edit").disabled && document.getElementById("ar-invoice-payment_date").disabled');
        assert.deepEqual(arPatches.at(-1), {payment_date: value || null});
        assert.equal(await evaluate('document.getElementById("ar-invoice-payment_date").value'), value);
        assert.equal(await evaluate('document.getElementById("ar-invoice-invoice_date").value'), "2026-09-15");
        await waitFor(value ? `document.getElementById('ar-recognition-body').textContent.includes('${value}')`
            : 'document.getElementById("ar-recognition-body").textContent.includes("No receipt recognized yet")');
        if (value) {
            assert.ok(await evaluate('document.getElementById("ar-recognition-body").textContent.includes("Manual full-payment date")'));
            assert.ok(await evaluate('document.getElementById("ar-recognition-body").textContent.includes("1.234567 EUR")'));
            assert.ok(await evaluate('document.getElementById("ar-recognition-body").textContent.includes("0.006 USD")'));
        }
    }
    rejectArPatch = true;
    await click("#unlock-ar-invoice-edit");
    await evaluate('document.getElementById("ar-invoice-amount_original").value = "0.50"');
    await click("#save-ar-invoice-edit");
    await waitFor('document.getElementById("ar-invoice-editor-status").textContent.includes("existing allocations")');
    assert.equal(await evaluate('document.getElementById("ar-invoice-amount_original").disabled'), false);
    assert.equal(await evaluate('document.getElementById("ar-invoice-amount_original").value'), "0.50");
    await click("#cancel-ar-invoice-edit");
    rejectArPatch = false;
    await click('[data-pdf-filename="Source One.PDF"]');
    assert.equal(await evaluate('document.querySelector(".ar-db-table .is-selected").dataset.invoiceId'), "ar-1");
    await click('[data-pdf-filename="New.pdf"]');
    assert.equal(await evaluate('document.getElementById("ar-invoice-editor-status").textContent.startsWith("No persisted")'), true);
    arDelay = 200;
    const beforeRefresh = arRequests.length;
    await click("#refresh-ar-invoice-files");
    assert.equal(await evaluate('document.getElementById("ar-invoice-file-list").textContent'), "Loading PDFs…");
    assert.equal(await evaluate('document.getElementById("ar-invoice-db-body").textContent'), "Loading outgoing invoices…");
    await waitFor('!document.getElementById("refresh-ar-invoice-files").disabled');
    assert.equal(arRequests.length, beforeRefresh + 2);
    assert.equal(arProcessCalls, 0);
    await click("#process-ar-invoice-directory");
    assert.equal(await evaluate('document.getElementById("process-ar-invoice-directory").disabled'), true);
    assert.equal(await evaluate('document.getElementById("ar-invoice-import-status").textContent'), "Processing…");
    await waitFor('!document.getElementById("process-ar-invoice-directory").disabled');
    assert.equal(arProcessCalls, 1);
    assert.equal(await evaluate('document.getElementById("ar-invoice-db-count").textContent'), "2 records");
    assert.equal(await evaluate('document.getElementById("ar-invoice-import-status").textContent'),
        "Source One.PDF — already imported\nNew.pdf — imported\nBroken.pdf — failed: gross amount not found");
    assert.deepEqual(arRequests.slice(-2).map(item => item.path).sort(),
        ["/acct/v0/outgoing-invoices", "/acct/v0/outgoing-invoices/source-files"]);
    await click("#next-ar-invoice");
    assert.equal(await evaluate('document.getElementById("ar-invoice-invoice_number").value'), "2702");
    await click("#previous-ar-invoice");
    assert.equal(await evaluate('document.getElementById("ar-invoice-invoice_number").value'), "2701");
    arMode = "empty";
    await click("#refresh-ar-invoice-files");
    await waitFor('!document.getElementById("refresh-ar-invoice-files").disabled');
    assert.equal(await evaluate('document.getElementById("ar-invoice-file-list").textContent'), "No PDFs found.");
    assert.equal(await evaluate('document.getElementById("ar-invoice-db-body").textContent'), "No outgoing invoices stored yet.");
    assert.equal(await evaluate('document.getElementById("ar-invoice-invoice_number").value'), "");
    assert.equal(await evaluate('document.getElementById("unlock-ar-invoice-edit").disabled'), true);
    arMode = "error";
    await click("#refresh-ar-invoice-files");
    await waitFor('!document.getElementById("refresh-ar-invoice-files").disabled');
    assert.equal(await evaluate('document.getElementById("ar-invoice-file-list").textContent'), "Could not load source PDFs.");
    assert.equal(await evaluate('document.getElementById("ar-invoice-db-body").textContent'), "Could not load outgoing invoices.");
    arMode = "normal";
    arProcessFailure = true;
    await click("#process-ar-invoice-directory");
    await waitFor('!document.getElementById("process-ar-invoice-directory").disabled');
    assert.equal(await evaluate('document.getElementById("ar-invoice-import-status").textContent'), "Could not process AR invoice directory: Import unavailable");
    assert.equal(await evaluate('document.getElementById("ar-invoice-db-count").textContent'), "2 records");
    await click("#show-input-view");
    assert.equal(await evaluate('location.hash'), "#new");
    await evaluate(`(() => {
        const form=document.getElementById('entry-form');
        form.elements.counterparty_name.value='Manual vendor';
        form.elements.payment_date.value='2026-09-21';
        form.elements.amount_original.value='12.34';
        form.elements.invoice_date.value='2026-09-21';
        form.elements.invoice_number.value='MANUAL-1';
        form.requestSubmit();
    })()`);
    await waitFor('document.getElementById("message").textContent.startsWith("Saved entry:")');
    assert.equal(writes.at(-1).payload.amount_original, "12.34");
    await click("#load-example-json");
    await click("#submit-json");
    await waitFor('document.getElementById("message").textContent.includes("Saved pasted JSON batch" )');
    assert.equal(writes.at(-1).payload.entries.length, 2);
    await click("#fetch-contract-json");
    await waitFor('document.getElementById("contract-json-area").value.includes("fixture_contract")');
    await command("Browser.grantPermissions", {origin,permissions:["clipboardReadWrite","clipboardSanitizedWrite"]});
    await click("#copy-contract-json");
    await waitFor('document.getElementById("message").textContent.includes("copied")');
    assert.equal(JSON.parse(await evaluate('navigator.clipboard.readText()')).fixture_contract, true);
    await click("#show-process-view");
    await evaluate('document.getElementById("message").textContent = ""');
    await click('.entry-row[data-entry-id="1"]');
    await waitFor('document.getElementById("message").textContent === "Loaded entry: 1"');
    await click("#unlock-entry-edit");
    await evaluate('document.getElementById("detail_counterparty_name").value="Edited AP vendor"');
    await click("#save-entry-edit");
    await waitFor('document.getElementById("message").textContent.startsWith("Updated entry:")');
    assert.equal(writes.at(-1).method, "PUT");
    assert.equal(writes.at(-1).payload.counterparty_name,"Edited AP vendor");
    assert.equal(await evaluate('document.getElementById("process-entry").textContent'), "Process Entry");
    assert.equal(await evaluate('document.getElementById("reprocess-pending-conversions").textContent'), "Process Entries");
    await click("#process-entry");
    await waitFor('document.getElementById("message").textContent.includes("processed: Recalculated")');
    assert.equal(writes.at(-1).path, "/acct/v0/entries/1/process");
    assert.equal(await evaluate('document.getElementById("detail_amount_common").value'), "10.00");
    assert.equal(await evaluate('document.getElementById("detail_vat_amount").value'), "1.60");
    await click("#reprocess-pending-conversions");
    await waitFor('document.getElementById("message").textContent.includes("4 processed")');
    assert.ok(writes.at(-1).path.endsWith("entries/process"));
    await evaluate('location.hash="#ar"');
    await waitFor('!document.getElementById("ar-view").hidden');
    // Sorting uses persisted values, preserves drafts, and drives adjacent navigation.
    arInvoices = [
        {...arInvoice, id:"sort-a", invoice_number:"2", invoice_date:"2026-02-01", gross_amount:"9007199254740993.01", amount_original:"9007199254740993.01"},
        {...arInvoice, id:"sort-b", invoice_number:"10", invoice_date:"2026-01-01", gross_amount:"9007199254740993.02", amount_original:"9007199254740993.02"},
        {...arInvoice, id:"sort-c", invoice_number:"1", invoice_date:"2026-03-01", gross_amount:"9.00", amount_original:"9.00"},
    ];
    await click("#refresh-ar-invoice-files");
    await waitFor('document.querySelectorAll("#ar-invoice-db-body tr[data-invoice-id]").length === 3 && !document.getElementById("refresh-ar-invoice-files").disabled');
    await click('[data-invoice-id="sort-a"]');
    await click("#unlock-ar-invoice-edit");
    await evaluate('document.getElementById("ar-invoice-remarks").value="Unsaved draft"');
    const arOrder = () => evaluate('Array.from(document.querySelectorAll("#ar-invoice-db-body tr"), row=>row.dataset.invoiceId)');
    await click('.ar-db-table th:nth-child(5) button');
    assert.deepEqual(await arOrder(), ["sort-c","sort-a","sort-b"]);
    await click('.ar-db-table th:nth-child(5) button');
    assert.deepEqual(await arOrder(), ["sort-b","sort-a","sort-c"]);
    assert.equal(await evaluate('document.getElementById("ar-invoice-remarks").value'), "Unsaved draft");
    assert.equal(await evaluate('document.querySelector(".ar-db-table .is-selected").dataset.invoiceId'), "sort-a");
    await click('.ar-db-table th:nth-child(2) button');
    assert.deepEqual(await arOrder(), ["sort-b","sort-a","sort-c"]);
    assert.equal(await evaluate('document.querySelector(".ar-db-table th:nth-child(2)").getAttribute("aria-sort")'), "ascending");
    await click("#next-ar-invoice");
    assert.equal(await evaluate('document.getElementById("ar-invoice-invoice_number").value'), "1");
    await click("#refresh-ar-invoice-files");
    await waitFor('!document.getElementById("refresh-ar-invoice-files").disabled');
    assert.deepEqual(await arOrder(), ["sort-b","sort-a","sort-c"]);
    await click("#show-process-view");
    const apOrder = () => evaluate('Array.from(document.querySelectorAll(".entry-row"), row=>row.dataset.entryId)');
    await click('.entries-table th:nth-child(2) button');
    assert.deepEqual(await apOrder(), ["1","2","3","4"]);
    await click('.entries-table th:nth-child(2) button');
    assert.deepEqual(await apOrder(), ["4","3","2","1"]);
    await click('.entry-row[data-entry-id="2"]');
    await waitFor('document.getElementById("detail_id").value === "2"');
    await click("#next-source-image");
    await waitFor('document.getElementById("detail_id").value === "1"');
    await click("#reprocess-pending-conversions");
    await waitFor('document.getElementById("message").textContent.includes("4 processed")');
    assert.deepEqual(await apOrder(), ["4","3","2","1"]);
    await click('.entries-table th:nth-child(1) button');
    assert.equal(await evaluate('document.querySelector(".entries-table th").getAttribute("aria-sort")'), "ascending");
    await click("#show-ar-view");
    console.log("PASS: AP/AR header sorting, ascending/descending, changed column, precise decimals, selection/draft preservation, refresh and sorted Previous/Next.");
    assert.equal(arNormalizeCalls, 0, "Initial load, import, refresh, and editing never normalize automatically");
    await waitFor('document.querySelectorAll("#ar-payment-body [data-payment-id]").length === 1');
    const selectedInvoiceBeforePayments = await evaluate('document.getElementById("ar-invoice-invoice_number").value');
    await click('[data-payment-id="payment-1"]');
    assert.equal(await evaluate('document.querySelector("#ar-payment-form [name=allocated_amount]").value'), '40.00');
    assert.equal(await evaluate('document.querySelector("#ar-payment-form [name=allocated_amount]").readOnly'), true);
    assert.equal(await evaluate('document.querySelector("#ar-payment-form [name=unallocated_amount]").value'), '60.00');
    await click('#new-ar-payment');
    await evaluate(`(() => { const f=document.getElementById('ar-payment-form');
        for (const [k,v] of Object.entries({payment_date:'2026-05-01',amount:'123.123456',currency:'EUR',payer_name:'New payer',bank_reference:'ABC',payment_method:'cash',remarks:'Note'})) f.elements.namedItem(k).value=v; })()`);
    await click('#save-ar-payment');
    await waitFor('document.getElementById("ar-payment-status").textContent.startsWith("Payment saved.") && !document.getElementById("save-ar-payment").disabled');
    assert.equal(paymentWrites.at(-1).method,'POST');
    assert.equal(paymentWrites.at(-1).payload.amount,'123.123456');
    assert.equal(await evaluate('document.querySelectorAll("#ar-payment-body [data-payment-id]").length'),2);
    for (const [field,value] of [['payment_date','2027-01-02'],['amount','150.123456'],['remarks','Changed note']]) {
        await evaluate(`document.getElementById('ar-payment-form').elements.namedItem(${JSON.stringify(field)}).value=${JSON.stringify(value)}`);
        await click('#save-ar-payment');
        await waitFor('document.getElementById("ar-payment-status").textContent.startsWith("Payment saved.") && !document.getElementById("save-ar-payment").disabled');
        assert.equal(paymentWrites.at(-1).method,'PATCH');
        assert.deepEqual(paymentWrites.at(-1).payload,{[field]:value});
    }
    assert.equal(await evaluate('document.getElementById("ar-invoice-invoice_number").value'),selectedInvoiceBeforePayments);
    paymentReject=true;
    await evaluate('document.querySelector("#ar-payment-form [name=amount]").value="1"');
    await click('#save-ar-payment');
    await waitFor('document.getElementById("ar-payment-status").textContent.includes("existing allocations")');
    assert.equal(await evaluate('document.querySelector("#ar-payment-form [name=amount]").value'),'1');
    paymentReject=false;
    await click('#cancel-ar-payment');
    console.log('PASS: payments load/create/changed-only PATCH/date/amount/metadata/backend errors/read-only balances/independent invoice selection.');
    arInvoices=[{...arInvoice,id:'allocation-invoice',invoice_number:'ALLOC',currency:'EUR',currency_original:'EUR',
        gross_amount:'100',amount_original:'100',payment_date:'2024-01-01',allocations:[]}];
    payments=[{id:'alloc-a',payment_date:'2026-01-01',amount:'60',currency:'EUR',payer_name:'First',bank_reference:'A'},
        {id:'alloc-b',payment_date:'2027-01-01',amount:'80',currency:'EUR',payer_name:'Second',bank_reference:'B'},
        {id:'alloc-usd',payment_date:'2026-01-01',amount:'100',currency:'USD'}];
    refreshAllocationFixtures();
    await click('#refresh-ar-payments');
    await waitFor('!document.getElementById("refresh-ar-payments").disabled');
    await click('#refresh-ar-invoice-files');
    await waitFor('!document.getElementById("refresh-ar-invoice-files").disabled');
    await click('[data-invoice-id="allocation-invoice"]');
    assert.equal(await evaluate('document.querySelectorAll("#ar-allocation-payment option").length'),2);
    assert.equal(await evaluate('document.getElementById("ar-allocation-amount").value'),'60');
    await click('#unlock-ar-invoice-edit');
    await evaluate('document.getElementById("ar-invoice-remarks").value="Keep draft"');
    async function allocateAmount(amount) {
        await evaluate(`document.getElementById('ar-allocation-amount').value=${JSON.stringify(amount)}`);
        await click('#allocate-ar-payment');
        await waitFor('!document.getElementById("ar-allocation-status").textContent.includes("Saving allocation")');
    }
    await allocateAmount('101');
    assert.ok(await evaluate('document.getElementById("ar-allocation-status").textContent.includes("invoice outstanding")'));
    await allocateAmount('70');
    assert.ok(await evaluate('document.getElementById("ar-allocation-status").textContent.includes("payment remaining")'));
    await allocateAmount('40');
    await waitFor('document.getElementById("ar-recognition-body").textContent.includes("Payment allocation")');
    assert.ok(!(await evaluate('document.getElementById("ar-recognition-body").textContent.includes("Manual full-payment date")')));
    assert.equal(await evaluate('document.getElementById("ar-invoice-remarks").value'),'Keep draft');
    assert.equal(await evaluate('document.getElementById("ar-invoice-remarks").disabled'),false);
    assert.equal(await evaluate('document.getElementById("ar-invoice-paid_amount").value'),'40');
    assert.equal(await evaluate('document.getElementById("ar-invoice-outstanding_amount").value'),'60');
    assert.equal(await evaluate('document.getElementById("ar-invoice-payment_status").value'),'partially_paid');
    assert.ok(await evaluate('document.querySelector("#ar-payment-body [data-payment-id=alloc-a]").textContent.includes("20")'));
    assert.equal(await evaluate('document.querySelectorAll("#ar-allocation-list li").length'),1);
    await click('[data-payment-id="alloc-a"]');
    await evaluate('document.querySelector("#ar-payment-form [name=payment_date]").value="2028-01-01"');
    await click('#save-ar-payment');
    await waitFor('document.getElementById("ar-payment-status").textContent.startsWith("Payment saved.") && !document.getElementById("save-ar-payment").disabled');
    assert.ok(await evaluate('document.getElementById("ar-allocation-list").textContent.includes("2028-01-01")'));
    await waitFor('document.getElementById("ar-recognition-body").textContent.includes("2028-01-01")');
    assert.equal(await evaluate('document.getElementById("ar-invoice-remarks").value'),'Keep draft');
    await evaluate('document.getElementById("ar-allocation-payment").value="alloc-b"; document.getElementById("ar-allocation-payment").dispatchEvent(new Event("change"))');
    assert.equal(await evaluate('document.getElementById("ar-allocation-amount").value'),'60');
    await allocateAmount('60');
    await waitFor('document.querySelectorAll("#ar-recognition-body tr").length===2');
    assert.equal(await evaluate('document.querySelectorAll("#ar-allocation-list li").length'),2);
    assert.equal(await evaluate('document.getElementById("ar-invoice-payment_status").value'),'paid');
    assert.equal(await evaluate('document.getElementById("allocate-ar-payment").disabled'),true);
    await evaluate('window.confirm=()=>true');
    for (let remaining=1;remaining>=0;remaining--) {
        await click('#ar-allocation-list button');
        await waitFor(`document.querySelectorAll('#ar-allocation-list li').length===${remaining} && !document.getElementById('allocate-ar-payment').disabled`);
    }
    assert.equal(payments.length,3);
    assert.equal(await evaluate('document.getElementById("ar-invoice-payment_date").value'),'2024-01-01');
    assert.equal(await evaluate('document.getElementById("ar-invoice-payment_status").value'),'open');
    assert.equal(await evaluate('document.getElementById("ar-invoice-remarks").value'),'Keep draft');
    await waitFor('document.getElementById("ar-recognition-body").textContent.includes("Manual full-payment date")');
    await click('#cancel-ar-invoice-edit');
    recognitionFailure=true;
    await click('[data-invoice-id="allocation-invoice"]');
    await waitFor('document.getElementById("ar-recognition-body").textContent.includes("Could not load recognition events")');
    assert.equal(await evaluate('document.getElementById("unlock-ar-invoice-edit").disabled'),false);
    assert.equal(await evaluate('document.getElementById("ar-invoice-payment_date").value'),'2024-01-01');
    recognitionFailure=false;
    await click('[data-invoice-id="allocation-invoice"]');
    await waitFor('document.getElementById("ar-recognition-body").textContent.includes("Manual full-payment date")');
    console.log('PASS: recognition empty/manual/allocated/multiple/date refresh/precision/local error/recovery/draft preservation.');
    console.log('PASS: allocation filtering/defaults/partial/multiple/full/errors/removal/balances/parent dates/manual-date preservation/invoice drafts.');
    arInvoices = [
        {...arInvoice, id:"normalize-eur", invoice_number:"EUR", currency_original:"EUR", currency:"EUR", amount_original:"12.50", gross_amount:"12.50"},
        {...arInvoice, id:"normalize-usd", invoice_number:"USD"},
    ];
    await click("#refresh-ar-invoice-files");
    await waitFor('!document.getElementById("refresh-ar-invoice-files").disabled');
    await click('[data-invoice-id="normalize-eur"]');
    assert.equal(await evaluate('document.getElementById("ar-invoice-amount_common").value'), "");
    assert.equal(await evaluate('document.getElementById("process-ar-entry").textContent'), "Process Entry");
    assert.equal(await evaluate('document.getElementById("normalize-ar-invoices").textContent'), "Process Entries");
    await click("#process-ar-entry");
    await waitFor('document.getElementById("ar-invoice-editor-status").textContent.startsWith("Processed invoice:")');
    assert.equal(await evaluate('document.getElementById("ar-invoice-amount_common").value'), "12.50");
    assert.equal(arInvoices[1].amount_common, null);
    assert.equal(await evaluate('document.querySelector(".ar-db-table .is-selected").dataset.invoiceId'), "normalize-eur");
    await click("#normalize-ar-invoices");
    assert.equal(await evaluate('document.getElementById("normalize-ar-invoices").disabled'), true);
    await waitFor('!document.getElementById("normalize-ar-invoices").disabled');
    assert.equal(arNormalizeCalls, 1);
    assert.equal(await evaluate('document.getElementById("ar-invoice-amount_common").value'), "12.50");
    assert.equal(await evaluate('document.querySelector("[data-invoice-id=normalize-eur]").cells[10].textContent'), "12.50");
    assert.ok(await evaluate('document.getElementById("ar-invoice-conversion-status").textContent.includes("Unsupported conversion")'));
    arNormalizeFailure = true;
    await click("#normalize-ar-invoices");
    await waitFor('!document.getElementById("normalize-ar-invoices").disabled');
    assert.ok(await evaluate('document.getElementById("ar-invoice-conversion-status").textContent.includes("Database is busy")'));
    console.log("PASS: explicit AR normalization, common/original fields, no automatic requests, busy state, refreshed selected values and errors.");
    const beforeSummaryWrites = [writes.length, paymentWrites.length, arPatches.length, arNormalizeCalls, arProcessCalls];
    await click('#unlock-ar-invoice-edit');
    await evaluate('document.getElementById("ar-invoice-customer_name").value="AR report draft"');
    await click('#show-summary-view');
    await waitFor('!document.getElementById("summary-results").hidden');
    assert.equal(await evaluate('location.hash'),'#summary');
    assert.equal(summaryRequests.at(-1).path, `/acct/v0/yearly-accounting-summary/${new Date().getFullYear()}`);
    assert.equal(await evaluate('document.getElementById("summary-completeness").textContent'),'Complete preview');
    assert.equal(await evaluate('document.querySelector("[data-summary-field=gross_basis_result]").textContent'),'987.006 CHF');
    assert.equal(await evaluate('document.querySelector("[data-summary-field=recognized_ar_gross_common]").textContent'),'123456789012345678.123456 CHF');
    assert.ok(await evaluate('document.getElementById("summary-counts").textContent.includes("AP included: 7")'));
    assert.ok(await evaluate('document.getElementById("summary-ap-body").textContent.includes("incomeburodomesticCHF")'));
    assert.deepEqual(await evaluate('Array.from(document.getElementById("summary-ar-body").rows,r=>r.cells[0].textContent)'),['EUR','USD']);
    assert.deepEqual(await evaluate('Array.from(document.getElementById("summary-ar-body").rows[1].cells,c=>c.textContent)'),['USD','2','100.00','Unavailable','20.006','2','1']);
    await evaluate('document.getElementById("summary-year").value="2024"; document.getElementById("summary-year").dispatchEvent(new Event("change"))');
    await waitFor('document.getElementById("summary-status").textContent==="Summary for 2024"');
    assert.equal(summaryRequests.at(-1).path,'/acct/v0/yearly-accounting-summary/2024');
    summaryMode='incomplete';
    await click('#refresh-summary');
    await waitFor('document.getElementById("summary-completeness").textContent==="Incomplete preview"');
    assert.equal(await evaluate('document.querySelector("[data-summary-field=gross_basis_result]").textContent'),'Unavailable');
    assert.equal(await evaluate('document.getElementById("summary-currency").textContent'),'Report currency: Unavailable');
    assert.ok(await evaluate('document.getElementById("summary-warnings").textContent.includes("Common currencies disagree: EUR, USD. (Count: 2)")'));
    summaryMode='empty';
    await click('#refresh-summary');
    await waitFor('document.getElementById("summary-ap-body").textContent.includes("No AP records")');
    assert.equal(await evaluate('document.querySelector("[data-summary-field=gross_basis_result]").textContent'),'0');
    assert.ok(await evaluate('document.getElementById("summary-ar-body").textContent.includes("No AR receipts")'));
    summaryMode='error';
    await click('#refresh-summary');
    await waitFor('document.getElementById("summary-status").textContent.includes("HTTP 503")');
    assert.equal(await evaluate('document.getElementById("summary-results").hidden'),true);
    assert.equal(await evaluate('document.getElementById("summary-year").value'),'2024');
    summaryMode='normal';
    await click('#refresh-summary');
    await waitFor('!document.getElementById("summary-results").hidden');
    await click('#show-ar-view');
    assert.equal(await evaluate('document.getElementById("ar-invoice-customer_name").value'),'AR report draft');
    await click('#cancel-ar-invoice-edit');
    await click('#show-process-view');
    await click('#unlock-entry-edit');
    await evaluate('document.getElementById("detail_counterparty_name").value="AP report draft"');
    await click('#show-summary-view');
    await waitFor('!document.getElementById("summary-results").hidden');
    await click('#show-process-view');
    assert.equal(await evaluate('document.getElementById("detail_counterparty_name").value'),'AP report draft');
    await click('#cancel-entry-edit');
    assert.deepEqual([writes.length,paymentWrites.length,arPatches.length,arNormalizeCalls,arProcessCalls],beforeSummaryWrites);
    assert.ok(summaryRequests.every(r=>r.method==='GET'));
    await click('#show-ar-view');
    console.log('PASS: summary navigation/year/refresh/backend headlines/exact decimals/currencies/completeness/warnings/nulls/empty/errors/AP and AR drafts/read-only requests.');
    await command("Emulation.setDeviceMetricsOverride", {width:600,height:900,deviceScaleFactor:1,mobile:false});
    assert.equal(await evaluate('getComputedStyle(document.querySelector(".ar-workspace")).gridTemplateColumns.split(" ").length'), 1);
    assert.equal(await evaluate('getComputedStyle(document.querySelector(".ar-records-column")).position'), "static");
    assert.deepEqual(runtimeErrors, []);
    blockFeatureModule = true;
    await command("Network.setCacheDisabled", {cacheDisabled: true});
    await command("Page.navigate", {url: origin});
    await waitFor('document.getElementById("show-ar-view") && location.hash === "#ap"');
    for (const [button, view] of [["show-ar-view", "ar-view"], ["show-input-view", "input-view"], ["show-process-view", "process-view"]]) {
        await click(`#${button}`);
        await waitFor(`!document.getElementById(${JSON.stringify(view)}).hidden`);
    }
    console.log("PASS: all three navigation buttons work when the AP feature module cannot load.");
    console.log("PASS: three-view/hash navigation; AR selection/edit/cancel/PATCH/validation/read-only fields/PDF matching/Previous/Next/removal; responsive layout; manual/batch/contract copy; AP save and conversion.");
    console.log("PASS: AR initial datasets, original/common currency columns, Refresh without POST, body-free processing, busy state, per-file results, refreshed DB, empty/error states and recovery.");
    console.log("PASS: JPEG rendering; bounded zoom/fit; mouse pan and bounds; fixed layout; Ctrl+wheel and normal scrolling; focused keyboard shortcuts; row/Previous/Next reset; empty/error states; form editing; Process/Input.");
} finally {
    await command("Page.close");
    socket.close();
    server.closeAllConnections();
    await new Promise(resolve => server.close(resolve));
}
