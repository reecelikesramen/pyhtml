/**
 * DOM Updater using morphdom for efficient DOM diffing.
 */
import morphdom from 'morphdom';

export class DOMUpdater {
    /**
     * Update the DOM with new HTML content.
     */
    update(newHtml: string): void {
        if (morphdom) {
            morphdom(document.documentElement, newHtml, {
                onBeforeElUpdated: (fromEl, toEl) => {
                    if (fromEl === document.activeElement && (fromEl.tagName === 'INPUT' || fromEl.tagName === 'TEXTAREA')) {
                        let s = toEl.getAttribute('value') || '';
                        let c = (fromEl as any).value || '';
                        // Relaxed check: if client state is just "ahead" or "behind" (backspace) of server state,
                        // keep the client state. Only overwrite if completely different.
                        if (c.startsWith(s) || s.startsWith(c)) {
                            toEl.setAttribute('value', c);
                            (toEl as any).value = c;
                            if (fromEl.tagName === 'TEXTAREA') toEl.textContent = c;
                        }
                    }
                    return true;
                }
            });
        } else {
            // Fallback: full document replacement
            document.open();
            document.write(newHtml);
            document.close();
        }
    }
}
