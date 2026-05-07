// Global functions for the pharmacy system

// Format number with commas
function numberWithCommas(x) {
    return x.toString().replace(/\B(?=(\d{3})+(?!\d))/g, ",");
}

// Show loading spinner
function showLoading() {
    $('#loadingSpinner').show();
}

// Hide loading spinner
function hideLoading() {
    $('#loadingSpinner').hide();
}

// Show notification
function showNotification(message, type = 'success') {
    const alertDiv = `
        <div class="alert alert-${type} alert-dismissible fade show" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `;
    $('#notificationArea').html(alertDiv);
    
    // Auto dismiss after 5 seconds
    setTimeout(() => {
        $('.alert').alert('close');
    }, 5000);
}

// Confirm action
function confirmAction(message, callback) {
    if (confirm(message)) {
        callback();
    }
}

// Format date
function formatDate(dateString) {
    const date = new Date(dateString);
    return date.toLocaleDateString();
}

// Get status badge class
function getStatusBadge(status) {
    switch(status) {
        case 'expired': return 'bg-danger';
        case 'expiring_soon': return 'bg-warning text-dark';
        case 'low_stock': return 'bg-success';
        default: return 'bg-secondary';
    }
}