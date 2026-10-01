# GTv Studio

Application éditoriale Flask pour transformer un contenu brut en article journalistique puis en audio.
Le développement local utilise SQLite ; le déploiement gratuit utilise PostgreSQL et
le stockage de fichiers Supabase.

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
- Création et conservation des contenus en local dans **SQLite via `sqlite3`**, sans SQLAlchemy.
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

Ouvrez http://127.0.0.1:5000. En local, la base SQLite est créée automatiquement
dans `instance/2gc_converter.sqlite3`.

## Base de données

La base SQLite locale est visible avec DB Browser for SQLite ou l'extension SQLite Viewer de VS Code :

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

## Déploiement gratuit : Render + Supabase

En local, l'application utilise SQLite et un dossier audio local. En production,
elle utilise PostgreSQL hébergé par Supabase et un bucket privé Supabase Storage.
Render Free n'a pas de stockage local persistant ; ne définissez donc pas
`DATABASE_PATH` ou `AUDIO_STORAGE_PATH` comme stockage de production.

### Préparer Supabase

1. Créez un projet Supabase sur l'offre Free et choisissez un mot de passe de base
   de données solide.
2. Dans **Project Settings → Database → Connection string**, copiez la chaîne
   **Session pooler** (Render utilise une connexion IPv4). Remplacez le mot de
   passe placeholder et gardez `sslmode=require` si fourni.
3. Dans **Storage**, créez un bucket nommé `gtv-audios` et laissez-le **privé**.
4. Depuis **Project Settings → API**, copiez l'URL du projet et la clé secrète
   serveur `service_role`. Ne l'utilisez jamais dans le navigateur ni sur GitHub.

### Déployer l’application

1. Dans Render, créez un **Blueprint** depuis le dépôt GitHub `Gotuel/GTv_Studio`.
2. Le Blueprint utilise le plan **Free**, Gunicorn et `/health`. Il ne crée pas de
   disque Render.
3. Renseignez les variables secrètes demandées :
   - `APP_ACCESS_PASSWORD` : mot de passe partagé des pages éditoriales ;
   - `OPENROUTER_API_KEY` : nouvelle clé OpenRouter ;
   - `DATABASE_URL` : chaîne PostgreSQL Session pooler Supabase ;
   - `SUPABASE_URL` : URL du projet Supabase ;
   - `SUPABASE_SERVICE_ROLE_KEY` : clé serveur Supabase.
4. Render génère `SECRET_KEY`. Les tables sont créées automatiquement au premier
   démarrage. Vérifiez ensuite `https://<service>.onrender.com/health`.

Les articles sont stockés dans PostgreSQL. Les fichiers MP3 sont envoyés au
bucket privé `gtv-audios`, puis transmis au navigateur par l'application après
authentification. La clé Supabase n'est jamais envoyée au client.

### Migrer les données SQLite locales

Avant la première migration, effectuez une copie de votre base locale et de
`instance/audio`. Configurez temporairement `.env` avec les secrets Supabase,
`DATABASE_URL` et `STORAGE_BACKEND=supabase`, puis exécutez :

```powershell
python -m flask --app run migrate-local-db
```

Pour une autre base source :

```powershell
python -m flask --app run migrate-local-db --source chemin\vers\base.sqlite3
```

La migration conserve les identifiants et est relançable sans dupliquer les lignes.
Les audios `ready` doivent exister sous `AUDIO_STORAGE_PATH`; l'outil les envoie
au bucket avant d'insérer leurs métadonnées. Vérifiez les comptes d'articles,
versions et audios dans Supabase avant d'exposer le lien Render.

### Limites des offres gratuites

- Render Free met le service en veille après une période sans trafic ; le premier
  accès suivant peut attendre le redémarrage.
- Le système de fichiers de Render Free est éphémère ; PostgreSQL et les MP3 sont
  donc externalisés vers Supabase.
- Supabase Free peut mettre en pause un projet resté inactif une semaine ; il faut
  le réactiver depuis Supabase si cela arrive.
- Les quotas gratuits (base, stockage et bande passante) sont limités. Surveillez
  leur utilisation dans les tableaux de bord Render et Supabase.
- Cette combinaison convient à un prototype ou une petite démonstration, pas à
  une disponibilité professionnelle garantie.

### Configuration Render

`render.yaml` déclare le plan gratuit et demande à Render les variables sensibles
ci-dessus sans les stocker dans Git. Les variables `DATABASE_URL`, `SUPABASE_URL`
et `SUPABASE_SERVICE_ROLE_KEY` ne doivent jamais être commitées.

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
