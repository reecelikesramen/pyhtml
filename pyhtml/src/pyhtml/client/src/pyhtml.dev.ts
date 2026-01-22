/**
 * PyHTML Dev Bundle Entry Point
 * Includes all core features plus development tools:
 * - Connection status overlay
 * - Error trace with source loading for DevTools
 * - Enhanced console output
 */
import { PyHTMLDevApp } from './dev/dev-app';

// Re-export core
export * from './core';

// Export dev-specific
export { PyHTMLDevApp } from './dev/dev-app';
export { StatusOverlay } from './dev/status-overlay';
export { ErrorTraceHandler } from './dev/error-trace';

// Auto-init with dev app
const app = new PyHTMLDevApp();

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => app.init());
} else {
    app.init();
}

export { app };
