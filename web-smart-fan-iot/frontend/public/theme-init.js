// Preserve legacy first-paint theme without an inline script or token storage.
(function () {
  try {
    if (globalThis.localStorage.getItem('ventora-theme') === 'light') {
      globalThis.document.documentElement.classList.remove('dark');
    }
  } catch {
    // An unavailable preference store does not prevent the application loading.
  }
})();
