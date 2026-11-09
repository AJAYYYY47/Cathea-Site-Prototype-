# cathea — celebrating love.

An interactive, contemporary editorial website for **cathea** (`@cathea.studio`), inspired by fine-art photography book layouts and kinetic interactive art installations.

---

## 🏛️ Aesthetic Architecture & Features

1. **Homepage Gallery Preview (Inspired by Reference Mood Board)**
   - Staggered asymmetric contact-sheet layout with intentional negative whitespace tiles.
   - Interspersed candid moments: tea ceremony, couple outdoors, bridesmaids in silk, two rings on satin pearls, gold heirloom emblem, bride alone with veil, and balcony embrace.

2. **Kinetic Animation with Looping Ambient Video Effect**
   - Interactive Blandina-style kinetic wave canvas overlaying an ambient looping motion video.
   - Balanced with a delicate gradient veil and grayscale filter so the video and particle wave harmonize crisply.

3. **Undercase Butler-Light Branding & Crisp Header**
   - Brand mark is styled in undercase `cathea` using Butler-Light typography.
   - Header is styled with a sharp `#111111` hairline bottom rule and high contrast so it never blends into the background.

4. **"celebrating love." Theme**
   - Replaced all destination tagline texts with `celebrating love.`.

5. **About / Manifesto Hero Section Near End of Main Page**
   - Minimalist full-width feature block near the footer with large Butler typography: `celebrating love.`.
   - Art statement on authentic presence, unposed intimacy, and timeless framing.

6. **Alternating Grid with Responsive Micro-Watermarks**
   - On `/photos` and `/cinema`: dynamic alternating grid rhythms (square, 4:5 portrait, and 16:10 wide).
   - Every single photo and video card features:
     - Top-right: very small `cathea`
     - Bottom-right: very small couple initials (e.g. `c + j`, `m + r`, `j + k`)
     - Backed by an ultra-thin glass pill (`rgba(0,0,0,0.48)` + `backdrop-filter: blur(8px)`) so it is readable on any photo background without blending.

7. **Tucked "Consult Us" Assistant (No Green Buttons / No WhatsApp Logos)**
   - Subtle rectangular black button tucked at bottom-right corner.
   - Opens a monochrome consultation drawer with AI assistance or 1-click text handoff to WhatsApp.

8. **Role-based Team Portal**
   - Administrator: manage accounts and roles, revoke sessions, set access timeouts, and review account activity.
   - Management: manage the website, galleries, assignments, and commissions.
   - Employee: view their Employee Space, calendar, assigned work, upcoming commissions, and payment status.

---

## 🚀 Running The Site

```bash
python3 app.py
```

