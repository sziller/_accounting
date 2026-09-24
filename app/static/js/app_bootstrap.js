import {initializeAccountsPayable} from "./accounting_entries.js";
import {initializeNewEntries} from "./new_entries.js";
import {initializeArPanel} from "./ar_invoice_import.js?v=currency-usd-2";
import {initializeI18n} from "./i18n/i18n.js";


const API_BASE = "/acct/v0";


async function apiGet(path) {
    const response = await fetch(`${API_BASE}${path}`);

    if (!response.ok) {
        throw new Error(`GET ${path} failed`);
    }

    return await response.json();
}


function formatError(error) {
    if (error && typeof error === "object" && "detail" in error) {
        return typeof error.detail === "string"
            ? error.detail
            : JSON.stringify(error.detail, null, 2);
    }

    if (error instanceof Error) {
        return error.message;
    }

    return JSON.stringify(error, null, 2);
}


function reportFeatureError(feature, error) {
    const text = formatError(error);

    console.error(`${feature} initialization failed:`, error);

    if (feature === "Accounts Receivable") {
        const status = document.getElementById(
            "ar-invoice-import-status"
        );

        if (status) {
            status.textContent =
                `Accounts Receivable initialization failed:\n${text}`;
        }

        return;
    }

    if (feature === "Accounts Payable") {
        const status = document.getElementById(
            "entry-processing-status"
        );

        if (status) {
            status.textContent =
                `Accounts Payable initialization failed:\n${text}`;
        }

        return;
    }

    if (feature === "New Entries") {
        const status = document.getElementById("message");

        if (status) {
            status.textContent =
                `New Entries initialization failed:\n${text}`;
        }
    }
}


function reportMetadataError(error) {
    const text = formatError(error);

    console.error(
        "Accounting metadata initialization failed:",
        error
    );

    const apStatus = document.getElementById(
        "entry-processing-status"
    );

    const newEntriesStatus = document.getElementById(
        "message"
    );

    if (apStatus) {
        apStatus.textContent =
            `Unable to load accounting metadata:\n${text}`;
    }

    if (newEntriesStatus) {
        newEntriesStatus.textContent =
            `Unable to load accounting metadata:\n${text}`;
    }
}


export async function initializeApplication() {
        initializeI18n();
    /*
     * AR is deliberately independent from AP/New Entries.
     *
     * A failure while starting AR must not prevent the other frontend
     * features from initializing.
     */
    try {
        await initializeArPanel();
    } catch (error) {
        reportFeatureError(
            "Accounts Receivable",
            error
        );
    }


    /*
     * AP and New Entries use the same backend metadata.
     *
     * Fetch it once here and inject the resulting data into both feature
     * modules. Neither feature module owns the metadata request anymore.
     */
    let metadata;

    try {
        metadata = await apiGet("/metadata");
    } catch (error) {
        reportMetadataError(error);
        return;
    }


    /*
     * Initialize AP independently.
     *
     * Keep the returned controller so New Entries can request an AP list
     * refresh after successfully creating entries, without knowing AP's
     * internal loadEntries() implementation.
     */
    let accountsPayable = null;

    try {
        accountsPayable = await initializeAccountsPayable({
            metadata,
        });
    } catch (error) {
        reportFeatureError(
            "Accounts Payable",
            error
        );
    }


    /*
     * Initialize New Entries even if AP initialization failed.
     *
     * If AP is available, successful creation refreshes its entry list.
     * If AP failed to initialize, entry creation itself remains usable.
     */
    try {
        initializeNewEntries({
            metadata,

            onEntriesCreated: async () => {
                if (!accountsPayable) {
                    return;
                }

                await accountsPayable.refreshEntries();
            },
        });
    } catch (error) {
        reportFeatureError(
            "New Entries",
            error
        );
    }


    return {
        accountsPayable,
    };
}


await initializeApplication();
