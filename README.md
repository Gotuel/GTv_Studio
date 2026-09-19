# GTv Studio

Application éditoriale Flask pour transformer un contenu brut en article journalistique puis en audio.

## Structure du projet

```text
GTv_Studio/
├── app/
│   ├── db.py
│   ├── routes.py
│   ├── services.py
│   ├── templates/
│   └── static/
├── tests/
├── instance/              # données locales, ignorées par Git
├── .env.example
├── requirements.txt
├── run.py
└── README.md
```

## Fonctionnalités

- Tableau de bord d'accueil dynamique avec statistiques et activité récente.
- Création et conservation des contenus dans **SQLite via `sqlite3`**, sans SQLAlchemy.
- Base normalisée avec les tables `categories`, `articles`, `article_versions` et `audios`.
- Génération d'article avec OpenRouter, niveau basic/intermediate/professional.
- Édition, validation, historique, recherche et filtres.
- Génération, lecture et téléchargement audio avec gTTS.

## Installation

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Renseignez `OPENROUTER_API_KEY` dans `.env` (la clé n'est jamais affichée ni commitée), puis lancez :

```powershell
python run.py
```

Ouvrez http://127.0.0.1:5000. La base est créée automatiquement dans `instance/2gc_converter.sqlite3`.

## Base de données

La base est visible avec DB Browser for SQLite ou l'extension SQLite Viewer de VS Code :

```text
instance/2gc_converter.sqlite3
```

Tables :

- `categories` : catégories actives des contenus ;
- `articles` : informations principales et texte brut ;
- `article_versions` : générations IA, modifications manuelles et versions validées ;
- `audios` : fichiers audio, moteur utilisé et état de génération.

La migration depuis l'ancien schéma est automatique au démarrage. Une copie de sécurité
est créée dans `instance/2gc_converter.backup.sqlite3`.

Pour afficher un résumé depuis le terminal :

```powershell
python -m flask --app run inspect-db
```

Pour recréer/initialiser explicitement les tables :

```powershell
python -m flask --app run init-db
```

## Tests

```powershell
pytest
```

L'API OpenRouter et gTTS doivent être mockés dans les tests afin de ne pas appeler de services externes.

## Publication GitHub

Avant de publier :

1. Révoquez toute clé OpenRouter qui aurait été exposée.
2. Copiez `.env.example` vers `.env` et renseignez vos valeurs localement.
3. Vérifiez que `.env`, `.venv`, `instance/` et les caches ne sont pas suivis par Git.
4. Lancez `python -m pytest -q`.

Les modèles OpenRouter gratuits peuvent être limités ou temporairement indisponibles.
Le modèle utilisé reste configurable avec `OPENROUTER_MODEL`.

## Limites actuelles

Cette version est destinée à un usage local ou à un dépôt privé de démonstration.
Avant une exposition publique, ajoutez une authentification et une protection CSRF
adaptées au contexte de déploiement.
