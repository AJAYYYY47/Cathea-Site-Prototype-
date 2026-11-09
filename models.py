import re
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

calendar_event_attendees = db.Table(
    'calendar_event_attendees',
    db.Column('event_id', db.Integer, db.ForeignKey('calendar_events.id'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True)
)


class User(db.Model):
    __tablename__ = 'users'
    
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    full_name = db.Column(db.String(120), default='')
    email = db.Column(db.String(254), default='')
    role = db.Column(db.String(50), default='employee', nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    session_version = db.Column(db.Integer, default=0, nullable=False)
    timed_out_until = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def normalized_role(self):
        return {'admin': 'administrator', 'manager': 'management'}.get(self.role, self.role)


class Gallery(db.Model):
    __tablename__ = 'galleries'
    
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    slug = db.Column(db.String(180), unique=True, nullable=False)
    client = db.Column(db.String(120), default='')
    photographer = db.Column(db.String(120), nullable=False, default='Cathea Studio')
    location = db.Column(db.String(150), default='Batam / Singapore')
    cover_url = db.Column(db.String(600), default='')
    cover_position_desktop_x = db.Column(db.Float, default=50)
    cover_position_desktop_y = db.Column(db.Float, default=50)
    cover_position_tablet_x = db.Column(db.Float, default=50)
    cover_position_tablet_y = db.Column(db.Float, default=50)
    cover_position_mobile_x = db.Column(db.Float, default=50)
    cover_position_mobile_y = db.Column(db.Float, default=50)
    year = db.Column(db.String(20), default='2025')
    is_active = db.Column(db.Boolean, default=True)
    is_listed = db.Column(db.Boolean, default=True, nullable=False)
    is_featured = db.Column(db.Boolean, default=True)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    items = db.relationship('MediaItem', backref='gallery', cascade='all, delete-orphan', lazy=True, order_by='MediaItem.sort_order.asc()')

    def get_initials(self):
        if self.client and '&' in self.client:
            parts = self.client.split('&')
            return f"{parts[0].strip()[:1].lower()} + {parts[1].strip()[:1].lower()}"
        elif self.client and 'and' in self.client.lower():
            parts = re.split(r'\band\b', self.client, flags=re.IGNORECASE)
            return f"{parts[0].strip()[:1].lower()} + {parts[1].strip()[:1].lower()}"
        return 'c + j'


class GallerySection(db.Model):
    __tablename__ = 'gallery_sections'

    id = db.Column(db.Integer, primary_key=True)
    gallery_id = db.Column(db.Integer, db.ForeignKey('galleries.id'), nullable=False)
    title = db.Column(db.String(180), nullable=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    gallery = db.relationship('Gallery', backref=db.backref(
        'sections',
        cascade='all, delete-orphan',
        lazy=True,
        order_by='GallerySection.sort_order.asc()'
    ))
    items = db.relationship('MediaItem', backref='section', lazy=True)


class MediaItem(db.Model):
    __tablename__ = 'media_items'
    
    id = db.Column(db.Integer, primary_key=True)
    gallery_id = db.Column(db.Integer, db.ForeignKey('galleries.id'), nullable=True)
    section_id = db.Column(db.Integer, db.ForeignKey('gallery_sections.id'), nullable=True)
    media_type = db.Column(db.String(20), nullable=False, default='image')  # 'image' or 'video'
    title = db.Column(db.String(200), nullable=False)
    photographer = db.Column(db.String(120), nullable=False, default='Cathea Studio')
    description = db.Column(db.Text, default='')
    url = db.Column(db.String(600), nullable=False)
    thumbnail_url = db.Column(db.String(600), default='')
    duration = db.Column(db.String(50), default='')
    is_listed = db.Column(db.Boolean, default=True, nullable=False)
    is_featured = db.Column(db.Boolean, default=False)
    is_cta_featured = db.Column(db.Boolean, default=False)
    sort_order = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def get_initials(self):
        if self.description and '+' in self.description:
            return self.description.strip().lower()
        if self.gallery and self.gallery.client:
            return self.gallery.get_initials()
        return 'c + s'


class SiteSettings(db.Model):
    __tablename__ = 'site_settings'
    
    id = db.Column(db.Integer, primary_key=True)
    site_title = db.Column(db.String(120), default='cathea')
    whatsapp_number = db.Column(db.String(50), default='6281234567890')
    instagram_handle = db.Column(db.String(80), default='cathea.studio')
    llm_provider = db.Column(db.String(50), default='mock')
    llm_api_key = db.Column(db.String(255), default='')
    llm_system_prompt = db.Column(db.Text, default='You are Cathea Studio Assistant. You provide elegant, concise assistance to prospective clients regarding our wedding, prewedding, and editorial photography portfolios in Batam, Singapore, and destinations worldwide. For bespoke quotations or calendar reservations, invite them to consult via WhatsApp.')


class HomepageContent(db.Model):
    __tablename__ = 'homepage_content'

    id = db.Column(db.Integer, primary_key=True)
    hero_subtitle = db.Column(db.String(180), default='celebrating love.')
    hero_index = db.Column(db.String(100), default='INDEX • 01 — 09')
    stills_heading = db.Column(db.String(180), default='Selected Stills')
    stills_kicker = db.Column(db.String(180), default='CATHEA.STUDIO • ATELIER')
    archive_link_label = db.Column(db.String(100), default='View Complete Archive →')
    cinema_kicker = db.Column(db.String(180), default='CATHEA.STUDIO • CINEMA')
    cinema_link_label = db.Column(db.String(100), default='Explore Cinema →')
    about_heading = db.Column(db.String(180), default='celebrating love.')
    about_lead = db.Column(db.Text, default='We believe the most poignant memories are unscripted. We document genuine human presence, candid laughter, quiet touches, and the unhurried elegance of two people coming together.')
    about_body = db.Column(db.Text, default='Cathea is an independent photography and motion atelier based between Batam and Singapore. We reject manufactured drama in favor of natural light, subtle chemistry, and timeless framing. Available for intimate weddings, prewedding journeys, and private commissions globally.')
    about_coordinates = db.Column(db.String(180), default="1°07'N 104°02'E • BATAM / SINGAPORE")
    about_link_label = db.Column(db.String(100), default='Initiate Inquiries →')
    about_image_url = db.Column(db.String(600), default='')
    hero_video_id = db.Column(db.Integer, default=None)
    hero_video_url = db.Column(db.String(600), default='')
    cta_heading = db.Column(db.String(180), default='Every tales is one of a kind.')
    cta_subheading = db.Column(db.String(180), default='That include yours...')
    cta_button_label = db.Column(db.String(120), default='Weave your tale with us')
    photo_selection_initialized = db.Column(db.Boolean, default=False)
    cta_photo_selection_initialized = db.Column(db.Boolean, default=False)


class Inquiry(db.Model):
    __tablename__ = 'inquiries'
    
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(50), default='')
    service_type = db.Column(db.String(100), default='Wedding')
    message = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(50), default='New')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class WorkAssignment(db.Model):
    __tablename__ = 'work_assignments'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, default='')
    deadline = db.Column(db.Date, nullable=True)
    scheduled_for = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(30), default='Pending', nullable=False)
    notes = db.Column(db.Text, default='')
    priority = db.Column(db.String(10), default='Low', nullable=False)
    commission_amount = db.Column(db.Float, default=0, nullable=False)
    commission_paid = db.Column(db.Boolean, default=False, nullable=False)
    assigned_to_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    assigned_to = db.relationship('User', foreign_keys=[assigned_to_id], backref='assignments')
    created_by = db.relationship('User', foreign_keys=[created_by_id])


