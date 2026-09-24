export const EN = {
    // Application
    "app.title": "Accounting",
    "app.subtitle": "Review, maintain and add bookkeeping entries.",

    // Navigation
    "nav.accountsPayable": "Accounts Payable",
    "nav.accountsReceivable": "Accounts Receivable",
    "nav.newEntries": "New Entries",
    "nav.yearlySummary": "Yearly Summary",
    "nav.ariaLabel": "Bookkeeping sections",

    // Language
    "language.label": "Language",
    "language.english": "English",
    "language.german": "German",

    // Common actions
    "common.save": "Save Changes",
    "common.cancel": "Cancel",
    "common.refresh": "Refresh",
    "common.previous": "Previous",
    "common.next": "Next",
    "common.edit": "Edit",
    "common.process": "Process",
    "common.copy": "Copy",
    "common.loading": "Loading...",
    "common.none": "None",

    // Common fields
    "common.date": "Date",
    "common.amount": "Amount",
    "common.currency": "Currency",
    "common.status": "Status",
    "common.remarks": "Remarks",
    "common.reference": "Reference",

    // Accounts Payable
    "ap.selectedEntry": "Selected Entry Detail",
    "ap.selectedEntryHelp":
        "Select an entry from the list to inspect it. Unlock editing to modify raw fields. Derived fields remain read-only and are recalculated by the backend.",

    "ap.sourceImage": "Source Image",
    "ap.sourceImageHelp":
        "JPEG source associated with the selected entry.",

    "ap.sourceImage.entryNavigation": "Entry image navigation",
    "ap.sourceImage.previousEntry": "Previous entry",
    "ap.sourceImage.nextEntry": "Next entry",

    "ap.sourceImage.zoomControls": "Image zoom controls",
    "ap.sourceImage.zoomOut": "Zoom out",
    "ap.sourceImage.zoomIn": "Zoom in",
    "ap.sourceImage.zoomOutTitle": "Zoom out (−)",
    "ap.sourceImage.zoomInTitle": "Zoom in (+)",
    "ap.sourceImage.fit": "Fit",
    "ap.sourceImage.fitTitle": "Fit entire image (0)",

    "ap.sourceImage.viewerHelp":
        "Source image viewer. Ctrl+wheel or plus and minus to zoom; drag to pan; 0 to fit.",

    "ap.sourceImage.alt":
        "Source document for the selected entry",

    "ap.sourceImage.empty":
        "Select an entry to display its source JPEG.",

    "ap.sourceImage.file": "File:",
    "ap.sourceImage.noneSelected": "None selected",
    "ap.entries": "Entries",
    "ap.processing": "Processing",

    "ap.processEntry": "Process Entry",
    "ap.unlockEditing": "Unlock Editing",

    "ap.editableRawFields": "Editable Raw Fields",
    "ap.derivedReadOnlyFields": "Derived / Read-only Fields",

    "ap.field.type": "Type",
    "ap.field.category": "Category",
    "ap.field.taxScope": "Tax Scope",
    "ap.field.counterparty": "Counterparty",
    "ap.field.paymentMethod": "Payment Method",
    "ap.field.paymentDate": "Payment Date",
    "ap.field.amountOriginal": "Amount Original",
    "ap.field.currencyOriginal": "Currency Original",
    "ap.field.hasInvoice": "Has invoice",
    "ap.field.invoiceNumber": "Invoice Number",
    "ap.field.invoiceDate": "Invoice Date",
    "ap.field.remarks": "Remarks",
    "ap.field.tags": "Tags, comma-separated",
    "ap.field.sourceFilename": "Source Filename",

    "ap.field.bookingYear": "Booking Year",
    "ap.field.amountCommon": "Amount Common",
    "ap.field.currencyCommon": "Currency Common",
    "ap.field.exchangeRate": "Exchange Rate",
    "ap.field.exchangeRateDate": "Exchange Rate Date",
    "ap.field.vatRatePercent": "VAT Rate Percent",
    "ap.field.vatAmount": "VAT Amount",
    "ap.field.deductiblePercent": "Deductible Percent",
    "ap.field.deductibleAmount": "Deductible Amount",
    "ap.field.deductibleVatAmount": "Deductible VAT Amount",
    "ap.field.writeoffMethod": "Write-off Method",
    "ap.field.conversionStatus": "Conversion Status",
    "ap.field.conversionNote": "Conversion Note",
    "ap.field.createdAt": "Created At",
    "ap.field.updatedAt": "Updated At",
    "ap.entriesHelp":
        "Select a row to inspect its data and source image.",
    "ap.entries.column.vat": "VAT",
    "ap.entries.column.deductible": "Deductible",
    "ap.processEntries": "Process Entries",
    "ap.processingHelp":
        "Recalculate all Accounts Payable entries using current rules and stored historical rates.",

    // AP validation
    "ap.validation.payloadObject": "Payload must be one JSON object.",
    "ap.validation.entryTypeRequired": "Entry type is required.",
    "ap.validation.categoryRequired": "Category is required.",
    "ap.validation.taxScopeRequired": "Tax scope is required.",
    "ap.validation.counterpartyRequired": "Counterparty is required.",
    "ap.validation.paymentMethodRequired": "Payment method is required.",
    "ap.validation.paymentDateRequired": "Payment date is required.",
    "ap.validation.amountPositive": "Amount must be greater than zero.",
    "ap.validation.currencyRequired": "Currency is required.",
    "ap.validation.invoiceDateRequired":
        "Invoice date is required when invoice exists.",

    // AP dynamic table state
    "ap.table.pending": "pending",

    // AP dynamic source-image state
    "ap.sourceImage.noSource": "No source image",
    "ap.sourceImage.noSourceAssociated":
        "No source image associated with this entry.",
    "ap.sourceImage.loading": "Loading source image…",
    "ap.sourceImage.loadFailed": "Unable to load source image.",

    // AP dynamic status messages
    "ap.status.loadedEntry": "Loaded entry",
    "ap.status.noEntrySelected": "No entry selected.",
    "ap.status.updatedEntry": "Updated entry",
    "ap.status.processing": "Processing…",
    "ap.status.processed": "processed",
    "ap.status.failed": "failed",
    "ap.status.reprocessing":
        "Reprocessing pending currency conversions...",
    "ap.status.selectEntryFirst": "Select an entry first.",
    "ap.status.editingUnlocked":
        "Editing unlocked. Derived fields remain read-only.",
    "ap.status.editCancelled": "Edit cancelled.",

    // Accounts Receivable
    "ar.selectedInvoice": "Selected Outgoing Invoice",
    "ar.sourcePdfs": "AR Source PDFs",
    "ar.outgoingInvoices": "Outgoing Invoices",
    "ar.processing": "Outgoing Invoice Processing",
    "ar.processEntry": "Process Entry",
    "ar.processEntries": "Process Entries",
    "ar.updateFromDirectory": "Update DB from Directory",

    // Incoming payments
    "payments.title": "Incoming Payments",
    "payments.newPayment": "New Payment",
    "payments.paymentDate": "Payment Date",
    "payments.payer": "Payer",
    "payments.paymentMethod": "Payment Method",
    "payments.bankReference": "Bank / Reference",
    "payments.allocatedAmount": "Allocated Amount",
    "payments.unallocatedAmount": "Unallocated Amount",

    // Allocations
    "allocations.title": "Payments / Allocations",
    "allocations.incomingPayment": "Incoming Payment",
    "allocations.allocatedAmount": "Allocated Amount",
    "allocations.allocatePayment": "Allocate Payment",
    "allocations.noAllocations": "No allocations.",

    // Recognition
    "recognition.title": "Recognition",

    // New Entries
    "newEntries.title": "New Entry",
    "newEntries.batchTitle": "JSON Batch Entry",
    "newEntries.contractTitle": "Entry Creation Contract",
    "newEntries.saveEntry": "Save Entry",
    "newEntries.loadExample": "Load Example JSON",
    "newEntries.submitJson": "Submit JSON",
    "newEntries.fetchContract": "Fetch Contract",
    "newEntries.copyContract": "Copy Contract",

    // Accounting category display labels
    "metadata.category.auto": "Car / Vehicle",
    "metadata.category.bahn": "Rail travel",
    "metadata.category.betriebsbedarf": "Business supplies",
    "metadata.category.betriebskosten": "Operating expenses",
    "metadata.category.bewirtung": "Business entertainment",
    "metadata.category.buro": "Office",
    "metadata.category.bvg": "Public transport",
    "metadata.category.eingang": "Income / Receipt",
    "metadata.category.einkommen-kirchen-soli-vorauszahlung":
        "Income / Church / Solidarity tax prepayment",
    "metadata.category.einrichtung": "Furnishings",
    "metadata.category.fachliteratur": "Professional literature",
    "metadata.category.festnetz": "Landline",
    "metadata.category.haftpflichtversicherung": "Liability insurance",
    "metadata.category.handy-prepaid": "Mobile prepaid",
    "metadata.category.handy-vertrag": "Mobile contract",
    "metadata.category.hausratversicherung": "Household contents insurance",
    "metadata.category.honorar": "Professional fee",
    "metadata.category.krankenversicherung": "Health insurance",
    "metadata.category.n/a": "N/A",
    "metadata.category.pfegeversicherung": "Long-term care insurance",
    "metadata.category.porto-mit-ust": "Postage with VAT",
    "metadata.category.porto-ohne-ust": "Postage without VAT",
    "metadata.category.raum": "Premises / Space",
    "metadata.category.reiseversicherung": "Travel insurance",
    "metadata.category.rentenversicherung": "Pension insurance",
    "metadata.category.steuerberatung": "Tax consulting",
    "metadata.category.ubernachtung": "Accommodation",
    "metadata.category.umsatzsteuer-vorauszahlung": "VAT prepayment",
    "metadata.category.werbung": "Advertising",
    "metadata.category.werkzeug": "Tools",
    "metadata.category.werkzeug-mehrjaehrige-abschreibung":
        "Tools — multi-year depreciation",

    // Yearly summary
    "summary.title": "Yearly Accounting Summary",
    "summary.year": "Year",

    // Metadata display labels
    "metadata.entryType.correction": "Correction",
    "metadata.entryType.expense": "Expense",
    "metadata.entryType.income": "Income",
    "metadata.entryType.private": "Private",
    "metadata.entryType.tax": "Tax",

    "metadata.taxScope.domestic": "Domestic",
    "metadata.taxScope.eu": "EU",
    "metadata.taxScope.not_applicable": "Not applicable",
    "metadata.taxScope.third_country": "Third country",

    "metadata.paymentMethod.bank_transfer": "Bank transfer",
    "metadata.paymentMethod.blockchain": "Blockchain",
    "metadata.paymentMethod.card": "Card",
    "metadata.paymentMethod.cash": "Cash",
    "metadata.paymentMethod.paypal": "PayPal",
    "metadata.paymentMethod.unknown": "Unknown",
};
