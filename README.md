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
├── render.yaml
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

## Déploiement sur Render

Le dépôt inclut `render.yaml`, qui configure le service web, Gunicorn, le bilan
de santé et un disque persistant monté sur `/var/data`. SQLite et les fichiers
audio y sont tous deux stockés afin de survivre aux redémarrages et déploiements.

1. Poussez la branche contenant `render.yaml` sur GitHub.
2. Dans Render, créez un **Blueprint** et sélectionnez ce dépôt.
3. Confirmez la création du service et du disque persistant. Le disque Render
   nécessite un service payant ; l'offre gratuite utilise un système de fichiers
   éphémère et ne convient pas à cette configuration SQLite.
4. Saisissez `OPENROUTER_API_KEY` dans les variables d'environnement du service.
   `APP_ACCESS_PASSWORD` doit aussi être défini dans Render. `SECRET_KEY` est
   générée par le Blueprint et les autres variables sont définies dans `render.yaml`.
5. Attendez la fin du déploiement et vérifiez `/health` sur l'URL Render attribuée.

Le démarrage utilise Gunicorn avec un seul worker et plusieurs threads. Gardez
un seul processus applicatif pour SQLite : ne mettez pas plusieurs instances du
service derrière le même fichier de base. Le stockage audio et SQLite sont sur le
même disque persistant ; configurez des sauvegardes régulières du disque.

Les variables Render attendues :

| Variable | Utilisation |
| --- | --- |
| `SECRET_KEY` | Signature des sessions et protection CSRF, générée par Render |
| `APP_ACCESS_PASSWORD` | Mot de passe partagé protégeant l’espace éditorial |
| `OPENROUTER_API_KEY` | Clé OpenRouter, saisie dans le tableau de bord Render |
| `OPENROUTER_MODEL` | Identifiant du modèle IA configurable |
| `DATABASE_PATH` | Fichier SQLite sur le disque persistant |
| `AUDIO_STORAGE_PATH` | Dossier des fichiers audio sur le disque persistant |
| `APP_ENV` | `production` active les réglages sécurisés derrière le proxy Render |

## Publication GitHub

Avant de publier :

1. Révoquez toute clé OpenRouter qui aurait été exposée.
2. Copiez `.env.example` vers `.env` et renseignez vos valeurs localement.
3. Vérifiez que `.env`, `.venv`, `instance/` et les caches ne sont pas suivis par Git.
4. Lancez `python -m pytest -q`.

Les modèles OpenRouter gratuits peuvent être limités ou temporairement indisponibles.
Le modèle utilisé reste configurable avec `OPENROUTER_MODEL`.

## Limites actuelles

En production, l'accès éditorial est protégé par un mot de passe partagé configuré
dans `APP_ACCESS_PASSWORD`; la page publique et la sonde `/health` restent
accessibles sans connexion. Cette protection convient à une petite équipe connue,
mais ne remplace pas des comptes individuels et des rôles pour une utilisation
multi-utilisateur à grande échelle.
