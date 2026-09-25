import {EN} from "./en.js";
import {DE} from "./de.js";
import {HU} from "./hu.js";


const STORAGE_KEY = "accounting.language";
const DEFAULT_LANGUAGE = "en";

const TRANSLATIONS = {
    en: EN,
    de: DE,
    hu: HU,
};

let currentLanguage = DEFAULT_LANGUAGE;


/*
 * Return all language codes supported by the frontend.
 *
 * At the moment:
 *
 *     en
 *     de
 *     hu (New Entries; other views fall back to English)
 *
 * Later another dictionary can be added here without changing the
 * translation mechanism itself.
 */
export function getSupportedLanguages() {
    return Object.keys(TRANSLATIONS);
}


/*
 * Return the currently active language code.
 */
export function getLanguage() {
    return currentLanguage;
}


/*
 * Translate one stable translation key.
 *
 * Example:
 *
 *     t("common.save")
 *
 * returns either:
 *
 *     "Save Changes"
 *
 * or:
 *
 *     "Änderungen speichern"
 *
 * depending on the active language.
 *
 * If a key is missing from the selected language, English is used as the
 * fallback. If the key is missing there as well, the supplied fallback is
 * used. As a final fallback, the key itself is returned.
 */
export function t(key, fallback = null) {
    const activeDictionary = TRANSLATIONS[currentLanguage] ?? {};
    const defaultDictionary = TRANSLATIONS[DEFAULT_LANGUAGE] ?? {};

    if (Object.prototype.hasOwnProperty.call(activeDictionary, key)) {
        return activeDictionary[key];
    }

    if (Object.prototype.hasOwnProperty.call(defaultDictionary, key)) {
        return defaultDictionary[key];
    }

    if (fallback !== null) {
        return fallback;
    }

    console.warn(`Missing translation key: ${key}`);

    return key;
}


/*
 * Translate the visible text content of an element carrying:
 *
 *     data-i18n="some.translation.key"
 */
function translateElementText(element) {
    const key = element.dataset.i18n;

    if (!key) {
        return;
    }

    element.textContent = t(
        key,
        element.textContent
    );
}


/*
 * Translate an HTML attribute whose translation key is stored in a
 * data-* attribute.
 *
 * Example:
 *
 *     data-i18n-aria-label="nav.ariaLabel"
 *
 * translates the actual:
 *
 *     aria-label="..."
 */
function translateAttribute(
    element,
    dataAttribute,
    targetAttribute
) {
    const key = element.dataset[dataAttribute];

    if (!key) {
        return;
    }

    const currentValue = element.getAttribute(
        targetAttribute
    );

    element.setAttribute(
        targetAttribute,
        t(key, currentValue)
    );
}


/*
 * Apply translations to a DOM subtree.
 *
 * By default the complete document is translated.
 *
 * Supported markup:
 *
 *     data-i18n
 *     data-i18n-placeholder
 *     data-i18n-title
 *     data-i18n-aria-label
 */
export function applyTranslations(root = document) {
    root.querySelectorAll("[data-i18n]").forEach(
        translateElementText
    );

    root.querySelectorAll(
        "[data-i18n-placeholder]"
    ).forEach(
        (element) => {
            translateAttribute(
                element,
                "i18nPlaceholder",
                "placeholder"
            );
        }
    );

    root.querySelectorAll(
        "[data-i18n-title]"
    ).forEach(
        (element) => {
            translateAttribute(
                element,
                "i18nTitle",
                "title"
            );
        }
    );

    root.querySelectorAll(
        "[data-i18n-aria-label]"
    ).forEach(
        (element) => {
            translateAttribute(
                element,
                "i18nAriaLabel",
                "aria-label"
            );
        }
    );

    root.querySelectorAll(
        "[data-i18n-alt]"
    ).forEach(
        (element) => {
            translateAttribute(
                element,
                "i18nAlt",
                "alt"
            );
        }
    );

}


/*
 * Keep the visible language selector synchronized with the currently
 * active language.
 *
 * This function deliberately changes only the selector's value.
 * It does not translate anything itself.
 */
function synchronizeLanguageSelector() {
    const selector = document.getElementById(
        "language-select"
    );

    if (!selector) {
        return;
    }

    selector.value = currentLanguage;
}


/*
 * Change the active frontend language.
 *
 * This affects presentation only:
 *
 * - current translation dictionary
 * - <html lang="...">
 * - translated DOM text
 * - stored browser preference
 *
 * It does NOT change backend/API/accounting values.
 */
export function setLanguage(
    language,
    {
        persist = true,
        translate = true,
    } = {}
) {
    if (
        !Object.prototype.hasOwnProperty.call(
            TRANSLATIONS,
            language
        )
    ) {
        console.warn(
            `Unsupported language "${language}".`
        );

        return false;
    }

    currentLanguage = language;

    document.documentElement.lang = language;

    if (persist) {
        localStorage.setItem(
            STORAGE_KEY,
            language
        );
    }

    if (translate) {
        applyTranslations(document);
    }

    synchronizeLanguageSelector();

    /*
     * Other frontend modules can later listen for this event when they
     * contain dynamically generated text that needs to be rebuilt after
     * a language change.
     *
     * We are not using that capability yet, but this is the clean hook
     * for the later AP/AR/New Entries migration.
     */
    document.dispatchEvent(
        new CustomEvent(
            "accounting:language-changed",
            {
                detail: {
                    language,
                },
            }
        )
    );

    return true;
}


/*
 * Connect the header's language selector to setLanguage().
 */
function initializeLanguageSelector() {
    const selector = document.getElementById(
        "language-select"
    );

    if (!selector) {
        console.warn(
            "Language selector #language-select was not found."
        );

        return;
    }

    /*
     * Make sure the selector initially reflects the language selected by
     * initializeI18n().
     */
    selector.value = currentLanguage;

    selector.addEventListener(
        "change",
        () => {
            setLanguage(
                selector.value,
                {
                    persist: true,
                    translate: true,
                }
            );
        }
    );
}


/*
 * Initialize frontend internationalization.
 *
 * Startup priority:
 *
 * 1. use a valid previously stored language;
 * 2. otherwise use English.
 *
 * We deliberately do not automatically use the browser/OS language.
 * The application's default remains deterministic: English.
 */
export function initializeI18n() {
    const storedLanguage = localStorage.getItem(
        STORAGE_KEY
    );

    const initialLanguage = (
        storedLanguage &&
        Object.prototype.hasOwnProperty.call(
            TRANSLATIONS,
            storedLanguage
        )
    )
        ? storedLanguage
        : DEFAULT_LANGUAGE;

    /*
     * Apply the initial language before installing the selector listener.
     *
     * persist=false means simply loading the page does not unnecessarily
     * rewrite localStorage.
     */
    setLanguage(
        initialLanguage,
        {
            persist: false,
            translate: true,
        }
    );

    initializeLanguageSelector();

    return {
        language: initialLanguage,
        setLanguage,
        getLanguage,
        t,
        applyTranslations,
    };
}
