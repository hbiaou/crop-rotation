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
});
