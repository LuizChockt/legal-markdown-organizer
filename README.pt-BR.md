<picture>
  <source media="(prefers-color-scheme: dark) and (max-width: 600px)" srcset="./assets/cover-mobile-dark.svg">
  <source media="(max-width: 600px)" srcset="./assets/cover-mobile-light.svg">
  <source media="(prefers-color-scheme: dark)" srcset="./assets/cover-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="./assets/cover-light.svg">
  <img src="./assets/cover-light.svg" alt="Legal Markdown Organizer — organização local por regras, dry-run e preservação dos bytes dos documentos." width="1200">
</picture>

# Legal Markdown Organizer

[English](./README.md) · [Referência completa em inglês](./docs/reference.md) · [Saída do dry-run](./docs/demo.txt)

[![Testes](https://github.com/LuizChockt/legal-markdown-organizer/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/LuizChockt/legal-markdown-organizer/actions/workflows/tests.yml)

**Transforma uma pasta de arquivos jurídicos Markdown em categorias claras, com uma prévia antes de mover qualquer documento.**

Classifica arquivos do primeiro nível por nome ou por um `type` reconhecido no front matter simples. Útil para acervos Markdown e cópias de vaults Obsidian. Não utiliza dependências de execução de terceiros, serviços de IA nem upload de documentos.

## Início rápido

Requer **Python 3.11+**. O código funciona sem instalar dependências:

```bash
git clone https://github.com/LuizChockt/legal-markdown-organizer.git
cd legal-markdown-organizer
python main.py examples --dry-run
```

No Linux/macOS, utiliza `python3` se esse for o comando do Python 3. Os documentos de exemplo são fictícios. O dry-run lê e planeja sem criar pastas nem mover arquivos.

Os três exemplos produzem estes destinos:

```text
agravo_instrumento.md -> Agravos/agravo_instrumento.md
despacho.md -> Despachos/despacho.md
recurso_especial.md -> Recursos/recurso_especial.md
```

[Saída completa registrada](./docs/demo.txt).

## Organizar teu acervo

Começa por uma cópia com backup. Confere a prévia antes de executar sem `--dry-run`:

```powershell
# Windows PowerShell — substitui o caminho pela tua pasta
python main.py "D:\Notes\Legal" --dry-run
python main.py "D:\Notes\Legal"
```

```bash
# Linux / macOS — substitui o caminho pela tua pasta
python3 main.py ./legal-notes --dry-run
python3 main.py ./legal-notes
```

Os movimentos preservam os bytes e acrescentam sufixos numéricos em colisões. **Não existe comando de desfazer**. Mover um arquivo pode quebrar links relativos; o organizador não os reescreve.

## Classificação e escopo

| Regra | Comportamento |
| --- | --- |
| `type` reconhecido no front matter | Tem prioridade sobre o nome, como `type: agravo`. |
| Nome do arquivo | Palavras-chave sem distinção de acentos, com prioridade explícita. |
| Documento desconhecido | Categoria `Outros`. |
| Seleção de arquivos | `.md` do primeiro nível; `.txt` opcional com `--include-txt`. |
| Subpastas existentes | Não são percorridas nem reorganizadas. |
| Conteúdo e links | Bytes preservados; destinos dos links não são atualizados. |

As categorias incluem petições, despachos, sentenças, agravos, recursos, contratos e outras. O leitor de front matter aceita apenas um subconjunto de YAML. [Categorias e regras completas](./docs/reference.md#legal-categories).

## Desenvolvimento e testes

Cria um ambiente virtual:

```bash
python -m venv .venv
```

**Windows PowerShell**, sem ativar scripts:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\legal-organizer.exe --help
```

**Linux / macOS**:

```bash
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest
.venv/bin/legal-organizer --help
```

`pytest` é uma dependência de desenvolvimento. A suíte verifica prioridades, metadados, Unicode, colisões, snapshots de dry-run, preservação dos bytes, falhas de cópia e execução real da CLI. O GitHub Actions usa Python **3.11 e 3.14** em **Linux, Windows e macOS**.

[Arquitetura e uso detalhado](./docs/reference.md#project-structure) · [Contribuição](./CONTRIBUTING.md) · [Segurança](./SECURITY.md) · [Licença MIT](./LICENSE)
