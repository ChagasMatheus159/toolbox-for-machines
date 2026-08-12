# Brazilian Private Credit Data Resources

> **Eyes and ears for credit analysis** — where an AI agent finds the raw material for
> Brazilian private credit underwriting: emissões, escrituras, covenants, informes de
> agente fiduciário, ratings, curvas e balanços.
>
> Complementa o [00_CORE — Brazilian Private Credit Underwriting Framework](../../Framework%20-%20Crédito/Framework_Credito_BWAG/00_CORE_Brazilian_Private_Credit_Underwriting_Framework.md)
> e o fluxo de execução (06F): cada seção do núcleo (§3-§47) tem aqui a FONTE de dado.

---

## 1. Emissões (debêntures, CRIs, CRAs) — ANBIMA

| Fonte | URL | O que tem | Uso no núcleo |
|---|---|---|---|
| **ANBIMA Data** | `https://data.anbima.com.br/debentures` | Todas as emissões: código, spread, indexador, vencimento, volume, agente fiduciário | §20 Identification |
| **ANBIMA Data (CRI)** | `https://data.anbima.com.br/certificados-de-recebiveis-imobiliarios` | CRIs por securitizadora | §20 |
| **ANBIMA Data (CRA)** | `https://data.anbima.com.br/certificados-de-recebiveis-do-agronegocio` | CRAs | §20 |
| **Debêntures.com.br** | `https://www.debentures.com.br/emissoesdebentures/consultaemissoesbusca.asp` | Base histórica completa (antiga, mantida) | §20, §13 |

**Dica agente:** ANBIMA Data responde a consultas por CNPJ do emissor e por nome.
Coletar: código, série, emissão, vencimento, spread, indexador, volume, agente fiduciário.

---

## 2. Escrituras e informes de agente fiduciário

### 2.1 Sites dos agentes (a fonte canônica de covenants, EOD, garantias)

| Agente | URL | Observação |
|---|---|---|
| **Pentágono** (maior) | `https://pentagonotrustee.com.br/` | Informes trimestrais + relatório anual por emissão. Buscar por emissor. |
| **Vórtx** | `https://www.vortx.com.br/` | Informes + escrituras |
| **Oliveira Trust** | `https://www.oliveiratrust.com.br/` | Informes |
| **Itaú/Itaú Corretora** | site institucional | Relatórios de agente |
| **B3 (emissões registradas)** | `https://www.b3.com.br/` | Consulta de emissões listadas |

**O que cada informe traz (e que nenhuma outra fonte tem):**
- **Covenants MEDIDOS** (valor atual vs threshold — o "headroom" real, §24)
- Status de adimplência / eventos de default (§26)
- Composição da dívida da emissão
- Relatório anual do agente (obrigatório CVM, artigo 68 Lei 6.404/76)

### 2.2 Escrituras no RI da empresa
Muitas empresas publicam as escrituras no próprio RI (fatos relevantes / central de downloads):
- Padrão: `ri.{empresa}.com.br` → "Central de Resultados" ou "Informações Financeiras" → "Escrituras"
- Exemplo Movida: 25ª emissão (19/jan/2026) publicada no RI — traz **fiança da operacional**, covenant DL/EBITDA ≤ 4,0x trimestral, agente Pentágono

---

## 3. Ratings e análises de crédito de bancos

| Fonte | URL | O que tem |
|---|---|---|
| **Moody's Local** | `https://moodyslocal.com.br/` | Comunicados de rating + **resumo dos covenants e estrutura** (PDF público) |
| **S&P Global** | `https://www.spglobal.com/ratings/` | Ratings nacionais BR |
| **Fitch Ratings** | `https://www.fitchratings.com/` | Ratings + relatórios |
| **Santander Credit Research** | `cms.santander.com.br` (PDFs públicos) | **Análises de crédito completas de bancos** (ex: Lar Cooperativa — alavancagem, covenants, vencimentos) |
| **XP Research (renda fixa)** | `conteudos.xpi.com.br/renda-fixa/relatorios/` | Análises de crédito (ex: Simpar) |
| **Itaú BBA / BTG Research** | sites institucionais | Relatórios de crédito |

