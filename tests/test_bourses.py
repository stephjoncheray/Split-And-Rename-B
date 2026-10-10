import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
from bourses import identite, propre, nom_prenom

def test_acceptation():
    t = """Notification\nMme Marie DUPONT\nObjet : Décision d'attribution de bourse de lycée\nPaul MARTIN (2MRC2 - n° élève 1234)"""
    assert identite(t) == ('DUPONT', 'Marie', 'MARTIN', 'Paul', '2MRC2', 'Acceptation')

def test_refus():
    t = 'M. Jean DURAND\nObjet : Décision de refus de bourse de lycée\nAlice PETIT (1AEPA - n° élève 55)'
    assert identite(t)[-1] == 'Refus'

def test_invalide():
    assert identite('texte quelconque') is None
    assert propre('NOM:/\\*') == 'NOM'
