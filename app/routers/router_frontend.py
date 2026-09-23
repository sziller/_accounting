# app/routers/router_frontend.py

"""
=== Module: router_frontend ===
Define the HTTP router responsible for serving the application's local
browser-based frontend.

This module contains the presentation-layer entry point for the bookkeeping
application. Its responsibility is deliberately narrow: render the main
Jinja2 HTML template and expose it through the root browser URL.

Accounting data is not queried or injected into the HTML template by this
module. The rendered page acts as the frontend shell; browser-side JavaScript
subsequently communicates with the accounting API endpoints to retrieve and
modify application data.

=== Responsibilities ===
- Configure the Jinja2 template directory.
- Define `FrontendRouter`.
- Register the browser root endpoint:
  - `GET /`
- Render `app/templates/index.html`.
- Pass the active FastAPI/Starlette `Request` object to Jinja2.

=== Non-Responsibilities ===
This module does not:

- access the accounting database;
- create SQLAlchemy sessions;
- query accounting entries;
- validate accounting-entry payloads;
- perform accounting calculations;
- perform currency conversion;
- expose static files;
- implement browser-side application behavior.

Static files are mounted separately by the application composition root, while
accounting data operations are handled by `AccountingEntriesRouter`.

=== Frontend Architecture ===
The browser loading sequence is conceptually:

GET /
    ->
FrontendRouter.index()
    ->
Jinja2 renders index.html
    ->
browser receives HTML
    ->
frontend JavaScript executes
    ->
JavaScript calls /acct/... API endpoints
    ->
accounting data is retrieved or modified

This separation means the HTML shell can render successfully even when a
later accounting API request fails.

=== Template Configuration ===
The module-level `templates` object is configured with:

`app/templates`

as its template directory.

Template lookup is therefore relative to that directory.

=== by Sziller & ChatGPT ===
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


templates = Jinja2Templates(directory="app/templates")


class FrontendRouter(APIRouter):
    """
    === Class: FrontendRouter ===
    FastAPI router responsible for serving the local bookkeeping browser
    frontend.

    `FrontendRouter` extends `APIRouter` and owns browser-facing HTML routes
    rather than accounting-data API routes.

    At present, the router exposes one endpoint:

    `GET /`

    which renders the application's main `index.html` template.

    === Purpose ===
    The class provides the presentation-layer entry point through which a user
    opens the bookkeeping application in a web browser.

    It intentionally keeps server-side frontend rendering minimal. The HTML
    page is rendered without accounting-entry data in its Jinja context.
    Dynamic data is retrieved after page load by browser-side JavaScript using
    the `/acct/...` API.

    === Route Ownership ===
    Currently registered route:

    - `GET /`
      - Handler: `index`
      - Response type: `HTMLResponse`
      - Purpose: render the main accounting frontend.

    === Authorization ===
    - No authentication or authorization is currently required.
    - The application is intended for local use on `127.0.0.1`.

    === Database Behavior ===
    - This router does not inject a SQLAlchemy session.
    - It does not access the accounting database directly.
    - It does not depend on accounting-entry persistence being successful in
      order to render the initial HTML shell.

    === Separation of Responsibilities ===
    `FrontendRouter` is responsible for HTML delivery.

    It is separate from:

    - `AccountingEntriesRouter`
      Handles accounting JSON API operations.

    - frontend JavaScript
      Handles browser-side API calls and interactive behavior.

    - FastAPI static-file mounting
      Serves JavaScript, CSS, and other static assets.

    - accounting services/processors
      Handle persistence and domain calculations.

    === Notes ===
    - The router currently has no URL prefix.
    - Its root path therefore resolves directly to `/`.
    - The router is tagged as `frontend` in FastAPI route metadata.
    - Additional browser pages can later be registered in this class if the
      application grows beyond a single-page frontend.

    === by Sziller & ChatGPT ===
    """

    def __init__(self) -> None:
        """
        === Method name: __init__ ===
        Initialize the frontend router and register its browser-facing routes.

        The constructor initializes the underlying FastAPI `APIRouter` and
        explicitly binds the application root URL to the `index()` handler.

        === Parameters ===
        - None.

        The constructor currently accepts no:
        - router prefix;
        - database configuration;
        - dependency injection configuration;
        - language setting;
        - authentication configuration.

        === Functionality ===
        1. Initializes the parent `APIRouter`.
        2. Assigns the FastAPI documentation tag:

           `frontend`

        3. Registers:

           `GET /`

           with:

           - endpoint: `self.index`
           - response class: `HTMLResponse`
           - OpenAPI summary: `Accounting frontend`

        === Registered Route ===
        Route:

        `GET /`

        Handler:

        `FrontendRouter.index`

        Response class:

        `HTMLResponse`

        FastAPI/OpenAPI summary:

        `Accounting frontend`

        === Database Behavior ===
        - No database session is created.
        - No database access occurs during router initialization.

        === Side Effects ===
        Instantiating this class creates the router's route definition in
        memory.

        It does not itself start the FastAPI application or HTTP server.

        The initialized router becomes part of the application only when it is
        included by the application composition root using:

        `api.include_router(frontend_router)`

        === Notes ===
        - Route registration occurs directly in the constructor using
          `add_api_route()`.
        - Unlike `AccountingEntriesRouter`, this router currently has no
          separate `reinit()` or route-registration lifecycle.
        - Because no prefix is supplied to the parent router, `/` remains the
          actual application-root path.

        === by Sziller & ChatGPT ===
        """
        super().__init__(tags=["frontend"])

        self.add_api_route(
            path="/",
            endpoint=self.index,
            methods=["GET"],
            response_class=HTMLResponse,
            summary="Accounting frontend",
        )

    def index(self, request: Request) -> HTMLResponse:
        """
        === Method name: index ===
        Render and return the main browser page of the bookkeeping application.

        HTTP endpoint:
        GET /

        This endpoint renders `app/templates/index.html` using the configured
        Jinja2 template engine and returns the resulting HTML document to the
        browser.

        The endpoint provides the frontend shell only. It does not retrieve
        accounting entries or other accounting-domain data before rendering.

        === Authorization ===
        - No authentication or authorization is currently required.
        - The application is intended for local use on `127.0.0.1`.

        === Parameters ===
        - `request: Request`
          FastAPI/Starlette request object representing the current HTTP
          request.

          FastAPI supplies this parameter automatically.

          The request object is passed to `Jinja2Templates.TemplateResponse`
          because Starlette/Jinja template rendering requires the active
          request context.

        === Functionality ===
        1. FastAPI receives:

           `GET /`

        2. FastAPI supplies the current `Request` object.
        3. The endpoint asks the module-level Jinja2 template engine to render:

           `index.html`

        4. The template is resolved relative to:

           `app/templates`

        5. An empty application-specific template context is supplied:

           `context={}`

        6. The rendered HTML response is returned to the browser.

        === Template Context ===
        No accounting data is currently injected server-side.

        The explicitly supplied application context is:

        `{}`

        The `request` object is supplied separately to `TemplateResponse`.

        Consequently, values such as:

        - accounting entries;
        - metadata;
        - categories;
        - currencies;
        - conversion state;

        are not populated into `index.html` by this endpoint.

        === Response Format ===
        Successful rendering returns:

        - **200 OK**
        - Content type: HTML
        - Response class: `HTMLResponse`
        - Rendered template: `app/templates/index.html`

        === Frontend Data Loading ===
        After the HTML document reaches the browser, frontend JavaScript is
        responsible for requesting dynamic application data through the
        accounting API.

        Conceptually:

        GET /
            ->
        render index.html
            ->
        browser loads page
            ->
        browser JavaScript executes
            ->
        GET /acct/v0/metadata
        GET /acct/v0/entries
        other /acct/... requests as required

        These API requests are independent HTTP requests and are not part of
        the server-side execution of `index()`.

        === Failure Isolation ===
        Because this endpoint does not query the accounting database, the root
        HTML page may still return successfully even if a subsequent accounting
        API request fails.

        For example:

        `GET /`
            -> 200 OK

        may be followed independently by:

        `GET /acct/v0/entries`
            -> 500 Internal Server Error

        without preventing the original HTML shell from being delivered.

        === Persistence Behavior ===
        - This is a read-only frontend-rendering endpoint.
        - It does not access the accounting database.
        - It does not create or modify accounting entries.
        - It does not create a SQLAlchemy session.
        - It does not trigger accounting calculations.
        - It does not trigger currency conversion.

        === Errors ===
        - **500 Internal Server Error**
          - May occur if template rendering fails unexpectedly.
          - Examples include:
            - `index.html` cannot be found;
            - template syntax/rendering failure;
            - unexpected Jinja2/Starlette processing failure.

        No application-specific 400, 404, or database-related error handling
        is currently implemented in this endpoint.

        === Static Assets ===
        This endpoint itself does not serve JavaScript, CSS, or other static
        resources.

        Static resources under `/static/...` are exposed separately by the
        FastAPI application's static-files mount.

        References from `index.html` to those resources therefore result in
        additional browser HTTP requests after the HTML document is received.

        === Notes ===
        - This is currently the only browser-page endpoint.
        - Server-side rendering is intentionally minimal.
        - `index.html` acts primarily as the application shell.
        - Accounting functionality is accessed through separate JSON API
          endpoints rather than embedded into the initial template response.
        - This architecture keeps browser presentation and accounting-domain
          processing separate.

        === by Sziller & ChatGPT ===
        """
        return templates.TemplateResponse(
            request=request,
            name="index.html",
            context={},
        )
