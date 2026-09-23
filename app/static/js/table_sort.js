// Shared client-side ordering. Decimal comparisons preserve the API's full precision.
export function compareDecimal(left, right) {
    const parts = value => {
        const match = String(value).match(/^([+-]?)(\d+)(?:\.(\d*))?$/);
        if (!match) return null;
        return {value: BigInt(`${match[1] === "-" ? "-" : ""}${match[2]}${match[3] ?? ""}`), places: (match[3] ?? "").length};
    };
    const a = parts(left), b = parts(right);
    if (!a || !b) return String(left).localeCompare(String(right), undefined, {numeric: true});
    const places = Math.max(a.places, b.places);
    const x = a.value * 10n ** BigInt(places - a.places);
    const y = b.value * 10n ** BigInt(places - b.places);
    return x < y ? -1 : x > y ? 1 : 0;
}

export function initializeTableSort(table, columns, onChange) {
    let active = null;
    let direction = 1;
    const headers = [...table.querySelectorAll("thead th")];
    headers.forEach((header, index) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "table-sort-button";
        button.textContent = header.textContent;
        header.replaceChildren(button);
        header.setAttribute("scope", "col");
        button.addEventListener("click", () => {
            direction = active === index ? -direction : 1;
            active = index;
            headers.forEach((item, i) => {
                if (i === active) item.setAttribute("aria-sort", direction === 1 ? "ascending" : "descending");
                else item.removeAttribute("aria-sort");
            });
            onChange();
        });
    });
    return items => {
        if (active === null) return [...items];
        const [key, type] = columns[active];
        return [...items].sort((a, b) => {
            const left = a[key], right = b[key];
            // Missing/pending amounts stay at the end in either direction.
            if (left == null || left === "") return right == null || right === "" ? 0 : 1;
            if (right == null || right === "") return -1;
            return direction * (type === "decimal" ? compareDecimal(left, right)
                : String(left).localeCompare(String(right), undefined, {numeric: true, sensitivity: "base"}));
        });
    };
}

export function reorderTableRows(body, items, attribute) {
    const rows = new Map([...body.rows].map(row => [row.dataset[attribute], row]));
    for (const item of items) {
        const row = rows.get(String(item.id));
        if (row) body.appendChild(row);
    }
}
