/**
 * app.js — Interactive UI logic for the crop rotation application.
 *
 * Currently provides:
 * - Mobile navigation toggle
 * - Flash message auto-dismiss
 * - Confirm dialogs
 *
 * Future: slider controls, live validation, drag-and-drop rotation editor.
 */

document.addEventListener('DOMContentLoaded', function () {
    // --- Mobile Navigation Toggle ---
    const navToggle = document.getElementById('navToggle');
    const navLinks = document.getElementById('navLinks');

    if (navToggle && navLinks) {
        navToggle.addEventListener('click', function () {
            navLinks.classList.toggle('nav-open');
            navToggle.classList.toggle('nav-toggle-active');
        });
    }

    // --- Flash Message Auto-Dismiss ---
    const flashMessages = document.querySelectorAll('.flash');
    flashMessages.forEach(function (flash) {
        setTimeout(function () {
            flash.style.opacity = '0';
            flash.style.transform = 'translateY(-10px)';
            setTimeout(function () {
                flash.remove();
            }, 300);
        }, 5000);
    });

    // --- Confirm Dialogs ---
    document.querySelectorAll('[data-confirm]').forEach(function (el) {
        el.addEventListener('click', function (e) {
            const message = this.getAttribute('data-confirm');
            if (!confirm(message)) {
                e.preventDefault();
            }
        });
    });


    // =====================================================
    // Bootstrap Page — Interactive Logic
    // =====================================================
    const bootstrapPage = document.querySelector('.bootstrap-page');
    if (bootstrapPage) {
        const gardenId = bootstrapPage.dataset.gardenId;
        const totalBeds = parseInt(bootstrapPage.dataset.total, 10);
        const cropsByCategory = window.CROPS_BY_CATEGORY || {};
        const i18nBs = window.BOOTSTRAP_I18N || {};

        // --- Progress Counter ---
        function updateProgress() {
            const filled = document.querySelectorAll('.category-select').length -
                document.querySelectorAll('.category-select option[value=""]:checked').length;
            let count = 0;
            document.querySelectorAll('.category-select').forEach(function (sel) {
                if (sel.value) count++;
            });
            const pct = totalBeds > 0 ? Math.round((count / totalBeds) * 100) : 0;
            const progressText = document.getElementById('progressText');
            const progressBar = document.getElementById('progressBar');
            if (progressText) progressText.textContent = count + '/' + totalBeds + ' ' + i18nBs.progress_label;
            if (progressBar) progressBar.style.width = pct + '%';
        }

        // --- Category → Crop Filtering ---
        function populateCropSelect(cropSelect, category) {
            const currentVal = cropSelect.value;
            cropSelect.innerHTML = '<option value="">' + i18nBs.select_crop + '</option>';

            if (category && cropsByCategory[category]) {
                cropsByCategory[category].forEach(function (crop) {
                    const opt = document.createElement('option');
                    opt.value = crop.id;
                    opt.textContent = crop.name;
                    cropSelect.appendChild(opt);
                });
            }

            // Restore if still valid
            if (currentVal) {
                const exists = Array.from(cropSelect.options).some(function (o) { return o.value === currentVal; });
                if (exists) cropSelect.value = currentVal;
            }
        }

        document.querySelectorAll('.category-select').forEach(function (sel) {
            sel.addEventListener('change', function () {
                const subbedId = this.dataset.subbed;
                const cropSel = document.querySelector('.crop-select[data-subbed="' + subbedId + '"]');
                if (cropSel) populateCropSelect(cropSel, this.value);

                // Update card border color
                const entry = this.closest('.sub-bed-entry');
                if (entry) {
                    entry.classList.remove('has-error');
                    // Remove old cat classes
                    entry.className = entry.className.replace(/entry-cat-\w+/g, '');
                    if (this.value) entry.classList.add('entry-cat-' + this.value.toLowerCase());
                }

                updateProgress();
            });
        });

        // --- Quick Fill ---
        document.querySelectorAll('[data-quick-fill]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                const cat = this.dataset.quickFill;
                document.querySelectorAll('.category-select').forEach(function (sel) {
                    sel.value = cat;
                    const subbedId = sel.dataset.subbed;
                    const cropSel = document.querySelector('.crop-select[data-subbed="' + subbedId + '"]');
                    if (cropSel) populateCropSelect(cropSel, cat);

                    const entry = sel.closest('.sub-bed-entry');
                    if (entry) {
                        entry.classList.remove('has-error');
                        entry.className = entry.className.replace(/entry-cat-\w+/g, '');
                        entry.classList.add('entry-cat-' + cat.toLowerCase());
                    }
                });
                updateProgress();
            });
        });

        // --- Auto-Distribute ---
        const autoBtn = document.getElementById('autoDistribute');
        if (autoBtn) {
            autoBtn.addEventListener('click', function () {
                autoBtn.disabled = true;
                autoBtn.textContent = '⏳ ...';

                fetch('/bootstrap/' + gardenId + '/auto-distribute', { method: 'POST' })
                    .then(function (r) { return r.json(); })
                    .then(function (data) {
                        Object.keys(data).forEach(function (subbedId) {
                            const info = data[subbedId];
                            const catSel = document.querySelector('.category-select[data-subbed="' + subbedId + '"]');
                            const cropSel = document.querySelector('.crop-select[data-subbed="' + subbedId + '"]');

                            if (catSel) {
                                catSel.value = info.category;
                                if (cropSel) populateCropSelect(cropSel, info.category);

                                const entry = catSel.closest('.sub-bed-entry');
                                if (entry) {
                                    entry.classList.remove('has-error');
                                    entry.className = entry.className.replace(/entry-cat-\w+/g, '');
                                    entry.classList.add('entry-cat-' + info.category.toLowerCase());
                                }
                            }
                            if (cropSel && info.crop_id) {
                                cropSel.value = info.crop_id;
                            }
                        });
                        updateProgress();
                    })
                    .catch(function (err) { console.error('Auto-distribute error:', err); })
                    .finally(function () {
                        autoBtn.disabled = false;
                        autoBtn.innerHTML = '<span class="btn-icon">🎲</span> ' + (i18nBs.auto_distribute || 'Répartition automatique');
                    });
            });
        }

        // --- Collapse / Expand ---
        document.querySelectorAll('[data-toggle-bed]').forEach(function (header) {
            header.addEventListener('click', function () {
                const bedNum = this.dataset.toggleBed;
                const body = document.getElementById('bed-body-' + bedNum);
                const toggle = this.querySelector('.bed-toggle');
                if (body) {
                    const isOpen = !body.classList.contains('collapsed');
                    body.classList.toggle('collapsed');
                    if (toggle) toggle.textContent = isOpen ? '▸' : '▾';
                }
            });
        });

        var expandAllBtn = document.getElementById('expandAll');
        var collapseAllBtn = document.getElementById('collapseAll');

        if (expandAllBtn) {
            expandAllBtn.addEventListener('click', function () {
                document.querySelectorAll('.bed-card-body').forEach(function (b) { b.classList.remove('collapsed'); });
                document.querySelectorAll('.bed-toggle').forEach(function (t) { t.textContent = '▾'; });
            });
        }
        if (collapseAllBtn) {
            collapseAllBtn.addEventListener('click', function () {
                document.querySelectorAll('.bed-card-body').forEach(function (b) { b.classList.add('collapsed'); });
                document.querySelectorAll('.bed-toggle').forEach(function (t) { t.textContent = '▸'; });
            });
        }

        // --- Form Validation ---
        var form = document.getElementById('bootstrapForm');
        if (form) {
            form.addEventListener('submit', function (e) {
                var hasErrors = false;
                var firstError = null;

                document.querySelectorAll('.sub-bed-entry').forEach(function (entry) {
                    entry.classList.remove('has-error');
                });

                document.querySelectorAll('.category-select').forEach(function (sel) {
                    if (!sel.value) {
                        hasErrors = true;
                        var entry = sel.closest('.sub-bed-entry');
                        if (entry) {
                            entry.classList.add('has-error');
                            // Make sure its bed card is expanded
                            var bedBody = entry.closest('.bed-card-body');
                            if (bedBody) bedBody.classList.remove('collapsed');
                            if (!firstError) firstError = entry;
                        }
                    }
                });

                if (hasErrors) {
                    e.preventDefault();
                    if (firstError) {
                        firstError.scrollIntoView({ behavior: 'smooth', block: 'center' });
                    }
                    // Show validation flash
                    var existing = document.querySelector('.bootstrap-validation-error');
                    if (!existing) {
                        var flash = document.createElement('div');
                        flash.className = 'flash flash-error bootstrap-validation-error';
                        flash.textContent = '⚠️ ' + i18nBs.validation_error;
                        var toolbar = document.querySelector('.bootstrap-toolbar');
                        if (toolbar) toolbar.insertAdjacentElement('afterend', flash);
                        setTimeout(function () { flash.remove(); }, 5000);
                    }
                }
            });
        }

        // Initial progress update
        updateProgress();
    }


    // ========================================
    // Map Page — Override Modal
    // ========================================

    var mapTable = document.getElementById('mapTable');
    if (mapTable) {
        var modal = document.getElementById('overrideModal');
        var modalPlanId = document.getElementById('modalPlanId');
        var modalBedInfo = document.getElementById('modalBedInfo');
        var modalPlanned = document.getElementById('modalPlanned');
        var modalCategory = document.getElementById('modalCategory');
        var modalCrop = document.getElementById('modalCrop');
        var modalNotes = document.getElementById('modalNotes');
        var modalCancel = document.getElementById('modalCancel');

        // Click handler on map cells
        mapTable.addEventListener('click', function (e) {
            var cell = e.target.closest('.map-cell');
            if (!cell) return;

            var planId = cell.dataset.planId;
            var bed = cell.dataset.bed;
            var pos = cell.dataset.position;
            var plannedCat = cell.dataset.plannedCategory;
            var plannedCrop = cell.dataset.plannedCrop;
            var actualCat = cell.dataset.actualCategory;
            var actualCropId = cell.dataset.actualCropId;
            var notes = cell.dataset.notes;

            // Populate modal
            modalPlanId.value = planId;
            modalBedInfo.textContent = 'P' + bed + '-S' + pos;
            modalPlanned.value = plannedCrop || plannedCat || '—';
            modalNotes.value = notes || '';

            // Set category dropdown
            modalCategory.value = actualCat || plannedCat || '';
            updateCropDropdown(modalCategory.value, actualCropId);

            // Show modal
            modal.style.display = 'flex';
        });

        // Category change → update crop dropdown
        modalCategory.addEventListener('change', function () {
            updateCropDropdown(this.value, '');
        });

        function updateCropDropdown(category, selectedCropId) {
            modalCrop.innerHTML = '<option value="">— Choisir —</option>';
            var crops = window.cropsByCategory[category] || [];
            crops.forEach(function (c) {
                var opt = document.createElement('option');
                opt.value = c.id;
                opt.textContent = c.name;
                if (String(c.id) === String(selectedCropId)) {
                    opt.selected = true;
                }
                modalCrop.appendChild(opt);
            });
        }

        // Close modal
        function closeModal() {
            modal.style.display = 'none';
        }

        modalCancel.addEventListener('click', closeModal);

        // Close on overlay click
        modal.addEventListener('click', function (e) {
            if (e.target === modal) closeModal();
        });

        // Close on Escape key
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && modal.style.display === 'flex') {
                closeModal();
            }
        });
    }
});
