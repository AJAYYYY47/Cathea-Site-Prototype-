import json
import math
import os
import re
import secrets
import shutil
import time
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps
from pathlib import Path
from PIL import Image, UnidentifiedImageError
from sqlalchemy import func
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from cryptography.fernet import Fernet, InvalidToken
from flask import Flask, abort, g, render_template, request, jsonify, redirect, url_for, session, flash, send_from_directory
from oauthlib.oauth2 import OAuth2Error
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from requests.exceptions import RequestException
from werkzeug.utils import secure_filename, safe_join

from config import Config
from models import (
    db, User, Gallery, GallerySection, MediaItem, SiteSettings,
    HomepageContent, Inquiry, WorkAssignment, CalendarEvent, EmployeeCommissionRate,
    EventCommission, CommissionAdjustment, GoogleCalendarCredential, AccountActivity
)
from database import init_db, slugify
from llm_service import query_llm

app = Flask(__name__)
app.config.from_object(Config)

CALENDAR_EVENT_TYPES = (
    'Wedding - Full Day',
    'Wedding - Half Day',
    'Event - Long',
    'Event - Short',
    'Photoshoot',
    'Pre-Wedding Shoot',
    'Advertisement Shoot'
)
GOOGLE_CALENDAR_SCOPES = ['https://www.googleapis.com/auth/calendar.events']


def portal_host_matches(host):
    configured_host = (app.config.get('PORTAL_HOST') or '').lower()
    request_host = (host or '').lower()
    if not configured_host:
        return False
    configured_name = urlparse(f'//{configured_host}').hostname
    request_name = urlparse(f'//{request_host}').hostname
    configured_port = urlparse(f'//{configured_host}').port
    request_port = urlparse(f'//{request_host}').port
    return configured_name == request_name and (
        configured_port is None or configured_port == request_port
    )


class PortalHostMiddleware:
    def __init__(self, application, portal_host):
        self.application = application
        self.portal_host = portal_host

    def __call__(self, environ, start_response):
        if not portal_host_matches(environ.get('HTTP_HOST') or environ.get('SERVER_NAME')):
            return self.application(environ, start_response)

        path = environ.get('PATH_INFO', '/')
        if path == '/':
            environ['PATH_INFO'] = '/portal'
        elif not path.startswith(('/portal', '/static/', '/uploads/')):
            environ['PATH_INFO'] = f'/portal{path}'

        captured = {}

        def capture_response(status, headers, exc_info=None):
            captured['status'] = status
            captured['headers'] = headers
            captured['exc_info'] = exc_info

        body_iter = self.application(environ, capture_response)
        headers = captured['headers']
        rewritten_headers = []
        is_html = False
        for name, value in headers:
            if name.lower() == 'content-type' and 'text/html' in value.lower():
                is_html = True
            if name.lower() == 'location':
                location = urlparse(value)
                location_path = location.path
                if location_path == '/portal':
                    location_path = '/'
                elif location_path.startswith('/portal/'):
                    location_path = location_path[len('/portal'):]
                value = urlunparse(location._replace(path=location_path))
            rewritten_headers.append((name, value))

        if not is_html:
            start_response(captured['status'], rewritten_headers, captured.get('exc_info'))
            return body_iter

        try:
            body = b''.join(body_iter)
        finally:
            close = getattr(body_iter, 'close', None)
            if close:
                close()
        body = body.replace(b'/portal/', b'/').replace(b'/portal?', b'/?')
        body = body.replace(b'href="/portal"', b'href="/"')
        rewritten_headers = [
            (name, value) for name, value in rewritten_headers
            if name.lower() != 'content-length'
        ]
        rewritten_headers.append(('Content-Length', str(len(body))))
        start_response(captured['status'], rewritten_headers, captured.get('exc_info'))
        return [body]


# Ensure upload directory exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# Initialize database
init_db(app)

MEDIA_UPLOAD_CHUNK_SIZE = app.config['MEDIA_UPLOAD_CHUNK_SIZE']
if not 0 < MEDIA_UPLOAD_CHUNK_SIZE < app.config['MAX_CONTENT_LENGTH']:
    raise ValueError('MEDIA_UPLOAD_CHUNK_SIZE must be positive and smaller than MAX_CONTENT_LENGTH.')
MEDIA_UPLOAD_STAGING_DIR = app.config['MEDIA_STAGING_DIR']
os.makedirs(MEDIA_UPLOAD_STAGING_DIR, exist_ok=True)

def allowed_media_file(filename, media_type):
    extension = filename.rsplit('.', 1)[-1].lower() if '.' in filename else ''
    image_extensions = {'png', 'jpg', 'jpeg', 'webp', 'gif'}
    video_extensions = {'mp4', 'mov', 'webm'}
    return extension in (image_extensions if media_type == 'image' else video_extensions)


def generate_image_thumbnail_url(url):
    source_url = (url or '').strip()
    if not source_url:
        return ''

    parsed_source = urlparse(source_url)
    source_path = parsed_source.path or ''
    if source_path.startswith('/uploads/'):
        filename = os.path.basename(source_path)
        if not filename:
            return source_url
        if filename.lower().startswith('thumb_'):
            return source_url
        if filename != secure_filename(filename):
            return source_url

        upload_source_path = safe_join(app.config['UPLOAD_FOLDER'], filename)
        if not upload_source_path:
            return source_url
        if not os.path.isfile(upload_source_path):
            return source_url

        stem = Path(filename).stem
        thumb_filename = f'thumb_{stem}.jpg'
        thumb_disk_path = safe_join(app.config['UPLOAD_FOLDER'], thumb_filename)
        if not thumb_disk_path:
            return source_url
        thumb_url = f'/uploads/{thumb_filename}'

        if not os.path.isfile(thumb_disk_path):
            try:
                with Image.open(upload_source_path) as image:
                    if getattr(image, 'is_animated', False):
                        image.seek(0)
                    if image.mode not in ('RGB', 'L'):
                        image = image.convert('RGB')
                    image.thumbnail(
                        (640, 640),
                        getattr(Image, 'Resampling', Image).LANCZOS
                    )
                    image.save(thumb_disk_path, format='JPEG', quality=82, optimize=True)
            except (OSError, ValueError, UnidentifiedImageError):
                app.logger.warning('Unable to generate thumbnail for uploaded image: %s', source_url)
                return source_url
        return thumb_url

    host = (parsed_source.hostname or '').lower()
    if host == 'images.unsplash.com':
        query_params = parse_qs(parsed_source.query, keep_blank_values=True)
        query_params['auto'] = ['format']
        query_params['fit'] = ['crop']
        query_params['w'] = ['640']
        query_params['h'] = ['640']
        query_params['q'] = ['75']
        return urlunparse(parsed_source._replace(query=urlencode(query_params, doseq=True)))
    return source_url


def ensure_gallery_image_thumbnails(gallery):
    updated = False
    for item in gallery.items:
        if item.media_type != 'image':
            continue
        thumbnail_url = generate_image_thumbnail_url(item.url)
        if thumbnail_url and item.thumbnail_url != thumbnail_url:
            item.thumbnail_url = thumbnail_url[:600]
            updated = True
    if updated:
        db.session.commit()


def media_upload_stage_path(upload_id):
    try:
        normalized_id = str(uuid.UUID(upload_id))
    except (ValueError, AttributeError, TypeError):
        return None
    return os.path.join(MEDIA_UPLOAD_STAGING_DIR, normalized_id)


def media_import_root():
    configured_root = app.config.get('MEDIA_IMPORT_ROOT', '')
    return Path(configured_root).expanduser().resolve() if configured_root else None


def media_import_path(relative_path):
    root = media_import_root()
    if not root or not root.is_dir():
        return None
    if not isinstance(relative_path, str) or '\x00' in relative_path:
        return None
    try:
        candidate = (root / relative_path).resolve()
    except (OSError, RuntimeError, ValueError):
        return None
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def video_embed_url(url):
    parsed = urlparse(url or '')
    host = (parsed.hostname or '').lower().removeprefix('www.')
    drive_file_id = google_drive_file_id(parsed)
    if drive_file_id:
        return f'https://drive.google.com/file/d/{drive_file_id}/preview'
    video_id = ''
    if host in {'youtu.be', 'youtube.com', 'm.youtube.com', 'youtube-nocookie.com'}:
        if host == 'youtu.be':
            video_id = parsed.path.strip('/').split('/')[0]
        elif parsed.path.startswith('/embed/'):
            video_id = parsed.path.split('/')[2]
        else:
            video_id = parse_qs(parsed.query).get('v', [''])[0]
        return (
            f'https://www.youtube-nocookie.com/embed/{video_id}'
            f'?autoplay=1&mute=1&loop=1&playlist={video_id}&controls=0&playsinline=1'
        ) if video_id else ''
    if host in {'vimeo.com', 'player.vimeo.com'}:
        video_id = parsed.path.strip('/').split('/')[-1]
        if video_id.isdigit():
            return f'https://player.vimeo.com/video/{video_id}?background=1&autoplay=1&muted=1&loop=1'
    return ''


def google_calendar_event_url(assignment):
    if not assignment.scheduled_for:
        return ''
    start = assignment.scheduled_for.strftime('%Y%m%d')
    end = (assignment.scheduled_for + timedelta(days=1)).strftime('%Y%m%d')
    details = assignment.description or ''
    if assignment.deadline:
        details = f'{details}\nDeadline: {assignment.deadline.isoformat()}'.strip()
    query = urlencode({
        'action': 'TEMPLATE',
        'text': assignment.title,
        'dates': f'{start}/{end}',
        'details': details
    })
    return f'https://calendar.google.com/calendar/render?{query}'


def google_calendar_redirect_uri():
    configured_uri = app.config.get('GOOGLE_CALENDAR_REDIRECT_URI')
    if configured_uri:
        return configured_uri
    portal_host = app.config.get('PORTAL_HOST')
    if portal_host:
        scheme = app.config.get('PORTAL_SCHEME') or 'https'
        return f'{scheme}://{portal_host}/calendar/google/callback'
    return url_for('google_calendar_oauth_callback', _external=True)


def google_calendar_oauth_configured():
    return all((
        app.config.get('GOOGLE_OAUTH_CLIENT_ID'),
        app.config.get('GOOGLE_OAUTH_CLIENT_SECRET'),
        app.config.get('GOOGLE_CALENDAR_TOKEN_KEY')
    ))


def google_calendar_flow(state=None):
    client_config = {
        'web': {
            'client_id': app.config['GOOGLE_OAUTH_CLIENT_ID'],
            'client_secret': app.config['GOOGLE_OAUTH_CLIENT_SECRET'],
            'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
            'token_uri': 'https://oauth2.googleapis.com/token',
            'redirect_uris': [google_calendar_redirect_uri()]
        }
    }
    return Flow.from_client_config(
        client_config,
        scopes=GOOGLE_CALENDAR_SCOPES,
        state=state,
        redirect_uri=google_calendar_redirect_uri()
    )


def google_calendar_credential_record():
    return GoogleCalendarCredential.query.order_by(GoogleCalendarCredential.id.asc()).first()


def encrypt_google_credentials(credentials_json):
    encryption_key = app.config.get('GOOGLE_CALENDAR_TOKEN_KEY', '')
    if not encryption_key:
        raise ValueError('GOOGLE_CALENDAR_TOKEN_KEY is not configured.')
    return Fernet(encryption_key.encode('ascii')).encrypt(
        credentials_json.encode('utf-8')
    ).decode('ascii')


def save_google_calendar_credentials(credentials, connected_by_id=None):
    record = google_calendar_credential_record()
    if not record:
        if connected_by_id is None:
            raise ValueError('Google Calendar authorization record is missing.')
        record = GoogleCalendarCredential(connected_by_id=connected_by_id)
        db.session.add(record)
    record.encrypted_credentials = encrypt_google_credentials(credentials.to_json())
    if connected_by_id is not None:
        record.connected_by_id = connected_by_id
    db.session.commit()
    return record