**Dica agente:** bancos publicam "Risco de crédito em foco" (Santander) e relatórios de renda fixa (XP/Itaú) **gratuitos e indexados** — são análises de crédito prontas com os números que o núcleo pede (alavancagem, ICR, covenants, vencimentos). Buscar `{empresa} risco de crédito PDF` ou `{empresa} análise de crédito site:xpi.com.br`.

---

## 4. Balanços e releases (RI-first)

| Fonte | URL | O que tem |
|---|---|---|
| **RI da empresa** | `ri.{empresa}.com.br` | Releases trimestrais, DFs, ITRs, transcrições — **fonte primária** |
| **MZ API** | `https://api.mz.com/` (quando o RI usa MZ) | Download em massa de releases (200+ PDFs) |
| **BRAPI** | `https://brapi.dev` | Dados estruturados: DRE, balanço, DFC, market cap, histórico de preços (para Merton §37) |
| **CVM (fallback)** | `https://www.rad.cvm.gov.br/ENET/` | DFs/ITRs — usar só como fallback (unidades em milhares confundem!) |

**Lições de extração (importantes):**
- CVM ITR/DFP reporta em **milhares** (RDOR3 caixa 9,4M = R$ 9,4B real)
- EBITDA **trimestral vs DL anual** infla/achata alavancagem — sempre usar LTM ou o número do covenant
- Dívida **ajustada (covenant)** ≠ dívida econômica (inclui arrendamento, confirming, put)

---

## 5. Cooperativas e fechadas (sem RI)

| Fonte | URL | O que tem |
|---|---|---|
| Site institucional | `{empresa}.com.br/institucional/relatorios-de-balanco` | Balanços auditados (LAR, J. Macêdo...) |
| **Globo Rural** | `globorural.globo.com` | Resultados de cooperativas |
| **Relatórios de banco** | Santander/XP (ver §3) | Análises de crédito de fechadas |
| **Prospectos de CRA/CRI** | ANBIMA + sites dos coordenadores (Itaú, Bradesco BBI) | Dados completos da emissora no prospecto |

---

## 6. Curva de crédito e mercado secundário

| Fonte | URL | O que tem |
|---|---|---|
| **ANBIMA (curva de debêntures)** | `https://data.anbima.com.br/curva-de-debentures` | Curva por rating — benchmark de spread (§39) |
| **ANBIMA (preços)** | `https://data.anbima.com.br/precos` | PU dos papéis (marcação a mercado) |
| **B3 (tesouro direto/curva)** | `https://www.b3.com.br/` | Curva DI/IPCA |

---

## 7. Macro e cenários (§29-33)

| Fonte | URL | O que tem |
|---|---|---|
| **BCB Focus** | `https://www.bcb.gov.br/controleinflacao/historicotaxasjuros` | Selic atual + expectativas |
| **BCB SGS** | `https://www3.bcb.gov.br/sgspub/` | Séries (Selic 432, IPCA 433, câmbio 1...) |

---

## Workflow recomendado por empresa (ordem do núcleo)

```
1. RI da empresa → releases + DFs (fonte primária)
2. Agente fiduciário (Pentágono/Vórtx) → escrituras + informes (covenants MEDIDOS)
3. Moody's Local/Santander/XP → rating + análise de crédito pronta (validação)
4. ANBIMA Data → todas as emissões (spread, vencimento, volume)
5. BRAPI → market cap + histórico (Merton)
6. Santander "Risco de crédito em foco" → fechadas e validação cruzada
```

> **Regra de ouro:** o informe do agente fiduciário é a ÚNICA fonte com o covenant MEDIDO.
> Rating de agência é a ÚNICA com análise de crédito pronta (mas tem conflito de interesse).
> A combinação das duas + o release da empresa = o que o 00_CORE pede.
