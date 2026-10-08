"""Edit this module to add categories, keywords, metadata aliases or extensions.

Rules are evaluated in CATEGORY_PRIORITY order. Accents, case, underscores
and hyphens are normalized by the classifier, so keywords need no duplicates.
"""

CATEGORY_PRIORITY: tuple[str, ...] = (
    "Despachos",
    "Sentencas",
    "Acordaos",
    "Agravos",
    "Contestacoes",
    "Manifestacoes",
    "Peticoes",
    "Recursos",
    "Decisoes",
    "Procuracoes",
    "Contratos",
    "Certidoes",
    "Jurisprudencia",
    "Legislacao",
    "Doutrina",
    "Documentos_Pessoais",
    "Financeiro",
    "Outros",
)

KEYWORDS: dict[str, tuple[str, ...]] = {
    "Peticoes": ("peticao", "peticao inicial", "inicial"),
    "Contestacoes": ("contestacao", "defesa"),
    "Manifestacoes": ("manifestacao", "peticao intermediaria"),
    "Despachos": ("despacho", "despacho judicial", "despacho de intimacao"),
    "Decisoes": ("decisao", "decisao interlocutoria", "liminar", "tutela"),
    "Sentencas": ("sentenca", "sentenca procedente", "sentenca improcedente"),
    "Acordaos": ("acordao", "julgamento colegiado"),
    "Agravos": (
        "agravo",
        "agravo de instrumento",
        "agravo interno",
        "agravo regimental",
        "agravo em recurso especial",
        "agravo em recurso extraordinario",
    ),
    "Recursos": (
        "recurso",
        "apelacao",
        "recurso especial",
        "resp",
        "recurso extraordinario",
        "re",
        "embargos de declaracao",
        "embargos infringentes",
        "recurso ordinario",
        "recurso inominado",
        "contrarrazoes",
    ),
    "Procuracoes": ("procuracao", "substabelecimento"),
    "Contratos": ("contrato", "contrato de honorarios", "acordo extrajudicial"),
    "Certidoes": (
        "certidao", "antecedentes", "negativa", "positiva", "objeto e pe", "narratoria",
    ),
    "Jurisprudencia": (
        "jurisprudencia", "precedente", "sumula", "tema repetitivo", "repercussao geral",
    ),
    "Legislacao": (
        "lei", "decreto", "codigo", "constituicao", "resolucao", "portaria",
    ),
    "Doutrina": ("doutrina", "artigo", "livro", "comentario", "resumo doutrinario"),
    "Documentos_Pessoais": (
        "documento pessoal", "documentos pessoais", "rg", "cpf", "identidade", "cnh",
        "comprovante de residencia",
    ),
    "Financeiro": (
        "financeiro", "boleto", "recibo", "pagamento", "comprovante de pagamento",
        "nota fiscal", "fatura", "custas", "honorarios",
    ),
    "Outros": (),
}

# Category names and exact keyword phrases also work as front matter types.
# These additional aliases are intentionally explicit and easy to extend.
TYPE_ALIASES: dict[str, tuple[str, ...]] = {
    "Manifestacoes": ("manifestacoes processuais",),
    "Peticoes": ("peticoes iniciais",),
    "Documentos_Pessoais": ("pessoal", "documentos pessoais"),
    "Financeiro": ("documento financeiro", "documentos financeiros"),
    "Outros": ("outro",),
}

DEFAULT_EXTENSIONS: frozenset[str] = frozenset({".md"})
OPTIONAL_EXTENSIONS: frozenset[str] = frozenset({".txt"})
