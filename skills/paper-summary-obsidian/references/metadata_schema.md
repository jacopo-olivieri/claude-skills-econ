# Metadata Schema

Provide metadata to `scripts/save_paper_summary.py` via `--metadata-file` as JSON.

## Required keys

- `title` (string, can be empty)
- `authors` (array of strings, can be empty)

## Optional keys

- `citationKey` or `citation_key` or `citekey` (string, recommended for metadata completeness)
- `date_published` or `date-published` or `date` (ISO date string, e.g. `2020-07-31`). The saved note always emits the vault-dominant `date-published` key.
- `itemType` or `item_type` (string)
- `url` (string)
- `doi` (string)
- `journal` or `publicationTitle` (string)
- `abstract` or `abstractNote` (string)
- `bibliography` (string)
- `zotero_uri` (string, defaults to `zotero://select/library/items/<item_key>`)
- `attachments` (array of objects)

Attachment objects accept:

- `key` (string, optional)
- `title` (string, optional)
- `path` (string, optional)
- `is_pdf` (boolean, optional)

## Minimal example

```json
{
  "title": "Disparities in PM2.5 air pollution in the United States",
  "authors": [
    "Jonathan Colmer",
    "Ian Hardman",
    "Jay Shimshack",
    "John Voorheis"
  ],
  "citationKey": "colmerDisparitiesPM2.5Air2020",
  "date_published": "2020-07-31",
  "itemType": "journalArticle",
  "url": "https://www.science.org/doi/10.1126/science.aaz9353",
  "doi": "10.1126/science.aaz9353",
  "journal": "Science",
  "abstract": "Air pollution at any given time is unequally distributed across locations...",
  "zotero_uri": "zotero://select/library/items/FXDRBVG4",
  "attachments": [
    {
      "key": "VMRESN7A",
      "title": "colmer_et_al._2020_disparities_in_pm2.5_air_pollution_in_the_united_states.pdf",
      "is_pdf": true
    }
  ],
  "bibliography": "Colmer, Jonathan, et al. (2020) ..."
}
```
