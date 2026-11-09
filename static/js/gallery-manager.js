document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('[data-close-gallery-form]').forEach((button) => {
    button.addEventListener('click', () => {
      const card = button.closest('details');
      if (card) card.open = false;
    });
  });

  document.querySelectorAll('[data-copy-to]').forEach((select) => {
    select.addEventListener('change', () => {
      const target = document.querySelector(select.dataset.copyTo);
      if (target) target.value = select.value;
    });
  });

  const dropzoneConfigs = [
    {
      dropzone: '[data-photo-dropzone]',
      input: '[data-photo-input]',
      selection: '[data-photo-selection]',
      accepts: (file) => file.type.startsWith('image/') || /\.(png|jpe?g|webp|gif)$/i.test(file.name),
      label: 'photo'
    },
    {
      dropzone: '[data-media-dropzone]',
      input: '[data-media-input]',
      selection: '[data-media-selection]',
      accepts: (file) => file.type.startsWith('video/') || /\.(mp4|mov|webm)$/i.test(file.name),
      label: 'video'
    },
    {
      dropzone: '[data-hero-dropzone]',
      input: '[data-hero-file-input]',
      selection: '[data-hero-file-selection]',
      accepts: (file) => file.type.startsWith('video/') || /\.(mp4|mov|webm)$/i.test(file.name),
      label: 'video'
    }
  ];

  dropzoneConfigs.forEach(({ dropzone: dropzoneSelector, input: inputSelector, selection: selectionSelector, accepts, label }) => {
    const dropzone = document.querySelector(dropzoneSelector);
    const input = document.querySelector(inputSelector);
    const selection = document.querySelector(selectionSelector);
    if (!dropzone || !input || !selection) return;

    const showFiles = (files) => {
      selection.textContent = files.length
        ? `${files.length} ${label}${files.length === 1 ? '' : 's'} selected`
        : '';
    };

    input.addEventListener('change', () => showFiles(input.files));
    dropzone.addEventListener('dragover', (event) => {
      event.preventDefault();
      dropzone.classList.add('drag-over');
    });
    dropzone.addEventListener('dragleave', (event) => {
      if (!dropzone.contains(event.relatedTarget)) dropzone.classList.remove('drag-over');
    });
    dropzone.addEventListener('drop', (event) => {
      event.preventDefault();
      dropzone.classList.remove('drag-over');
      const files = [...event.dataTransfer.files].filter(accepts);
      if (!files.length) {
        selection.textContent = `Drop ${label} files only.`;
        return;
      }

      const transfer = new DataTransfer();
      files.slice(0, input.multiple ? files.length : 1).forEach((file) => transfer.items.add(file));
      input.files = transfer.files;
      input.dispatchEvent(new Event('change', { bubbles: true }));
      showFiles(input.files);
    });
  });

  const photoDropzone = document.querySelector('[data-photo-dropzone]');
  const photoInput = document.querySelector('[data-photo-input]');
  const photoDropText = document.querySelector('[data-photo-drop-text]');
  const uploadSubmit = document.querySelector('[data-upload-submit]');
  const updateUploadButton = () => {
    if (!photoInput || !uploadSubmit) return;
    const count = [...document.querySelectorAll('[data-photo-input], [data-photo-folder-input]')]
      .reduce((total, input) => total + input.files.length, 0);
    uploadSubmit.disabled = count === 0;
    uploadSubmit.textContent = count ? `Upload ${count} ${count === 1 ? 'photo' : 'photos'}` : 'Upload photos';
  };
  document.querySelectorAll('[data-photo-input], [data-photo-folder-input]')
    .forEach((input) => input.addEventListener('change', updateUploadButton));
  photoDropzone?.addEventListener('dragover', (event) => {
    const count = [...(event.dataTransfer?.items || [])].filter((item) => item.kind === 'file').length;
    if (photoDropText) {
      photoDropText.textContent = count
        ? `Drop ${count} ${count === 1 ? 'image' : 'images'} to upload`
        : 'Drop images here to upload';
    }
  });
  photoDropzone?.addEventListener('dragleave', (event) => {
    if (!photoDropzone.contains(event.relatedTarget) && photoDropText) {
      photoDropText.textContent = 'Drop images here to upload';
    }
  });
  photoDropzone?.addEventListener('drop', () => {
    if (photoDropText) photoDropText.textContent = 'Drop images here to upload';
    window.setTimeout(updateUploadButton, 0);
  });

  const photoCards = [...document.querySelectorAll('[data-photo-card]')];
  const selectedPhotoCount = document.querySelector('[data-selected-count]');
  const deleteSelectedButton = document.querySelector('[data-delete-selected]');
  const selectAllButton = document.querySelector('[data-select-all]');
  const updatePhotoSelection = () => {
    const selectedCount = photoCards.filter((card) => card.dataset.selected === 'true').length;
    if (selectedPhotoCount) {
      selectedPhotoCount.textContent = `${selectedCount} selected`;
    }
    if (deleteSelectedButton) deleteSelectedButton.disabled = selectedCount === 0;
    photoCards.forEach((card) => {
      const selected = card.dataset.selected === 'true';
      card.classList.toggle('is-selected', selected);
      card.setAttribute('aria-pressed', String(selected));
      const input = card.querySelector('[data-photo-select]');
      if (input) input.disabled = !selected;
    });
    if (selectAllButton) {
      selectAllButton.textContent = selectedCount && selectedCount === photoCards.length
        ? 'Clear selection'
        : 'Select all';
    }
  };
  let rangeAnchor = null;
  const selectPhotoRange = (index, selected) => {
    if (rangeAnchor !== null) {
      const start = Math.min(rangeAnchor, index);
      const end = Math.max(rangeAnchor, index);
      for (let cursor = start; cursor <= end; cursor += 1) {
        photoCards[cursor].dataset.selected = String(selected);
      }
    } else {
      photoCards[index].dataset.selected = String(selected);
    }
    rangeAnchor = index;
    updatePhotoSelection();
  };
  photoCards.forEach((card, index) => {
    card.addEventListener('click', (event) => {
      if (suppressPhotoClick) {
        event.preventDefault();
        event.stopPropagation();
        suppressPhotoClick = false;
        return;
      }
      const selected = card.dataset.selected !== 'true';
      if (event.shiftKey) {
        selectPhotoRange(index, selected);
        return;
      }
      card.dataset.selected = String(selected);
      rangeAnchor = index;
      updatePhotoSelection();
    });
    card.addEventListener('keydown', (event) => {
      if (event.key !== ' ' && event.key !== 'Enter') return;
      event.preventDefault();
      card.dataset.selected = String(card.dataset.selected !== 'true');
      rangeAnchor = index;
      updatePhotoSelection();
    });
  });
  selectAllButton?.addEventListener('click', () => {
    const select = photoCards.some((card) => card.dataset.selected !== 'true');
    photoCards.forEach((card) => {
      card.dataset.selected = String(select);
    });
    updatePhotoSelection();
  });
  updatePhotoSelection();

  const photoGrid = document.querySelector('.gallery-photo-grid');
  let dragSelection = null;
  let suppressPhotoClick = false;
  photoGrid?.addEventListener('pointerdown', (event) => {
    if (event.pointerType !== 'mouse' || event.button !== 0 || !event.target.closest('[data-photo-card]')) return;
    const card = event.target.closest('[data-photo-card]');
    dragSelection = {
      x: event.clientX,
      y: event.clientY,
      moved: false,
      selected: card.dataset.selected !== 'true'
    };
  });
  document.addEventListener('pointermove', (event) => {
    if (!dragSelection) return;
    if (!dragSelection.moved && Math.hypot(event.clientX - dragSelection.x, event.clientY - dragSelection.y) < 6) return;
    dragSelection.moved = true;
    const card = document.elementFromPoint(event.clientX, event.clientY)?.closest('[data-photo-card]');
    if (card && card.dataset.selected !== String(dragSelection.selected)) {
      card.dataset.selected = String(dragSelection.selected);
      updatePhotoSelection();
    }
  });
  document.addEventListener('pointerup', () => {
    if (dragSelection?.moved) suppressPhotoClick = true;
    dragSelection = null;
  });

  document.querySelectorAll('[data-section-label]').forEach((label) => {
    const sectionItem = label.closest('.gallery-section-item');
    const link = label.closest('a');
    const renameForm = sectionItem?.querySelector('.section-inline-rename');
    const renameInput = renameForm?.querySelector('input[name="title"]');
    if (!sectionItem || !link || !renameForm || !renameInput) return;

    const beginRename = () => {
      label.hidden = true;
      renameForm.hidden = false;
      renameInput.focus();
      renameInput.select();
    };
    let navigationTimer = null;
    link.addEventListener('click', (event) => {
      if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
      event.preventDefault();
      if (navigationTimer) {
        window.clearTimeout(navigationTimer);
        navigationTimer = null;
        beginRename();
      } else {
        navigationTimer = window.setTimeout(() => {
          window.location.assign(link.href);
        }, 240);
      }
    });
    link.addEventListener('dblclick', (event) => {
      event.preventDefault();
      if (navigationTimer) window.clearTimeout(navigationTimer);
      navigationTimer = null;
      beginRename();
    });
    renameInput.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        event.preventDefault();
        renameForm.hidden = true;
        label.hidden = false;
      }
    });
  });

  document.querySelectorAll('[data-confirm-delete]').forEach((form) => {
    form.addEventListener('submit', (event) => {
      const message = form.dataset.confirmMessage || 'Are you sure you want to delete this?';
      if (!window.confirm(message)) event.preventDefault();
    });
  });

  const galleryDetailsDialog = document.querySelector('[data-gallery-details-dialog]');
  document.querySelector('[data-open-gallery-details]')?.addEventListener('click', () => {
    galleryDetailsDialog?.showModal();
  });
  document.querySelector('[data-close-gallery-details]')?.addEventListener('click', () => {
    galleryDetailsDialog?.close();
  });

  const coverOptions = [...document.querySelectorAll('[data-cover-option]')];
  const cropPreview = document.querySelector('[data-crop-preview]');
  const cropPreviewImage = document.querySelector('[data-crop-preview-image]');
  const cropPreviewCaption = document.querySelector('[data-crop-preview-caption]');
  const selectedCoverId = document.querySelector('[data-selected-cover-id]');
  const cropFactors = [...document.querySelectorAll('[data-crop-factor]')];
  let activeCropFactor = 'desktop';
  const updateCropPreview = () => {
    if (!cropPreview || !cropPreviewImage) return;
    const controls = document.querySelector(`[data-crop-controls="${activeCropFactor}"]`);
    const x = controls?.querySelector('[data-crop-axis="x"]')?.value || '50';
    const y = controls?.querySelector('[data-crop-axis="y"]')?.value || '50';
    cropPreviewImage.style.objectPosition = `${x}% ${y}%`;
  };
  coverOptions.forEach((option) => {
    option.addEventListener('click', () => {
      coverOptions.forEach((candidate) => {
        const selected = candidate === option;
        candidate.classList.toggle('selected', selected);
        candidate.setAttribute('aria-pressed', String(selected));
      });
      if (selectedCoverId) selectedCoverId.value = option.dataset.photoId;
      if (cropPreviewImage) cropPreviewImage.src = option.dataset.imageUrl;
      updateCropPreview();
    });
  });
  cropFactors.forEach((button) => {
    button.addEventListener('click', () => {
      activeCropFactor = button.dataset.cropFactor;
      cropFactors.forEach((candidate) => candidate.classList.toggle('active', candidate === button));
      document.querySelectorAll('[data-crop-controls]').forEach((controls) => {
        controls.hidden = controls.dataset.cropControls !== activeCropFactor;
      });
      cropPreview?.classList.remove('aspect-desktop', 'aspect-tablet', 'aspect-mobile');
      cropPreview?.classList.add(`aspect-${activeCropFactor}`);
      if (cropPreviewCaption) {
        cropPreviewCaption.textContent = `${activeCropFactor[0].toUpperCase()}${activeCropFactor.slice(1)} preview`;
      }
      updateCropPreview();
    });
  });
  document.querySelectorAll('[data-crop-axis]').forEach((input) => {
    input.addEventListener('input', updateCropPreview);
  });
  document.querySelectorAll('[data-reset-crop]').forEach((button) => {
    button.addEventListener('click', () => {
      const controls = document.querySelector(`[data-crop-controls="${button.dataset.resetCrop}"]`);
      controls?.querySelectorAll('[data-crop-axis]').forEach((input) => {
        input.value = '50';
      });
      if (button.dataset.resetCrop === activeCropFactor) updateCropPreview();
    });
  });
  updateCropPreview();

  const publishedDialog = document.querySelector('[data-gallery-published-dialog]');
  document.querySelector('[data-close-published-dialog]')?.addEventListener('click', () => {
    publishedDialog?.close();
    const url = new URL(window.location.href);
    url.searchParams.delete('published');
    window.history.replaceState(null, '', url);
  });
  if (publishedDialog && new URLSearchParams(window.location.search).get('published') === '1') {
    publishedDialog.showModal();
  }

  const heroMode = document.querySelector('[data-hero-video-mode]');
  const heroPanels = document.querySelectorAll('[data-hero-video-panel]');
  const updateHeroMode = () => {
    if (!heroMode) return;
    heroPanels.forEach((panel) => {
      const active = panel.dataset.heroVideoPanel === heroMode.value;
      panel.hidden = !active;
      panel.querySelectorAll('input, select').forEach((control) => {
        control.disabled = !active;
      });
    });
  };
  heroMode?.addEventListener('change', updateHeroMode);
  updateHeroMode();

  const ctaPhotoInputs = document.querySelectorAll('input[name="cta_photo_ids"]');
  const ctaPhotoError = document.querySelector('[data-cta-photo-error]');
  ctaPhotoInputs.forEach((checkbox) => {
    checkbox.addEventListener('change', () => {
      const selectedCount = document.querySelectorAll('input[name="cta_photo_ids"]:checked').length;
      if (selectedCount > 12) {
        checkbox.checked = false;
        if (ctaPhotoError) ctaPhotoError.textContent = 'Maximum twelve photos.';
        return;
      }
      if (ctaPhotoError) ctaPhotoError.textContent = '';
    });
  });
});
