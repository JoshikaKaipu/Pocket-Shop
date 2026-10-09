Link to the working app: https://joshikakaipu.github.io/Pocket-Shop/

Pocket Shop
A lightweight, crash-proof tool for tracking art print sales, stock levels, profit, best sellers, and pricing suggestions.

Choose Your Version

Pocket Shop comes in three versions that all share the exact same core logic:

| Version | Folder / File | Requirements | Where It Runs |


1. | Web Page | index.html | None | Any browser (hosted free via GitHub Pages) |
2. | Terminal | terminal/print_ledger.py | Python 3 | Your computer's command line |
3. | Flask App | flask_app/app.py | Python 3 + Flask | Local web server (browser or local Wi-Fi phone) |

How to Run It

Terminal Version
Run this command in your terminal:
python3 terminal/print_ledger.py

Flask Web App
 * Open your terminal and navigate to the folder:
   cd flask_app

 * Install the required dependencies:
   pip install -r requirements.txt

 * Start the application:
   python3 app.py

(Open the address it outputs in your browser, or use the phone address on any device connected to the same Wi-Fi network.)

Flask API Reference
Python handles all calculations on the backend, serving data directly to the interface.
 * GET /api/state — Returns prints, totals, best sellers, pricing suggestions, and next steps.
 * POST /api/prints — Adds a new print design.
 * POST /api/sell/<id> — Records a single sale.
 * POST /api/undo — Removes the most recently logged sale.
 * POST /api/prints/<id>/restock — Adds stock (automatically recalculates and blends the print cost).
 * POST /api/prints/<id>/price — Updates the price (historical sales retain their original price).
 * DELETE /api/prints/<id> — Removes a print and its associated sales history.
 * POST /api/reset — Clears all data.

Core Architecture Highlights
 * Crash-Proof Storage: Data is saved to print_data.json by writing to a temporary file first and swapping it in instantly, preventing file corruption if the app crashes.
 * Zero Sync Drift: Stock is never manually stored as a static number. Instead, it is dynamically computed as total prints made minus total sales logged, ensuring your undo button never desynchronizes the inventory.
 * Thread Safety: A built-in thread lock prevents rapid consecutive requests from colliding or corrupting the data state.

Pricing Rule of Thumb (Customizable rules for automated suggestions):
 * Sold Out: Raise price by 15%
 * 60%+ Sold: Raise price by 10%
 * Under 25% Sold (after 5+ total sales): Lower price by 10%
 * Safety Floor: Prices will never drop below 1.5x the production cost.
