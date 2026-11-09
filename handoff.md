# Cathea Studio Portal Handoff

## Current state

The Flask portal has separate Administrator, Management, and Employee access. Employee Space supports work assignments and employee-specific calendar events. Management selects which employees can see each event; employees only see events assigned to them. Events use one date and one of these types:

- Wedding - Full Day
- Wedding - Half Day
- Event - Long
- Event - Short
- Photoshoot
- Pre-Wedding Shoot
- Advertisement Shoot

The Commissions page supports employee-specific rates for every event type, an event commission ledger, and administrator-entered additions or deductions in Rp. Event commissions snapshot each selected employee's rate when the event is created.

Employees can view their own commissions and payment status; upcoming commission descriptions remain visible without displaying currency amounts. Accounts can change their own passwords, and administrators can reset account passwords. The account list is searchable, filterable, and collapsible.

## Media uploads and Google Drive videos

Gallery photos, Cinema videos, and homepage hero videos support browser uploads in chunks (4 MiB by default), including selecting a folder. An interrupted upload can resume in the same browser session when the user selects the same file again. Upload completion is retry-safe to avoid duplicate media entries.

Gallery photo uploads now begin automatically after files or a folder are selected, or images are dropped into the gallery workspace; the separate Upload photos button is no longer required. The gallery-published confirmation dialog is explicitly centered in the viewport. Local browser verification confirmed automatic uploads from file selection, folder selection, and drag-and-drop, and confirmed the publish dialog is centered at desktop and mobile viewport sizes. A deployed test with real media is still recommended.

The portal also supports listing-only Hide/Show controls for published galleries and Cinema videos. Hiding an item removes it from the public Photos or Cinema listing without changing gallery publication, direct gallery access, or homepage selections. Existing hidden states are migrated where identifiable.

Administrators can also use **Import from server folder** in Cinema or a gallery section to copy supported files from `MEDIA_IMPORT_ROOT`. The importer is admin-only and confines browsing to that configured root.

Cinema and the homepage hero accept Google Drive shared-file links. Supported link forms include `/file/d/FILE_ID/view`, `/open?id=FILE_ID`, and `/uc?id=FILE_ID`. The app converts recognized links to Drive's `/preview` embed URL. Set the Drive file's General access to **Anyone with the link** for public playback; Drive permissions and playback limits still apply. A live test with a real shared Drive video remains to be done.

Media configuration:

- `MEDIA_STORAGE_DIR` — directory for served media; defaults to `static/uploads`.
- `MEDIA_STAGING_DIR` — private chunk staging directory; defaults to `instance/media-upload-staging`.
- `MEDIA_IMPORT_ROOT` — optional server-side source directory for administrator imports.
- `MEDIA_UPLOAD_CHUNK_SIZE` — chunk size in bytes; defaults to 4 MiB and must be positive and below Flask's 32 MiB `MAX_CONTENT_LENGTH`. The hosting proxy must also allow at least this request size.
- `MAX_MEDIA_FILE_SIZE` — maximum size of each media file; defaults to 4 GiB.

On hosting, configure media and staging paths as persistent, writable mounted storage. With multiple app instances, the shared media volume must be available to every instance, and staging must be shared if uploads need to resume across instances. Keep staging outside the public media directory.

## Google Calendar integration

The existing Google Calendar iframe is display-only. The portal now also has an administrator-only OAuth flow to connect a Google account, create all-day Calendar API events, and send invitations to selected employees with valid email addresses.

Configure these environment variables; never commit their values:

- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`
- `GOOGLE_CALENDAR_TOKEN_KEY` — a Fernet key; keep a secure backup because stored OAuth tokens depend on it.
- `GOOGLE_CALENDAR_REDIRECT_URI` — must exactly match the redirect URI registered on the Google OAuth web client.
- `GOOGLE_CALENDAR_ID` — optional; defaults to `primary`.

In Google Cloud Console, enable the Google Calendar API, configure the OAuth consent screen, create a Web application OAuth client, and register the redirect URI displayed under **Accounts & Activity → Google Calendar connection**. Then sign in as an administrator and select **Connect Google Calendar**. Google OAuth credentials were not configured in the development environment, so a real account connection and invitation delivery remain to be tested.

When Google is connected, employee accounts require an email address. Existing accounts can be updated under **Accounts & Activity**. New portal events are first saved in the portal; if Google sync fails, the portal event remains and management receives a warning. A successful Google insertion sends invitations to the selected employees.

## Important implementation files

- `app.py` — portal access control, employee email validation, OAuth flow, encrypted credential handling, Calendar API insert, event and commission routes.
- `models.py` — `User.email`, `CalendarEvent`, `GoogleCalendarCredential`, `EventCommission`, `EmployeeCommissionRate`, and `CommissionAdjustment`.
- `database.py` — startup migrations for existing user and event tables.
- `config.py` — Google OAuth and Calendar environment settings.
- `templates/portal_accounts.html` — employee email editing and Google connection controls.
- `templates/portal_employee.html` — date-only event creation and employee recipient selection.
- `templates/portal_commissions.html` — employee rates, commission ledgers, and adjustments.
- `templates/portal_dashboard.html` — Cinema uploads and Google Drive video links, homepage video settings, and server-folder importing.
- `templates/portal_gallery_detail.html` — gallery photo uploads and server-folder importing.
- `static/js/media-transfer.js` — browser chunk uploader, resume behavior, automatic gallery upload on selection, and server-folder import UI.
- `static/js/gallery-manager.js` — drag-and-drop gallery uploads, crop controls, and gallery dialogs.
- `static/css/portal.css` — portal and calendar form styling, including the centered gallery publish dialog.
- `static/js/gallery.js` — Cinema modal player for hosted, YouTube, Vimeo, and Google Drive videos.
- `requirements.txt` — Google OAuth/API and Fernet dependencies.
- `README.md` — local and deployment OAuth setup instructions.

## Validation completed

- Python compilation passed for the changed Python modules.
- Isolated database tests covered existing-database email migration, employee account email validation/editing, OAuth state handling, encrypted token storage, event recipient addresses, `sendUpdates=all`, and Google Calendar all-day event payloads.
- Calendar API calls were mocked for tests; no real Google account credentials or calendar events were used.
- Media checks covered chunk upload, identical-chunk retries, completion idempotency, exact saved bytes, server-folder import, and traversal rejection. Python compilation and editor diagnostics passed; the browser parsed and executed the upload script.
- Google Drive link checks covered the supported URL forms, validation, conversion to Drive preview URLs, and saving a video through the Cinema link route. A browser check confirmed the Cinema modal creates a Drive preview iframe; the test file ID was a placeholder, so the real-file playback check remains open.
- Listing-only gallery/video visibility checks covered a legacy-state migration, repeatable migration, hidden gallery direct URLs, homepage visibility, portal controls, and hide/show routes using temporary SQLite databases.
- Browser testing used an isolated temporary database and storage directory; no test media or database changes were written to the project data.

## Next steps

1. Initialize a private GitHub repository and push only source files; verify `.gitignore` excludes `.venv/`, `cathea.db`, `instance/`, `static/uploads/`, `.env` files, and bytecode.
2. Create a Railway service from GitHub, attach a persistent volume at `/data`, and set `DATABASE_URL=sqlite:////data/cathea.db`, `MEDIA_STORAGE_DIR=/data/uploads`, and `MEDIA_STAGING_DIR=/data/media-upload-staging`.
3. Add GitHub Actions repository secrets `RAILWAY_TOKEN`, `RAILWAY_PROJECT_ID`, and `RAILWAY_SERVICE_ID`; the workflow in `.github/workflows/deploy-railway.yml` deploys `main` with Railway CLI.
4. Add a strong Railway `SECRET_KEY`; set the optional Google Calendar variables only when OAuth is configured. Set Railway's health check path to `/healthz`.
5. Back up the local database, copy `cathea.db` and `static/uploads/` to the Railway volume while writes are stopped, and verify homepage, Photos, Cinema, portal login, gallery/video management, and one real upload.
6. Change the seeded local administrator password immediately after migration and rotate production secrets before public launch.
7. Verify the hosting proxy request-size limit is at least the configured `MEDIA_UPLOAD_CHUNK_SIZE`, then test uploads/imports with real media on the deployed instance, including survival across a restart if required.
8. Confirm deployed gallery uploads auto-start for file, folder, and drag/drop selection, and the published-gallery dialog is centered on desktop and mobile.
9. Add a real Google Drive video with General access set to **Anyone with the link**, then verify playback on Cinema and as the homepage hero.
10. Configure the Google Cloud OAuth client and environment secrets on the deployment.
11. Verify the displayed Calendar callback URI matches the registered URI exactly, connect the calendar as an administrator, and test a small event with consenting recipients.
12. Confirm the chosen `GOOGLE_CALENDAR_ID` is writable by the connected Google account.
