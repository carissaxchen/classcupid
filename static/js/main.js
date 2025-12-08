// Minimal JavaScript for Class Cupid
// Most interactions are handled via form submissions

document.addEventListener('DOMContentLoaded', function() {
    console.log('Class Cupid loaded');
});

// Toggle all concentration checkboxes
function toggleAllConcentrations() {
    const selectAll = document.getElementById('select-all-concentrations');
    const checkboxes = document.querySelectorAll('.concentration-checkbox');
    
    checkboxes.forEach(checkbox => {
        checkbox.checked = selectAll.checked;
    });
}

// Toggle affiliation sections based on selection
function toggleAffiliationSections() {
    const harvardRadio = document.querySelector('input[name="affiliation"][value="Harvard College"]');
    const otherRadio = document.querySelector('input[name="affiliation"][value="Other"]');
    const harvardSection = document.getElementById('harvard-college-section');
    const otherSection = document.getElementById('other-affiliation-section');
    
    if (harvardRadio && harvardRadio.checked) {
        if (harvardSection) harvardSection.style.display = 'block';
        if (otherSection) otherSection.style.display = 'none';
    } else if (otherRadio && otherRadio.checked) {
        if (harvardSection) harvardSection.style.display = 'none';
        if (otherSection) otherSection.style.display = 'block';
    } else {
        if (harvardSection) harvardSection.style.display = 'none';
        if (otherSection) otherSection.style.display = 'none';
    }
}

// Toggle info tooltip on click
function toggleInfoTooltip(event) {
    event.stopPropagation();
    const tooltip = document.getElementById('divisional-info-tooltip');
    if (tooltip) {
        tooltip.classList.toggle('show');
    }
}

// Close tooltip when clicking outside
document.addEventListener('DOMContentLoaded', function() {
    document.addEventListener('click', function(event) {
        const tooltip = document.getElementById('divisional-info-tooltip');
        const infoIcon = event.target.closest('.info-icon');
        
        if (tooltip && !infoIcon && !tooltip.contains(event.target)) {
            tooltip.classList.remove('show');
        }
    });
    
    // Check if welcome popup was already dismissed
    const welcomePopup = document.getElementById('welcomePopup');
    if (welcomePopup && sessionStorage.getItem('welcomePopupDismissed') === 'true') {
        welcomePopup.classList.add('hidden');
    }
});

// Close welcome popup and remember dismissal
function closeWelcomePopup() {
    const popup = document.getElementById('welcomePopup');
    if (popup) {
        popup.classList.add('hidden');
        sessionStorage.setItem('welcomePopupDismissed', 'true');
    }
}
