# Split-And-Rename-B — version web

**[Ouvrir l'application web](https://stephjoncheray.github.io/Split-And-Rename-B/)** *(après activation de GitHub Pages)*

Application web statique qui sépare des notifications de bourse contenues dans des PDF multi-pages, extrait les informations de la notification, puis produit un ZIP renommé avec les dossiers `Acceptation/` et `Refus/`.

## Confidentialité et architecture

- Traitement des documents **dans le navigateur**, sans téléversement de PDF ni compte serveur.
- Les fichiers sources et le ZIP sont conservés localement côté poste. Le ZIP n'est créé qu'au clic de l'utilisateur.
- L'interface se charge depuis GitHub Pages ; les bibliothèques JavaScript sont actuellement téléchargées auprès de CDN publics. **Pour un fonctionnement entièrement autonome ou sous contrôle informatique de l'établissement, héberger localement ces bibliothèques et ajouter une politique CSP stricte.**
- Les bibliothèques utilisées sont PDF.js (extraction texte), pdf-lib (copie de pages), JSZip (archivage).
- L'application **ne comporte actuellement aucun envoi interne**. Un serveur interne d'envoi nécessitera une API séparée, authentification, restrictions réseau, contrôles d'accès, et validation explicite des documents destinataires. Ne pas exposer cette API à Internet.
- Aucun PDF réel, élève ou représentant ne doit être enregistré dans le dépôt public.

## Utilisation

1. Importer un ou plusieurs PDF multi-notifications.
2. Cliquer **Analyser les PDF** ; les notifications sont supposées compter exactement **deux pages**, texte présent dans la couche PDF.
3. Contrôler et corriger dans le tableau les noms, prénoms, classe et décision (acceptation/refus).
4. Désélectionner les lignes non désirées.
5. Cliquer **Télécharger le ZIP**.

La détection automatisée dépend des libellés imprimés, de l'ordre et de la typographie du PDF. **Vérification humaine obligatoire**, notamment avant tout envoi ; les documents scannés sans couche texte ne sont pas reconnus. Les décisions non reconnues restent « À vérifier » et ne sont pas exportées tant qu'elles ne sont pas corrigées.

## Lancer en local

Un navigateur récent est requis. Certaines fonctions nécessitent une origine HTTP(S) : servir le répertoire statique avec :

```sh
python -m http.server 8000
```

Puis ouvrir `http://localhost:8000`. Le serveur local ne traite pas les PDF ; ils sont exploités par le navigateur.

## GitHub Pages

Le workflow `.github/workflows/pages.yml` est conçu pour déployer uniquement `index.html` sur GitHub Pages. Il faut éventuellement activer **Settings → Pages → Source : GitHub Actions** dans les paramètres du dépôt. L'adresse de publication est `https://stephjoncheray.github.io/Split-And-Rename-B/`. Sa disponibilité doit être confirmée après le déploiement.

## Historique

Le moteur `src/bourses.py`, son interface Tkinter et les fichiers Python sont conservés provisoirement **à titre de version historique**. Pour l'application web, c'est `index.html` qui fait foi ; Python n'est pas nécessaire.

## Limites connues

- Pas d'OCR.
- Découpage fixe par deux pages.
- Pas de détection fiable garantie pour toutes les éditions de notifications.
- Les dépendances JS sont actuellement chargées sur CDN ; l'usage strictement intranet demandera un hébergement local.
- Aucun connecteur de messagerie n'est actif.
