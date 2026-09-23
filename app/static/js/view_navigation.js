// Stable DOM IDs are independent of visible labels and future translations.
function initializeViewNavigation() {
    const buttons = document.querySelectorAll("[data-view-target]");
    const views = document.querySelectorAll(".app-view");
    const hashes = {"process-view": "#ap", "ar-view": "#ar", "input-view": "#new", "summary-view": "#summary"};
    const targets = {"#ap": "process-view", "#ar": "ar-view", "#new": "input-view",
        "#process": "process-view", "#input": "input-view", "#summary": "summary-view"};
    function showView(id) {
        views.forEach(view => {
            view.hidden = view.id !== id;
            view.classList.toggle("is-active", view.id === id);
        });
        buttons.forEach(button => {
            const active = button.dataset.viewTarget === id;
            button.classList.toggle("is-active", active);
            button.setAttribute("aria-selected", String(active));
        });
        history.replaceState(null, "", hashes[id]);
        window.dispatchEvent(new CustomEvent('accounting-view-change', {detail: id}));
    }
    buttons.forEach(button => button.addEventListener("click", () => showView(button.dataset.viewTarget)));
    window.addEventListener("hashchange", () => showView(targets[location.hash] ?? "process-view"));
    showView(targets[location.hash] ?? "process-view");
}

initializeViewNavigation();
