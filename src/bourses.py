"""Traitement local des notifications de bourses en PDF (2 pages par notification)."""
from __future__ import annotations
import argparse
import logging
import re
import unicodedata
from pathlib import Path

from pypdf import PdfReader, PdfWriter

LOG = logging.getLogger(__name__)
ELEVE_RE = re.compile(r"([^\n()]+?)\s*\(\s*([0-9A-Z]{2,12})\s*-\s*n[°º]\s*élève", re.I)
REP_RE = re.compile(r"\b(?:M\.?|Mme|MME|Monsieur|Madame)\s+([\wÀ-ÿ'’\- ]+)", re.I)


def normaliser(texte: str) -> str:
    texte = unicodedata.normalize('NFKC', texte or '').replace('\u00a0', ' ')
    return '\n'.join(' '.join(ligne.split()) for ligne in texte.splitlines())


def nom_prenom(texte: str) -> tuple[str, str] | None:
    mots = texte.strip(' ,.;:()[]{}!?').split()
    if len(mots) < 2:
        return None
    pos = next((i for i, mot in enumerate(mots) if i > 0 and mot.isupper() and any(c.isalpha() for c in mot)), None)
    if pos is None:
        pos = 1
    return ' '.join(mots[pos:]).upper(), ' '.join(mots[:pos]).title()


def identite(texte: str) -> tuple[str, str, str, str, str, str] | None:
    texte = normaliser(texte)
    eleve = ELEVE_RE.search(texte)
    if not eleve:
        return None
    nom_eleve = nom_prenom(eleve.group(1))
    if not nom_eleve:
        return None
    lignes = texte.splitlines()
    candidats = []
    for i, ligne in enumerate(lignes):
        if '@ac-corse.fr' in ligne.lower() and i + 1 < len(lignes):
            candidats.append(lignes[i + 1])
    candidats.extend(lignes)
    representant = next((m for ligne in candidats if (m := REP_RE.search(ligne))), None)
    if not representant or not (nom_rep := nom_prenom(representant.group(1))):
        return None
    bas = texte.casefold()
    if 'décision de refus de bourse de lycée' in bas:
        decision = 'Refus'
    elif "décision d'attribution de bourse de lycée" in bas or 'décision d’attribution de bourse de lycée' in bas:
        decision = 'Acceptation'
    else:
        return None
    return nom_rep[0], nom_rep[1], nom_eleve[0], nom_eleve[1], eleve.group(2).upper(), decision


def propre(valeur: str) -> str:
    valeur = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', valeur)
    valeur = re.sub(r'\s+', '_', valeur.strip().rstrip('.'))
    return valeur[:90] or 'INCONNU'


def chemin_libre(dossier: Path, fichier: str) -> Path:
    base = dossier / fichier
    n = 2
    while base.exists():
        base = dossier / f'{Path(fichier).stem}-{n}{Path(fichier).suffix}'
        n += 1
    return base


def traiter(dossier: Path, sortie: Path | None = None, progression=None) -> dict[str, int]:
    dossier = dossier.resolve()
    sortie = (sortie or dossier / 'export').resolve()
    if not dossier.is_dir():
        raise NotADirectoryError(dossier)
    if sortie == dossier:
        raise ValueError('Le dossier de sortie doit être distinct du dossier source.')
    stats = {'produits': 0, 'ignores': 0, 'erreurs': 0}
    fichiers = sorted(p for p in dossier.iterdir() if p.is_file() and p.suffix.lower() == '.pdf')
    for fichier in fichiers:
        try:
            lecteur = PdfReader(str(fichier))
            if lecteur.is_encrypted:
                LOG.warning('PDF chiffré ignoré : %s', fichier.name)
                stats['erreurs'] += 1
                continue
            if len(lecteur.pages) % 2:
                LOG.warning('Nombre impair de pages : %s (%d). Dernière page ignorée.', fichier.name, len(lecteur.pages))
            for i in range(0, len(lecteur.pages) - 1, 2):
                try:
                    texte = lecteur.pages[i].extract_text() or ''
                    donnees = identite(texte)
                    if not donnees:
                        stats['ignores'] += 1
                        LOG.warning('Informations non reconnues : %s, pages %d-%d', fichier.name, i+1, i+2)
                        continue
                    rep_nom, rep_prenom, el_nom, el_prenom, classe, decision = donnees
                    dest = sortie / decision
                    dest.mkdir(parents=True, exist_ok=True)
                    nom = '_'.join(map(propre, [rep_nom, rep_prenom, el_nom, el_prenom, classe, f'Notification_{decision}'])) + '.pdf'
                    cible = chemin_libre(dest, nom)
                    writer = PdfWriter()
                    writer.add_page(lecteur.pages[i]); writer.add_page(lecteur.pages[i+1])
                    with cible.open('wb') as flux:
                        writer.write(flux)
                    stats['produits'] += 1
                except Exception:
                    stats['erreurs'] += 1
                    LOG.exception('Erreur dans %s, pages %d-%d', fichier.name, i+1, i+2)
                finally:
                    if progression: progression()
        except Exception:
            stats['erreurs'] += 1
            LOG.exception('Impossible de lire le PDF %s', fichier.name)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description='Séparer et renommer les notifications de bourses.')
    parser.add_argument('dossier', type=Path)
    parser.add_argument('--sortie', type=Path)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
    print(traiter(args.dossier, args.sortie))

if __name__ == '__main__':
    main()
