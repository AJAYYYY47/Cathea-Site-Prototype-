import os
import re
from sqlalchemy import inspect, text
from models import db, User, Gallery, GallerySection, MediaItem, SiteSettings, HomepageContent, Inquiry

def init_db(app):
    db.init_app(app)
    with app.app_context():
        db.create_all()
        schema = inspect(db.engine)
        migrations = {
            'users': {
                'email': "VARCHAR(254) NOT NULL DEFAULT ''",
                'is_active': 'BOOLEAN NOT NULL DEFAULT 1',
                'session_version': 'INTEGER NOT NULL DEFAULT 0',
                'timed_out_until': 'DATETIME'
            },
            'media_items': {
                'section_id': 'INTEGER REFERENCES gallery_sections(id)',
                'is_cta_featured': 'BOOLEAN DEFAULT 0',
                'photographer': "VARCHAR(120) NOT NULL DEFAULT 'Cathea Studio'",
                'is_listed': 'BOOLEAN NOT NULL DEFAULT 1'
            },
            'homepage_content': {
                'hero_video_id': 'INTEGER',
                'hero_video_url': 'VARCHAR(600) DEFAULT \'\'',
                'photo_selection_initialized': 'BOOLEAN DEFAULT 0',
                'cta_photo_selection_initialized': 'BOOLEAN DEFAULT 0'
            },
            'calendar_events': {
                'event_date': 'DATE',
                'event_type': "VARCHAR(40) NOT NULL DEFAULT 'Wedding - Full Day'",
                'google_calendar_event_id': 'VARCHAR(255)',
                'google_calendar_sync_error': 'VARCHAR(500)'
            },
            'galleries': {
                'photographer': "VARCHAR(120) NOT NULL DEFAULT 'Cathea Studio'",
                'cover_position_desktop_x': 'FLOAT DEFAULT 50',
                'cover_position_desktop_y': 'FLOAT DEFAULT 50',
                'cover_position_tablet_x': 'FLOAT DEFAULT 50',
                'cover_position_tablet_y': 'FLOAT DEFAULT 50',
                'cover_position_mobile_x': 'FLOAT DEFAULT 50',
                'cover_position_mobile_y': 'FLOAT DEFAULT 50',
                'is_listed': 'BOOLEAN NOT NULL DEFAULT 1'
            }
        }
        with db.engine.begin() as connection:
            for table, columns in migrations.items():
                if not schema.has_table(table):
                    continue
                existing_columns = {
                    column['name'] for column in schema.get_columns(table)
                }
                for column_name, column_definition in columns.items():
                    if column_name not in existing_columns:
                        connection.execute(text(
                            f'ALTER TABLE {table} ADD COLUMN {column_name} {column_definition}'
                        ))
                        if column_name == 'is_listed' and table == 'media_items' and 'is_active' in existing_columns:
                            connection.execute(text(
                                'UPDATE media_items SET is_listed = is_active'
                            ))
                        elif column_name == 'is_listed' and table == 'galleries':
                            connection.execute(text(
                                'UPDATE galleries SET is_listed = is_active'
                            ))
                            connection.execute(text(
                                "UPDATE galleries SET is_active = 1 "
                                "WHERE is_active = 0 AND COALESCE(cover_url, '') != ''"
                            ))
            if schema.has_table('calendar_events'):
                connection.execute(text(
                    'UPDATE calendar_events SET event_date = DATE(starts_at) '
                    'WHERE event_date IS NULL AND starts_at IS NOT NULL'
                ))
            if schema.has_table('users'):
                connection.execute(text(
                    "UPDATE users SET role = 'administrator' WHERE role = 'admin'"
                ))
                connection.execute(text(
                    "UPDATE users SET role = 'management' WHERE role = 'manager'"
                ))
        seed_data()
        ensure_cta_photo_selection()
        ensure_gallery_sections()


