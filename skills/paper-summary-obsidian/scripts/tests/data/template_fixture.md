{#- Structural fixture mirroring the live Obsidian Zotero template's landmarks.
    Used by tests as --template-path. Contains the frontmatter keys, fold
    headings, %% fold %% markers, persist blocks, and the ## Reading notes /
    ## Key takeaways / contribution:: anchors that the save script's template
    contract check (R10) validates. No personal paths. -#}

{%- set frontmatter_fields = {
  "title": title,
  "author": author_yaml,
  "year": date | format("YYYY"),
  "date-published": date | format("YYYY-MM-DD"),
  "citekey": citekey,
  "itemType": itemType,
  "url": url,
  "cssclasses": "lit-note",
  "links": links,
  "journal": journal_yaml,
  "doi": DOI
} -%}

---
project:
class: lit_note
aliases: []
{{generateFields("",": ",frontmatter_fields) -}}
lit_review:
---

{% persist "notes" -%}
## Key takeaways

contribution:: <% tp.file.cursor(1) %>
{% endpersist %}

> [!abstract]+
> {{abstractNote}}

> [!info]- Additional Metadata 🔗 [**Zotero**]({{desktopURI}})

> [!quote]- Citations
> 
> ```query
> content: "@{{citekey}}" -file:@{{citekey}}
> ```

___

## Reading notes

{% set colorValueMap = {
    "#ffd400": { "heading": "💬 Research Question and Motivation" },
    "#2ea8e5": { "heading": "📌 Data and Empirical Strategy" },
    "#5fb236": { "heading": "🎯 Results" },
    "#f19837": { "heading": "✒️ Limitations and Extensions" },
    "#a28ae5": { "heading": "🧩 Comments and Ideas" },
    "#e56eee": { "heading": "🗺️ Background, context and connections" },
    "#ff6666": { "heading": "🚧 Digging and disclaimers" },
    "#aaaaaa": { "heading": "❓ Problem formulation" }
} -%}

{% persist "annotations" %}
{%- for color, colorValue in colorValueMap %}

### {{colorValue.heading}} %% fold %%
{% endfor -%}
{% endpersist %}