def load_google_calendar_credentials():
    record = google_calendar_credential_record()
    if not record:
        return None
    encryption_key = app.config.get('GOOGLE_CALENDAR_TOKEN_KEY', '')
    if not encryption_key:
        raise ValueError('GOOGLE_CALENDAR_TOKEN_KEY is not configured.')
    encrypted_credentials = record.encrypted_credentials.encode('ascii')
    credentials_json = Fernet(encryption_key.encode('ascii')).decrypt(
        encrypted_credentials
    ).decode('utf-8')
    credentials = Credentials.from_authorized_user_info(
        json.loads(credentials_json),
        scopes=GOOGLE_CALENDAR_SCOPES
    )
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(GoogleAuthRequest())
        save_google_calendar_credentials(credentials)
    return credentials


def create_google_calendar_event(event):
    credentials = load_google_calendar_credentials()
    if not credentials:
        return None
    attendees = [
        {'email': employee.email}
        for employee in event.attendees
    ]
    body = {
        'summary': event.title,
        'description': event.description or '',
        'start': {'date': event.event_date.isoformat()},
        'end': {'date': (event.event_date + timedelta(days=1)).isoformat()},
        'attendees': attendees,
        'extendedProperties': {
            'private': {'cathea_portal_event_id': str(event.id)}
        }
    }
    service = build('calendar', 'v3', credentials=credentials, cache_discovery=False)
    response = service.events().insert(
        calendarId=app.config.get('GOOGLE_CALENDAR_ID') or 'primary',
        body=body,
        sendUpdates='all'
    ).execute()
    save_google_calendar_credentials(credentials)
    event_id = response.get('id')
    if not event_id:
        raise ValueError('Google Calendar returned no event ID.')
    return event_id


def account_email_error(email, role, exclude_user_id=None):
    normalized_email = (email or '').strip().lower()
    if role == 'employee' and not normalized_email:
        return 'An email address is required for employee accounts so Google Calendar invitations can be sent.'
    if normalized_email and (
        len(normalized_email) > 254
        or not re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', normalized_email)
    ):
        return 'Enter a valid email address.'
    if normalized_email:
        existing_email = User.query.filter(
            func.lower(User.email) == normalized_email,
            User.id != (exclude_user_id or 0)
        ).first()
        if existing_email:
            return 'That email address is already linked to another account.'
    return ''


def is_video_url(url):
    parsed = urlparse(url or '')
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        return False
    host = (parsed.hostname or '').lower().removeprefix('www.')
    if host == 'drive.google.com':
        return bool(google_drive_file_id(parsed))
    return (
        host in {'youtu.be', 'youtube.com', 'm.youtube.com', 'youtube-nocookie.com', 'vimeo.com', 'player.vimeo.com'}
        or parsed.path.lower().endswith(('.mp4', '.mov', '.webm'))
    )


def google_drive_file_id(parsed_url):
    if (parsed_url.hostname or '').lower().removeprefix('www.') != 'drive.google.com':
        return ''
    match = re.fullmatch(r'/file/d/([A-Za-z0-9_-]+)(?:/.*)?', parsed_url.path)
    if match:
        return match.group(1)
    if parsed_url.path in {'/open', '/uc'}:
        file_id = parse_qs(parsed_url.query).get('id', [''])[0]
        return file_id if re.fullmatch(r'[A-Za-z0-9_-]+', file_id) else ''
    return ''


def save_media_upload(file):
    filename = f'{uuid.uuid4().hex}_{secure_filename(file.filename)}'
    file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
    return f'/uploads/{filename}'


@app.context_processor
def inject_site_context():
    settings = SiteSettings.query.first()
    return dict(settings=settings)


@app.after_request
def prevent_portal_page_caching(response):
    if request.path.startswith('/portal') or portal_host_matches(request.host):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
    return response


def record_account_activity(action, details='', subject_id=None, actor_id=None):
    db.session.add(AccountActivity(
        actor_id=actor_id if actor_id is not None else session.get('user_id'),
        subject_id=subject_id,
        action=action,
        details=details[:500]
    ))


def authenticated_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        user = db.session.get(User, session.get('user_id')) if session.get('user_id') else None
        if not user:
            flash('Access restricted.', 'warning')
            return redirect(url_for('portal_login', next=request.url))
        if (
            not user.is_active
            or user.session_version != session.get('session_version')
            or (user.timed_out_until and user.timed_out_until > datetime.utcnow())
        ):
            session.clear()
            flash('Your portal access has expired or was ended. Please sign in again.', 'warning')
            return redirect(url_for('portal_login', next=request.url))
        referrer = urlparse(request.referrer or '')
        same_portal_host = portal_host_matches(request.host) and referrer.netloc == request.host
        trusted_oauth_return = session.pop('portal_oauth_return', False)
        if not trusted_oauth_return and not same_portal_host and (
            referrer.netloc != request.host or not referrer.path.startswith('/portal')
        ):
            session.clear()
            flash('Please sign in again to access the portal.', 'warning')
            return redirect(url_for('portal_login', next=request.url))
        g.current_user = user
        return f(*args, **kwargs)
    return decorated_function


def login_required(f):
    @wraps(f)
    @authenticated_required
    def management_access(*args, **kwargs):
        if g.current_user.normalized_role == 'employee':
            if request.endpoint == 'portal_dashboard':
                return redirect(url_for('portal_employee_space'))
            abort(403)
        return f(*args, **kwargs)
    return management_access


def administrator_required(f):
    @wraps(f)
    @authenticated_required
    def administrator_access(*args, **kwargs):
        if g.current_user.normalized_role != 'administrator':
            abort(403)
        return f(*args, **kwargs)
    return administrator_access


def portal_space_required(f):
    @wraps(f)
    @authenticated_required
    def portal_access(*args, **kwargs):
        return f(*args, **kwargs)
    return portal_access


def read_media_upload_metadata(upload_id):
    stage_path = media_upload_stage_path(upload_id)
    if not stage_path:
        return None, None
    metadata_path = os.path.join(stage_path, 'metadata.json')
    try:
        with open(metadata_path, encoding='utf-8') as metadata_file:
            metadata = json.load(metadata_file)
    except (OSError, ValueError):
        return stage_path, None
    if metadata.get('user_id') != g.current_user.id:
        abort(404)
    return stage_path, metadata


def cleanup_expired_media_uploads():
    cutoff = time.time() - 48 * 60 * 60
    try:
        for entry in os.scandir(MEDIA_UPLOAD_STAGING_DIR):
            if not entry.is_dir(follow_symlinks=False):
                continue
            try:
                uuid.UUID(entry.name)
                if entry.stat(follow_symlinks=False).st_mtime < cutoff:
                    shutil.rmtree(entry.path)
            except (ValueError, OSError):
                app.logger.warning('Unable to clean expired media upload staging directory: %s', entry.name)
    except OSError:
        app.logger.exception('Unable to scan media upload staging directory.')


@app.route('/portal/uploads/init', methods=['POST'])
@login_required
def portal_init_media_upload():
    data = request.get_json(silent=True) or {}
    filename = Path(str(data.get('filename', ''))).name
    media_type = data.get('media_type')
    context = data.get('context')
    total_size = data.get('total_size')
    if (
        not filename
        or media_type not in {'image', 'video'}
        or not allowed_media_file(filename, media_type)
        or type(total_size) is not int
        or total_size < 1
        or total_size > app.config['MAX_MEDIA_FILE_SIZE']
    ):
        return jsonify(error='Choose a supported file within the configured maximum size.'), 400
    if context not in {'gallery_photo', 'video_library', 'homepage_hero'}:
        return jsonify(error='Choose a valid media destination.'), 400
    if (context == 'gallery_photo' and media_type != 'image') or (
        context in {'video_library', 'homepage_hero'} and media_type != 'video'
    ):
        return jsonify(error='This file type is not valid for the selected destination.'), 400

    metadata = {
        'user_id': g.current_user.id,
        'filename': filename,
        'media_type': media_type,
        'context': context,
        'total_size': total_size,
        'chunk_count': math.ceil(total_size / MEDIA_UPLOAD_CHUNK_SIZE),
        'gallery_id': data.get('gallery_id'),
        'section_id': data.get('section_id'),
        'title': str(data.get('title', '')).strip()[:180],
        'photographer': str(data.get('photographer', '')).strip()[:120] or 'Cathea Studio',
        'thumbnail_url': str(data.get('thumbnail_url', '')).strip()[:600]
    }
    if context == 'gallery_photo':
        gallery_id = metadata['gallery_id']
        section_id = metadata['section_id']
        if not str(gallery_id).isdigit() or not str(section_id).isdigit():
            return jsonify(error='Choose a gallery section before uploading photos.'), 400
        section = GallerySection.query.filter_by(
            id=int(section_id),
            gallery_id=int(gallery_id)
        ).first()
        if not section:
            return jsonify(error='The selected gallery section is unavailable.'), 404

    cleanup_expired_media_uploads()
    upload_id = str(uuid.uuid4())
    stage_path = media_upload_stage_path(upload_id)
    os.makedirs(stage_path, exist_ok=False)
    with open(os.path.join(stage_path, 'metadata.json'), 'w', encoding='utf-8') as metadata_file:
        json.dump(metadata, metadata_file)
    return jsonify(
        upload_id=upload_id,
        chunk_size=MEDIA_UPLOAD_CHUNK_SIZE,
        chunk_count=metadata['chunk_count']
    )


@app.route('/portal/uploads/<upload_id>/chunk/<int:chunk_index>', methods=['PUT'])
@login_required
def portal_write_media_upload_chunk(upload_id, chunk_index):
    stage_path, metadata = read_media_upload_metadata(upload_id)
    if not metadata:
        return jsonify(error='Upload was not found or has expired.'), 404
    chunk_count = metadata['chunk_count']
    if chunk_index < 0 or chunk_index >= chunk_count:
        return jsonify(error='Invalid upload chunk number.'), 400
    chunk_data = request.get_data(cache=False)
    offset = chunk_index * MEDIA_UPLOAD_CHUNK_SIZE
    expected_size = min(
        MEDIA_UPLOAD_CHUNK_SIZE,
        metadata['total_size'] - offset
    )
    if len(chunk_data) != expected_size:
        return jsonify(error='Upload chunk size did not match the expected size.'), 400
    chunk_path = os.path.join(stage_path, f'{chunk_index:08d}.part')
    try:
        with open(chunk_path, 'xb') as chunk_file:
            chunk_file.write(chunk_data)
    except FileExistsError:
        with open(chunk_path, 'rb') as existing_chunk:
            if existing_chunk.read() != chunk_data:
                return jsonify(error='This upload chunk was already received with different content.'), 409
    return jsonify(received=chunk_index)


@app.route('/portal/uploads/<upload_id>/status')
@login_required
def portal_media_upload_status(upload_id):
    stage_path, metadata = read_media_upload_metadata(upload_id)
    if not metadata:
        return jsonify(error='Upload was not found or has expired.'), 404
    receipt_path = os.path.join(stage_path, 'complete.json')
    if os.path.isfile(receipt_path):
        with open(receipt_path, encoding='utf-8') as receipt_file:
            return jsonify(json.load(receipt_file))
    missing_chunks = [
        chunk_index for chunk_index in range(metadata['chunk_count'])
        if not os.path.isfile(os.path.join(stage_path, f'{chunk_index:08d}.part'))
    ]
    return jsonify(
        filename=metadata['filename'],
        media_type=metadata['media_type'],
        context=metadata['context'],
        total_size=metadata['total_size'],
        gallery_id=metadata['gallery_id'],
        section_id=metadata['section_id'],
        complete=False,
        missing_chunks=missing_chunks
    )