- **Homepage**: [http://127.0.0.1:5002](http://127.0.0.1:5002)
- **Photos Gallery**: [http://127.0.0.1:5002/photos](http://127.0.0.1:5002/photos)
- **Cinema**: [http://127.0.0.1:5002/cinema](http://127.0.0.1:5002/cinema)
- **Inquiries**: [http://127.0.0.1:5002/inquiries](http://127.0.0.1:5002/inquiries)
- **Local Staff Login**: [http://127.0.0.1:5002/portal/login](http://127.0.0.1:5002/portal/login)

## GitHub and Railway deployment

The repository should contain application source only. Before the first push, confirm that `.venv/`, `cathea.db`, `instance/`, `static/uploads/`, `.env` files, and Python bytecode are ignored by `.gitignore`. Do not commit Google OAuth credentials, Fernet keys, API keys, or production database/media files.

This project includes a `Procfile` for Railway:

```text
web: gunicorn --bind 0.0.0.0:$PORT --workers 2 --threads 4 --timeout 120 app:app
```

### Railway setup

1. Create a **private** GitHub repository and push the source files after reviewing `git status --ignored`.
2. Create a Railway project from that GitHub repository. Railway will install `requirements.txt` and use the `Procfile`.
3. Add a Railway volume and mount it at `/data`. Use these variables:

   ```text
   DATABASE_URL=sqlite:////data/cathea.db
   MEDIA_STORAGE_DIR=/data/uploads
   MEDIA_STAGING_DIR=/data/media-upload-staging
   ```

4. Add a strong random `SECRET_KEY`. If Google Calendar is enabled, also add `GOOGLE_OAUTH_CLIENT_ID`, `GOOGLE_OAUTH_CLIENT_SECRET`, `GOOGLE_CALENDAR_TOKEN_KEY`, `GOOGLE_CALENDAR_REDIRECT_URI`, and optionally `GOOGLE_CALENDAR_ID`.
5. Set Railway's health check path to `/healthz`, deploy, and open the generated Railway domain. The public site is `/`; the portal is `/portal/login`.
6. Change the seeded local administrator password immediately after the first successful login. The current seed password is intended only for local development and must not be used as a production credential.

### Optional GitHub Actions deployment

The repository includes `.github/workflows/deploy-railway.yml`. It deploys `main` to Railway after each push and can also be started manually from the **Actions** tab. In the GitHub repository settings, add these **Repository secrets**:

```text
RAILWAY_TOKEN       # Railway project/service deployment token
RAILWAY_PROJECT_ID  # Railway project ID
RAILWAY_SERVICE_ID  # Railway web service ID
```

The workflow installs Railway's official CLI and runs `railway up --ci`. Configure the Railway volume and variables in the Railway service before the first workflow run. GitHub Actions secrets are only for deployment access; application variables such as `SECRET_KEY` and `DATABASE_URL` belong in Railway's service Variables.

### Migrating the current site

Do not put the current database or media in GitHub. Back up `cathea.db` first, then copy it and the contents of `static/uploads/` to the mounted Railway volume as `/data/cathea.db` and `/data/uploads/`. Copy `instance/media-upload-staging/` to `/data/media-upload-staging/` only if interrupted uploads need to survive the migration. Stop writes during the copy, or take a consistent SQLite backup, to avoid copying a partially written database.

After migration, verify `/healthz`, the homepage, `/photos`, `/cinema`, portal login, gallery/video management, and one upload. Rotate `SECRET_KEY` and any Google/Fernet credentials before making the deployment public. Keep an independent backup of the SQLite database and media volume; a GitHub repository is not a media backup.

Railway's generated domain can be used initially. A custom domain, object storage for media, and a managed database can be added later if traffic or media volume outgrows SQLite and a Railway volume.

## Team Portal Deployment

The portal host is configurable so local development can continue to use `/portal`, while deployment can use a dedicated host such as `portal.example.com`.

1. Point the `portal` DNS record to the same web service as the public site and configure TLS and the reverse proxy to forward that hostname to this Flask app.
2. Set `PORTAL_HOST=portal.example.com` in the app environment. Set `PORTAL_SCHEME=https` if the proxy needs an explicit redirect scheme.
3. The provided Google Calendar embed is preconfigured. To replace it, set `GOOGLE_CALENDAR_EMBED_URL` to the URL from the calendar's iframe `src`. The embed remains display-only; portal events are inserted into Google Calendar through the OAuth setup below.
4. Restart the app. Requests to `/portal` on the public host redirect to the portal hostname; the portal root opens its login page.

Administrators can create accounts and set their roles in **Accounts & Activity**. Session termination and role changes take effect on the account's next request. In **Commissions**, administrators can set a separate Rp rate for each employee and event type, and add or deduct one-time fees. An event uses the employee's rate when it is created; completed assignment commissions and event commissions (on the event date) are included in earned totals. Employees can view their own upcoming commission estimates, earned and unpaid commissions, payment status, and adjustments in **My Commissions**. The portal does not currently track a fixed salary or the payment status of manual adjustments.

### Media uploads and server-folder imports

Browser uploads for gallery photos, Cinema videos, and the homepage hero video are sent in 4 MiB chunks by default. You can choose individual files or a folder from your computer; interrupted uploads can resume when you select the same file(s) again in the same browser session. The Flask request limit remains 32 MiB, while the hosting proxy must allow a request at least as large as the configured chunk. Set `MEDIA_UPLOAD_CHUNK_SIZE` (in bytes) to a smaller value if needed; it must be positive and below Flask's `MAX_CONTENT_LENGTH`.

In the portal's **Galleries** manager, use **Hide gallery** or **Show gallery** to remove a published gallery from or restore it to the public gallery listing. Hidden galleries remain published, accessible by their direct URL, and eligible for homepage use. In **Cinema**, the corresponding video controls affect only the public Cinema listing; hidden videos remain available for homepage selections and hero use.

Media files are served from `MEDIA_STORAGE_DIR` (an absolute path). It defaults to `static/uploads` for local development. For hosting, set it to a persistent mounted volume path so uploads survive deploys and restarts, and ensure the app process can write to that directory. The volume must be available to every app instance that serves the media. In-progress chunks are stored outside the public web directory under `MEDIA_STAGING_DIR` (default: `instance/media-upload-staging`); mount this path persistently as well if interrupted uploads need to survive restarts.

For example, use the same settings with paths appropriate to each environment:

```text
# Local development
MEDIA_STORAGE_DIR=/Users/you/CatheaMedia
MEDIA_STAGING_DIR=/Users/you/CatheaMediaStaging
MEDIA_IMPORT_ROOT=/Users/you/MediaToImport

# Hosting: paths must be on persistent mounted storage
MEDIA_STORAGE_DIR=/mnt/cathea/media
MEDIA_STAGING_DIR=/mnt/cathea/staging
MEDIA_IMPORT_ROOT=/mnt/cathea/import
```

To import files that are already on the app server, set `MEDIA_IMPORT_ROOT` to a directory the app can read. Administrators can use **Import from server folder** in the Cinema manager or a gallery section to browse that root and copy supported files into media storage. Imported images support PNG, JPG/JPEG, WEBP, and GIF; videos support MP4, MOV, and WEBM. The importer cannot browse a visitor's computer; use the file/folder upload controls for files on your computer.

`MAX_MEDIA_FILE_SIZE` sets the per-file limit in bytes and defaults to 4 GiB. Keep media storage and upload staging on persistent writable storage if uploads must survive app restarts while in progress.

Cinema and the homepage hero also accept Google Drive shared-file links (for example, `https://drive.google.com/file/d/FILE_ID/view`). Set the file's General access to **Anyone with the link** so visitors can play it. The site embeds Drive's preview player; Google Drive permissions and playback limits still apply.

### Google Calendar API and invitations

1. In Google Cloud Console, create or select a project, enable the **Google Calendar API**, and configure the OAuth consent screen. Add the Google account that owns or can edit the target calendar as a test user if the consent screen is in Testing.
2. Create an OAuth client ID with application type **Web application**. Add the exact redirect URI shown in **Accounts & Activity → Google Calendar connection** to the OAuth client's Authorized redirect URIs.
3. Configure these environment variables in the app host's secret/environment settings (do not commit credentials):
   - `GOOGLE_OAUTH_CLIENT_ID`: OAuth web client ID.
   - `GOOGLE_OAUTH_CLIENT_SECRET`: OAuth web client secret.
   - `GOOGLE_CALENDAR_REDIRECT_URI`: the exact callback URI registered in Google Cloud. For local work this is usually `http://127.0.0.1:5002/portal/calendar/google/callback`; with `PORTAL_HOST` it is `https://portal.example.com/calendar/google/callback`.
   - `GOOGLE_CALENDAR_TOKEN_KEY`: a Fernet encryption key. Generate it in a trusted local shell with `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` and store the output as a secret. Back up this key securely; the portal cannot decrypt its saved OAuth token without it.
   - `GOOGLE_CALENDAR_ID`: optional; defaults to `primary`. Set it to the target shared calendar ID when the authorizing account should write to a shared team calendar.
4. Restart the app, sign in as administrator, open **Accounts & Activity**, and select **Connect Google Calendar**. Complete Google's consent flow using the account that can create events on the target calendar.
5. Add each employee's email in **Accounts & Activity**. When the connection is active, creating an Employee Space event inserts an all-day event on the selected date and sends Google Calendar invitations to the selected employees (`sendUpdates=all`). Events remain visible in Employee Space according to its employee selection even if a Google invitation is declined.

The portal stores OAuth tokens encrypted in the database with `GOOGLE_CALENDAR_TOKEN_KEY`, refreshes access tokens when needed, and does not store client secrets in source code. Disconnecting removes the locally stored token; revoke the app separately from the Google account's security settings if needed. If Google event creation fails after an Employee Space event is saved, the event remains in the portal with a sync error shown to management.
