from pathlib import Path

import pytest

from legal_organizer.classifier import (
    classify_file,
    classify_filename,
    classify_type,
    normalize_text,
)


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("peticao_inicial.md", "Peticoes"),
        ("petição.md", "Peticoes"),
        ("inicial.md", "Peticoes"),
        ("contestacao.md", "Contestacoes"),
        ("contestação.md", "Contestacoes"),
        ("defesa.md", "Contestacoes"),
        ("manifestacao.md", "Manifestacoes"),
        ("manifestação.md", "Manifestacoes"),
        ("petição intermediária.md", "Manifestacoes"),
        ("despacho_intimacao.md", "Despachos"),
        ("despacho de intimação.md", "Despachos"),
        ("decisao_interlocutoria.md", "Decisoes"),
        ("decisão.md", "Decisoes"),
        ("liminar.md", "Decisoes"),
        ("tutela_urgencia.md", "Decisoes"),
        ("sentenca_procedente.md", "Sentencas"),
        ("sentença.md", "Sentencas"),
        ("SENTENCA.md", "Sentencas"),
        ("sentenca.md", "Sentencas"),
        ("acordao_tjrs.md", "Acordaos"),
        ("acórdão.md", "Acordaos"),
        ("julgamento_colegiado.md", "Acordaos"),
        ("AGRAVO DE INSTRUMENTO.md", "Agravos"),
        ("agravo_de_instrumento.md", "Agravos"),
        ("Agravo-de-Instrumento.md", "Agravos"),
        ("agravo instrumento.md", "Agravos"),
        ("agravo_interno.md", "Agravos"),
        ("agravo_regimental.md", "Agravos"),
        ("recurso_especial.md", "Recursos"),
        ("RESP.md", "Recursos"),
        ("recurso_extraordinario.md", "Recursos"),
        ("recurso extraordinário.md", "Recursos"),
        ("re.md", "Recursos"),
        ("apelação.md", "Recursos"),
        ("apelacao.md", "Recursos"),
        ("embargos_de_declaracao.md", "Recursos"),
        ("embargos de declaração.md", "Recursos"),
        ("embargos_infringentes.md", "Recursos"),
        ("recurso_ordinario.md", "Recursos"),
        ("recurso_inominado.md", "Recursos"),
        ("contrarrazões.md", "Recursos"),
        ("procuracao_cliente.md", "Procuracoes"),
        ("procuração.md", "Procuracoes"),
        ("substabelecimento.md", "Procuracoes"),
        ("contrato_honorarios.md", "Contratos"),
        ("acordo_extrajudicial.md", "Contratos"),
        ("certidao_negativa.md", "Certidoes"),
        ("certidão.md", "Certidoes"),
        ("antecedentes.md", "Certidoes"),
        ("objeto_e_pé.md", "Certidoes"),
        ("narratória.md", "Certidoes"),
        ("jurisprudência.md", "Jurisprudencia"),
        ("precedente.md", "Jurisprudencia"),
        ("súmula.md", "Jurisprudencia"),
        ("tema_repetitivo.md", "Jurisprudencia"),
        ("repercussao_geral.md", "Jurisprudencia"),
        ("lei_123_exemplo.md", "Legislacao"),
        ("decreto_exemplo.md", "Legislacao"),
        ("código.md", "Legislacao"),
        ("constituição.md", "Legislacao"),
        ("resolução.md", "Legislacao"),
        ("portaria.md", "Legislacao"),
        ("doutrina.md", "Doutrina"),
        ("artigo.md", "Doutrina"),
        ("livro.md", "Doutrina"),
        ("comentário.md", "Doutrina"),
        ("resumo_doutrinario.md", "Doutrina"),
        ("RG.md", "Documentos_Pessoais"),
        ("cpf.md", "Documentos_Pessoais"),
        ("comprovante_de_residencia.md", "Documentos_Pessoais"),
        ("recibo.md", "Financeiro"),
        ("comprovante_de_pagamento.md", "Financeiro"),
        ("custas.md", "Financeiro"),
        ("observacoes_processo.md", "Outros"),
    ],
)
def test_classify_file_by_filename(tmp_path: Path, filename: str, expected: str) -> None:
    document = tmp_path / filename
    document.write_text("# Fictional document\n", encoding="utf-8")
    assert classify_file(document) == expected