@app.route('/portal/uploads/<upload_id>/complete', methods=['POST'])
@login_required
def portal_complete_media_upload(upload_id):
    stage_path, metadata = read_media_upload_metadata(upload_id)
    if not metadata:
        return jsonify(error='Upload was not found or has expired.'), 404
    receipt_path = os.path.join(stage_path, 'complete.json')
    if os.path.isfile(receipt_path):
        with open(receipt_path, encoding='utf-8') as receipt_file:
            return jsonify(json.load(receipt_file))
    assembled_path = os.path.join(stage_path, 'assembled.tmp')
    total_size = 0
    try:
        with open(assembled_path, 'wb') as assembled_file:
            for chunk_index in range(metadata['chunk_count']):
                chunk_path = os.path.join(stage_path, f'{chunk_index:08d}.part')
                if not os.path.isfile(chunk_path):
                    return jsonify(error='An upload chunk is missing.'), 400
                chunk_size = os.path.getsize(chunk_path)
                expected_size = min(
                    MEDIA_UPLOAD_CHUNK_SIZE,
                    metadata['total_size'] - chunk_index * MEDIA_UPLOAD_CHUNK_SIZE
                )
                if chunk_size != expected_size:
                    return jsonify(error='An upload chunk has an invalid size.'), 400
                with open(chunk_path, 'rb') as chunk_file:
                    shutil.copyfileobj(chunk_file, assembled_file)
                total_size += chunk_size
        if total_size != metadata['total_size']:
            return jsonify(error='Uploaded file size does not match the original.'), 400

        filename = Path(metadata['filename']).name
        name, extension = os.path.splitext(filename)
        safe_name = secure_filename(name) or 'media'
        stored_filename = f'{uuid.uuid4().hex}_{safe_name}{extension.lower()}'
        destination = os.path.join(app.config['UPLOAD_FOLDER'], stored_filename)
        os.replace(assembled_path, destination)
        media_url = f'/uploads/{stored_filename}'

        media_item = None
        if metadata['context'] == 'gallery_photo':
            section = GallerySection.query.filter_by(
                id=int(metadata['section_id']),
                gallery_id=int(metadata['gallery_id'])
            ).first()
            if not section:
                os.remove(destination)
                return jsonify(error='The selected gallery section is no longer available.'), 404
            title = os.path.splitext(filename)[0].replace('_', ' ').strip() or 'Untitled photo'
            media_item = MediaItem(
                gallery_id=section.gallery_id,
                section_id=section.id,
                media_type='image',
                title=title[:180],
                url=media_url,
                thumbnail_url=generate_image_thumbnail_url(media_url)
            )
        elif metadata['context'] == 'video_library':
            fallback_gallery = Gallery.query.order_by(Gallery.sort_order.asc()).first()
            title = (
                os.path.splitext(filename)[0].replace('_', ' ').strip()
                or metadata['title']
                or 'Untitled video'
            )
            media_item = MediaItem(
                media_type='video',
                title=title[:180],
                photographer=metadata['photographer'],
                url=media_url,
                thumbnail_url=metadata['thumbnail_url']
                or (fallback_gallery.cover_url if fallback_gallery else media_url)
            )

        if media_item:
            db.session.add(media_item)
            try:
                db.session.commit()
            except Exception:
                db.session.rollback()
                os.remove(destination)
                raise
        result = {
            'url': media_url,
            'title': metadata['filename'],
            'media_type': metadata['media_type'],
            'complete': True
        }
        temporary_receipt_path = f'{receipt_path}.tmp'
        with open(temporary_receipt_path, 'w', encoding='utf-8') as receipt_file:
            json.dump(result, receipt_file)
        os.replace(temporary_receipt_path, receipt_path)
        try:
            for chunk_index in range(metadata['chunk_count']):
                chunk_path = os.path.join(stage_path, f'{chunk_index:08d}.part')
                if os.path.exists(chunk_path):
                    os.remove(chunk_path)
        except OSError:
            app.logger.warning('Uploaded media is saved but its staging chunks could not be removed: %s', upload_id)
        return jsonify(result)
    except OSError:
        app.logger.exception('Failed to assemble uploaded media file.')
        return jsonify(error='The server could not save the uploaded file. Check storage availability.'), 500


@app.route('/portal/uploads/<upload_id>', methods=['DELETE'])
@login_required
def portal_cancel_media_upload(upload_id):
    stage_path, metadata = read_media_upload_metadata(upload_id)
    if not metadata:
        return jsonify(error='Upload was not found or has expired.'), 404
    shutil.rmtree(stage_path)
    return jsonify(cancelled=True)


@app.route('/portal/media/import/browse')
@administrator_required
def portal_browse_media_import():
    root = media_import_root()
    if not root or not root.is_dir():
        return jsonify(error='Configure MEDIA_IMPORT_ROOT as an existing folder on the server.'), 400
    media_type = request.args.get('media_type', '')
    if media_type not in {'image', 'video'}:
        return jsonify(error='Choose image or video files.'), 400
    relative_path = request.args.get('path', '')
    current = media_import_path(relative_path)
    if not current or not current.is_dir():
        return jsonify(error='That folder is outside the configured import folder or unavailable.'), 400
    entries = []
    try:
        for entry in os.scandir(current):
            candidate = media_import_path(os.path.relpath(entry.path, root))
            if not candidate:
                continue
            if entry.is_dir(follow_symlinks=False) and candidate.is_dir():
                entries.append({'name': entry.name, 'path': candidate.relative_to(root).as_posix(), 'kind': 'folder'})
            elif (
                entry.is_file(follow_symlinks=False)
                and candidate.is_file()
                and allowed_media_file(entry.name, media_type)
            ):
                entries.append({'name': entry.name, 'path': candidate.relative_to(root).as_posix(), 'kind': 'file'})
    except OSError:
        app.logger.exception('Failed to list the configured media import folder.')
        return jsonify(error='The server could not read that import folder.'), 500
    entries.sort(key=lambda item: (item['kind'] != 'folder', item['name'].lower()))
    return jsonify(
        current=relative_path,
        parent=(
            '' if not relative_path or Path(relative_path).parent.as_posix() == '.'
            else Path(relative_path).parent.as_posix()
        ),
        entries=entries
    )


@app.route('/portal/media/import', methods=['POST'])
@administrator_required
def portal_import_media():
    data = request.get_json(silent=True) or {}
    media_type = data.get('media_type')
    paths = data.get('paths')
    if media_type not in {'image', 'video'} or not isinstance(paths, list) or not paths:
        return jsonify(error='Choose supported files to import.'), 400
    if len(paths) > 200 or any(not isinstance(path, str) for path in paths):
        return jsonify(error='Select no more than 200 files at a time.'), 400
    if len(paths) != len(set(paths)):
        return jsonify(error='A file was selected more than once.'), 400

    section = None
    if media_type == 'image':
        gallery_id = data.get('gallery_id')
        section_id = data.get('section_id')
        if not str(gallery_id).isdigit() or not str(section_id).isdigit():
            return jsonify(error='Choose a gallery section for the imported photos.'), 400
        section = GallerySection.query.filter_by(
            id=int(section_id),
            gallery_id=int(gallery_id)
        ).first()
        if not section:
            return jsonify(error='The selected gallery section is unavailable.'), 404

    sources = []
    for relative_path in paths:
        source = media_import_path(relative_path)
        if (
            not source
            or not source.is_file()
            or not allowed_media_file(source.name, media_type)
        ):
            return jsonify(error='One or more selected files are invalid or outside the import folder.'), 400
        if source.stat().st_size > app.config['MAX_MEDIA_FILE_SIZE']:
            return jsonify(error=f'{source.name} exceeds the configured maximum file size.'), 400
        sources.append(source)

    copied_files = []
    items = []
    try:
        fallback_gallery = Gallery.query.order_by(Gallery.sort_order.asc()).first() if media_type == 'video' else None
        for source in sources:
            name, extension = os.path.splitext(source.name)
            safe_name = secure_filename(name) or 'media'
            stored_filename = f'{uuid.uuid4().hex}_{safe_name}{extension.lower()}'
            destination = os.path.join(app.config['UPLOAD_FOLDER'], stored_filename)
            shutil.copyfile(source, destination)
            copied_files.append(destination)
            media_url = f'/uploads/{stored_filename}'
            if media_type == 'image':
                items.append(MediaItem(
                    gallery_id=section.gallery_id,
                    section_id=section.id,
                    media_type='image',
                    title=(os.path.splitext(source.name)[0].replace('_', ' ') or 'Untitled photo')[:180],
                    url=media_url,
                    thumbnail_url=generate_image_thumbnail_url(media_url)
                ))
            else:
                items.append(MediaItem(
                    media_type='video',
                    title=(os.path.splitext(source.name)[0].replace('_', ' ') or 'Untitled video')[:180],
                    photographer='Cathea Studio',
                    url=media_url,
                    thumbnail_url=fallback_gallery.cover_url if fallback_gallery else media_url
                ))
        db.session.add_all(items)
        db.session.commit()
    except OSError:
        db.session.rollback()
        for copied_file in copied_files:
            if os.path.exists(copied_file):
                os.remove(copied_file)
        app.logger.exception('Failed to import media files from the configured folder.')
        return jsonify(error='The server could not copy the selected files. Check folder permissions and available storage.'), 500
    except Exception:
        db.session.rollback()
        for copied_file in copied_files:
            if os.path.exists(copied_file):
                os.remove(copied_file)
        raise
    return jsonify(imported=len(items), titles=[item.title for item in items])


@app.before_request
def move_portal_to_configured_host():
    portal_host = app.config.get('PORTAL_HOST')
    if portal_host and not portal_host_matches(request.host) and request.path.startswith('/portal'):
        portal_path = request.path[len('/portal'):] or '/'
        configured_scheme = app.config.get('PORTAL_SCHEME')
        default_scheme = 'http' if urlparse(f'//{portal_host}').port else 'https'
        destination = f'{configured_scheme or default_scheme}://{portal_host}{portal_path}'
        if request.query_string:
            destination = f'{destination}?{request.query_string.decode("latin-1")}'
        return redirect(destination, code=302)


# ==========================================
# PUBLIC FRONTEND ROUTES (WHITE / MINIMALIST)
# ==========================================

@app.route('/healthz')
def healthz():
    return jsonify(status='ok')


@app.route('/')
def index():
    galleries = Gallery.query.filter_by(is_active=True).order_by(Gallery.sort_order.asc()).all()
    photos = MediaItem.query.join(Gallery).filter(
        MediaItem.media_type == 'image',
        Gallery.is_active.is_(True),
        MediaItem.is_featured.is_(True)
    ).order_by(MediaItem.sort_order.asc(), MediaItem.id.desc()).all()
    cta_photos = MediaItem.query.join(Gallery).filter(
        MediaItem.media_type == 'image',
        Gallery.is_active.is_(True),
        MediaItem.is_cta_featured.is_(True)
    ).order_by(MediaItem.sort_order.asc(), MediaItem.id.desc()).limit(12).all()
    videos = MediaItem.query.filter_by(
        media_type='video',
        is_featured=True
    ).order_by(MediaItem.sort_order.asc(), MediaItem.id.desc()).limit(1).all()
    homepage = HomepageContent.query.first() or HomepageContent()
    hero_video = MediaItem.query.filter_by(
        id=homepage.hero_video_id,
        media_type='video'
    ).first() if homepage.hero_video_id else (videos[0] if videos else None)
    hero_video_source = homepage.hero_video_url or (hero_video.url if hero_video else '')
    return render_template(
        'index.html',
        galleries=galleries,
        photos=photos,
        cta_photos=cta_photos,
        videos=videos,
        hero_video=hero_video,
        hero_video_source=hero_video_source,
        hero_video_embed_url=video_embed_url(hero_video_source),
        homepage=homepage
    )


@app.route('/photos')
@app.route('/gallery')
def photos():
    # Pure image gallery without search bars or categorization fluff
    galleries = Gallery.query.filter_by(
        is_active=True,
        is_listed=True
    ).order_by(Gallery.sort_order.asc()).all()
    return render_template('photos.html', galleries=galleries)


@app.route('/story/<slug>')
@app.route('/gallery/<slug>')
def story_detail(slug):
    # Full collection of photos for a clicked gallery
    gallery = Gallery.query.filter_by(slug=slug, is_active=True).first_or_404()
    ensure_gallery_image_thumbnails(gallery)
    return render_template('story_detail.html', gallery=gallery)


@app.route('/cinema')
@app.route('/videos')
def videos():
    # Pure video frames, minimal text
    video_items = MediaItem.query.filter_by(
        media_type='video',
        is_listed=True
    ).order_by(MediaItem.sort_order.asc(), MediaItem.id.desc()).all()
    return render_template('videos.html', videos=video_items)


@app.route('/inquiries')
@app.route('/contact')
def contact():
    # Minimalist consultation page referencing @cathea.studio
    return render_template('contact.html')


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ==========================================
# PUBLIC API (CONSULT US AI CONCIERGE)
# ==========================================

@app.route('/api/chat', methods=['POST'])
def api_chat():
    data = request.get_json() or {}
    user_message = data.get('message', '').strip()
    history = data.get('history', [])
    
    if not user_message:
        return jsonify({'error': 'Message is required'}), 400
        
    settings = SiteSettings.query.first()
    response_data = query_llm(user_message, history, settings)
    
    return jsonify({
        'reply': response_data['reply'],
        'suggest_whatsapp': response_data.get('suggest_whatsapp', False),
        'whatsapp_number': settings.whatsapp_number if settings else ''
    })


