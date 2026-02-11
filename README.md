# Wellcome Collection → Wikimedia Commons Upload

Batch upload pipeline for transferring pathology and museum images from the [Wellcome Collection](https://wellcomecollection.org/) to [Wikimedia Commons](https://commons.wikimedia.org/).

## Overview

This project automates the process of:
1. **Fetching** image metadata from the Wellcome Collection API
2. **Downloading** full-resolution images via IIIF Image API
3. **Deduplicating** against existing Wikimedia Commons uploads
4. **Renaming** images to follow Commons naming conventions (e.g., `Leprosy_skin_Wellcome_W0043368.jpg`)
5. **Uploading** to Wikimedia Commons with proper wikitext, licensing, and categorization using Pywikibot

## Collections

### SB Lucas Pathology Collection (124 images)
- **Source**: [Wellcome Collection – SB Lucas](https://wellcomecollection.org/search/images?source.contributors.agent.label=%22SB+Lucas%22)
- **Content**: Histopathology slides covering leprosy, schistosomiasis, amoebiasis, leishmaniasis, histoplasmosis, tuberculosis, and other tropical diseases
- **License**: CC0 1.0 Universal (Public Domain)
- **Status**: Ready for upload / uploaded

### Museum Objects Collection (12 new images)
- **Source**: [Wellcome Collection – Museum Objects](https://wellcomecollection.org/search/images?source.genres.label=%22Museum+object%22&sortOrder=desc&sort=source.production.dates)
- **Content**: Historical medical instruments, anatomical models, and artifacts
- **License**: CC BY 4.0 (842 images) / Public Domain Mark (10 images)
- **Status**: 840 of 852 already on Commons; 12 new images remaining

## Repository Structure

```
wellcome-commons-upload/
├── README.md
├── upload_to_commons.py            ← Pywikibot upload script
├── download_images.py              ← Script to download images from Wellcome API
├── sb_lucas_wellcome_images.csv    ← Full metadata for 124 SB Lucas images
├── museum_objects.csv              ← Full metadata for 12 new museum object images
└── images/
    ├── sb_lucas/                   ← 124 pathology images
    └── museum_objects/             ← 12 museum object images
```

## Setup

### Prerequisites

```bash
pip install pywikibot
```

### Bot Password

1. Go to [Special:BotPasswords](https://commons.wikimedia.org/wiki/Special:BotPasswords) on Wikimedia Commons
2. Create a new bot password with these permissions:
   - Edit existing pages
   - Create, edit, and move pages
   - Upload new files
   - Upload, replace, and move files
3. Copy the generated password

### Configuration

Edit the top of `upload_to_commons.py`:

```python
COMMONS_USERNAME = "YourUsername"
BOT_USERNAME     = "YourUsername@botname"
BOT_PASSWORD     = "your-bot-password"
```

Create `user-config.py` in the repo root:

```python
family = 'commons'
mylang = 'commons'
usernames['commons']['commons'] = 'YourUsername'
password_file = 'user-password.py'
put_throttle = 5
maxlag = 5
```

Create `user-password.py` in the repo root:

```python
("YourUsername@botname", "your-bot-password")
```

## Usage

### Upload SB Lucas images

```bash
# Preview (no upload)
python upload_to_commons.py --dry-run --limit 5

# Pilot test
python upload_to_commons.py --limit 5

# Upload all
python upload_to_commons.py

# Resume if interrupted
python upload_to_commons.py --resume

# Start from a specific image
python upload_to_commons.py --start 50
```

### Download images from Wellcome API

If you need to re-download the images from the Wellcome Collection:

```bash
python download_images.py
```

## Wikitext Format

Each uploaded image uses this format on Commons:

```wikitext
== {{int:filedesc}} ==
{{Information
|description={{en|1=Description text}}
|date=
|source={{Wellcome Images}}<br/>Source: [URL Wellcome Collection]
|author=SB Lucas
|permission=
|other versions=
}}

== {{int:license-header}} ==
{{cc-zero}}

[[Category:Disease Name]]
```

## CSV Columns

| Column | Description |
|---|---|
| `image_id` | Wellcome Collection image identifier |
| `work_id` | Wellcome Collection work identifier |
| `miro_image_number` | Miro/Wellcome reference number |
| `title` | Image title |
| `description` | Full pathological description |
| `contributors` | Image author/creator |
| `license_id` | License identifier (cc-0) |
| `work_page_url` | Source URL on Wellcome Collection |
| `filename` | Local filename (Commons naming convention) |

## License

- **Images**: CC0 1.0 (SB Lucas) / CC BY 4.0 (Museum Objects) — as licensed by Wellcome Collection
- **Code**: MIT License

## Acknowledgements

- [Wellcome Collection](https://wellcomecollection.org/) for making their collections openly available
- [Wellcome Collection API](https://developers.wellcomecollection.org/) for programmatic access
- [IIIF Image API](https://iiif.io/) for standardised image delivery