@pytest.mark.parametrize(
    ("filename", "expected"),
    [
        ("agravo_em_recurso_especial.md", "Agravos"),
        ("agravo_em_recurso_extraordinario.md", "Agravos"),
        ("sentenca_decisao.md", "Sentencas"),
        ("despacho_decisao.md", "Despachos"),
        ("acordao_decisao.md", "Acordaos"),
        ("peticao_contestacao.md", "Contestacoes"),
        ("peticao_intermediaria.md", "Manifestacoes"),
        ("peticao_manifestacao.md", "Manifestacoes"),
        ("contrato_de_honorarios.md", "Contratos"),
    ],
)
def test_specific_rules_take_priority(filename: str, expected: str) -> None:
    assert classify_filename(filename) == expected


@pytest.mark.parametrize("filename", [
    "relatorio.md", "leitura.md", "expressao.md", "livraria.md", "secretaria.md",
])
def test_keywords_do_not_match_inside_unrelated_words(filename: str) -> None:
    assert classify_filename(filename) == "Outros"


@pytest.mark.parametrize(
    ("original", "normalized"),
    [
        ("AGRAVO DE INSTRUMENTO", "agravo de instrumento"),
        ("agravo_de_instrumento", "agravo de instrumento"),
        ("Agravo-de-Instrumento", "agravo de instrumento"),
        ("  Decisão__Interlocutória--  ", "decisao interlocutoria"),
        ("Sentenc\u0327a", "sentenca"),
        ("Sentença", "sentenca"),
        ("  RECURSO\t ESPECIAL\n", "recurso especial"),
    ],
)
def test_normalization(original: str, normalized: str) -> None:
    assert normalize_text(original) == normalized


@pytest.mark.parametrize(
    ("filename", "document_type", "expected"),
    [
        ("documento_123.md", "sentenca", "Sentencas"),
        ("agravo.md", "despacho", "Despachos"),
        ("sentenca.md", "recurso especial", "Recursos"),
        ("peticao.md", "agravo de instrumento", "Agravos"),
        ("agravo.md", "Outros", "Outros"),
        ("documento.MD", "Acórdãos", "Acordaos"),
    ],
)
def test_frontmatter_has_priority(
    tmp_path: Path, filename: str, document_type: str, expected: str,
) -> None:
    document = tmp_path / filename
    document.write_text(f"---\ntype: {document_type}\n---\n# Fictional\n", encoding="utf-8")
    assert classify_file(document) == expected


@pytest.mark.parametrize("document_type", ["unrecognized", "", "[sentenca]"])
def test_unknown_or_unsupported_type_falls_back_to_filename(tmp_path: Path, document_type: str) -> None:
    document = tmp_path / "agravo.md"
    document.write_text(f"---\ntype: {document_type}\n---\n", encoding="utf-8")
    assert classify_file(document) == "Agravos"


@pytest.mark.parametrize(
    ("document_type", "expected"),
    [
        ("Documentos_Pessoais", "Documentos_Pessoais"),
        ("pessoal", "Documentos_Pessoais"),
        ("documento financeiro", "Financeiro"),
        ("MANIFESTAÇÕES PROCESSUAIS", "Manifestacoes"),
        ("peticoes iniciais", "Peticoes"),
        ("other", None),
    ],
)
def test_metadata_aliases(document_type: str, expected: str | None) -> None:
    assert classify_type(document_type) == expected


def test_document_body_is_not_classified(tmp_path: Path) -> None:
    document = tmp_path / "observacoes.md"
    document.write_text("# Sentença\nAgravo e recurso especial.\n", encoding="utf-8")
    assert classify_file(document) == "Outros"


def test_txt_uses_only_its_filename(tmp_path: Path) -> None:
    document = tmp_path / "agravo.txt"
    document.write_text("---\ntype: sentenca\n---\n", encoding="utf-8")
    assert classify_file(document) == "Agravos"
