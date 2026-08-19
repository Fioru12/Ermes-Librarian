import pytest
from legacy_winsarp.modules.winsarp import _check_balance, _find_comment_start, clean_code, validate_winsarp

def test_comment_handling():
    # Test il riconoscimento del commento fuori da stringhe
    # (500="DURATA?X"); ?commento
    # 0123456789012345678
    #                  ^ indice 18
    assert _find_comment_start('(500="DURATA?X"); ?commento') == 18

    assert _find_comment_start('(500="DURATA?X")') is None
    assert clean_code('(500="DURATA?X"); ?commento') == '(500="DURATA?X");'

def test_balance_complex():
    # Costrutto IF-THEN-ELSE tipico WinSarp che non richiede parentesi chiuse
    s = "21UZ(V04;(504='SFN');21>4((564=4)(K21S4)(!4)V05;"
    assert len(_check_balance(s)) == 0

def test_balance_string_containing_parens():
    # Parentesi dentro stringhe non devono influenzare il bilanciamento
    s = "(500='(NON_TOCCARE)');"
    assert len(_check_balance(s)) == 0

def test_validate_forbidden_fields():
    # Verifica il rilevamento di campi vietati
    errors = validate_winsarp("(70=1);")
    assert any("Campi 7-9 vietati" in e for e in errors)
    
    # Formula valida
    assert len(validate_winsarp("(500=1);")) == 0