@app.route('/api/inquiries', methods=['POST'])
def submit_inquiry():
    data = request.form if request.form else (request.get_json() or {})
    name = data.get('name', '').strip()
    email = data.get('email', '').strip()
    phone = data.get('phone', '').strip()
    service_type = data.get('service_type', 'Wedding')
    message = data.get('message', '').strip()
    
    if not name or not email or not message:
        return jsonify({'success': False, 'message': 'Please complete all required fields.'}), 400
        
    new_inquiry = Inquiry(
        name=name,
        email=email,
        phone=phone,
        service_type=service_type,
        message=message
    )
    db.session.add(new_inquiry)
    db.session.commit()
    
    if request.is_json:
        return jsonify({'success': True, 'message': 'Consultation received. We will respond shortly.'})
    
    flash('Thank you. Your inquiry has been submitted.', 'success')
    return redirect(url_for('contact'))


# ==========================================
# DEDICATED PRIVATE PORTAL (ZERO TRACE ON PUBLIC SITE)
# ==========================================

@app.route('/portal/login', methods=['GET', 'POST'])
def portal_login():
    current_user = db.session.get(User, session.get('user_id')) if session.get('user_id') else None
    if current_user and current_user.is_active and (
        not current_user.timed_out_until or current_user.timed_out_until <= datetime.utcnow()
    ) and current_user.session_version == session.get('session_version'):
        destination = 'portal_employee_space' if current_user.normalized_role == 'employee' else 'portal_dashboard'
        return redirect(url_for(destination))
    session.clear()
        
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        
        user = User.query.filter_by(username=username).first()
        if (
            user and user.check_password(password) and user.is_active
            and (not user.timed_out_until or user.timed_out_until <= datetime.utcnow())
        ):
            session.clear()
            session.permanent = False
            session['user_id'] = user.id
            session['username'] = user.username
            session['full_name'] = user.full_name
            session['role'] = user.normalized_role
            session['session_version'] = user.session_version
            record_account_activity('login', 'Successful sign-in.', subject_id=user.id, actor_id=user.id)
            db.session.commit()
            next_page = request.args.get('next', '')
            parsed_next = urlparse(next_page)
            safe_next = (
                next_page if parsed_next.netloc == request.host and (
                    parsed_next.path.startswith('/portal') or portal_host_matches(request.host)
                ) else ''
            )
            if safe_next:
                return redirect(safe_next)
            destination = 'portal_employee_space' if user.normalized_role == 'employee' else 'portal_dashboard'
            return redirect(url_for(destination))
        else:
            record_account_activity(
                'login_failed',
                f'Failed sign-in for username: {username[:80]}.',
                subject_id=user.id if user else None,
                actor_id=None
            )
            db.session.commit()
            flash('Invalid credentials.', 'danger')
            
    return render_template('portal_login.html')


@app.route('/portal/logout')
def portal_logout():
    if session.get('user_id'):
        record_account_activity('logout', 'Signed out.', subject_id=session['user_id'])
        db.session.commit()
    session.clear()
    return redirect(url_for('portal_login'))


@app.route('/portal')
@login_required
def portal_dashboard():
    settings = SiteSettings.query.first()
    homepage = HomepageContent.query.first() or HomepageContent()
    galleries = Gallery.query.order_by(Gallery.id.desc()).all()
    videos = MediaItem.query.filter_by(media_type='video').order_by(MediaItem.id.desc()).all()
    inquiries = Inquiry.query.order_by(Inquiry.id.desc()).all()
    user = User.query.get(session['user_id'])
    photo_count = MediaItem.query.filter_by(media_type='image').count()
    featured_photos = MediaItem.query.filter_by(
        media_type='image',
        is_featured=True
    ).all()
    cta_photos = MediaItem.query.filter_by(
        media_type='image',
        is_cta_featured=True
    ).order_by(MediaItem.sort_order.asc(), MediaItem.id.desc()).limit(12).all()
    assignments = WorkAssignment.query.order_by(WorkAssignment.deadline.asc(), WorkAssignment.id.desc()).limit(8).all()
    open_assignment_count = WorkAssignment.query.filter(
        WorkAssignment.status != 'Done'
    ).count()
    employees = User.query.filter(User.role == 'employee').order_by(User.full_name.asc()).all()
    
    return render_template('portal_dashboard.html',
                           user=user,
                           settings=settings,
                           homepage=homepage,
                           galleries=galleries,
                           videos=videos,
                           featured_photos=featured_photos,
                           cta_photos=cta_photos,
                           photo_count=photo_count,
                           inquiries=inquiries,
                           assignments=assignments,
                           open_assignment_count=open_assignment_count,
                           employees=employees)


@app.route('/portal/employee')
@portal_space_required
def portal_employee_space():
    user = g.current_user
    assignments_query = WorkAssignment.query
    if user.normalized_role == 'employee':
        assignments_query = assignments_query.filter_by(assigned_to_id=user.id)
    team_members = User.query.filter_by(is_active=True).order_by(User.full_name.asc()).all()
    employees = User.query.filter_by(role='employee', is_active=True).order_by(
        User.full_name.asc()
    ).all()
    assignments = assignments_query.order_by(
        WorkAssignment.scheduled_for.asc().nullslast(),
        WorkAssignment.deadline.asc().nullslast(),
        WorkAssignment.id.desc()
    ).all()
    events_query = CalendarEvent.query
    if user.normalized_role == 'employee':
        events_query = events_query.filter(CalendarEvent.attendees.any(id=user.id))
    calendar_events = events_query.order_by(
        CalendarEvent.event_date.asc().nullslast(),
        CalendarEvent.id.desc()
    ).all()
    calendar_embed_url = app.config.get('GOOGLE_CALENDAR_EMBED_URL', '')
    google_calendar_connected = google_calendar_credential_record() is not None
    return render_template(
        'portal_employee.html',
        user=user,
        assignments=assignments,
        calendar_events=calendar_events,
        calendar_embed_url=calendar_embed_url,
        google_calendar_connected=google_calendar_connected,
        calendar_event_url=google_calendar_event_url,
        team_members=team_members,
        employees=employees,
        event_types=CALENDAR_EVENT_TYPES,
        statuses=('Pending', 'In Progress', 'Delayed', 'Done', 'Revision'),
        priorities=('Low', 'High')
    )


@app.route('/portal/calendar-events/create', methods=['POST'])
@portal_space_required
def portal_create_calendar_event():
    user = g.current_user
    title = request.form.get('title', '').strip()
    if not title:
        flash('Event title is required.', 'danger')
        return redirect(url_for('portal_employee_space'))

    try:
        event_date = date.fromisoformat(request.form.get('event_date', ''))
    except ValueError:
        flash('Choose a valid event date.', 'danger')
        return redirect(url_for('portal_employee_space'))

    event_type = request.form.get('event_type', '')
    if event_type not in CALENDAR_EVENT_TYPES:
        flash('Choose a valid event type.', 'danger')
        return redirect(url_for('portal_employee_space'))

    if user.normalized_role in {'administrator', 'management'}:
        attendee_ids = request.form.getlist('attendee_ids')
        if not attendee_ids or any(not attendee_id.isdigit() for attendee_id in attendee_ids):
            flash('Select at least one employee for this event.', 'danger')
            return redirect(url_for('portal_employee_space'))
        attendees = User.query.filter(
            User.id.in_([int(attendee_id) for attendee_id in attendee_ids]),
            User.role == 'employee',
            User.is_active.is_(True)
        ).all()
        if len(attendees) != len(set(attendee_ids)):
            flash('Choose only active employee accounts for this event.', 'danger')
            return redirect(url_for('portal_employee_space'))
    else:
        attendees = [user]

    google_calendar_connected = google_calendar_credential_record() is not None
    if google_calendar_connected and any(not employee.email for employee in attendees):
        flash('Add an email address to every selected employee account before inviting them to Google Calendar.', 'danger')
        return redirect(url_for('portal_employee_space'))

    event = CalendarEvent(
        title=title,
        description=request.form.get('description', '').strip(),
        event_date=event_date,
        event_type=event_type,
        starts_at=datetime.combine(event_date, datetime.min.time()),
        ends_at=datetime.combine(event_date, datetime.min.time()),
        created_by_id=user.id,
        attendees=attendees
    )
    db.session.add(event)
    db.session.flush()
    rates = {
        (rate.user_id, rate.event_type): rate.amount
        for rate in EmployeeCommissionRate.query.filter(
            EmployeeCommissionRate.user_id.in_([employee.id for employee in attendees]),
            EmployeeCommissionRate.event_type == event_type
        ).all()
    }
    db.session.add_all([
        EventCommission(
            event_id=event.id,
            user_id=employee.id,
            amount=rates.get((employee.id, event_type), Decimal('0.00'))
        )
        for employee in attendees
    ])
    record_account_activity(
        'calendar_event_created',
        f'Created calendar event {event.id}: {event.title}.',
        subject_id=attendees[0].id if len(attendees) == 1 else None
    )
    db.session.commit()
    if google_calendar_connected:
        try:
            event.google_calendar_event_id = create_google_calendar_event(event)
            event.google_calendar_sync_error = None
            db.session.commit()
            flash('Event added to the team calendar and Google Calendar invitations were sent.', 'success')
        except (GoogleAuthError, HttpError, InvalidToken, OSError, RequestException, ValueError):
            app.logger.exception('Google Calendar event creation failed for portal event %s.', event.id)
            event.google_calendar_sync_error = (
                'Google Calendar could not create the event or send invitations. '
                'Check the connection and Google Calendar settings, then reconnect.'
            )
            db.session.commit()
            flash(
                'The event was saved in Employee Space, but Google Calendar could not create it or send invitations. '
                'Check the Google Calendar connection in Accounts & Activity.',
                'warning'
            )
    else:
        flash(
            'Event added to Employee Space. Connect Google Calendar in Accounts & Activity to create calendar events and send invitations.',
            'success'
        )
    return redirect(url_for('portal_employee_space'))


@app.route('/portal/calendar/google/connect')
@administrator_required
def google_calendar_oauth_connect():
    if not google_calendar_oauth_configured():
        flash('Set GOOGLE_OAUTH_CLIENT_ID, GOOGLE_OAUTH_CLIENT_SECRET, and GOOGLE_CALENDAR_TOKEN_KEY before connecting.', 'danger')
        return redirect(url_for('portal_accounts'))
    try:
        Fernet(app.config['GOOGLE_CALENDAR_TOKEN_KEY'].encode('ascii'))
        flow = google_calendar_flow()
    except (UnicodeEncodeError, ValueError):
        flash('GOOGLE_CALENDAR_TOKEN_KEY must be a valid Fernet key. Generate one using the README instructions.', 'danger')
        return redirect(url_for('portal_accounts'))

    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent'
    )
    session['google_calendar_oauth_state'] = state
    session['google_calendar_oauth_user_id'] = g.current_user.id
    session['google_calendar_oauth_session_version'] = g.current_user.session_version
    return redirect(authorization_url)


@app.route('/portal/calendar/google/callback')
def google_calendar_oauth_callback():
    expected_state = session.pop('google_calendar_oauth_state', '')
    state = request.args.get('state', '')
    user_id = session.pop('google_calendar_oauth_user_id', None)
    session_version = session.pop('google_calendar_oauth_session_version', None)
    user = db.session.get(User, user_id) if user_id else None
    if (
        not expected_state
        or not state
        or not secrets.compare_digest(expected_state, state)
        or not user
        or not user.is_active
        or user.normalized_role != 'administrator'
        or user.session_version != session_version
        or session.get('user_id') != user.id
        or session.get('session_version') != user.session_version
    ):
        abort(403)
    session['portal_oauth_return'] = True

    if request.args.get('error'):
        flash('Google Calendar authorization was cancelled or denied.', 'warning')
        return redirect(url_for('portal_accounts'))
    if not google_calendar_oauth_configured() or not request.args.get('code'):
        flash('Google Calendar authorization could not be completed. Check the OAuth configuration and try again.', 'danger')
        return redirect(url_for('portal_accounts'))

    try:
        flow = google_calendar_flow(state=state)
        flow.fetch_token(code=request.args['code'])
        save_google_calendar_credentials(flow.credentials, connected_by_id=user.id)
    except (HttpError, OAuth2Error, OSError, RequestException, UnicodeEncodeError, ValueError):
        app.logger.exception('Google Calendar OAuth callback failed.')
        flash('Google Calendar could not be connected. Check the OAuth redirect URI and client credentials, then try again.', 'danger')
        return redirect(url_for('portal_accounts'))

    record_account_activity(
        'google_calendar_connected',
        'Administrator connected Google Calendar OAuth.'
    )
    db.session.commit()
    flash('Google Calendar connected. New portal events will be created there and invitations sent to selected employees.', 'success')
    return redirect(url_for('portal_accounts'))


