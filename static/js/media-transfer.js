document.addEventListener('DOMContentLoaded', () => {
  const uploadJson = async (url, options = {}) => {
    const response = await fetch(url, { credentials: 'same-origin', ...options });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      const error = new Error(result.error || `Request failed (${response.status}).`);
      error.status = response.status;
      throw error;
    }
    return result;
  };

  const getUploadKey = (form, file) => [
    'media-upload',
    form.dataset.uploadContext,
    form.dataset.galleryId || '',
    form.dataset.sectionId || '',
    file.webkitRelativePath || file.name,
    file.size,
    file.lastModified
  ].join(':');

  const transferFile = async (form, file, fileIndex, fileCount, status) => {
    const context = form.dataset.uploadContext;
    const mediaType = form.dataset.mediaType;
    const storageKey = getUploadKey(form, file);
    const metadata = {
      filename: file.name,
      media_type: mediaType,
      context,
      total_size: file.size,
      gallery_id: form.dataset.galleryId,
      section_id: form.dataset.sectionId,
      title: form.querySelector('[name="title"]')?.value || '',
      photographer: form.querySelector('[name="photographer"]')?.value || '',
      thumbnail_url: form.querySelector('[name="thumbnail_url"]')?.value || ''
    };

    let uploadId = sessionStorage.getItem(storageKey);
    let missingChunks;
    if (uploadId) {
      try {
        const existing = await uploadJson(`/portal/uploads/${encodeURIComponent(uploadId)}/status`);
        const matches = existing.filename === metadata.filename
          && existing.media_type === metadata.media_type
          && existing.context === metadata.context
          && existing.total_size === metadata.total_size
          && String(existing.gallery_id || '') === String(metadata.gallery_id || '')
          && String(existing.section_id || '') === String(metadata.section_id || '');
        if (matches) {
          if (existing.complete) {
            sessionStorage.removeItem(storageKey);
            return existing;
          }
          missingChunks = existing.missing_chunks;
        } else {
          sessionStorage.removeItem(storageKey);
          uploadId = null;
        }
      } catch (error) {
        if (error.status !== 404) throw error;
        sessionStorage.removeItem(storageKey);
        uploadId = null;
      }
    }

    if (!uploadId) {
      const initialized = await uploadJson('/portal/uploads/init', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(metadata)
      });
      uploadId = initialized.upload_id;
      sessionStorage.setItem(storageKey, uploadId);
      missingChunks = Array.from({ length: initialized.chunk_count }, (_, index) => index);
    }

    const chunkSize = Number(form.dataset.chunkSize);
    for (let chunkIndex = 0; chunkIndex < missingChunks.length; chunkIndex += 1) {
      const partNumber = missingChunks[chunkIndex];
      const start = partNumber * chunkSize;
      const blob = file.slice(start, Math.min(start + chunkSize, file.size));
      status.textContent = `Uploading ${fileIndex + 1}/${fileCount}: ${file.name} · part ${chunkIndex + 1}/${missingChunks.length}`;
      let uploaded = false;
      for (let attempt = 0; attempt < 3 && !uploaded; attempt += 1) {
        try {
          await uploadJson(`/portal/uploads/${encodeURIComponent(uploadId)}/chunk/${partNumber}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/octet-stream' },
            body: blob
          });
          uploaded = true;
        } catch (error) {
          if (error.status && error.status < 500) throw error;
          if (attempt === 2) throw error;
          await new Promise((resolve) => window.setTimeout(resolve, 600 * (attempt + 1)));
        }
      }
    }

    status.textContent = `Finalizing ${fileIndex + 1}/${fileCount}: ${file.name}`;
    const completed = await uploadJson(`/portal/uploads/${encodeURIComponent(uploadId)}/complete`, {
      method: 'POST'
    });
    sessionStorage.removeItem(storageKey);
    return completed;
  };

  document.querySelectorAll('form[data-chunk-upload]').forEach((form) => {
    if (form.dataset.uploadContext === 'gallery_photo') {
      form.querySelectorAll('[data-chunk-file-input]').forEach((input) => {
        input.addEventListener('change', () => {
          if (input.files.length && form.dataset.uploading !== 'true') {
            form.requestSubmit();
          }
        });
      });
    }

    form.addEventListener('submit', async (event) => {
      const files = [...form.querySelectorAll('[data-chunk-file-input]')]
        .flatMap((input) => [...input.files]);
      if (!files.length) return;

      event.preventDefault();
      if (form.dataset.uploading === 'true') return;
      const status = form.querySelector('[data-transfer-status]');
      const submitButton = form.querySelector('button[type="submit"]');
      if (!status) return;
      form.dataset.uploading = 'true';
      if (submitButton) submitButton.disabled = true;
      form.querySelectorAll('[data-chunk-file-input]').forEach((input) => {
        input.disabled = true;
      });

      try {
        let lastCompleted;
        for (let index = 0; index < files.length; index += 1) {
          lastCompleted = await transferFile(form, files[index], index, files.length, status);
        }

        form.querySelectorAll('[data-chunk-file-input]').forEach((input) => {
          input.value = '';
        });
        if (form.dataset.uploadContext === 'gallery_photo') {
          status.textContent = `${files.length} photo(s) uploaded.`;
          window.location.assign(form.dataset.returnUrl);
          return;
        }
        if (form.dataset.uploadContext === 'homepage_hero') {
          const heroMode = form.querySelector('[name="hero_video_source"]');
          const heroUrl = form.querySelector('[name="hero_video_url"]');
          if (heroMode) heroMode.value = 'custom';
          if (heroUrl) heroUrl.value = lastCompleted.url;
          status.textContent = 'Hero video uploaded. Saving homepage settings…';
          form.requestSubmit();
          return;
        }

        const link = form.querySelector('[name="url"]')?.value.trim();
        if (link) {
          status.textContent = `${files.length} video(s) uploaded. Adding the video link…`;
          form.requestSubmit();
          return;
        }
        status.textContent = `${files.length} video(s) uploaded.`;
        window.location.assign(form.dataset.returnUrl);
      } catch (error) {
        status.textContent = `Upload stopped: ${error.message} Select the same file(s) again to resume.`;
        form.dataset.uploading = 'false';
        form.querySelectorAll('[data-chunk-file-input]').forEach((input) => {
          input.disabled = false;
        });
        if (submitButton) submitButton.disabled = false;
      }
    });
  });

  document.querySelectorAll('[data-media-import]').forEach((importer) => {
    const entriesNode = importer.querySelector('[data-import-entries]');
    const locationNode = importer.querySelector('[data-import-location]');
    const parentButton = importer.querySelector('[data-import-parent]');
    const importButton = importer.querySelector('[data-import-submit]');
    const status = importer.querySelector('[data-import-status]');
    if (!entriesNode || !importButton || !status) return;

    let currentPath = '';
    const selectedPaths = new Set();
    const updateImportButton = () => {
      importButton.disabled = selectedPaths.size === 0;
      importButton.textContent = `Import selected ${importer.dataset.mediaType === 'image' ? 'photos' : 'videos'} (${selectedPaths.size})`;
    };

    const browse = async (path = '') => {
      status.textContent = 'Loading folder…';
      try {
        const url = new URL(importer.dataset.browseUrl, window.location.origin);
        url.searchParams.set('media_type', importer.dataset.mediaType);
        url.searchParams.set('path', path);
        const result = await uploadJson(url);
        currentPath = result.current;
        if (locationNode) locationNode.textContent = currentPath || 'Import folder';
        if (parentButton) {
          parentButton.hidden = !currentPath;
          parentButton.dataset.parentPath = result.parent;
        }
        entriesNode.replaceChildren();

        result.entries.forEach((entry) => {
          const row = document.createElement('div');
          row.className = 'server-media-import-entry';
          if (entry.kind === 'folder') {
            const openFolder = document.createElement('button');
            openFolder.type = 'button';
            openFolder.className = 'server-media-folder-button';
            openFolder.textContent = `Open folder: ${entry.name}`;
            openFolder.addEventListener('click', () => browse(entry.path));
            row.append(openFolder);
          } else {
            const checkbox = document.createElement('input');
            checkbox.type = 'checkbox';
            checkbox.value = entry.path;
            checkbox.checked = selectedPaths.has(entry.path);
            checkbox.addEventListener('change', () => {
              if (checkbox.checked) selectedPaths.add(entry.path);
              else selectedPaths.delete(entry.path);
              updateImportButton();
            });
            const name = document.createElement('span');
            name.textContent = entry.name;
            const fileLabel = document.createElement('label');
            fileLabel.append(checkbox, name);
            row.append(fileLabel);
          }
          entriesNode.append(row);
        });
        status.textContent = '';
      } catch (error) {
        status.textContent = error.message;
      }
    };

    importer.addEventListener('toggle', () => {
      if (importer.open && !importer.dataset.loaded) {
        importer.dataset.loaded = 'true';
        browse();
      }
    });
    parentButton?.addEventListener('click', () => browse(parentButton.dataset.parentPath || ''));
    importButton.addEventListener('click', async () => {
      if (!selectedPaths.size) return;
      importButton.disabled = true;
      status.textContent = 'Importing selected files…';
      const payload = {
        media_type: importer.dataset.mediaType,
        paths: [...selectedPaths],
        gallery_id: importer.dataset.galleryId,
        section_id: importer.dataset.sectionId
      };
      try {
        const result = await uploadJson(importer.dataset.importUrl, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        status.textContent = `Imported ${result.imported} file(s).`;
        window.location.assign(importer.dataset.returnUrl);
      } catch (error) {
        status.textContent = error.message;
        updateImportButton();
      }
    });
  });
});
