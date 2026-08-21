(function() {
    // Inactivity timeout setting: 20 minutes (in milliseconds)
    const INACTIVITY_TIMEOUT = 20 * 60 * 1000; 
    let inactivityTimer;

    function resetInactivityTimer() {
        clearTimeout(inactivityTimer);
        inactivityTimer = setTimeout(function() {
            window.location.href = window.LOGOUT_URL || '/logout';
        }, INACTIVITY_TIMEOUT);
    }

    const activityEvents = ['mousemove', 'keydown', 'click', 'scroll', 'touchstart'];
    activityEvents.forEach(function(event) {
        window.addEventListener(event, resetInactivityTimer, false);
    });

    resetInactivityTimer();
})();