@app.route('/portal/calendar/google/disconnect', methods=['POST'])
@administrator_required
def google_calendar_oauth_disconnect():
    credential = google_calendar_credential_record()
    if credential:
        db.session.delete(credential)
        record_account_activity('google_calendar_disconnected', 'Administrator removed the local Google Calendar connection.')
        db.session.commit()
    flash('Google Calendar connection removed from this portal. Google account access can be revoked in Google Account security settings.', 'success')
    return redirect(url_for('portal_accounts'))


@app.route('/portal/calendar-events/<int:event_id>/delete', methods=['POST'])
@portal_space_required
def portal_delete_calendar_event(event_id):
    event = CalendarEvent.query.get_or_404(event_id)
    user = g.current_user
    if user.normalized_role not in {'administrator', 'management'} and event.created_by_id != user.id:
        abort(403)
    record_account_activity(
        'calendar_event_deleted',
        f'Deleted calendar event {event.id}: {event.title}.'
    )
    db.session.delete(event)
    db.session.commit()
    flash('Event removed from the team calendar.', 'success')
    return redirect(url_for('portal_employee_space'))


@app.route('/portal/assignments/create', methods=['POST'])
@portal_space_required
def portal_create_assignment():
    user = g.current_user
    title = request.form.get('title', '').strip()
    if not title:
        flash('Assignment title is required.', 'danger')
        return redirect(url_for('portal_employee_space'))

    assigned_to_id = user.id
    requested_assignee = request.form.get('assigned_to_id', '').strip()
    if user.normalized_role in {'administrator', 'management'} and requested_assignee.isdigit():
        assignee = db.session.get(User, int(requested_assignee))
        if not assignee or not assignee.is_active:
            flash('Choose an active team member for this assignment.', 'danger')
            return redirect(url_for('portal_employee_space'))
        assigned_to_id = assignee.id

    try:
        deadline = date.fromisoformat(request.form['deadline']) if request.form.get('deadline') else None
        scheduled_for = date.fromisoformat(request.form['scheduled_for']) if request.form.get('scheduled_for') else None
    except ValueError:
        flash('Enter valid calendar dates.', 'danger')
        return redirect(url_for('portal_employee_space'))

    priority = request.form.get('priority', 'Low')
    if priority not in {'Low', 'High'}:
        flash('Choose a valid priority.', 'danger')
        return redirect(url_for('portal_employee_space'))

    assignment = WorkAssignment(
        title=title,
        description=request.form.get('description', '').strip(),
        deadline=deadline,
        scheduled_for=scheduled_for,
        status='Pending',
        notes=request.form.get('notes', '').strip(),
        priority=priority,
        assigned_to_id=assigned_to_id,
        created_by_id=user.id
    )
    db.session.add(assignment)
    db.session.flush()
    record_account_activity(
        'assignment_created',
        f'Created assignment {assignment.id}: {assignment.title}.',
        subject_id=assigned_to_id
    )
    db.session.commit()
    flash('Assignment added.', 'success')
    return redirect(url_for('portal_employee_space'))


@app.route('/portal/assignments/<int:assignment_id>/update', methods=['POST'])
@portal_space_required
def portal_update_assignment(assignment_id):
    assignment = WorkAssignment.query.get_or_404(assignment_id)
    user = g.current_user
    is_manager = user.normalized_role in {'administrator', 'management'}
    if not is_manager and assignment.assigned_to_id != user.id:
        abort(403)

    status = request.form.get('status', assignment.status)
    if status not in {'Pending', 'In Progress', 'Delayed', 'Done', 'Revision'}:
        flash('Choose a valid assignment status.', 'danger')
        return redirect(url_for('portal_employee_space'))
    assignment.status = status
    assignment.notes = request.form.get('notes', '').strip()

    if is_manager:
        title = request.form.get('title', '').strip()
        if title:
            assignment.title = title
        assignment.description = request.form.get('description', '').strip()
        priority = request.form.get('priority', assignment.priority)
        if priority not in {'Low', 'High'}:
            flash('Choose a valid priority.', 'danger')
            return redirect(url_for('portal_employee_space'))
        assignment.priority = priority
        try:
            assignment.deadline = date.fromisoformat(request.form['deadline']) if request.form.get('deadline') else None
            assignment.scheduled_for = date.fromisoformat(request.form['scheduled_for']) if request.form.get('scheduled_for') else None
        except ValueError:
            flash('Enter valid calendar dates.', 'danger')
            return redirect(url_for('portal_employee_space'))
        requested_assignee = request.form.get('assigned_to_id', '').strip()
        if requested_assignee.isdigit():
            assignee = db.session.get(User, int(requested_assignee))
            if not assignee or not assignee.is_active:
                flash('Choose an active team member for this assignment.', 'danger')
                return redirect(url_for('portal_employee_space'))
            assignment.assigned_to_id = assignee.id

    record_account_activity(
        'assignment_updated',
        f'Updated assignment {assignment.id}: {assignment.title} ({assignment.status}).',
        subject_id=assignment.assigned_to_id
    )
    db.session.commit()
    flash('Assignment updated.', 'success')
    return redirect(url_for('portal_employee_space'))


@app.route('/portal/assignments/<int:assignment_id>/delete', methods=['POST'])
@administrator_required
def portal_delete_assignment(assignment_id):
    assignment = WorkAssignment.query.get_or_404(assignment_id)
    record_account_activity(
        'assignment_deleted',
        f'Deleted assignment {assignment.id}: {assignment.title}.',
        subject_id=assignment.assigned_to_id
    )
    db.session.delete(assignment)
    db.session.commit()
    flash('Assignment deleted.', 'success')
    return redirect(url_for('portal_employee_space'))


@app.route('/portal/commissions')
@portal_space_required
def portal_commissions():
    user = g.current_user
    if user.normalized_role == 'employee':
        today = date.today()
        assignments = WorkAssignment.query.filter_by(
            assigned_to_id=user.id
        ).order_by(
            WorkAssignment.scheduled_for.asc().nullslast(),
            WorkAssignment.id.desc()
        ).all()
        event_commissions = EventCommission.query.filter_by(
            user_id=user.id
        ).join(CalendarEvent).order_by(
            CalendarEvent.event_date.desc(),
            EventCommission.id.desc()
        ).all()
        adjustments = CommissionAdjustment.query.filter_by(
            user_id=user.id
        ).order_by(CommissionAdjustment.created_at.desc()).all()

        completed_assignments = [
            item for item in assignments if item.status == 'Done'
        ]
        dated_event_commissions = [
            (item, item.event.event_date or (
                item.event.starts_at.date() if item.event.starts_at else None
            ))
            for item in event_commissions
        ]
        earned_events = [
            item for item, event_date in dated_event_commissions
            if event_date and event_date <= today
        ]
        adjustment_total = sum(
            (
                item.amount if item.adjustment_type == 'addition' else -item.amount
                for item in adjustments
            ),
            Decimal('0')
        )
        earned = sum(
            (Decimal(str(item.commission_amount)) for item in completed_assignments),
            Decimal('0')
        ) + sum((item.amount for item in earned_events), Decimal('0')) + adjustment_total
        unpaid = sum(
            (
                Decimal(str(item.commission_amount))
                for item in completed_assignments if not item.commission_paid
            ),
            Decimal('0')
        ) + sum((item.amount for item in earned_events if not item.paid), Decimal('0'))

        upcoming_commissions = []
        payment_entries = []
        for assignment in assignments:
            amount = Decimal(str(assignment.commission_amount))
            entry = {
                'title': assignment.title,
                'date': assignment.scheduled_for,
                'amount': amount,
                'kind': 'Assignment',
                'paid': assignment.commission_paid,
                'payment_status': 'Not yet payable'
            }
            if (
                assignment.status != 'Done'
                and assignment.scheduled_for
                and assignment.scheduled_for > today
            ):
                upcoming_commissions.append(entry)
            elif assignment.status == 'Done' and amount > 0:
                payment_entries.append(entry)

        for commission, event_date in dated_event_commissions:
            entry = {
                'title': commission.event.title,
                'date': event_date,
                'amount': commission.amount,
                'kind': commission.event.event_type,
                'paid': commission.paid,
                'payment_status': 'Paid' if commission.paid else 'Unpaid'
            }
            if event_date and event_date > today:
                upcoming_commissions.append(entry)
            elif event_date and event_date <= today and commission.amount > 0:
                payment_entries.append(entry)

        upcoming_commissions.sort(key=lambda item: (item['date'], item['title']))
        payment_entries.sort(
            key=lambda item: (item['date'] or date.min, item['title']),
            reverse=True
        )
        return render_template(
            'portal_employee_commissions.html',
            user=user,
            earned=earned,
            unpaid=unpaid,
            upcoming_commissions=upcoming_commissions,
            payment_entries=payment_entries,
            adjustments=adjustments
        )

    assignments = WorkAssignment.query.order_by(
        WorkAssignment.commission_paid.asc(),
        WorkAssignment.deadline.asc().nullslast(),
        WorkAssignment.id.desc()
    ).all()
    completed = [item for item in assignments if item.status == 'Done']
    event_commissions = EventCommission.query.join(CalendarEvent).order_by(
        CalendarEvent.event_date.desc(),
        EventCommission.id.desc()
    ).all()
    earned_assignments = sum((Decimal(str(item.commission_amount)) for item in completed), Decimal('0'))
    earned_events = sum(
        (item.amount for item in event_commissions if item.event.event_date and item.event.event_date <= date.today()),
        Decimal('0')
    )
    adjustments = CommissionAdjustment.query.order_by(
        CommissionAdjustment.created_at.desc()
    ).all()
    adjustment_total = sum(
        (
            item.amount if item.adjustment_type == 'addition' else -item.amount
            for item in adjustments
        ),
        Decimal('0')
    )
    earned = earned_assignments + earned_events + adjustment_total
    unpaid = sum(
        (Decimal(str(item.commission_amount)) for item in completed if not item.commission_paid),
        Decimal('0')
    ) + sum(
        (
            item.amount for item in event_commissions
            if item.event.event_date and item.event.event_date <= date.today() and not item.paid
        ),
        Decimal('0')
    )
    employees = User.query.filter_by(role='employee', is_active=True).order_by(
        User.full_name.asc()
    ).all()
    rate_map = {
        (rate.user_id, rate.event_type): rate.amount
        for rate in EmployeeCommissionRate.query.all()
    }
    employee_totals = {}
    for employee in employees:
        employee_assignment_total = sum(
            (Decimal(str(item.commission_amount)) for item in completed if item.assigned_to_id == employee.id),
            Decimal('0')
        )
        employee_event_total = sum(
            (
                item.amount for item in event_commissions
                if item.user_id == employee.id and item.event.event_date
                and item.event.event_date <= date.today()
            ),
            Decimal('0')
        )
        employee_adjustments = sum(
            (
                item.amount if item.adjustment_type == 'addition' else -item.amount
                for item in adjustments if item.user_id == employee.id
            ),
            Decimal('0')
        )
        employee_totals[employee.id] = (
            employee_assignment_total + employee_event_total + employee_adjustments
        )
    return render_template(
        'portal_commissions.html',
        user=g.current_user,
        assignments=assignments,
        event_commissions=event_commissions,
        adjustments=adjustments,
        employees=employees,
        event_types=CALENDAR_EVENT_TYPES,
        rate_map=rate_map,
        employee_totals=employee_totals,
        earned=earned,
        adjustment_total=adjustment_total,
        unpaid=unpaid
    )


