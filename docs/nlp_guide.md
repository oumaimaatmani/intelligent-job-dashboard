# Guide rapide — commandes pour la phase NLP

Ce fichier décrit les commandes pour reproduire la construction du modèle TF‑IDF et obtenir des recommandations depuis les scripts ajoutés (`src/nlp.py`, `src/recommend.py`).

Prérequis
- Python 3.8+
- Virtualenv (recommandé) ou conda

Installer les dépendances

Windows / PowerShell:
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m nltk.downloader wordnet omw-1.4
```

Linux / macOS:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m nltk.downloader wordnet omw-1.4
```

Emplacement des fichiers
- Données traitées attendues : `data/processed/job_listings_clean.csv`
- Scripts : `src/nlp.py`, `src/recommend.py`
- Modèle TF‑IDF sauvegardé : `models/tfidf/vectorizer.joblib` et `models/tfidf/matrix.joblib`

Étapes rapides

1) Construire et sauvegarder le modèle TF‑IDF (exécuter depuis la racine du projet) :

```powershell
python src/recommend.py --data data/processed/job_listings_clean.csv --build --model-dir models/tfidf
```

La commande crée `models/tfidf/` avec `vectorizer.joblib` et `matrix.joblib`.

2) Faire une recommandation (après build) :

```powershell
python src/recommend.py --data data/processed/job_listings_clean.csv --model-dir models/tfidf --query "data scientist" --top 10
```

3) Utiliser `src/nlp.py` pour tester TF‑IDF et debug (optionnel) :

```powershell
cd src
python nlp.py --data ../data/processed/job_listings_clean.csv --query "data scientist" --top 10
```

- Si vous changez le champ texte à vectoriser (par ex. `job_title` + `job_description`), adaptez les appels `--data` et les fonctions dans `src/recommend.py`.
- Pour servir des requêtes fréquentes, sérialisez les objets `vectorizer` et `matrix` (déjà fait par `--build`) et rechargez-les.
- Pour améliorer la pertinence : normaliser `job_title`, extraire `skills_required`, utiliser embeddings (sentence-transformers) au lieu de TF‑IDF.
- Respectez les limitations légales et les Terms of Service des sources (LinkedIn, Indeed) si vous décidez de scraper.
- If you are running Python 3.14 or cannot install `spaCy`, the skills extractor will automatically fall back to a regex-based method and does not require `spaCy`. You can continue without installing `spaCy` or changing Python versions. To force the fallback, call the extractor with `use_spacy=False`.

Dépannage rapide
- Erreur NLTK relacionada au tokenizer : exécuter `python -m nltk.downloader wordnet omw-1.4` (script utilise tokenisation regex, donc `punkt` n'est pas nécessaire).
- Fichier CSV manquant : vérifiez `data/processed/job_listings_clean.csv` ou régénérez avec le script de collecte `src/collect_data.py`.
- spaCy/Python 3.14: spaCy may import or runtime errors on Python 3.14 due to compatibility issues. If you see errors when importing spaCy, either run in a compatible Python version (3.11) or continue without spaCy; the skills extractor will still work with the regex fallback.

Si vous voulez, je peux :
- Si vous changez le champ texte à vectoriser (par ex. `job_title` + `job_description`), adaptez les appels `--data` et les fonctions dans `src/recommend.py`.
- Pour servir des requêtes fréquentes, sérialisez les objets `vectorizer` et `matrix` (déjà fait par `--build`) et rechargez-les.
- Pour améliorer la pertinence : normaliser `job_title`, extraire `skills_required`, utiliser embeddings (sentence-transformers) au lieu de TF‑IDF.
- Respectez les limitations légales et les Terms of Service des sources (LinkedIn, Indeed) si vous décidez de scraper.

## Test & Validation du Workflow

Pour vérifier que le système fonctionne correctement, exécutez les étapes suivantes (depuis la racine du projet) :

### Test 1 : Vérifier les imports

```powershell
python -c "from src.recommend import recommend, build_and_save, load_vectorizer_and_matrix; print('✓ Import OK')"
```

Attendu : aucune erreur, affiche "✓ Import OK".

### Test 2 : Construire le modèle TF-IDF

```powershell
python src/recommend.py --data data/processed/job_listings_clean.csv --build --model-dir models/tfidf
```

Attendu : crée `models/tfidf/vectorizer.joblib` et `models/tfidf/matrix.joblib`. Vérifiez :
```powershell
ls models/tfidf/
```

### Test 3 : Exécuter une recommandation simple

```powershell
python src/recommend.py --data data/processed/job_listings_clean.csv --model-dir models/tfidf --query "data scientist" --top 5
```

Attendu : affiche 5 offres d'emploi triées par similarité avec scores entre 0 et 1.

### Test 4 : Test d'extraction de compétences

```powershell
python -c "from src.skills import extract_skills_from_text; print(extract_skills_from_text('Python, SQL, AWS, Docker and TensorFlow experience required', use_spacy=False))"
```

Attendu : affiche `['aws', 'docker', 'python', 'sql', 'tensorflow']` (ou liste similaire).

### Test 5 : Test rapide intégré (pseudo-integration test)

```powershell
python -c "
import pandas as pd
from src.recommend import recommend

# Charger données
df = pd.read_csv('data/processed/job_listings_clean.csv')

# Recommander sans modèle pré-construit (construit à la volée)
res = recommend('python engineer', df, top_n=3)

# Vérifier résultats
print('Résultats:')
print(res[['job_title', 'company_name', '_similarity_score']])
print(f'✓ OK - {len(res)} résultats retournés')
"
```

Attendu : affiche 3 offres avec colonnes `job_title`, `company_name`, `_similarity_score`.

### Résumé des vérifications

✓ Imports sans erreur  
✓ Fichiers `.joblib` créés  
✓ Résultats affichent colonnes correctes  
✓ Scores entre 0 et 1  
✓ Scores décroissent (meilleurs d'abord)  
✓ Modèle chargé est beaucoup plus rapide  

Si tous les tests passent, votre pipeline NLP fonctionne correctement !

Dépannage rapide
- Erreur NLTK relacionada au tokenizer : exécuter `python -m nltk.downloader wordnet omw-1.4` (script utilise tokenisation regex, donc `punkt` n'est pas nécessaire).
- Fichier CSV manquant : vérifiez `data/processed/job_listings_clean.csv` ou régénérez avec le script de collecte `src/collect_data.py`.
