# Source images

Set `AP_SOURCE_DOCUMENT_DIRECTORY` in `app/core/config.py` to the directory containing
the original JPEG documents. The default is `PROJECT_ROOT / "data" / "AP_source_files"`.
Place files there using their exact stored `source_filename`; the API neither
creates the directory nor copies, renames, or converts images.

`GET /acct/v0/source-documents/{filename}` returns a `FileResponse` with media type
`image/jpeg`. Only `.jpg` and `.jpeg` extensions are accepted, case-insensitively;
the filename itself is preserved exactly. This is extension validation, not image
content decoding. Unsupported extensions return 415. Invalid basenames return
400; paths containing slashes do not match the route and return 404. Resolved
paths (including symlink targets) must remain inside the configured directory.
Missing files and directories requested as files return 404.

The route uses the existing accounting router and local application's access
model (no authentication), with no database dependency or entry-ID requirement.
Both `GET /acct/v0/entries` and `GET /acct/v0/entries/{entry_id}` already include
the optional `source_filename` field. No schema change is needed.

For a non-null source filename, the future frontend should use:

```javascript
const url = `/acct/v0/source-documents/${encodeURIComponent(entry.source_filename)}`;
```

No frontend behavior is changed by this backend addition.
