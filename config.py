import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DEFAULT_GOOGLE_CALENDAR_EMBED_URL = (
    'https://calendar.google.com/calendar/embed?height=600&wkst=1&ctz=Asia%2FJakarta'
    '&showPrint=0&src=amF5c29uemhhbmc0N0BnbWFpbC5jb20'
    '&src=ZmFtaWx5MTQ3NDc2MDc5Njk0OTczMzMyOTVAZ3JvdXAuY2FsZW5kYXIuZ29vZ2xlLmNvbQ'
    '&src=Y2xhc3Nyb29tMTAxMzU4NDIwNDAwMjkxNTc0MTY4QGdyb3VwLmNhbGVuZGFyLmdvb2dsZS5jb20'
    '&src=ZW4uaW5kb25lc2lhbiNob2xpZGF5QGdyb3VwLnYuY2FsZW5kYXIuZ29vZ2xlLmNvbQ'
    '&src=ZW4tZ2IuaW5kb25lc2lhbiNob2xpZGF5QGdyb3VwLnYuY2FsZW5kYXIuZ29vZ2xlLmNvbQ'
    '&src=Y2xhc3Nyb29tMTAxNDQ0MDgzNTc1NzQxOTk1MDQyQGdyb3VwLmNhbGVuZGFyLmdvb2dsZS5jb20'
    '&src=ZmVsaXh3aWpheWEyMzEzQGdtYWlsLmNvbQ'
    '&color=%23039be5&color=%23ef6c00&color=%231967d2&color=%230b8043'
    '&color=%230b8043&color=%233f51b5&color=%23e67c73'
)

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'cathea-studio-super-secret-key-2026')
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', f'sqlite:///{os.path.join(BASE_DIR, "cathea.db")}')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_PERMANENT = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PORTAL_HOST = os.environ.get('PORTAL_HOST', '').strip().lower()
    PORTAL_SCHEME = os.environ.get('PORTAL_SCHEME', '').strip().lower()
    GOOGLE_CALENDAR_EMBED_URL = os.environ.get(
        'GOOGLE_CALENDAR_EMBED_URL',
        DEFAULT_GOOGLE_CALENDAR_EMBED_URL
    ).strip()
    GOOGLE_OAUTH_CLIENT_ID = os.environ.get('GOOGLE_OAUTH_CLIENT_ID', '').strip()
    GOOGLE_OAUTH_CLIENT_SECRET = os.environ.get('GOOGLE_OAUTH_CLIENT_SECRET', '').strip()
    GOOGLE_CALENDAR_REDIRECT_URI = os.environ.get('GOOGLE_CALENDAR_REDIRECT_URI', '').strip()
    GOOGLE_CALENDAR_ID = os.environ.get('GOOGLE_CALENDAR_ID', 'primary').strip()
    GOOGLE_CALENDAR_TOKEN_KEY = os.environ.get('GOOGLE_CALENDAR_TOKEN_KEY', '').strip()
    MEDIA_STORAGE_DIR = os.path.abspath(os.path.expanduser(os.environ.get(
        'MEDIA_STORAGE_DIR',
        os.path.join(BASE_DIR, 'static', 'uploads')
    )))
    UPLOAD_FOLDER = MEDIA_STORAGE_DIR
    MEDIA_STAGING_DIR = os.path.abspath(os.path.expanduser(os.environ.get(
        'MEDIA_STAGING_DIR',
        os.path.join(BASE_DIR, 'instance', 'media-upload-staging')
    )))
    MEDIA_IMPORT_ROOT = os.path.abspath(os.path.expanduser(os.environ['MEDIA_IMPORT_ROOT'])) if os.environ.get('MEDIA_IMPORT_ROOT') else ''
    MEDIA_UPLOAD_CHUNK_SIZE = int(os.environ.get('MEDIA_UPLOAD_CHUNK_SIZE', str(4 * 1024 * 1024)))
    MAX_MEDIA_FILE_SIZE = int(os.environ.get('MAX_MEDIA_FILE_SIZE', str(4 * 1024 * 1024 * 1024)))
    MAX_CONTENT_LENGTH = 32 * 1024 * 1024  # 32 MB max upload
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'gif', 'mp4', 'mov', 'webm'}
