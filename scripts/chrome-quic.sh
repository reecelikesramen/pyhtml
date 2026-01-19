#!/bin/bash
# Launch Chrome with QUIC enabled for PyHTML local development

PORT="${1:-3000}"

# Warn if Chrome is running
if pgrep -f "Google Chrome" >/dev/null; then
    echo "⚠️  WARNING: Google Chrome is already running."
    echo "   For these flags to take effect, you must QUIT Chrome completely (Cmd+Q)."
    echo "   Closing the window is not enough."
    echo ""
    read -p "Press Enter to continue anyway (or Ctrl+C to stop and Quit Chrome)..."
fi

echo "Launching Chrome with QUIC enabled for localhost:$PORT"
echo "Logs will appear in the specific terminal window."
echo ""

# Check for Chrome installations
CHROME_PATHS=(
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    "/Applications/Google Chrome Canary.app/Contents/MacOS/Google Chrome Canary"
)

FLAGS=(
    "--origin-to-force-quic-on=localhost:$PORT"
    "--origin-to-force-quic-on=127.0.0.1:$PORT"
    "--ignore-certificate-errors"
)

for CHROME in "${CHROME_PATHS[@]}"; do
    if [ -f "$CHROME" ]; then
        echo "Found Chrome at: $CHROME"
        exec "$CHROME" "${FLAGS[@]}" "https://localhost:$PORT"
    fi
done

echo "Chrome not found in standard locations."
