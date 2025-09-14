/**
 * FactorialBot Authorization Server - Common JavaScript Functionality
 */

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    initializeFormValidation();
    initializeAlerts();
    initializeClipboard();
    initializeTooltips();
});

/**
 * Form validation helpers
 */
function initializeFormValidation() {
    // Add Bootstrap-like validation classes
    const forms = document.querySelectorAll('form');
    forms.forEach(form => {
        form.addEventListener('submit', function(e) {
            if (!form.checkValidity()) {
                e.preventDefault();
                e.stopPropagation();
            }
            form.classList.add('was-validated');
        });
    });

    // Real-time validation for specific inputs
    const inputs = document.querySelectorAll('input[required]');
    inputs.forEach(input => {
        input.addEventListener('blur', function() {
            validateInput(this);
        });
    });
}

/**
 * Validate individual input field
 */
function validateInput(input) {
    const value = input.value.trim();
    const isValid = input.checkValidity();
    
    // Remove existing validation classes
    input.classList.remove('is-valid', 'is-invalid');
    
    // Add appropriate class
    if (value.length > 0) {
        input.classList.add(isValid ? 'is-valid' : 'is-invalid');
    }
    
    // Special validation for email
    if (input.type === 'email' && value.length > 0) {
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        const isValidEmail = emailRegex.test(value);
        input.classList.toggle('is-valid', isValidEmail);
        input.classList.toggle('is-invalid', !isValidEmail);
    }
    
    // Special validation for password confirmation
    if (input.name === 'passwordConfirmation') {
        const passwordField = document.querySelector('input[name="password"]');
        if (passwordField) {
            const passwordsMatch = input.value === passwordField.value;
            input.classList.toggle('is-valid', passwordsMatch && value.length > 0);
            input.classList.toggle('is-invalid', !passwordsMatch && value.length > 0);
        }
    }
}

/**
 * Auto-dismiss alerts after a certain time
 */
function initializeAlerts() {
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        // Auto-dismiss success messages after 5 seconds
        if (alert.classList.contains('alert-success')) {
            setTimeout(() => {
                fadeOut(alert);
            }, 5000);
        }
        
        // Add close button if not present
        if (!alert.querySelector('.alert-close')) {
            const closeBtn = document.createElement('button');
            closeBtn.innerHTML = '&times;';
            closeBtn.className = 'alert-close';
            closeBtn.style.cssText = `
                position: absolute;
                top: 0.5rem;
                right: 0.75rem;
                background: none;
                border: none;
                font-size: 1.25rem;
                cursor: pointer;
                padding: 0;
                line-height: 1;
                opacity: 0.7;
            `;
            closeBtn.addEventListener('click', () => fadeOut(alert));
            
            alert.style.position = 'relative';
            alert.appendChild(closeBtn);
        }
    });
}

/**
 * Clipboard functionality for code elements
 */
function initializeClipboard() {
    // Add click-to-copy functionality for code elements
    const codeElements = document.querySelectorAll('code, .credential-value');
    codeElements.forEach(element => {
        if (!element.classList.contains('no-copy')) {
            element.style.cursor = 'pointer';
            element.title = 'Click to copy';
            
            element.addEventListener('click', function() {
                copyToClipboard(this.textContent.trim());
                showCopyFeedback(this);
            });
        }
    });
}

/**
 * Copy text to clipboard
 */
function copyToClipboard(text) {
    if (navigator.clipboard && window.isSecureContext) {
        return navigator.clipboard.writeText(text);
    } else {
        // Fallback for older browsers
        const textArea = document.createElement('textarea');
        textArea.value = text;
        textArea.style.position = 'absolute';
        textArea.style.left = '-999999px';
        document.body.prepend(textArea);
        textArea.select();
        
        try {
            document.execCommand('copy');
        } catch (error) {
            console.error('Failed to copy text: ', error);
        } finally {
            textArea.remove();
        }
    }
}

/**
 * Show visual feedback when text is copied
 */
function showCopyFeedback(element) {
    const originalBg = element.style.backgroundColor;
    const originalTitle = element.title;
    
    element.style.backgroundColor = '#d4edda';
    element.style.transition = 'background-color 0.2s ease';
    element.title = 'Copied!';
    
    setTimeout(() => {
        element.style.backgroundColor = originalBg;
        element.title = originalTitle;
    }, 1500);
}

/**
 * Initialize tooltips (simple implementation)
 */
function initializeTooltips() {
    const elementsWithTooltip = document.querySelectorAll('[title]');
    elementsWithTooltip.forEach(element => {
        let tooltip;
        
        element.addEventListener('mouseenter', function(e) {
            const title = e.target.getAttribute('title');
            if (!title || title === 'Click to copy' || title === 'Copied!') return;
            
            // Create tooltip
            tooltip = document.createElement('div');
            tooltip.textContent = title;
            tooltip.style.cssText = `
                position: absolute;
                background: rgba(0, 0, 0, 0.8);
                color: white;
                padding: 0.5rem;
                border-radius: 4px;
                font-size: 0.875rem;
                white-space: nowrap;
                z-index: 1000;
                pointer-events: none;
            `;
            
            // Position tooltip
            document.body.appendChild(tooltip);
            const rect = e.target.getBoundingClientRect();
            tooltip.style.left = (rect.left + rect.width / 2 - tooltip.offsetWidth / 2) + 'px';
            tooltip.style.top = (rect.top - tooltip.offsetHeight - 5) + 'px';
            
            // Remove title to prevent default tooltip
            e.target.setAttribute('data-original-title', title);
            e.target.removeAttribute('title');
        });
        
        element.addEventListener('mouseleave', function(e) {
            if (tooltip) {
                tooltip.remove();
                tooltip = null;
            }
            
            // Restore title
            const originalTitle = e.target.getAttribute('data-original-title');
            if (originalTitle) {
                e.target.setAttribute('title', originalTitle);
                e.target.removeAttribute('data-original-title');
            }
        });
    });
}

/**
 * Fade out element
 */
function fadeOut(element, duration = 500) {
    element.style.transition = `opacity ${duration}ms ease`;
    element.style.opacity = '0';
    
    setTimeout(() => {
        element.style.display = 'none';
    }, duration);
}

/**
 * Show loading state for buttons
 */
function showButtonLoading(button, text = null) {
    button.classList.add('btn-loading');
    button.disabled = true;
    
    if (text) {
        button.setAttribute('data-original-text', button.textContent);
        button.textContent = text;
    }
}

/**
 * Hide loading state for buttons
 */
function hideButtonLoading(button) {
    button.classList.remove('btn-loading');
    button.disabled = false;
    
    const originalText = button.getAttribute('data-original-text');
    if (originalText) {
        button.textContent = originalText;
        button.removeAttribute('data-original-text');
    }
}

/**
 * Format date for display
 */
function formatDate(dateString, options = {}) {
    const date = new Date(dateString);
    const defaultOptions = {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    };
    
    return date.toLocaleDateString('en-US', { ...defaultOptions, ...options });
}

/**
 * Debounce function for search inputs
 */
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Show confirmation dialog
 */
function confirmAction(message, callback) {
    if (confirm(message)) {
        callback();
    }
}

/**
 * Utility functions available globally
 */
window.AuthUtils = {
    validateInput,
    copyToClipboard,
    showCopyFeedback,
    showButtonLoading,
    hideButtonLoading,
    formatDate,
    debounce,
    confirmAction,
    fadeOut
};