@app.route('/portal/commissions/rates/<int:user_id>', methods=['POST'])
@administrator_required
def portal_update_employee_commission_rates(user_id):
    employee = User.query.filter_by(id=user_id, role='employee', is_active=True).first_or_404()
    parsed_rates = {}
    try:
        for index, event_type in enumerate(CALENDAR_EVENT_TYPES):
            amount = Decimal(request.form.get(f'rate_{index}', '').strip())
            if not amount.is_finite() or amount < 0:
                raise InvalidOperation
            parsed_rates[event_type] = amount.quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        flash('Enter valid non-negative Rp rates for each event type.', 'danger')
        return redirect(url_for('portal_commissions'))

    for event_type, amount in parsed_rates.items():
        rate = EmployeeCommissionRate.query.filter_by(
            user_id=employee.id,
            event_type=event_type
        ).first()
        if rate:
            rate.amount = amount
        else:
            db.session.add(EmployeeCommissionRate(
                user_id=employee.id,
                event_type=event_type,
                amount=amount
            ))
    record_account_activity(
        'commission_rates_updated',
        f'Updated event commission rates for {employee.full_name or employee.username}.',
        subject_id=employee.id
    )
    db.session.commit()
    flash('Employee event commission rates saved.', 'success')
    return redirect(url_for('portal_commissions'))


@app.route('/portal/commissions/adjustments/create', methods=['POST'])
@administrator_required
def portal_create_commission_adjustment():
    employee_id = request.form.get('employee_id', '').strip()
    adjustment_type = request.form.get('adjustment_type', '')
    note = request.form.get('note', '').strip()
    employee = db.session.get(User, int(employee_id)) if employee_id.isdigit() else None
    try:
        amount = Decimal(request.form.get('amount', '').strip())
    except InvalidOperation:
        amount = Decimal('NaN')
    if not employee or employee.normalized_role != 'employee' or not employee.is_active:
        flash('Choose an active employee for this adjustment.', 'danger')
        return redirect(url_for('portal_commissions'))
    if adjustment_type not in {'addition', 'deduction'} or not amount.is_finite() or amount <= 0 or not note:
        flash('Choose an adjustment type, enter a positive Rp amount, and provide a note.', 'danger')
        return redirect(url_for('portal_commissions'))

    adjustment = CommissionAdjustment(
        user_id=employee.id,
        adjustment_type=adjustment_type,
        amount=amount.quantize(Decimal('0.01')),
        note=note[:240],
        created_by_id=g.current_user.id
    )
    db.session.add(adjustment)
    record_account_activity(
        'commission_adjustment_created',
        f'Added a commission {adjustment_type} of Rp {amount:,.2f}: {note[:200]}.',
        subject_id=employee.id
    )
    db.session.commit()
    flash('Commission adjustment added.', 'success')
    return redirect(url_for('portal_commissions'))


@app.route('/portal/commissions/events/<int:commission_id>/update', methods=['POST'])
@administrator_required
def portal_update_event_commission(commission_id):
    commission = EventCommission.query.get_or_404(commission_id)
    commission.paid = request.form.get('paid') == 'on'
    record_account_activity(
        'event_commission_updated',
        f'Updated event commission {commission.id} payment status.',
        subject_id=commission.user_id
    )
    db.session.commit()
    flash('Event commission payment status updated.', 'success')
    return redirect(url_for('portal_commissions'))


@app.route('/portal/commissions/<int:assignment_id>/update', methods=['POST'])
@login_required
def portal_update_commission(assignment_id):
    assignment = WorkAssignment.query.get_or_404(assignment_id)
    try:
        amount = float(request.form.get('commission_amount', '0'))
    except ValueError:
        flash('Enter a valid commission amount.', 'danger')
        return redirect(url_for('portal_commissions'))
    if not math.isfinite(amount) or amount < 0:
        flash('Commission must be a non-negative amount.', 'danger')
        return redirect(url_for('portal_commissions'))

    mark_paid = request.form.get('commission_paid') == 'on'
    if mark_paid and assignment.status != 'Done' and not assignment.commission_paid:
        flash('Only completed assignments can be marked as paid.', 'danger')
        return redirect(url_for('portal_commissions'))
    assignment.commission_amount = amount
    if assignment.status == 'Done':
        assignment.commission_paid = mark_paid
    record_account_activity(
        'commission_updated',
        f'Updated assignment {assignment.id} commission to {amount:.2f}.',
        subject_id=assignment.assigned_to_id
    )
    db.session.commit()
    flash('Commission updated.', 'success')
    return redirect(url_for('portal_commissions'))


@app.route('/portal/accounts')
@administrator_required
def portal_accounts():
    users = User.query.order_by(User.created_at.asc()).all()
    page = request.args.get('page', 1, type=int)
    activity = AccountActivity.query.order_by(
        AccountActivity.created_at.desc()
    ).paginate(page=page, per_page=100, error_out=False)
    return render_template(
        'portal_accounts.html',
        user=g.current_user,
        users=users,
        activity=activity,
        google_calendar_connected=google_calendar_credential_record() is not None,
        google_oauth_configured=google_calendar_oauth_configured(),
        google_calendar_redirect_uri=google_calendar_redirect_uri(),
        google_calendar_id=app.config.get('GOOGLE_CALENDAR_ID') or 'primary'
    )


@app.route('/portal/accounts/create', methods=['POST'])
@administrator_required
def portal_create_account():
    username = request.form.get('username', '').strip()
    full_name = request.form.get('full_name', '').strip()
    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '')
    role = request.form.get('role', '')
    if not username or not full_name or len(password) < 8 or role not in {'administrator', 'management', 'employee'}:
        flash('Provide a name, username, password of at least eight characters, and valid role.', 'danger')
        return redirect(url_for('portal_accounts'))
    email_error = account_email_error(email, role)
    if email_error:
        flash(email_error, 'danger')
        return redirect(url_for('portal_accounts'))
    if User.query.filter_by(username=username).first():
        flash('That username is already in use.', 'danger')
        return redirect(url_for('portal_accounts'))

    account = User(username=username, full_name=full_name, email=email, role=role, is_active=True)
    account.set_password(password)
    db.session.add(account)
    db.session.flush()
    record_account_activity(
        'account_created',
        f'Created {role} account {username}.',
        subject_id=account.id
    )
    db.session.commit()
    flash('Account created.', 'success')
    return redirect(url_for('portal_accounts'))


@app.route('/portal/accounts/<int:user_id>/update', methods=['POST'])
@administrator_required
def portal_update_account(user_id):
    account = User.query.get_or_404(user_id)
    role = request.form.get('role', account.normalized_role)
    if role not in {'administrator', 'management', 'employee'}:
        flash('Choose a valid access role.', 'danger')
        return redirect(url_for('portal_accounts'))
    email = request.form.get('email', '').strip().lower()
    email_error = account_email_error(email, role, exclude_user_id=account.id)
    if email_error:
        flash(email_error, 'danger')
        return redirect(url_for('portal_accounts'))
    account.role = role
    account.full_name = request.form.get('full_name', account.full_name).strip()
    account.email = email
    account.is_active = request.form.get('is_active') == 'on'
    timeout_minutes = request.form.get('timeout_minutes', '').strip()
    if timeout_minutes:
        try:
            duration = int(timeout_minutes)
        except ValueError:
            flash('Timeout must be a valid number of minutes.', 'danger')
            return redirect(url_for('portal_accounts'))
        if duration < 1:
            flash('Timeout must be at least one minute.', 'danger')
            return redirect(url_for('portal_accounts'))
        account.timed_out_until = datetime.utcnow() + timedelta(minutes=duration)
    else:
        account.timed_out_until = None
    account.session_version += 1
    record_account_activity(
        'account_access_updated',
        f'Updated access for {account.username}: role={role}, active={account.is_active}.',
        subject_id=account.id
    )
    db.session.commit()
    flash('Account access updated; existing sessions have been ended.', 'success')
    return redirect(url_for('portal_accounts'))


@app.route('/portal/accounts/<int:user_id>/terminate', methods=['POST'])
@administrator_required
def portal_terminate_account_sessions(user_id):
    account = User.query.get_or_404(user_id)
    account.session_version += 1
    record_account_activity(
        'sessions_terminated',
        f'Administrator ended all active sessions for {account.username}.',
        subject_id=account.id
    )
    db.session.commit()
    flash(f'All sessions for {account.username} have been terminated.', 'success')
    return redirect(url_for('portal_accounts'))


@app.route('/portal/accounts/<int:user_id>/password', methods=['POST'])
@administrator_required
def portal_admin_reset_password(user_id):
    account = User.query.get_or_404(user_id)
    new_password = request.form.get('new_password', '')
    confirm_password = request.form.get('confirm_password', '')
    if len(new_password) < 8:
        flash('Password must be at least 8 characters.', 'danger')
        return redirect(url_for('portal_accounts'))
    if new_password != confirm_password:
        flash('Passwords do not match.', 'danger')
        return redirect(url_for('portal_accounts'))

    account.set_password(new_password)
    account.session_version += 1
    if account.id == g.current_user.id:
        session['session_version'] = account.session_version
    record_account_activity(
        'password_reset_by_administrator',
        f'Administrator reset the password for {account.username}.',
        subject_id=account.id
    )
    db.session.commit()
    flash(f'Password reset for {account.username}; their other sessions have been ended.', 'success')
    return redirect(url_for('portal_accounts'))


@app.route('/portal/galleries')
@login_required
def portal_galleries():
    galleries = Gallery.query.order_by(Gallery.sort_order.asc(), Gallery.id.desc()).all()
    return render_template(
        'portal_galleries.html',
        user=User.query.get(session['user_id']),
        galleries=galleries
    )


@app.route('/portal/galleries/create', methods=['GET', 'POST'])
@login_required
def portal_create_gallery():
    if request.method == 'GET':
        return render_template(
            'portal_gallery_create.html',
            user=User.query.get(session['user_id'])
        )

    title = request.form.get('title', '').strip()
    client = request.form.get('client', '').strip()
    photographer = request.form.get('photographer', '').strip() or 'Cathea Studio'
    location = request.form.get('location', '').strip()
    year = request.form.get('year', '').strip()
    if not all((title, client, location, year)):
        flash('Complete the title, client name, location, and year to continue.', 'danger')
        return render_template(
            'portal_gallery_create.html',
            user=User.query.get(session['user_id']),
            form_values=request.form
        ), 400

    base_slug = slugify(title) or 'gallery'
    slug = base_slug
    suffix = 1
    while Gallery.query.filter_by(slug=slug).first():
        slug = f'{base_slug}-{suffix}'
        suffix += 1

    gallery = Gallery(
        title=title,
        slug=slug,
        client=client,
        photographer=photographer,
        location=location,
        year=year,
        cover_url='',
        is_active=False
    )
    db.session.add(gallery)
    db.session.flush()
    db.session.add(GallerySection(gallery_id=gallery.id, title='Session 1', sort_order=1))
    db.session.commit()
    flash('Gallery created. Add photos and organize sections to continue.', 'success')
    return redirect(url_for('portal_gallery_detail', gallery_id=gallery.id, step=2))


@app.route('/portal/galleries/<int:gallery_id>')
@login_required
def portal_gallery_detail(gallery_id):
    gallery = Gallery.query.get_or_404(gallery_id)
    sections = GallerySection.query.filter_by(gallery_id=gallery.id).order_by(
        GallerySection.sort_order.asc(),
        GallerySection.id.asc()
    ).all()
    selected_id = request.args.get('section', type=int)
    active_section = next((section for section in sections if section.id == selected_id), None)
    if not active_section and sections:
        active_section = sections[0]
    step = request.args.get('step', 2, type=int)
    if step not in (2, 3):
        step = 2
    photos = MediaItem.query.filter_by(
        gallery_id=gallery.id,
        media_type='image'
    ).order_by(MediaItem.sort_order.asc(), MediaItem.id.asc()).all()
    return render_template(
        'portal_gallery_detail.html',
        user=User.query.get(session['user_id']),
        gallery=gallery,
        sections=sections,
        active_section=active_section,
        step=step,
        photos=photos
    )


