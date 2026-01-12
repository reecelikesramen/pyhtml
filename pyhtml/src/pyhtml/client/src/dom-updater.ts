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
            morphdom(document.documentElement, newHtml);
        } else {
            // Fallback: full document replacement
            document.open();
            document.write(newHtml);
            document.close();
        }
    }
}
