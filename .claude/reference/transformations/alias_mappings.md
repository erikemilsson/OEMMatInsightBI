# Alias Mappings Reference

## Country Aliases

### Tier 1: Exact Match (Confidence: 1.0)
```
ISO3 codes → Themselves (USA → USA, CHN → CHN, etc.)
```

### Tier 2: Standard Aliases (Confidence: 0.95)
```
"United States" → "United States of America"
"US" → "United States of America"
"UK" → "United Kingdom"
"GB" → "United Kingdom"
"Great Britain" → "United Kingdom"
```

### Tier 3: Encoding Variants (Confidence: 0.80-0.90)
```
"Türkiye" → "Turkey" (0.80)
"Cote d'Ivoire" → "Côte d'Ivoire" (0.85)
```

### Tier 4: Territory Mappings (Confidence: 0.85)
```
"Hong Kong" → "China" (0.85)
"Macau" → "China" (0.85)
"Puerto Rico" → "United States of America" (0.85)
```

## Material Aliases

### Case Variations (Confidence: 0.95)
```
"COPPER" → "Copper"
"copper" → "Copper"
"CoPoER" → "Copper"
```

### Spelling Variants (Confidence: 0.95)
```
"Aluminum" → "Aluminium" (US vs UK spelling)
"Phosphorus" → "Phosphorous"
```

### Unit Suffixes (Confidence: 0.90)
```
"Copper (kg)" → "Copper"
"Lithium [t]" → "Lithium"
```

## Adding New Aliases

### Method 1: Update Lookup Tables
```python
# In notebook or via SQL
new_alias = spark.createDataFrame([
    ("New Alias", "Standard Name", 0.95)
], ["alias", "standard_name", "confidence"])

new_alias.write.mode("append").saveAsTable("gold_dim_country_lookup")
```

### Method 2: Update Notebook Dictionaries
```python
# In silver-to-gold2.Notebook
country_aliases = {
    "New Alias": ("Standard Name", 0.95),
    # ... existing aliases
}
```

After adding, re-run: `/run-gold`
