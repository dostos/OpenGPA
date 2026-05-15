# Dashboard fixture

To verify `dashboard/index.html` without rebuilding from `/data3`,
symlink this file to `dashboard/index.json`:

    ln -sf $(pwd)/tests/fixtures/dashboard/sample-index.json dashboard/index.json

Then open `dashboard/index.html` in a browser.
