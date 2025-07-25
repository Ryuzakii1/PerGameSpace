// static/js/theme_handler.js

/**
 * Applies the stored theme or dark mode preferences to the body.
 */
console.log("theme_handler.js is running!"); // <-- ADD THIS LINE

function applyThemeFromStorage() {
    const savedTheme = localStorage.getItem('theme') || 'modern'; // Default to 'modern'
    const savedDarkMode = localStorage.getItem('dark-mode') === 'true'; // Default to false

    const body = document.body;

    // Remove any existing theme classes
    // Ensure these match your THEMES dict keys in app.py
    body.classList.remove('modern-theme', 'crt-theme', 'arcade-theme');

    // Apply the saved theme class
    // 'modern' can be implicitly the default style, so no explicit class is always necessary for it
    if (savedTheme !== 'modern') { 
        body.classList.add(`${savedTheme}-theme`);
    }

    // Apply dark mode if saved
    if (savedDarkMode) {
        body.classList.add('dark-mode');
    } else {
        body.classList.remove('dark-mode');
    }

    // Update the theme selector on the settings page if it exists
    const themeInput = document.getElementById('selectedTheme');
    if (themeInput) {
        themeInput.value = savedTheme; // Update the hidden input
    }
    const themeOptions = document.querySelectorAll('.theme-option');
    themeOptions.forEach(option => {
        const optionThemeName = option.dataset.themeKey; // Assuming data-theme-key is set in HTML
        if (optionThemeName === savedTheme) {
            option.classList.add('selected');
        } else {
            option.classList.remove('selected');
        }
    });


    // Update the dark mode checkbox on the settings page if it exists
    const darkModeToggle = document.getElementById('dark-mode-toggle');
    if (darkModeToggle) {
        darkModeToggle.checked = savedDarkMode;
    }
}

/**
 * Call the function when the DOM is fully loaded.
 */
document.addEventListener('DOMContentLoaded', applyThemeFromStorage);
