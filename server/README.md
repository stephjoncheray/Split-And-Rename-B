# Service interne de notifications de bourses (Debian 12)

**Statut : code préparé sur GitHub ; rien n'a encore été installé sur 192.168.224.240.** Ce dépôt ne contient pas de serveur web d'envoi opérationnel. La première phase reprend l'approche prudente de `split-eval` : préparation côté navigateur, transfert manuel contrôlé du ZIP, simulation, puis exécution SMTP côté Debian.

## Architecture

- Application publique statique : `https://stephjoncheray.github.io/Split-And-Rename-B/`.
- Adresse interne **réservée** : `http://192.168.224.240/Split-And-Rename-B/`.
- Le script `server/bourses_sender.py` est un moteur CLI. Il ne crée **aucun port d'écoute** et n'expose pas de dépôt de fichiers via Apache.
- Pas de stockage persistant automatisé. Les ZIP transférés manuellement, les journaux CSV et l'état de reprise sont des fichiers sensibles sur disque jusqu'à leur suppression. Ne pas écrire qu'ils « ne restent jamais sur le serveur » : ce serait inexact.
- Le schéma du ZIP est propre aux bourses : `campagne.json` avec `status: PREPARE_NON_ENVOYE`, chaque message possède `attachment` (singulier), `to` et un `status`. Il est différent du ZIP de Split-Eval (`attachments`, `statut`). Ne pas mélanger les deux expéditeurs.

## Avant installation

Valider avec l'établissement la légitimité de ce canal pour une décision de bourse, les destinataires, la traçabilité et la confidentialité. Éviter de saisir ou faire transiter un mot de passe SMTP sur une page en HTTP.

Le serveur `192.168.224.240` est aussi utilisé pour FOG et Split-Eval. Ne **pas** modifier les vhosts, NFS, DNS, exports FOG, ni le service `split-eval-web` sans audit préalable.

### Diagnostic non intrusif sur Debian

```bash
hostnamectl
systemctl is-active apache2 split-eval-web
apache2ctl configtest
sudo apache2ctl -S
sudo ss -ltnp | grep -E ':80|:443|:587|:993' || true
python3 --version
curl -I http://127.0.0.1/split-eval/
```

Conserver la sortie pour adapter l'implantation sous `/Split-And-Rename-B/` sans conflit.

## Préparer le moteur CLI séparé

Après validation institutionnelle, depuis un shell sur Debian :

```bash
sudo useradd --system --home /var/lib/split-and-rename-b --shell /usr/sbin/nologin bourses-send 2>/dev/null || true
sudo install -d -m 0755 -o root -g root /opt/split-and-rename-b
sudo install -d -m 0700 -o bourses-send -g bourses-send /var/lib/split-and-rename-b
sudo curl --fail --location --silent --show-error \
  https://raw.githubusercontent.com/stephjoncheray/Split-And-Rename-B/main/server/bourses_sender.py \
  -o /opt/split-and-rename-b/bourses_sender.py
sudo chmod 0644 /opt/split-and-rename-b/bourses_sender.py
python3 -m py_compile /opt/split-and-rename-b/bourses_sender.py
```

Pour une installation reproductible en production, préférer un commit épinglé et une empreinte SHA256 vérifiée, plutôt qu'un téléchargement non figé de la branche `main`.

Transférer le ZIP de campagne dans un répertoire privé avec SCP depuis un poste d'administration (ne jamais utiliser un répertoire public Apache). Puis appliquer `chmod 600` et la propriété du compte opérateur. La commande d'exécution doit s'effectuer depuis un compte autorisé à lire ce ZIP.

### Simulation

```bash
python3 /opt/split-and-rename-b/bourses_sender.py \
  /chemin/prive/campagne-bourses-non-envoyee.zip \
  --sender prenom.nom@ac-corse.fr \
  --report /chemin/prive/simulation-bourses.csv \
  --simulate
```

La simulation vérifie le manifeste et les PDF puis génère un journal, **sans envoyer de message**.

### Envoi réel — seulement après validation

```bash
python3 /opt/split-and-rename-b/bourses_sender.py \
  /chemin/prive/campagne-bourses-non-envoyee.zip \
  --sender prenom.nom@ac-corse.fr \
  --report /chemin/prive/envoi-bourses.csv \
  --state /chemin/prive/reprise-bourses.jsonl \
  --send --confirm ENVOYER --authorized
```

Le mot de passe est demandé dans le terminal via `getpass` et n'est pas sauvegardé. SMTP 587 STARTTLS utilise le magasin de certificats de Debian. Aucun compte IMAP ni stockage dans « Envoyés » n'est encore pris en charge par ce composant, contrairement à certaines options de Split-Eval.

**Gestion des doublons :** l'état JSONL note chaque tentative avant et après son appel SMTP. Une tentative interrompue au mauvais moment est considérée comme incertaine : le script empêche sa retransmission automatique pour éviter les doublons. La confirmation de livraison finale n'est pas garantie ; le journal indique seulement l'acceptation par le relais. Conserver le ZIP et le fichier JSONL dans le même ensemble privé pour une reprise ; ne jamais supprimer l'état et relancer à l'aveugle.

## Étape ultérieure : façade web interne

L'adresse `/Split-And-Rename-B/` est **cible de déploiement**, non un service actif. Pour reproduire l'interface serveur de Split-Eval, il faudra inspecter sa configuration Apache actuelle puis ajouter un service web séparé, écoutant uniquement sur loopback derrière Apache, protégé par authentification et HTTPS, avec validation pré-envoi. Ne jamais exposer directement un endpoint d'envoi SMTP au navigateur public GitHub Pages, ni stocker les identifiants dans le JavaScript.

## Recette minimale

1. ZIP factice contenant un élève et un parent fictifs ; vérifier le refus des archives malformées.
2. Simulation et revue du journal.
3. Après autorisation et seulement à une adresse institutionnelle de test, un seul message SMTP.
4. Contrôle de la pièce jointe reçue, du nom sans préfixe et du journal.
5. Vérification de la reprise sans doublon, puis nettoyage des fichiers sensibles.