class CalendarEvent(db.Model):
    __tablename__ = 'calendar_events'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(180), nullable=False)
    description = db.Column(db.Text, default='')
    event_date = db.Column(db.Date, nullable=True)
    event_type = db.Column(db.String(40), nullable=False, default='Wedding - Full Day')
    starts_at = db.Column(db.DateTime, nullable=True)
    ends_at = db.Column(db.DateTime, nullable=True)
    google_calendar_event_id = db.Column(db.String(255), nullable=True)
    google_calendar_sync_error = db.Column(db.String(500), nullable=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    created_by = db.relationship('User', foreign_keys=[created_by_id])
    attendees = db.relationship(
        'User',
        secondary=calendar_event_attendees,
        backref=db.backref('calendar_events', lazy='select')
    )
    commissions = db.relationship(
        'EventCommission',
        backref='event',
        cascade='all, delete-orphan',
        lazy=True
    )


class EmployeeCommissionRate(db.Model):
    __tablename__ = 'employee_commission_rates'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'event_type', name='uq_employee_event_commission_rate'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    event_type = db.Column(db.String(40), nullable=False)
    amount = db.Column(db.Numeric(14, 2), nullable=False, default=0)

    employee = db.relationship('User', backref='commission_rates')


class EventCommission(db.Model):
    __tablename__ = 'event_commissions'
    __table_args__ = (
        db.UniqueConstraint('event_id', 'user_id', name='uq_event_employee_commission'),
    )

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey('calendar_events.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    amount = db.Column(db.Numeric(14, 2), nullable=False, default=0)
    paid = db.Column(db.Boolean, nullable=False, default=False)

    employee = db.relationship('User', backref='event_commissions')


class CommissionAdjustment(db.Model):
    __tablename__ = 'commission_adjustments'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    adjustment_type = db.Column(db.String(12), nullable=False)
    amount = db.Column(db.Numeric(14, 2), nullable=False)
    note = db.Column(db.String(240), nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    employee = db.relationship('User', foreign_keys=[user_id], backref='commission_adjustments')
    created_by = db.relationship('User', foreign_keys=[created_by_id])


class GoogleCalendarCredential(db.Model):
    __tablename__ = 'google_calendar_credentials'

    id = db.Column(db.Integer, primary_key=True)
    encrypted_credentials = db.Column(db.Text, nullable=False)
    connected_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    connected_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    connected_by = db.relationship('User')


class AccountActivity(db.Model):
    __tablename__ = 'account_activity'

    id = db.Column(db.Integer, primary_key=True)
    actor_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    subject_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action = db.Column(db.String(80), nullable=False)
    details = db.Column(db.String(500), default='')
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    actor = db.relationship('User', foreign_keys=[actor_id])
    subject = db.relationship('User', foreign_keys=[subject_id])
