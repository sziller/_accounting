export const DE = {
    // Anwendung
    "app.title": "Buchhaltung",
    "app.subtitle": "Buchungseinträge prüfen, verwalten und hinzufügen.",

    // Navigation
    "nav.accountsPayable": "Eingangsrechnungen",
    "nav.accountsReceivable": "Ausgangsrechnungen",
    "nav.newEntries": "Neue Einträge",
    "nav.yearlySummary": "Jahresübersicht",
    "nav.ariaLabel": "Buchhaltungsbereiche",

    // Sprache
    "language.label": "Sprache",
    "language.english": "Englisch",
    "language.german": "Deutsch",

    // Allgemeine Aktionen
    "common.save": "Änderungen speichern",
    "common.cancel": "Abbrechen",
    "common.refresh": "Aktualisieren",
    "common.previous": "Zurück",
    "common.next": "Weiter",
    "common.edit": "Bearbeiten",
    "common.process": "Verarbeiten",
    "common.copy": "Kopieren",
    "common.loading": "Wird geladen...",
    "common.none": "Keine",

    // Allgemeine Felder
    "common.date": "Datum",
    "common.amount": "Betrag",
    "common.currency": "Währung",
    "common.status": "Status",
    "common.remarks": "Anmerkungen",
    "common.reference": "Referenz",

    // Kreditoren / Eingangsrechnungen
    "ap.selectedEntry": "Ausgewählter Buchungseintrag",
    "ap.selectedEntryHelp":
        "Wählen Sie einen Eintrag aus der Liste aus, um ihn zu prüfen. Geben Sie die Bearbeitung frei, um Rohdaten zu ändern. Abgeleitete Felder bleiben schreibgeschützt und werden vom Backend neu berechnet.",

    "ap.sourceImage": "Quelldokument",
    "ap.sourceImageHelp":
        "JPEG-Quelldokument des ausgewählten Buchungseintrags.",

    "ap.sourceImage.entryNavigation": "Navigation zwischen Quelldokumenten",
    "ap.sourceImage.previousEntry": "Vorheriger Eintrag",
    "ap.sourceImage.nextEntry": "Nächster Eintrag",

    "ap.sourceImage.zoomControls": "Zoom-Steuerung für das Bild",
    "ap.sourceImage.zoomOut": "Verkleinern",
    "ap.sourceImage.zoomIn": "Vergrößern",
    "ap.sourceImage.zoomOutTitle": "Verkleinern (−)",
    "ap.sourceImage.zoomInTitle": "Vergrößern (+)",
    "ap.sourceImage.fit": "Einpassen",
    "ap.sourceImage.fitTitle": "Gesamtes Bild einpassen (0)",

    "ap.sourceImage.viewerHelp":
        "Quelldokument-Anzeige. Mit Strg+Mausrad oder Plus und Minus zoomen; zum Verschieben ziehen; 0 zum Einpassen.",

    "ap.sourceImage.alt":
        "Quelldokument des ausgewählten Buchungseintrags",

    "ap.sourceImage.empty":
        "Wählen Sie einen Eintrag aus, um das zugehörige JPEG anzuzeigen.",

    "ap.sourceImage.file": "Datei:",
    "ap.sourceImage.noneSelected": "Nichts ausgewählt",
    "ap.entries": "Buchungseinträge",
    "ap.processing": "Verarbeitung",

    "ap.processEntry": "Eintrag verarbeiten",
    "ap.unlockEditing": "Bearbeitung freigeben",

    "ap.editableRawFields": "Bearbeitbare Rohdaten",
    "ap.derivedReadOnlyFields": "Abgeleitete / schreibgeschützte Felder",

    "ap.field.type": "Typ",
    "ap.field.category": "Kategorie",
    "ap.field.taxScope": "Steuerbereich",
    "ap.field.counterparty": "Geschäftspartner",
    "ap.field.paymentMethod": "Zahlungsart",
    "ap.field.paymentDate": "Zahlungsdatum",
    "ap.field.amountOriginal": "Originalbetrag",
    "ap.field.currencyOriginal": "Originalwährung",
    "ap.field.hasInvoice": "Rechnung vorhanden",
    "ap.field.invoiceNumber": "Rechnungsnummer",
    "ap.field.invoiceDate": "Rechnungsdatum",
    "ap.field.remarks": "Anmerkungen",
    "ap.field.tags": "Tags, kommagetrennt",
    "ap.field.sourceFilename": "Quelldateiname",

    "ap.field.bookingYear": "Buchungsjahr",
    "ap.field.amountCommon": "Betrag in Basiswährung",
    "ap.field.currencyCommon": "Basiswährung",
    "ap.field.exchangeRate": "Wechselkurs",
    "ap.field.exchangeRateDate": "Wechselkursdatum",
    "ap.field.vatRatePercent": "USt.-Satz in Prozent",
    "ap.field.vatAmount": "USt.-Betrag",
    "ap.field.deductiblePercent": "Abzugsfähiger Anteil in Prozent",
    "ap.field.deductibleAmount": "Abzugsfähiger Betrag",
    "ap.field.deductibleVatAmount": "Abzugsfähiger USt.-Betrag",
    "ap.field.writeoffMethod": "Abschreibungsmethode",
    "ap.field.conversionStatus": "Umrechnungsstatus",
    "ap.field.conversionNote": "Hinweis zur Umrechnung",
    "ap.field.createdAt": "Erstellt am",
    "ap.field.updatedAt": "Aktualisiert am",
    "ap.entriesHelp":
        "Wählen Sie eine Zeile aus, um die Daten und das Quelldokument zu prüfen.",
    "ap.entries.column.vat": "USt.",
    "ap.entries.column.deductible": "Abzugsbetrag",
    "ap.processEntries": "Einträge verarbeiten",
    "ap.processingHelp":
        "Alle Eingangsrechnungen mit den aktuellen Regeln und den gespeicherten historischen Wechselkursen neu berechnen.",

    // AP-Validierung
    "ap.validation.payloadObject":
        "Die Nutzdaten müssen aus genau einem JSON-Objekt bestehen.",
    "ap.validation.entryTypeRequired": "Der Eintragstyp ist erforderlich.",
    "ap.validation.categoryRequired": "Die Kategorie ist erforderlich.",
    "ap.validation.taxScopeRequired": "Der Steuerbereich ist erforderlich.",
    "ap.validation.counterpartyRequired":
        "Der Geschäftspartner ist erforderlich.",
    "ap.validation.paymentMethodRequired":
        "Die Zahlungsart ist erforderlich.",
    "ap.validation.paymentDateRequired":
        "Das Zahlungsdatum ist erforderlich.",
    "ap.validation.amountPositive":
        "Der Betrag muss größer als null sein.",
    "ap.validation.currencyRequired": "Die Währung ist erforderlich.",
    "ap.validation.invoiceDateRequired":
        "Bei vorhandener Rechnung ist das Rechnungsdatum erforderlich.",

    // AP -Dynamischer Tabellenstatus
    "ap.table.pending": "ausstehend",

    // AP - Dynamischer Status des Quelldokuments
    "ap.sourceImage.noSource": "Kein Quelldokument",
    "ap.sourceImage.noSourceAssociated":
        "Diesem Eintrag ist kein Quelldokument zugeordnet.",
    "ap.sourceImage.loading": "Quelldokument wird geladen…",
    "ap.sourceImage.loadFailed":
        "Das Quelldokument konnte nicht geladen werden.",

    // AP - Dynamische Statusmeldungen
    "ap.status.loadedEntry": "Eintrag geladen",
    "ap.status.noEntrySelected": "Kein Eintrag ausgewählt.",
    "ap.status.updatedEntry": "Eintrag aktualisiert",
    "ap.status.processing": "Verarbeitung läuft…",
    "ap.status.processed": "verarbeitet",
    "ap.status.failed": "fehlgeschlagen",
    "ap.status.reprocessing":
        "Ausstehende Währungsumrechnungen werden neu verarbeitet...",
    "ap.status.selectEntryFirst":
        "Wählen Sie zuerst einen Eintrag aus.",
    "ap.status.editingUnlocked":
        "Bearbeitung freigegeben. Abgeleitete Felder bleiben schreibgeschützt.",
    "ap.status.editCancelled": "Bearbeitung abgebrochen.",

    // Debitoren / Ausgangsrechnungen
    "ar.selectedInvoice": "Ausgewählte Ausgangsrechnung",
    "ar.sourcePdfs": "AR-Quell-PDFs",
    "ar.outgoingInvoices": "Ausgangsrechnungen",
    "ar.processing": "Verarbeitung der Ausgangsrechnungen",
    "ar.processEntry": "Eintrag verarbeiten",
    "ar.processEntries": "Einträge verarbeiten",
    "ar.updateFromDirectory": "Datenbank aus Verzeichnis aktualisieren",

    // Zahlungseingänge
    "payments.title": "Zahlungseingänge",
    "payments.newPayment": "Neue Zahlung",
    "payments.paymentDate": "Zahlungsdatum",
    "payments.payer": "Zahler",
    "payments.paymentMethod": "Zahlungsart",
    "payments.bankReference": "Bank / Referenz",
    "payments.allocatedAmount": "Zugeordneter Betrag",
    "payments.unallocatedAmount": "Nicht zugeordneter Betrag",

    // Zahlungszuordnungen
    "allocations.title": "Zahlungen / Zuordnungen",
    "allocations.incomingPayment": "Zahlungseingang",
    "allocations.allocatedAmount": "Zugeordneter Betrag",
    "allocations.allocatePayment": "Zahlung zuordnen",
    "allocations.noAllocations": "Keine Zuordnungen.",

    // Erfassung
    "recognition.title": "Erfassung",

    // Neue Einträge
    "newEntries.title": "Neuer Eintrag",
    "newEntries.batchTitle": "JSON-Stapelverarbeitung",
    "newEntries.contractTitle": "Vertrag zur Eintragserstellung",
    "newEntries.saveEntry": "Eintrag speichern",
    "newEntries.loadExample": "Beispiel-JSON laden",
    "newEntries.submitJson": "JSON übermitteln",
    "newEntries.fetchContract": "Vertrag laden",
    "newEntries.copyContract": "Vertrag kopieren",

    // Anzeigetexte für Buchungskategorien
    "metadata.category.auto": "Auto",
    "metadata.category.bahn": "Bahn",
    "metadata.category.betriebsbedarf": "Betriebsbedarf",
    "metadata.category.betriebskosten": "Betriebskosten",
    "metadata.category.bewirtung": "Bewirtung",
    "metadata.category.buro": "Büro",
    "metadata.category.bvg": "BVG / ÖPNV",
    "metadata.category.eingang": "Eingang",
    "metadata.category.einkommen-kirchen-soli-vorauszahlung":
        "Einkommen/Kirchen/Soli Vorauszahlung",
    "metadata.category.einrichtung": "Einrichtung",
    "metadata.category.fachliteratur": "Fachliteratur",
    "metadata.category.festnetz": "Festnetz",
    "metadata.category.haftpflichtversicherung": "Haftpflichtversicherung",
    "metadata.category.handy-prepaid": "Handy Prepaid",
    "metadata.category.handy-vertrag": "Handy Vertrag",
    "metadata.category.hausratversicherung": "Hausratversicherung",
    "metadata.category.honorar": "Honorar",
    "metadata.category.krankenversicherung": "Krankenversicherung",
    "metadata.category.n/a": "N/A",
    "metadata.category.pfegeversicherung": "Pflegeversicherung",
    "metadata.category.porto-mit-ust": "Porto mit USt.",
    "metadata.category.porto-ohne-ust": "Porto ohne USt.",
    "metadata.category.raum": "Raum",
    "metadata.category.reiseversicherung": "Reiseversicherung",
    "metadata.category.rentenversicherung": "Rentenversicherung",
    "metadata.category.steuerberatung": "Steuerberatung",
    "metadata.category.ubernachtung": "Übernachtung",
    "metadata.category.umsatzsteuer-vorauszahlung":
        "Umsatzsteuer-Vorauszahlung",
    "metadata.category.werbung": "Werbung",
    "metadata.category.werkzeug": "Werkzeug",
    "metadata.category.werkzeug-mehrjaehrige-abschreibung":
        "Werkzeug — mehrjährige Abschreibung",

    // Jahresübersicht
    "summary.title": "Jahresübersicht Buchhaltung",
    "summary.year": "Jahr",

    // Anzeigetexte für Metadaten
    "metadata.entryType.correction": "Korrektur",
    "metadata.entryType.expense": "Ausgabe",
    "metadata.entryType.income": "Einnahme",
    "metadata.entryType.private": "Privat",
    "metadata.entryType.tax": "Steuer",

    "metadata.taxScope.domestic": "Inland",
    "metadata.taxScope.eu": "EU",
    "metadata.taxScope.not_applicable": "Nicht anwendbar",
    "metadata.taxScope.third_country": "Drittland",

    "metadata.paymentMethod.bank_transfer": "Banküberweisung",
    "metadata.paymentMethod.blockchain": "Blockchain",
    "metadata.paymentMethod.card": "Karte",
    "metadata.paymentMethod.cash": "Bar",
    "metadata.paymentMethod.paypal": "PayPal",
    "metadata.paymentMethod.unknown": "Unbekannt",
};