@app.route('/portal/galleries/<int:gallery_id>/update', methods=['POST'])
@login_required
def portal_update_gallery(gallery_id):
    gallery = Gallery.query.get_or_404(gallery_id)
    section_id = request.form.get('return_section', type=int)
    title = request.form.get('title', '').strip()
    client = request.form.get('client', '').strip()
    photographer = request.form.get('photographer', '').strip() or 'Cathea Studio'
    location = request.form.get('location', '').strip()
    year = request.form.get('year', '').strip()
    if not all((title, client, location, year)):
        flash('Complete the title, client name, location, and year.', 'danger')
        return redirect(url_for(
            'portal_gallery_detail',
            gallery_id=gallery.id,
            section=section_id,
            step=2
        ))

    gallery.title = title
    candidate_slug = slugify(title) or 'gallery'
    existing_slug = Gallery.query.filter(
        Gallery.slug == candidate_slug,
        Gallery.id != gallery.id
    ).first()
    if existing_slug:
        base_slug = candidate_slug
        suffix = 1
        while Gallery.query.filter(
            Gallery.slug == f'{base_slug}-{suffix}',
            Gallery.id != gallery.id
        ).first():
            suffix += 1
        candidate_slug = f'{base_slug}-{suffix}'
    gallery.slug = candidate_slug
    gallery.client = client
    gallery.photographer = photographer
    gallery.location = location
    gallery.year = year
    db.session.commit()
    flash('Gallery details saved.', 'success')
    return redirect(url_for(
        'portal_gallery_detail',
        gallery_id=gallery.id,
        section=section_id,
        step=2
    ))


@app.route('/portal/galleries/<int:gallery_id>/publish', methods=['POST'])
@login_required
def portal_publish_gallery(gallery_id):
    gallery = Gallery.query.get_or_404(gallery_id)
    photo_id = request.form.get('cover_photo_id', type=int)
    photo = MediaItem.query.filter_by(
        id=photo_id,
        gallery_id=gallery.id,
        media_type='image'
    ).first() if photo_id else None
    if not photo:
        flash('Upload and select a photo to use as the gallery thumbnail.', 'danger')
        return redirect(url_for('portal_gallery_detail', gallery_id=gallery.id, step=3))

    crop_positions = {}
    for form_factor in ('desktop', 'tablet', 'mobile'):
        for axis in ('x', 'y'):
            field = f'cover_position_{form_factor}_{axis}'
            raw_value = request.form.get(field, '')
            try:
                value = float(raw_value)
            except ValueError:
                value = float('nan')
            if not math.isfinite(value) or not 0 <= value <= 100:
                flash('Crop positions must be between 0 and 100.', 'danger')
                return redirect(url_for('portal_gallery_detail', gallery_id=gallery.id, step=3))
            crop_positions[field] = value
    gallery.cover_url = photo.url
    gallery.is_active = True
    gallery.is_listed = True
    for field, value in crop_positions.items():
        setattr(gallery, field, value)
    db.session.commit()
    return redirect(url_for(
        'portal_gallery_detail',
        gallery_id=gallery.id,
        step=3,
        published=1
    ))


@app.route('/portal/galleries/<int:gallery_id>/visibility', methods=['POST'])
@login_required
def portal_set_gallery_visibility(gallery_id):
    gallery = Gallery.query.get_or_404(gallery_id)
    action = request.form.get('action')
    if action not in ('hide', 'show'):
        flash('Choose whether to hide or show this gallery.', 'danger')
        return redirect(url_for('portal_galleries'))
    if not gallery.is_active or not gallery.cover_url:
        flash('Publish the gallery with a thumbnail before changing its listing visibility.', 'danger')
        return redirect(url_for('portal_galleries'))

    gallery.is_listed = action == 'show'
    db.session.commit()
    flash('Gallery hidden.' if action == 'hide' else 'Gallery shown.', 'success')
    return redirect(url_for('portal_galleries'))


@app.route('/portal/galleries/<int:gallery_id>/sections/create', methods=['POST'])
@login_required
def portal_create_gallery_section(gallery_id):
    gallery = Gallery.query.get_or_404(gallery_id)
    title = request.form.get('title', '').strip()
    if not title:
        flash('Section name is required.', 'danger')
        return redirect(url_for('portal_gallery_detail', gallery_id=gallery.id, step=2))

    next_order = db.session.query(db.func.max(GallerySection.sort_order)).filter_by(
        gallery_id=gallery.id
    ).scalar() or 0
    section = GallerySection(
        gallery_id=gallery.id,
        title=title,
        sort_order=next_order + 1
    )
    db.session.add(section)
    db.session.commit()
    flash('Section created.', 'success')
    return redirect(url_for('portal_gallery_detail', gallery_id=gallery.id, section=section.id, step=2))


@app.route('/portal/galleries/<int:gallery_id>/sections/<int:section_id>/update', methods=['POST'])
@login_required
def portal_update_gallery_section(gallery_id, section_id):
    gallery = Gallery.query.get_or_404(gallery_id)
    section = GallerySection.query.filter_by(
        id=section_id,
        gallery_id=gallery.id
    ).first_or_404()
    title = request.form.get('title', '').strip()
    if not title:
        flash('Section name is required.', 'danger')
    else:
        section.title = title
        db.session.commit()
        flash('Section name updated.', 'success')
    return redirect(url_for('portal_gallery_detail', gallery_id=gallery.id, section=section.id, step=2))


@app.route('/portal/galleries/<int:gallery_id>/sections/<int:section_id>/delete', methods=['POST'])
@login_required
def portal_delete_gallery_section(gallery_id, section_id):
    gallery = Gallery.query.get_or_404(gallery_id)
    section = GallerySection.query.filter_by(
        id=section_id,
        gallery_id=gallery.id
    ).first_or_404()
    if len(gallery.sections) <= 1:
        flash('Every gallery must keep at least one section.', 'danger')
    else:
        destination = next(
            candidate for candidate in gallery.sections if candidate.id != section.id
        )
        MediaItem.query.filter_by(
            gallery_id=gallery.id,
            section_id=section.id
        ).update({MediaItem.section_id: destination.id}, synchronize_session=False)
        db.session.delete(section)
        db.session.commit()
        flash(f'Section removed. Its photos were moved to {destination.title}.', 'info')
    remaining_section = GallerySection.query.filter_by(gallery_id=gallery.id).order_by(
        GallerySection.sort_order.asc()
    ).first()
    return redirect(url_for(
        'portal_gallery_detail',
        gallery_id=gallery.id,
        section=remaining_section.id if remaining_section else None,
        step=2
    ))


@app.route('/portal/galleries/<int:gallery_id>/photos/upload', methods=['POST'])
@login_required
def portal_upload_gallery_photos(gallery_id):
    gallery = Gallery.query.get_or_404(gallery_id)
    section_id = request.form.get('section_id', '')
    section = GallerySection.query.filter_by(
        id=section_id,
        gallery_id=gallery.id
    ).first() if section_id.isdigit() else None
    if not section:
        flash('Choose a section in this gallery before uploading photos.', 'danger')
        return redirect(url_for('portal_gallery_detail', gallery_id=gallery.id, step=2))

    files = [file for file in request.files.getlist('photos') if file and file.filename]
    if not files:
        flash('Select or drop at least one photo to upload.', 'danger')
        return redirect(url_for('portal_gallery_detail', gallery_id=gallery.id, section=section.id, step=2))
    invalid_files = [file.filename for file in files if not allowed_media_file(file.filename, 'image')]
    if invalid_files:
        flash('Only PNG, JPG, JPEG, WEBP, and GIF files can be uploaded as photos.', 'danger')
        return redirect(url_for('portal_gallery_detail', gallery_id=gallery.id, section=section.id, step=2))

    for file in files:
        original_name = secure_filename(file.filename)
        name, extension = os.path.splitext(original_name)
        filename = f'{uuid.uuid4().hex}_{name}{extension.lower()}'
        file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        url = f'/uploads/{filename}'
        db.session.add(MediaItem(
            gallery_id=gallery.id,
            section_id=section.id,
            media_type='image',
            title=name.replace('_', ' ') or 'Untitled photo',
            url=url,
            thumbnail_url=generate_image_thumbnail_url(url)
        ))
    db.session.commit()
    flash(f'{len(files)} photo(s) added to {section.title}.', 'success')
    return redirect(url_for('portal_gallery_detail', gallery_id=gallery.id, section=section.id, step=2))


@app.route('/portal/galleries/<int:gallery_id>/photos/delete', methods=['POST'])
@login_required
def portal_delete_gallery_photos(gallery_id):
    gallery = Gallery.query.get_or_404(gallery_id)
    photo_ids = {
        int(raw_id) for raw_id in request.form.getlist('photo_ids')
        if raw_id.isdigit()
    }
    if not photo_ids:
        flash('Select at least one photo to remove.', 'danger')
        return redirect(url_for('portal_gallery_detail', gallery_id=gallery.id, step=2))

    photos = MediaItem.query.filter(
        MediaItem.id.in_(photo_ids),
        MediaItem.gallery_id == gallery.id,
        MediaItem.media_type == 'image'
    ).all()
    if len(photos) != len(photo_ids):
        flash('One or more selected photos could not be found in this gallery.', 'danger')
        return redirect(url_for('portal_gallery_detail', gallery_id=gallery.id, step=2))

    deleted_urls = {photo.url for photo in photos}
    for photo in photos:
        db.session.delete(photo)
    if gallery.cover_url in deleted_urls:
        replacement = MediaItem.query.filter(
            MediaItem.gallery_id == gallery.id,
            MediaItem.media_type == 'image',
            ~MediaItem.id.in_(photo_ids)
        ).order_by(MediaItem.sort_order.asc(), MediaItem.id.asc()).first()
        gallery.cover_url = replacement.url if replacement else ''
        if not replacement:
            gallery.is_active = False
    db.session.commit()
    flash(f'{len(photos)} photo(s) removed from the gallery.', 'info')
    return redirect(url_for('portal_gallery_detail', gallery_id=gallery.id, step=2))


@app.route('/portal/galleries/<int:gallery_id>/delete', methods=['POST'])
@login_required
def portal_delete_gallery(gallery_id):
    gallery = Gallery.query.get_or_404(gallery_id)
    db.session.delete(gallery)
    db.session.commit()
    flash('Gallery deleted.', 'info')
    return redirect(url_for('portal_galleries'))


@app.route('/portal/media/upload', methods=['POST'])
@login_required
def portal_upload_media():
    media_type = 'video'
    title = request.form.get('title', '').strip()
    url = request.form.get('url', '').strip()
    thumbnail_url = request.form.get('thumbnail_url', '').strip()
    photographer = request.form.get('photographer', '').strip() or 'Cathea Studio'
    files = [
        file for field in ('video_files', 'media_file')
        for file in request.files.getlist(field)
        if file and file.filename
    ]

    if not files and not url:
        flash('Choose one or more video files or provide a video link.', 'danger')
        return redirect(url_for('portal_dashboard', tab='tabMedia'))
    if url and not title:
        flash('A title is required when adding a video link.', 'danger')
        return redirect(url_for('portal_dashboard', tab='tabMedia'))

    invalid_files = [file.filename for file in files if not allowed_media_file(file.filename, media_type)]
    if invalid_files:
        flash('Only MP4, MOV, and WEBM files can be uploaded as videos.', 'danger')
        return redirect(url_for('portal_dashboard', tab='tabMedia'))
    if url and not is_video_url(url):
        flash('Use a YouTube, Vimeo, Google Drive, or direct MP4/MOV/WEBM video link.', 'danger')
        return redirect(url_for('portal_dashboard', tab='tabMedia'))

    video_thumbnail = Gallery.query.order_by(Gallery.sort_order.asc()).first()
    fallback_thumbnail = thumbnail_url or (video_thumbnail.cover_url if video_thumbnail else '')
    for file in files:
        uploaded_url = save_media_upload(file)
        filename = secure_filename(file.filename)
        file_title = os.path.splitext(filename)[0].replace('_', ' ').strip() or title or 'Untitled video'
        db.session.add(MediaItem(
            media_type=media_type,
            title=file_title,
            photographer=photographer,
            url=uploaded_url,
            thumbnail_url=fallback_thumbnail or uploaded_url
        ))
    if url:
        db.session.add(MediaItem(
            media_type=media_type,
            title=title,
            photographer=photographer,
            url=url,
            thumbnail_url=fallback_thumbnail or url
        ))
    db.session.commit()
    added_count = len(files) + int(bool(url))
    flash(f'{added_count} video{"s" if added_count != 1 else ""} added.', 'success')
    return redirect(url_for('portal_dashboard', tab='tabMedia'))


