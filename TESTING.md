# Como Testar — flag-service

## Pré-requisitos

- Python 3.10+
- pip

---

## 1. Criar e ativar o ambiente virtual

```powershell
# Dentro de flag-service-main/
python -m venv .venv

# Ativar (Windows PowerShell)
.venv\Scripts\Activate.ps1

# Ativar (Linux/macOS)
source .venv/bin/activate
```

> O prompt muda para `(.venv)` quando o ambiente está ativo.

---

## 2. Instalar dependências de teste

```powershell
pip install -r requirements-test.txt
```

> Os avisos sobre `aws-sam-cli` são inofensivos — não afetam os testes.

---

## 3. Executar os testes

### Só os testes (resultado rápido)
```powershell
python -m pytest tests/ -v
```

### Testes + cobertura no terminal
```powershell
python -m pytest tests/ -v --cov=. --cov-report=term-missing
```

### Testes + cobertura em arquivo JSON
```powershell
python -m pytest tests/ -v --cov=. --cov-report=json:coverage.json
```

### Testes + relatório JUnit XML (formato usado pela pipeline CI)
```powershell
python -m pytest tests/ -v --junitxml=test-results.xml
```

### Tudo junto (equivalente ao que roda na pipeline)
```powershell
python -m pytest tests/ -v --tb=short \
  --junitxml=test-results.xml \
  --cov=. \
  --cov-report=term-missing \
  --cov-report=json:coverage.json
```

---

## 4. Executar lint

### Verificar problemas de estilo e formatação
```powershell
flake8 app.py --max-line-length=120
```

### Ver estatísticas por tipo de problema
```powershell
flake8 app.py --max-line-length=120 --statistics
```

### Exportar em JSON (formato usado pela pipeline CI)
```powershell
flake8 app.py --max-line-length=120 --format=json > flake8-output.json
```

#### Principais códigos do flake8

| Código | Significado |
|--------|-------------|
| `E1xx`  | Indentação |
| `E2xx`  | Espaços em branco |
| `E3xx`  | Linhas em branco |
| `E7xx`  | Statements problemáticos |
| `W2xx`  | Espaços sobrando |
| `W6xx`  | Features deprecadas |

> 💡 O lint **não quebra a pipeline** — apenas reporta no Job Summary.

---

## 5. Calcular complexidade ciclomática

### Resumo no terminal com score por função
```powershell
radon cc app.py -s -a
```

### Exportar em JSON (formato usado pela pipeline CI)
```powershell
radon cc app.py -s -j > radon-output.json
```

### Índice de manutenibilidade
```powershell
radon mi app.py -s
```

#### Legenda de ranks (radon)

| Rank | Score | Risco |
|------|-------|-------|
| A    | 1–5   | 🟢 Baixo |
| B    | 6–10  | 🟡 Moderado |
| C    | 11–15 | 🔴 Alto |
| D/E/F | 16+  | 🔴 Muito alto |

---

## 6. Resultados atuais

| Métrica | Valor |
|---------|-------|
| Testes  | ✅ 19/19 passando |
| Cobertura total | 94% |
| Complexidade média | B (5.14) |
| Função mais complexa | `update_flag` — score 8 |

---

## 7. Desativar o ambiente virtual

```powershell
deactivate
```

---

## 8. Arquivos gerados (não comitar)

Adicione ao `.gitignore`:

```
.venv/
__pycache__/
*.pyc
.coverage
coverage.json
test-results.xml
radon-output.json
```

---

## Estratégia dos testes

Os testes são **unitários** — todas as dependências externas são mockadas:

| Dependência real | Como é simulada nos testes |
|---|---|
| PostgreSQL (psycopg2 pool) | `unittest.mock.patch("psycopg2.pool.SimpleConnectionPool")` |
| auth-service (`/validate`) | `unittest.mock.patch("requests.get")` |

Nenhuma conexão real com banco de dados ou auth-service é feita. Os testes podem rodar sem banco, sem Docker e sem infraestrutura.
