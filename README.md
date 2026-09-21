# Gerty - <small>[LNbits](https://github.com/lnbits/lnbits) extension</small>

<small>For more about LNBits extension check [this tutorial](https://github.com/lnbits/lnbits/wiki/LNbits-Extensions)</small>

### Your Desktop Bitcoin Assistant

Gerty, a Bitcoin Assistant controlled from your LNbits wallet.

This extension can be used as a standalone to display a dashboard of Bitcoin information or you
can build / buy the Gerty hardware to display the information on an eink display.

Build your own Gerty or buy a [pre-assembled Gerty from the LNbits shop](https://shop.lnbits.com/product/gerty-a-bitcoin-assistant).

![Gerty](https://github.com/lnbits/gerty/raw/main/img/gerty-satoshi2.jpg)

[Find out more about the hardware Gerty here](https://github.com/lnbits/gerty/)

What does Gerty show?

- Current block height
- A list of Satoshi's quotes from bitcointalk.org
- Your LNbits wallet balance
- An onchain dashboard
- A lightning dashboard
- A mining dashboard
- Current Bitcoin price in your preferred currency
- Website status check

## Usage

- Create an LNbits wallet and enable the Gerty extension
- Create a new Gerty and configure your Gerty options
- Click the smiley face icon next to your Gerty to open your Gerty dashboard.

## Development

Use Python 3.12, uv, and Node.js to install the development dependencies:

```sh
uv sync --locked --all-extras --dev
npm ci
make check
make test
```

After changing Python dependencies in `pyproject.toml`, run `uv lock` and commit
the updated `uv.lock` alongside it.

## Releases

Pushing a version tag such as `v1.0.2` runs the release workflow. It creates a
GitHub release with generated release notes, then updates Gerty in
`lnbits/lnbits-extensions` and opens a pull request there.

Before releasing, configure the `EXT_GITHUB` repository Actions secret with a
token that can read and write contents and create pull requests in
`lnbits/lnbits-extensions`. The release itself uses the automatic `GITHUB_TOKEN`.
The workflow can be rerun to resume an existing release and update pull request.

## Image display API

Choose **Device type and screen resolution** in Gerty settings:

- **Epaper 800 x 480 (Seeed TRMNL 7.5 inch OG DIY Kit)**: grayscale PNGs for
  the monochrome Seeed kit. Gerty hardware converts these to black/white using
  ordered dithering. Use firmware environment `seeed-TRMNL-7_5`; the XIAO C3
  panel and reTerminal are different boards. The block explorer chart keeps its
  proportions with white margins; other e-paper screens render at native size.

- **Epaper 960 x 540** (default): 16-level grayscale PNG.
- **Colour 480 x 320**: native RGB PNG layouts for the Guition JC3248W535.
- **Colour 240 x 240**: native RGB PNG layouts for the ESP32-C6 1.3 inch LCD, with a compact Block explorer layout.
- **Colour 480 x 272**: native RGB PNG layouts for the Guition JC4827W543.

Colour displays offer **Cypherpunk**, **Bright day**, and **Orange Pill**.
Their named colour-role dictionaries live in `display_settings.py`.
The selection is stored inside the existing JSON `display_preferences` field:

```json
{
  "onchain_block_height": true,
  "block_explorer": true,
  "_display": {
    "profile": "colour_480x320",
    "theme": "Orange Pill"
  }
}
```

The page API returns `device_type` (`epaper_960x540`, `epaper_800x480`, `colour_480x320`, `colour_480x272`, or `colour_240x240`),
`width`, `height`, and `colour_theme` (null for e-paper). Its `image_url` serves
the selected device's image. Display settings do not count as enabled pages.
Changing profile or theme invalidates the cached snapshot. Old preferences
without `_display` continue to use e-paper. No database migration is needed.

`GET /gerty/api/v1/gerty/pages/{id}` returns page zero. Append `/{page}`
for another zero-based enabled page. Requests outside the enabled page range
return the first enabled page, with its actual `page`, `screen_name`, and
`next_page`, so devices recover after screens are disabled. If no screens are
enabled, the API returns 422. The old text-area response is replaced by:

```json
{
  "schema_version": 1,
  "image_url": "https://your-lnbits/gerty/api/v1/gerty/images/REVISION.png",
  "image_revision": "REVISION",
  "refresh_seconds": 300,
  "page": 0,
  "page_count": 8,
  "next_page": 1
}
```

Download `image_url`, display the PNG, sleep for `refresh_seconds`, then request
`next_page`. On HTTP 410 from an image URL, fetch the manifest again. On data or
network errors, retain the current display and retry. URLs use the request's
origin: configure LNbits/proxy forwarding correctly and use a hostname the device
can reach (not localhost). Treat device URLs as private bearer links because
images may contain wallet balances.

E-paper images are 960 × 540 landscape, non-interlaced 8-bit grayscale PNGs quantized to
16 levels. The renderer uses Pixel Operator and Pixel Operator Bold from
`fonts/PixelOperator/`, with the bundled CC0 licence in `LICENSE.txt`.
The bottom-right timestamp is snapshot generation time in the configured UTC
offset, not confirmation of a physical panel update. No face or device name is
rendered. The browser display previews these same images.

Generated PNGs exist only in process memory: at most 32 MiB, with snapshots
expiring after 24 hours or earlier under memory pressure. Fresh snapshots are
reused for the refresh interval. Configuration changes invalidate reuse.
Restarting LNbits clears the cache. Run this extension in a single worker;
multiple workers would require a shared cache. No persistent image storage or
background rendering task is used.

The current overnight sleep behaviour is retained (eight hours for requests
between 22:00 and midnight in the configured offset). Firmware must honour that
interval and `next_page`. Positive configured intervals are returned without
a 30–300 second clamp; the updated gerty-v3 firmware honours them after reflashing.
For server-quantized images, disable
firmware dithering. Future display profiles can separate dimensions and palette
from the shared screen data. Both display profiles use the same live data sources.

The Block explorer toggle adds a live `block_explorer` page. It uses the same
LNbits services as `/blockexplorer/api/v1/tip`, `/fees`, and `/blocks`, without
making HTTP requests back to the server or forwarding credentials. Block explorer
must be enabled in LNbits settings. Its image shows confirmation-target fees,
recent blocks, block intervals, and mempool virtual size by fee-rate range.
Fee estimates are converted from BTC/kB to sat/vB; chart sizes use decimal MvB.
Unavailable fee estimates and missing interval history are shown explicitly.
The normal page cache and refresh interval apply; no static example data is used.
The standalone `GET /gerty/api/v1/gerty/block-explorer` also renders live data
and requires an LNbits invoice/read key. Hardware should use the Gerty page URL.

### Wallet history

Enable **Wallet history** and add one wallet invoice key. The screen shows its
daily closing balance in sats for the last 30 UTC days (today shows the latest
balance). Inactive days carry the balance forward. LNbits supplies the balance history, including
outgoing fees. Colour displays use rainbow equaliser bars with a fading
reflection; e-paper uses a high-contrast grayscale version. Dates run along the
X axis and balance is labelled on the Y axis.

### Gallery

Enable **Gallery** in Gerty settings to upload JPEG or PNG photos. Gallery occupies one page in the rotation. A random photo is selected whenever
that page refreshes, using the configured refresh time. Repeated requests within
that interval show the same cached photo; random selections may repeat. Photos are center-cropped to fill the
selected display; e-paper displays use 16-level grayscale.

Large photos are resized in the browser before upload: the longest side is at
most 1024 pixels, with no upscaling, and each file is at most 1.5 MB (or the
LNbits Max Asset Size, if smaller). PNGs are
preserved when they fit; otherwise photos are compressed as JPEGs. Only the
resized copy is stored.

Uploads use LNbits account asset storage and its configured file size, type and
count limits (requires an LNbits version with `/api/v1/assets` support). Uploaded photos
remain private account assets, but rendered photos can be viewed by anyone with
the Gerty display link. Deleting a photo from Gallery immediately deletes its stored copy from LNbits files.
Deleting a Gerty does not delete its uploaded files.

Gallery follows LNbits **Settings > Assets**. The upload counter includes all
files in the account, not just Gallery photos. Super admins and users exempted
by LNbits have no asset-count cap; the file-size limit still applies. Setting
**Max Assets per User** to zero disables Gallery and its uploads for everyone,
including super admins, and skips existing Gallery pages in the display rotation.

### Sleep schedule and timezone

Select a timezone in the device settings. Enable **Enable Sleep Time** to reveal
**Sleep time** and **Wake time**. The schedule runs daily in that timezone and
follows daylight-saving changes. Sleep and wake times must differ. Existing
configurations keep their fixed UTC offset until a timezone is saved; scheduled
sleep is disabled by default.

During sleep, all device-specific data endpoints, including cached PNG URLs,
return `application/json` with only `schema_version`, `sleep_mode: true`,
`sleep_seconds` (seconds until wake), and `wake_at` (ISO 8601 with offset).
Firmware must check the response content type before decoding an image: all
devices should enter deep sleep for `sleep_seconds`, then request their page
again. Awake page manifests include `sleep_mode: false`.

The browser preview ignores sleep schedules. It requests page manifests with
`?preview=true`; their image URLs also include `?preview=true` so previews remain
visible during sleep. Normal device requests continue to respect the schedule.

The shared quote and block-explorer endpoints accept `?gerty_id=...` to apply a
device's schedule. Account, configuration, and gallery management endpoints remain
available during sleep. Schedule settings are stored in `display_preferences`
as `_schedule`, with `timezone` (IANA name), `enabled`, `sleep_time`, and `wake_time`.

### US national debt

Enable **US national debt** in Gerty settings to add a neutral debt dashboard to
its normal rotation. All five display profiles are supported. No API key or additional configuration is required.

The full dollar headline, recent Treasury updates and 30-day change come from
[Debt to the Penny](https://fiscaldata.treasury.gov/datasets/debt-to-the-penny/).
The headline is a reported observation rounded to whole dollars, not a projected
live counter. Each recent row compares its total with the preceding reporting
day. The 30-day baseline is the last observation on or before 30 calendar days
before the latest observation. Decreases keep their negative sign.

Colour displays use the reference's black background, green headline and red
area chart; e-paper uses a high-contrast grayscale layout. The table shows up to
five recent observations, reduced to three or two on shorter or smaller screens.
The 3.5-inch 480 × 320 layout uses at least 18-pixel supporting text, higher
contrast labels and two full-width update rows for readability.
There is no per-person share. The nominal debt chart starts in 1971 and marks
August 1971's suspension of dollar-gold convertibility. Historical quarterly
figures come from [FRED GFDEBTN](https://fred.stlouisfed.org/series/GFDEBTN).
Debt/GDP remains a numerical statistic from
[FRED GFDEGDQ188S](https://fred.stlouisfed.org/series/GFDEGDQ188S). The latest
quarters are labelled separately from the daily headline (the smallest display
omits the chart's end-quarter label). Total debt includes both publicly held and
intragovernmental debt. This screen uses its own reference palette rather than
the selected colour theme.

Source data is shared across devices in memory: Treasury refreshes hourly and
FRED daily. Failed refreshes retain the last successful observations and show
“Refresh failed”; missing sources show “Unavailable”. Retries are limited to
once per five minutes. Restarting LNbits clears this source cache. Observation
dates remain visible, including when a source has not published newer data.
