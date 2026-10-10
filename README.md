# Split-And-Rename-B

Outil local de séparation et de renommage des notifications de bourses PDF, avec interface graphique **Tkinter** et mode ligne de commande.

> Réécriture maintenable basée sur l'analyse statique d'un ancien exécutable Windows. Le code source original n'a pas été récupéré.

## Fonctionnalités

- Parcourt les PDF présents dans un dossier.
- Traite les notifications par **blocs de deux pages**.
- Recherche représentant légal, élève, classe et décision dans le texte extrait de la première page.
- Crée deux sous-dossiers : `export/Acceptation/` et `export/Refus/`.
- Renomme les documents selon le modèle `NOMREP_Prenomrep_NOMELEVE_Prenomeleve_CLASSE_Notification_Acceptation.pdf` (ou `Refus`).
- Ajoute un suffixe numérique en cas de doublon et journalise les erreurs.
- Ne transmet aucun PDF à un service externe.

## Installation sous Windows

Nécessite Python 3.13.

```powershell
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python src/gui.py
```

Exécution sans interface :

```powershell
python src/bourses.py "C:\Dossier\Bourses"
python src/bourses.py "C:\Dossier\Bourses" --sortie "D:\Exports\Bourses"
```

## Générer le .exe Windows

```powershell
python -m pip install -r requirements-dev.txt
python -m PyInstaller --noconfirm --onefile --windowed --name Split_And_Rename_Bourses --paths src src/gui.py
```

Le programme compilé se trouve dans `dist/`. La compilation doit être réalisée et testée sur Windows ; aucune version exécutable n'est encore publiée ici.

## Tests

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

## Limites et confidentialité

- **Attention :** le dépôt est actuellement **public**. Ne jamais y déposer de PDF administratifs réels ni de données personnelles ; `.gitignore` exclut les `*.pdf`.
- Le programme suppose que chaque notification comporte exactement deux pages et ne reconnaît que les mises en page prises en charge par ses règles d'extraction. Vérifier les résultats avec des documents synthétiques avant un usage opérationnel.
- Un PDF scanné sans couche texte n'est pas traité correctement : aucun OCR n'est intégré.
- Si le PDF comporte un nombre impair de pages, la dernière est ignorée et signalée.
- Aucun texte n'est anonymisé dans les PDF générés : ils restent confidentiels.

## Licence

Pas de licence définie pour l'instant. Vérifier les droits nécessaires avant réutilisation ou redistribution.
