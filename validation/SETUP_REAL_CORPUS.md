# Setting up a real attribution corpus

Salix's synthetic validation is a sanity check, not authorship attribution
evidence. To produce a defensible accuracy number, run against a public
labeled corpus.

## Recommended public corpora

### 1. Federalist Papers (Madison vs Hamilton vs Jay)

The classic stylometric test. 85 essays, three known authors, plus 12
disputed papers traditionally attributed to Madison.

```bash
# Download the full text from Project Gutenberg
mkdir -p validation/corpora/federalist
curl -L https://www.gutenberg.org/files/1404/1404-0.txt \
    > validation/corpora/federalist/raw.txt

# Use the included splitter to break the file into per-author subdirs
python3 scripts/split_federalist.py \
    --input validation/corpora/federalist/raw.txt \
    --out   validation/corpora/federalist/
```

After splitting:

```
validation/corpora/federalist/
  hamilton/  fed_01.txt  fed_06.txt  ...
  madison/   fed_10.txt  fed_14.txt  ...
  jay/       fed_02.txt  fed_03.txt  ...
```

(See `scripts/split_federalist.py` for the splitter — small, public-domain
specific.)

### 2. PAN authorship-attribution datasets

PAN evaluation labs (2011–2014) ship closed-set authorship corpora used
across the academic literature. Register at <https://pan.webis.de/> for the
download link, then arrange:

```
validation/corpora/pan13/
  candidate01/  doc1.txt  doc2.txt  ...
  candidate02/  ...
```

### 3. Reuters_50_50 (50 authors × 100 newswire articles each)

```bash
# Available on the UCI Machine Learning Repository
curl -O https://archive.ics.uci.edu/ml/machine-learning-databases/00217/C50.zip
unzip C50.zip
mkdir -p validation/corpora/reuters50
# C50 ships pre-split into C50train/ and C50test/. Concatenate per author:
for d in C50/C50train/*/; do
    a=$(basename "$d")
    mkdir -p "validation/corpora/reuters50/$a"
    cp "$d"*.txt "validation/corpora/reuters50/$a/"
    cp "C50/C50test/$a"/*.txt "validation/corpora/reuters50/$a/"
done
```

## Running validation

```bash
# Salix full-feature distance
./salix validate --corpus-dir validation/corpora/federalist

# Stamatatos 2009 char-3gram + cosine baseline (head-to-head)
./salix baseline --corpus-dir validation/corpora/federalist --top-k 1000

# JSON output for both, ready for diffing in CI
./salix baseline --corpus-dir validation/corpora/federalist --json > baseline.json
```

## Cross-domain stability

Once you have a real corpus, run:

```bash
./salix validate --cross-domain validation/corpora/<some-corpus>
```

Each author's docs are split alphabetically into halves; the harness reports
the same-author vs other-author distance ratio across the split. A ratio
above 1.0 means same-author documents cluster closer even when the test
docs come from different sub-parts of the corpus.

## Reporting

We recommend committing your numbers to `validation/results-<corpus>.md`:

```
| metric                   | Salix | Stamatatos baseline |
|--------------------------|-------|---------------------|
| accuracy                 | 0.78  | 0.71                |
| accuracy 95% CI          | (0.71, 0.85) | (0.64, 0.78) |
| authors                  | 5     | 5                   |
| docs/author              | 20    | 20                  |
| protocol                 | LOO k-fold | LOO k-fold     |
```