@app.route('/portal/media/<int:item_id>/update', methods=['POST'])
@login_required
def portal_update_media(item_id):
    item = MediaItem.query.get_or_404(item_id)
    title = request.form.get('title', '').strip()
    url = request.form.get('url', '').strip()

    if not title or not url:
        flash('Title and media URL are required.', 'danger')
        return redirect(url_for('portal_dashboard', tab='tabMedia'))

    if item.media_type == 'video' and not (
        url.startswith('/uploads/') or is_video_url(url)
    ):
        flash('Use a YouTube, Vimeo, Google Drive, or direct MP4/MOV/WEBM video link.', 'danger')
        return redirect(url_for('portal_dashboard', tab='tabMedia'))

    if item.media_type == 'image':
        section_id = request.form.get('section_id', '')
        section = GallerySection.query.filter_by(id=section_id, gallery_id=item.gallery_id).first() if section_id.isdigit() else None
        if not section:
            flash('Choose a valid section for this photo.', 'danger')
            return redirect(url_for('portal_gallery_detail', gallery_id=item.gallery_id))
        item.section_id = section.id
        item.thumbnail_url = generate_image_thumbnail_url(url)
    else:
        item.photographer = request.form.get('photographer', '').strip() or 'Cathea Studio'
        item.duration = request.form.get('duration', '').strip()
        thumbnail_url = request.form.get('thumbnail_url', '').strip()
        fallback_gallery = Gallery.query.order_by(Gallery.sort_order.asc()).first()
        item.thumbnail_url = thumbnail_url or (
            fallback_gallery.cover_url if fallback_gallery else url
        )

    item.title = title
    item.url = url
    if 'is_featured' in request.form:
        item.is_featured = request.form.get('is_featured') == 'on'
    if item.media_type == 'image':
        homepage = HomepageContent.query.first()
        if homepage:
            homepage.photo_selection_initialized = True
    if item.media_type == 'video' and item.is_featured:
        MediaItem.query.filter(
            MediaItem.media_type == 'video',
            MediaItem.id != item.id,
            MediaItem.is_featured.is_(True)
        ).update({MediaItem.is_featured: False}, synchronize_session=False)

    db.session.commit()
    flash('Media item updated.', 'success')
    if item.media_type == 'image' and item.gallery_id:
        return redirect(url_for('portal_gallery_detail', gallery_id=item.gallery_id, section=item.section_id))
    return redirect(url_for('portal_dashboard', tab='tabMedia'))


@app.route('/portal/media/<int:item_id>/visibility', methods=['POST'])
@login_required
def portal_set_video_visibility(item_id):
    item = MediaItem.query.filter_by(id=item_id, media_type='video').first_or_404()
    action = request.form.get('action')
    if action not in ('hide', 'show'):
        flash('Choose whether to hide or show this video.', 'danger')
        return redirect(url_for('portal_dashboard', tab='tabMedia'))

    item.is_listed = action == 'show'
    db.session.commit()
    flash('Video hidden.' if action == 'hide' else 'Video shown.', 'success')
    return redirect(url_for('portal_dashboard', tab='tabMedia'))


@app.route('/portal/homepage/update', methods=['POST'])
@login_required
def portal_update_homepage():
    homepage = HomepageContent.query.first()
    if not homepage:
        homepage = HomepageContent()
        db.session.add(homepage)

    selected_photo_ids = set()
    for raw_id in request.form.getlist('featured_photo_ids'):
        if raw_id.isdigit():
            selected_photo_ids.add(int(raw_id))
    all_photos = MediaItem.query.filter_by(media_type='image').all()
    valid_photo_ids = {photo.id for photo in all_photos}
    if not selected_photo_ids.issubset(valid_photo_ids):
        flash('One or more selected homepage photos no longer exist.', 'danger')
        return redirect(url_for('portal_dashboard', tab='tabHomepage'))
    selected_cta_photo_ids = {
        int(raw_id) for raw_id in request.form.getlist('cta_photo_ids')
        if raw_id.isdigit()
    }
    if not selected_cta_photo_ids.issubset(valid_photo_ids):
        flash('One or more selected CTA photos no longer exist.', 'danger')
        return redirect(url_for('portal_dashboard', tab='tabHomepage'))
    if len(selected_cta_photo_ids) > 12:
        flash('Choose no more than twelve CTA background photos.', 'danger')
        return redirect(url_for('portal_dashboard', tab='tabHomepage'))

    selected_video_id = request.form.get('featured_video_id', '').strip()
    selected_video = MediaItem.query.filter_by(
        id=int(selected_video_id),
        media_type='video'
    ).first() if selected_video_id.isdigit() else None
    if selected_video_id and not selected_video:
        flash('The selected Cinema video is unavailable.', 'danger')
        return redirect(url_for('portal_dashboard', tab='tabHomepage'))

    hero_video = None
    hero_video_url = ''
    if request.form.get('hero_video_source', 'existing') == 'custom':
        hero_file = request.files.get('hero_video_file')
        if hero_file and hero_file.filename:
            if not allowed_media_file(hero_file.filename, 'video'):
                flash('Hero background must be an MP4, MOV, or WEBM video.', 'danger')
                return redirect(url_for('portal_dashboard', tab='tabHomepage'))
            hero_video_url = save_media_upload(hero_file)
        else:
            hero_video_url = request.form.get('hero_video_url', '').strip()
            if not hero_video_url or (
                not hero_video_url.startswith('/uploads/')
                and not is_video_url(hero_video_url)
            ):
                flash('Choose a video link or upload a video for the hero background.', 'danger')
                return redirect(url_for('portal_dashboard', tab='tabHomepage'))
    else:
        hero_video_id = request.form.get('hero_video_id', '').strip()
        hero_video = MediaItem.query.filter_by(
            id=int(hero_video_id),
            media_type='video'
        ).first() if hero_video_id.isdigit() else None
        if hero_video_id and not hero_video:
            flash('The selected hero video is unavailable.', 'danger')
            return redirect(url_for('portal_dashboard', tab='tabHomepage'))

    editable_fields = (
        'hero_subtitle',
        'hero_index',
        'stills_heading',
        'stills_kicker',
        'archive_link_label',
        'cinema_kicker',
        'cinema_link_label',
        'about_heading',
        'about_lead',
        'about_body',
        'about_coordinates',
        'about_link_label',
        'about_image_url',
        'cta_heading',
        'cta_subheading',
        'cta_button_label'
    )
    for field in editable_fields:
        setattr(homepage, field, request.form.get(field, '').strip())

    for photo in all_photos:
        photo.is_featured = photo.id in selected_photo_ids
        photo.is_cta_featured = photo.id in selected_cta_photo_ids
    homepage.photo_selection_initialized = True
    homepage.cta_photo_selection_initialized = True

    for video in MediaItem.query.filter_by(media_type='video').all():
        video.is_featured = selected_video is not None and video.id == selected_video.id

    homepage.hero_video_id = hero_video.id if hero_video else None
    homepage.hero_video_url = hero_video_url

    db.session.commit()
    flash('Homepage content updated.', 'success')
    return redirect(url_for('portal_dashboard', tab='tabHomepage'))


@app.route('/portal/homepage/reset-text', methods=['POST'])
@login_required
def portal_reset_homepage_text():
    homepage = HomepageContent.query.first()
    if not homepage:
        homepage = HomepageContent()
        db.session.add(homepage)
    default_text = {
        'hero_subtitle': 'celebrating love.',
        'hero_index': 'INDEX • 01 — 09',
        'stills_heading': 'Selected Stills',
        'stills_kicker': 'CATHEA.STUDIO • ATELIER',
        'archive_link_label': 'View Complete Archive →',
        'cinema_kicker': 'CATHEA.STUDIO • CINEMA',
        'cinema_link_label': 'Explore Cinema →',
        'about_heading': 'celebrating love.',
        'about_lead': 'We believe the most poignant memories are unscripted. We document genuine human presence, candid laughter, quiet touches, and the unhurried elegance of two people coming together.',
        'about_body': 'Cathea is an independent photography and motion atelier based between Batam and Singapore. We reject manufactured drama in favor of natural light, subtle chemistry, and timeless framing. Available for intimate weddings, prewedding journeys, and private commissions globally.',
        'about_coordinates': "1°07'N 104°02'E • BATAM / SINGAPORE",
        'about_link_label': 'Initiate Inquiries →',
        'cta_heading': 'Every tales is one of a kind.',
        'cta_subheading': 'That include yours...',
        'cta_button_label': 'Weave your tale with us'
    }
    for field, value in default_text.items():
        setattr(homepage, field, value)
    db.session.commit()
    flash('Homepage text restored to its defaults. Photo and video selections were left unchanged.', 'success')
    return redirect(url_for('portal_dashboard', tab='tabHomepage'))


@app.route('/portal/media/<int:item_id>/delete', methods=['POST'])
@login_required
def portal_delete_media(item_id):
    item = MediaItem.query.get_or_404(item_id)
    gallery_id = item.gallery_id if item.media_type == 'image' else None
    section_id = item.section_id if gallery_id else None
    homepage = HomepageContent.query.first()
    if homepage and homepage.hero_video_id == item.id:
        homepage.hero_video_id = None
    db.session.delete(item)
    db.session.commit()
    flash('Item deleted.', 'info')
    if gallery_id:
        return redirect(url_for('portal_gallery_detail', gallery_id=gallery_id, section=section_id))
    return redirect(url_for('portal_dashboard', tab='tabMedia'))


@app.route('/portal/settings/update', methods=['POST'])
@login_required
def portal_update_settings():
    settings = SiteSettings.query.first()
    if not settings:
        settings = SiteSettings()
        db.session.add(settings)
        
    settings.site_title = request.form.get('site_title', settings.site_title).strip()
    settings.whatsapp_number = request.form.get('whatsapp_number', settings.whatsapp_number).strip().replace('+', '').replace(' ', '')
    settings.instagram_handle = request.form.get('instagram_handle', settings.instagram_handle).strip()
    settings.llm_provider = request.form.get('llm_provider', settings.llm_provider)
    settings.llm_api_key = request.form.get('llm_api_key', settings.llm_api_key).strip()
    settings.llm_system_prompt = request.form.get('llm_system_prompt', settings.llm_system_prompt).strip()
    
    db.session.commit()
    flash('Settings updated.', 'success')
    return redirect(url_for('portal_dashboard'))


@app.route('/portal/password/change', methods=['POST'])
@portal_space_required
def portal_change_password():
    current_pass = request.form.get('current_password', '')
    new_pass = request.form.get('new_password', '')
    confirm_pass = request.form.get('confirm_password', '')
    
    user = User.query.get(session['user_id'])
    if not user.check_password(current_pass):
        flash('Current password incorrect.', 'danger')
        destination = 'portal_employee_space' if user.normalized_role == 'employee' else 'portal_dashboard'
        return redirect(url_for(destination))
        
    if len(new_pass) < 8:
        flash('Password must be at least 8 characters.', 'danger')
        destination = 'portal_employee_space' if user.normalized_role == 'employee' else 'portal_dashboard'
        return redirect(url_for(destination))
        
    if new_pass != confirm_pass:
        flash('Passwords do not match.', 'danger')
        destination = 'portal_employee_space' if user.normalized_role == 'employee' else 'portal_dashboard'
        return redirect(url_for(destination))
        
    user.set_password(new_pass)
    user.session_version += 1
    session['session_version'] = user.session_version
    record_account_activity('password_changed', 'User changed their password.', subject_id=user.id)
    db.session.commit()
    flash('Password updated.', 'success')
    destination = 'portal_employee_space' if user.normalized_role == 'employee' else 'portal_dashboard'
    return redirect(url_for(destination))


@app.route('/portal/inquiries/<int:inquiry_id>/status', methods=['POST'])
@login_required
def portal_update_inquiry_status(inquiry_id):
    inquiry = Inquiry.query.get_or_404(inquiry_id)
    inquiry.status = request.form.get('status', 'Contacted')
    db.session.commit()
    flash('Status updated.', 'success')
    return redirect(url_for('portal_dashboard'))


if app.config.get('PORTAL_HOST'):
    app.wsgi_app = PortalHostMiddleware(app.wsgi_app, app.config['PORTAL_HOST'])


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5002))
    print(f"✨ Cathea Studio server running on http://127.0.0.1:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)
