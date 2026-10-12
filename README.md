# Gather

**Find products that fit your needs, and understand the tradeoffs behind your choice.**

Gather is an interactive shopping tool for consumers. Add products you are considering, describe your needs, and compare prices, specifications, user experiences, and uncertainties to find the best fit among your options.

Few products meet every expectation. Gather separates preferences from non-negotiable requirements, so a worthwhile option is not overlooked simply because one specification falls short.

## What you can do

- **Compare candidate products:** Choose built-in examples, paste specifications, or import text and JSON files. Compare 1–6 products at a time.
- **Describe your needs:** Explain how you plan to use a product, then confirm your budget, weight target, laptop size, capacity, and external dimensions.
- **Choose your tradeoffs:** Prioritize price, low weight, or carrying features, and mark specific requirements as non-negotiable.
- **See the reasoning:** Review benefits, specification gaps, source excerpts, missing information, and the conditions behind each suggestion.
- **Consider review evidence:** Explicitly accept the relevant usage conditions before structured evidence, such as compressed dimensions, influences the comparison. Conflicting evidence prevents that compression claim from being used.
- **Keep your own shortlist:** Products are stored locally and remain available after restarting. You can also delete products you imported.

## A choice with tradeoffs

Suppose you want a carry-on bag no larger than **30 × 30 × 40 cm**:

| | Bag A | Bag B |
| --- | --- | --- |
| Listed dimensions | 30 × 30 × 30 cm | 30 × 20 × 45 cm |
| Price | NT$2,800 | NT$1,400 |
| Bottle pocket | No | Yes |
| Usage evidence | Listed dimensions meet the target | A review describes compressing the bag to 30 × 20 × 40 cm when approximately 70% full, with no rigid items at the top |

If you accept those packing restrictions and the remaining uncertainty, Bag B can become the preferred option: it saves NT$1,400 and includes a bottle pocket. Gather still shows that its listed dimensions exceed the limit by 5 cm, presents the review excerpt and its conditions, and labels the recommendation as conditional.

If dimensions are non-negotiable, Bag A becomes the preferred option instead. A personal account never replaces the original specifications or guarantees acceptance by an airline.

The size limit, products, and reviews above are **fictional examples**, not verified airline rules or actual product reviews.

## Run locally

Requires Python 3.10 or later.

```sh
git clone https://github.com/tree145/gather.git
cd gather
python -m venv .venv
```

Activate the virtual environment:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```sh
# macOS / Linux
source .venv/bin/activate
```

Install dependencies and start the application:

```sh
python -m pip install -r requirements.txt
python -m gather
```

Open `http://127.0.0.1:8010`. Keep the terminal running and press `Ctrl+C` to stop.

If the default port is already in use:

```sh
python -m uvicorn gather.app:app --host 127.0.0.1 --port 8012
```

Then open http://127.0.0.1:8012. You can also set the `GATHER_PORT` environment variable to change the port used by `python -m gather`.

## Your first comparison

The current interface, presets, and natural-language requirement parser primarily support Traditional Chinese. The control names below are English translations for reference.

1. Choose a usage scenario and select the products you want to compare.
2. Describe your needs, select **Organize my needs**, and confirm or edit the extracted conditions.
3. Choose a ranking preference. Mark only truly essential conditions as non-negotiable.
4. Select **Compare based on my needs** to review the preferred option, its tradeoffs, and differences between products.

To try the example above, choose the **Carry-on tradeoffs A / B** scenario and compare once. Then enable **Accept the review's usage conditions and uncertainty** and compare again to see how the result changes.

## Import your own products

Select **Import product** to paste specifications or choose a UTF-8 `.txt`, `.md`, `.html`, or `.json` file. Files may be up to 64 KB, and product descriptions may contain up to 20,000 characters.

For numeric specifications, the following English text format is supported:

```text
Price: NT$2,800
Weight: 680 g
Capacity: 26 L
Laptop: 16 inches
Dimensions: 30x20x45 cm
```

Specifications that are missing or cannot be recognized remain unknown. Weight can be expressed in g or kg. Prices are interpreted in New Taiwan dollars, without currency conversion. Dimensions are expressed in cm; the comparison allows rotation to align the three sides.

JSON products use the `name`, `brand`, and `description` fields. An [importable example](gather/static/sample-product.json) is also available to download from the interface. Use that template for additional fields such as padded backs, hip belts, and bottle pockets, whose parser currently expects Traditional Chinese field labels.

If you already have evidence about compression, add structured entries in the optional section of the import dialog, or include a `compression_evidence` array in the product JSON:

```json
[
  {
    "source_label": "The source name or URL you provide",
    "quote": "Review excerpt: At about 70% full, with soft clothing at the top, the bag compresses to 30x20x40 cm.",
    "conditions": "Approximately 70% full, with no rigid items at the top; verify the dimensions after packing.",
    "compressed_dimensions_cm": [30, 20, 40],
    "stance": "supporting"
  }
]
```

This illustrates the data format, not a real review. Set `stance` to `supporting` or `conflicting`, with up to five entries per product. Source names and URLs are stored as text; the application does not open them or fetch their contents.

## Current version and costs

This is a **local, offline interactive prototype**. Requirement parsing, specification extraction, and feedback use deterministic rules and text templates rather than a language model.

- The application has no paid API integrations, cloud deployment, or telemetry, so running it does not incur usage charges.
- Installing Python dependencies initially requires internet access. Once installed, normal operation works offline.
- Built-in products and reviews are clearly labeled as fictional examples. Imported products are not automatically given fabricated reviews.

The current version focuses on backpack shopping. It does not yet search the web, verify real reviews, recognize images or PDFs, or interpret arbitrary product categories. Additional written preferences remain part of the usage context, but only supported and confirmed conditions affect the comparison.

Ranking weights, gap penalties, and evidence handling are prototype rules that have not been calibrated against real consumer preferences. Recommendations are not objective optima, confidence percentages, or guarantees of suitability.

## Local data

Products are stored in `data/gather.db` by default. Set the `GATHER_DB` environment variable to use a different location. Requirements and recommendation results are not saved as a separate history. Databases, local settings, recordings, and secret files are excluded from version control.

The application listens on `127.0.0.1` by default for local use. This version does not include multi-user accounts or access controls for a public service.

## Verification

Run the functional tests:

```sh
python -m unittest discover -s tests -p test_gather.py -v
```

The optional browser check exercises the interface and generates screenshots and a silent walkthrough recording. It uses a separate test database and does not modify your product list:

```sh
python -m pip install playwright
python -m playwright install chromium
python scripts/check_gather.py
```

Generated files are saved to `data/demo-artifacts/` and are not included in the repository.

## Project origins

Gather grew out of [misanthropics-ai/0815](https://github.com/misanthropics-ai/0815), which explored product specifications, user profiles, and recommendation analysis. Gather shifts the experience toward consumers describing their own needs, comparing candidate products, and understanding the tradeoffs involved in choosing between them.

This project adapts the predecessor's requirement data structures and HTML text-cleaning logic into an independent local application with a consumer-facing interface.
