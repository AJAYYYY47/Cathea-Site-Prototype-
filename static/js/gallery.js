/**
 * Cathea Studio — Photos Lightbox & Video Modal
 */

document.addEventListener('DOMContentLoaded', () => {
  // ==========================================
  // Lightbox for Photos
  // ==========================================
  const photoCards = document.querySelectorAll('.square-card');
  const lightboxModal = document.getElementById('lightboxModal');
  const lightboxImg = document.getElementById('lightboxImg');
  const lightboxClose = document.getElementById('lightboxClose');

  if (photoCards.length > 0 && lightboxModal && lightboxImg) {
    photoCards.forEach(card => {
      card.addEventListener('click', () => {
        const fullSrc = card.dataset.src || card.querySelector('img').src;
        lightboxImg.src = fullSrc;
        lightboxModal.classList.add('active');
        document.body.style.overflow = 'hidden';
      });
    });

    function closeLightbox() {
      lightboxModal.classList.remove('active');
      lightboxImg.src = '';
      document.body.style.overflow = '';
    }

    if (lightboxClose) lightboxClose.addEventListener('click', closeLightbox);
    lightboxModal.addEventListener('click', (e) => {
      if (e.target === lightboxModal) closeLightbox();
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && lightboxModal.classList.contains('active')) {
        closeLightbox();
      }
    });
  }

  // ==========================================
  // Video Modal for Cinema
  // ==========================================
  const videoCards = document.querySelectorAll('.video-frame-card');
  const videoModal = document.getElementById('videoModal');
  const videoPlayerContainer = document.getElementById('videoPlayerContainer');
  const videoModalClose = document.getElementById('videoModalClose');

  if (videoCards.length > 0 && videoModal && videoPlayerContainer) {
    function openVideo(url) {
      let parsedUrl;
      try {
        parsedUrl = new URL(url, window.location.origin);
      } catch {
        return;
      }

      const host = parsedUrl.hostname.toLowerCase().replace(/^www\./, '');
      let embedUrl = '';
      if (host === 'drive.google.com') {
        const driveMatch = parsedUrl.pathname.match(/^\/file\/d\/([A-Za-z0-9_-]+)(?:\/|$)/);
        const fileId = driveMatch?.[1] || (
          ['/open', '/uc'].includes(parsedUrl.pathname)
            ? parsedUrl.searchParams.get('id')
            : ''
        );
        if (fileId && /^[A-Za-z0-9_-]+$/.test(fileId)) {
          embedUrl = `https://drive.google.com/file/d/${fileId}/preview`;
        }
      } else if (['youtube.com', 'm.youtube.com', 'youtube-nocookie.com', 'youtu.be'].includes(host)) {
        const videoId = host === 'youtu.be'
          ? parsedUrl.pathname.split('/').filter(Boolean)[0]
          : parsedUrl.pathname.startsWith('/embed/')
            ? parsedUrl.pathname.split('/')[2]
            : parsedUrl.searchParams.get('v');
        if (videoId && /^[A-Za-z0-9_-]+$/.test(videoId)) {
          embedUrl = `https://www.youtube-nocookie.com/embed/${videoId}?autoplay=1`;
        }
      } else if (['vimeo.com', 'player.vimeo.com'].includes(host)) {
        const videoId = parsedUrl.pathname.split('/').filter(Boolean).pop();
        if (videoId && /^\d+$/.test(videoId)) {
          embedUrl = `https://player.vimeo.com/video/${videoId}?autoplay=1`;
        }
      }

      videoPlayerContainer.replaceChildren();
      if (embedUrl) {
        const iframe = document.createElement('iframe');
        iframe.src = embedUrl;
        iframe.allow = 'autoplay; encrypted-media; fullscreen';
        iframe.title = 'Video player';
        videoPlayerContainer.append(iframe);
      } else if (['http:', 'https:'].includes(parsedUrl.protocol)) {
        const video = document.createElement('video');
        video.controls = true;
        video.autoplay = true;
        video.style.cssText = 'width:100%;height:100%';
        const source = document.createElement('source');
        source.src = parsedUrl.href;
        source.type = 'video/mp4';
        video.append(source);
        videoPlayerContainer.append(video);
      } else {
        return;
      }
      videoModal.classList.add('active');
      document.body.style.overflow = 'hidden';
    }

    function closeVideo() {
      videoModal.classList.remove('active');
      videoPlayerContainer.innerHTML = '';
      document.body.style.overflow = '';
    }

    videoCards.forEach(card => {
      card.addEventListener('click', () => {
        const url = card.dataset.videoUrl;
        if (url) openVideo(url);
      });
    });

    if (videoModalClose) videoModalClose.addEventListener('click', closeVideo);
    videoModal.addEventListener('click', (e) => {
      if (e.target === videoModal) closeVideo();
    });

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && videoModal.classList.contains('active')) {
        closeVideo();
      }
    });
  }
});