def ensure_gallery_sections():
    for gallery in Gallery.query.all():
        section = GallerySection.query.filter_by(gallery_id=gallery.id).order_by(
            GallerySection.sort_order.asc()
        ).first()
        if not section:
            section = GallerySection(
                gallery_id=gallery.id,
                title='Session 1',
                sort_order=1
            )
            db.session.add(section)
            db.session.flush()
        MediaItem.query.filter_by(
            gallery_id=gallery.id,
            media_type='image',
            section_id=None
        ).update({MediaItem.section_id: section.id}, synchronize_session=False)
    db.session.commit()


def ensure_cta_photo_selection():
    homepage = HomepageContent.query.first()
    if homepage and not homepage.cta_photo_selection_initialized:
        initial_photos = MediaItem.query.filter_by(
            media_type='image',
            is_featured=True
        ).order_by(MediaItem.sort_order.asc(), MediaItem.id.asc()).limit(9).all()
        for photo in initial_photos:
            photo.is_cta_featured = True
        homepage.cta_photo_selection_initialized = True
        db.session.commit()

def slugify(text):
    text = text.lower()
    return re.sub(r'[\W_]+', '-', text).strip('-')

def seed_data():
    homepage = HomepageContent.query.first()
    if not homepage:
        homepage = HomepageContent()
        db.session.add(homepage)
        db.session.flush()

    # 1. Site Settings
    settings = SiteSettings.query.first()
    if not settings:
        settings = SiteSettings(
            site_title='cathea',
            whatsapp_number='6281234567890',
            instagram_handle='cathea.studio',
            llm_provider='mock',
            llm_api_key='',
            llm_system_prompt='You are Cathea Studio Assistant. You provide elegant, concise consultation regarding our wedding, prewedding, and event photography collections in Batam, Singapore, and worldwide (portfolio featured on Instagram @cathea.studio). When clients wish to discuss tailored packages or calendar availability, invite them to consult directly on WhatsApp.'
        )
        db.session.add(settings)

    # 2. Default Users
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', full_name='Studio Director', role='administrator')
        admin.set_password('cathea2026')
        db.session.add(admin)

    if not User.query.filter_by(username='employee').first():
        emp = User(username='employee', full_name='Studio Producer', role='employee')
        emp.set_password('cathea2026')
        db.session.add(emp)

    db.session.commit()

    # 3. Seed Galleries with Real Cathea Studio Mood & Initials
    if Gallery.query.count() == 0:
        g1 = Gallery(
            title='Harbour Bay Tea Ceremony',
            slug='harbour-bay-tea-ceremony',
            client='Cindy & Jonathan',
            location='Batam & Singapore',
            year='2025',
            cover_url='https://images.unsplash.com/photo-1519741497674-611481863552?auto=format&fit=crop&w=1000&h=1000&q=85',
            is_featured=True,
            sort_order=1
        )

        g2 = Gallery(
            title='Radisson Grand Ballroom',
            slug='radisson-grand-ballroom',
            client='Michelle & Ryan',
            location='Radisson Convention Center',
            year='2025',
            cover_url='https://images.unsplash.com/photo-1511285560929-80b456fea0bc?auto=format&fit=crop&w=1000&h=1000&q=85',
            is_featured=True,
            sort_order=2
        )

        g3 = Gallery(
            title='Nongsa Coastal Dusk',
            slug='nongsa-coastal-dusk',
            client='Jessica & Kevin',
            location='Nongsa Point Marina',
            year='2025',
            cover_url='https://images.unsplash.com/photo-1537633552985-df8429e8048b?auto=format&fit=crop&w=1000&h=1000&q=85',
            is_featured=True,
            sort_order=3
        )

        g4 = Gallery(
            title='Atelier Minimalist Study',
            slug='atelier-minimalist-study',
            client='Clara & David',
            location='Cathea Studio',
            year='2024',
            cover_url='https://images.unsplash.com/photo-1583939003579-730e3918a45a?auto=format&fit=crop&w=1000&h=1000&q=85',
            is_featured=True,
            sort_order=4
        )

        g5 = Gallery(
            title='Fort Canning & Marina',
            slug='fort-canning-marina',
            client='Valerie & Ethan',
            location='Singapore',
            year='2025',
            cover_url='https://images.unsplash.com/photo-1515934751635-c81c6bc9a2d8?auto=format&fit=crop&w=1000&h=1000&q=85',
            is_featured=True,
            sort_order=5
        )

        g6 = Gallery(
            title='The Private Residence Vows',
            slug='private-residence-vows',
            client='Amanda & William',
            location='Batam Island',
            year='2025',
            cover_url='https://images.unsplash.com/photo-1522335789203-aabd1fc54bc9?auto=format&fit=crop&w=1000&h=1000&q=85',
            is_featured=True,
            sort_order=6
        )

        db.session.add_all([g1, g2, g3, g4, g5, g6])
        db.session.commit()

        # Seed photos under each gallery with couple initials
        items = [
            # g1 (c + j)
            MediaItem(gallery_id=g1.id, media_type='image', title='Tea Ceremony Vows', description='c + j', url='https://images.unsplash.com/photo-1519741497674-611481863552?auto=format&fit=crop&w=1200&h=1200&q=85', sort_order=1),
            MediaItem(gallery_id=g1.id, media_type='image', title='The Ring & Pearls', description='c + j', url='https://images.unsplash.com/photo-1534528741775-53994a69daeb?auto=format&fit=crop&w=1200&h=1200&q=85', sort_order=2),
            MediaItem(gallery_id=g1.id, media_type='image', title='Garden Walkway', description='c + j', url='https://images.unsplash.com/photo-1509631179647-0177331693ae?auto=format&fit=crop&w=1200&h=1200&q=85', sort_order=3),
            MediaItem(gallery_id=g1.id, media_type='image', title='Veil on Staircase', description='c + j', url='https://images.unsplash.com/photo-1515886657613-9f3515b0c78f?auto=format&fit=crop&w=1200&h=1200&q=85', sort_order=4),

            # g2 (m + r)
            MediaItem(gallery_id=g2.id, media_type='image', title='Radisson Grand Entrance', description='m + r', url='https://images.unsplash.com/photo-1511285560929-80b456fea0bc?auto=format&fit=crop&w=1200&h=1200&q=85', sort_order=1),
            MediaItem(gallery_id=g2.id, media_type='image', title='First Dance Shadows', description='m + r', url='https://images.unsplash.com/photo-1513694203232-719a280e022f?auto=format&fit=crop&w=1200&h=1200&q=85', sort_order=2),
            MediaItem(gallery_id=g2.id, media_type='image', title='Champagne Toast', description='m + r', url='https://images.unsplash.com/photo-1490481651871-ab68de25d43d?auto=format&fit=crop&w=1200&h=1200&q=85', sort_order=3),

            # g3 (j + k)
            MediaItem(gallery_id=g3.id, media_type='image', title='Nongsa Sunset Horizon', description='j + k', url='https://images.unsplash.com/photo-1537633552985-df8429e8048b?auto=format&fit=crop&w=1200&h=1200&q=85', sort_order=1),
            MediaItem(gallery_id=g3.id, media_type='image', title='Ocean Rim Chemistry', description='j + k', url='https://images.unsplash.com/photo-1517841905240-472988babdf9?auto=format&fit=crop&w=1200&h=1200&q=85', sort_order=2),
            MediaItem(gallery_id=g3.id, media_type='image', title='Dusk by the Pier', description='j + k', url='https://images.unsplash.com/photo-1506794778202-cad84cf45f1d?auto=format&fit=crop&w=1200&h=1200&q=85', sort_order=3),

            # g4 (c + d)
            MediaItem(gallery_id=g4.id, media_type='image', title='Silk & Minimalist Studio', description='c + d', url='https://images.unsplash.com/photo-1583939003579-730e3918a45a?auto=format&fit=crop&w=1200&h=1200&q=85', sort_order=1),
            MediaItem(gallery_id=g4.id, media_type='image', title='Quiet Interlude', description='c + d', url='https://images.unsplash.com/photo-1600585154340-be6161a56a0c?auto=format&fit=crop&w=1200&h=1200&q=85', sort_order=2),

            # g5 (v + e)
            MediaItem(gallery_id=g5.id, media_type='image', title='Fort Canning Greenery', description='v + e', url='https://images.unsplash.com/photo-1515934751635-c81c6bc9a2d8?auto=format&fit=crop&w=1200&h=1200&q=85', sort_order=1),
            MediaItem(gallery_id=g5.id, media_type='image', title='Marina Bay Dusk', description='v + e', url='https://images.unsplash.com/photo-1531746020798-e6953c6e8e04?auto=format&fit=crop&w=1200&h=1200&q=85', sort_order=2),

            # g6 (a + w)
            MediaItem(gallery_id=g6.id, media_type='image', title='Family Blessing', description='a + w', url='https://images.unsplash.com/photo-1522335789203-aabd1fc54bc9?auto=format&fit=crop&w=1200&h=1200&q=85', sort_order=1),
            MediaItem(gallery_id=g6.id, media_type='image', title='Balcony Embrace', description='a + w', url='https://images.unsplash.com/photo-1527799820374-dcf8d9d4a388?auto=format&fit=crop&w=1200&h=1200&q=85', sort_order=2)
        ]
        db.session.add_all(items)

        # Cinema video items
        videos = [
            MediaItem(
                media_type='video',
                title='Cindy & Jonathan — Tea Ceremony Highlight',
                description='c + j',
                url='https://www.youtube.com/embed/ScMzIvxBSi4?autoplay=1',
                thumbnail_url='https://images.unsplash.com/photo-1519741497674-611481863552?auto=format&fit=crop&w=1000&h=1000&q=85',
                duration='03:15',
                is_featured=True
            ),
            MediaItem(
                media_type='video',
                title='Michelle & Ryan — Radisson Celebration',
                description='m + r',
                url='https://www.youtube.com/embed/Bey4XXJAqS8?autoplay=1',
                thumbnail_url='https://images.unsplash.com/photo-1511285560929-80b456fea0bc?auto=format&fit=crop&w=1000&h=1000&q=85',
                duration='04:20',
                is_featured=True
            ),
            MediaItem(
                media_type='video',
                title='Jessica & Kevin — Nongsa Marina Reel',
                description='j + k',
                url='https://www.youtube.com/embed/EngW7tLk6R8?autoplay=1',
                thumbnail_url='https://images.unsplash.com/photo-1537633552985-df8429e8048b?auto=format&fit=crop&w=1000&h=1000&q=85',
                duration='02:40',
                is_featured=True
            ),
            MediaItem(
                media_type='video',
                title='Clara & David — Studio Intimate Reel',
                description='c + d',
                url='https://www.youtube.com/embed/fJ9rUzIMcZQ?autoplay=1',
                thumbnail_url='https://images.unsplash.com/photo-1583939003579-730e3918a45a?auto=format&fit=crop&w=1000&h=1000&q=85',
                duration='01:50',
                is_featured=True
            )
        ]
        db.session.add_all(videos)

        db.session.commit()

    if not homepage.photo_selection_initialized:
        initial_photos = MediaItem.query.filter_by(media_type='image').order_by(
            MediaItem.sort_order.asc(), MediaItem.id.asc()
        ).limit(12).all()
        for photo in initial_photos:
            photo.is_featured = True
        homepage.photo_selection_initialized = True

    featured_videos = MediaItem.query.filter_by(media_type='video', is_featured=True).order_by(
        MediaItem.sort_order.asc(), MediaItem.id.asc()
    ).all()
    for video in featured_videos[1:]:
        video.is_featured = False

    db.session.commit()
