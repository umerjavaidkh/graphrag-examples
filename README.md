# Customer Graph — GraphRAG Setup Guide

> **Base repository:** https://github.com/neo4j-product-examples/graphrag-examples/tree/main/customer-graph
>
> This guide adapts the original tutorial to run on **Neo4j Community Edition via Docker** instead of AuraDB Professional. All code changes required to make this work are documented in [`CODE_CHANGES.md`](./CODE_CHANGES.md).

---

## What This Project Does

Builds a GraphRAG (Graph Retrieval-Augmented Generation) system over a fashion retail dataset by combining:

- **Unstructured data** — PDFs (fashion catalog, credit notes) extracted into a knowledge graph using LLM entity extraction
- **Structured data** — CSV files (customers, orders, articles, products, suppliers) imported as graph nodes and relationships
- **Vector embeddings** — Product descriptions embedded with OpenAI for semantic search
- **Agentic Q&A** — A Semantic Kernel agent that answers natural language questions by traversing the graph

---

## Why Docker Community Instead of AuraDB

The original tutorial uses **AuraDB Professional** which provides:
- Aura Importer (GUI-based CSV-to-graph tool)
- GenAI plugin for in-database vector embedding
- Graph Data Science (GDS) plugin

We replace all of this with:
- **Manual `LOAD CSV` Cypher queries** instead of Aura Importer
- **Python + OpenAI batched API calls** instead of GenAI plugin
- **`graph-data-science` Docker plugin** for community GDS support

---

## Prerequisites

- Python 3.13+ (only needed for the manual path)
- Docker Desktop installed and running
- OpenAI API key
- Git

---

## Two Ways to Run

You can run this project either way — pick one:

- **🚀 Quick Start (Docker Compose)** — the entire system (database + Python env + full graph build + agent) comes up with a few commands. Best for just trying it out. See below.
- **🛠️ Manual Setup (Step-by-step)** — run each step yourself for full control / learning. See [Step 1](#step-1--clone-the-repository) onward.

Both paths use the same code and produce the same graph.

---

## 🚀 Quick Start with Docker Compose

Everything in the manual guide below (Steps 4, 6, 7, 8, 9, 10) is automated here. The only manual touch-points are cloning the repo and pasting your OpenAI key.

### Runs as a separate, isolated instance (no conflicts)

This stack is intentionally namespaced so it can run **alongside any existing Neo4j** you already have in Docker. Nothing here reuses the default names or ports:

| Resource | This project | Default / your existing Neo4j |
|---|---|---|
| Compose project | `customer-graphrag` | — |
| Container name | `customer-graphrag-neo4j` | `neo4j` |
| Browser (host port) | **7475** → `http://localhost:7475` | 7474 |
| Bolt (host port) | **7688** → `bolt://localhost:7688` | 7687 |
| Data volume | `customer-graphrag_neo4j_data` | — |
| Logs volume | `customer-graphrag_neo4j_logs` | — |
| Network | `customer-graphrag_default` | — |

- Login for **this** instance: `neo4j` / `password123`.
- The app containers reach the DB over the internal Compose network (`bolt://neo4j:7687`), which is private to this project and never touches the host's `7687`.
- Your existing Neo4j on `7474`/`7687` keeps running, untouched.

> Want different host ports? Edit the `ports:` mappings under the `neo4j` service in `docker-compose.yml` (left side = host port).

**1. Clone and enter the project**

```bash
git clone https://github.com/neo4j-product-examples/graphrag-examples.git
cd graphrag-examples/customer-graph
```

**2. Add your OpenAI key**

```bash
cp .env.example .env
# edit .env and set OPENAI_API_KEY=sk-...
```

> You do **not** need to change `NEO4J_URI` — Docker Compose automatically points the app at the `neo4j` container.

**3. Start the Neo4j database**

```bash
docker compose up -d neo4j
```

This launches Neo4j Community with all plugins (APOC, APOC Extended, GDS), mounts the CSVs into the import directory, and waits until the DB is healthy. Browser available at **http://localhost:7475** (`neo4j` / `password123`) — see the isolation table above for why this won't clash with any existing Neo4j.

**4. Build the graph (one-time, takes several minutes)**

```bash
docker compose run --rm pipeline
```

This runs the full ingestion pipeline in order — unstructured PDF ingest → structured CSV import → cross-linking → embeddings + vector index (manual Steps 6–9).

**5. Chat with the agent**

You have two options:

**Option A — Browser chat UI (recommended)**

```bash
docker compose up -d web
```

Then open **http://localhost:8501**. You get a chat window with clickable sample questions in the sidebar. Stop it later with `docker compose stop web`.

![Browser chat UI answering a supplier-returns question](customer-graph/assets/chat-ui.png)

**Option B — Command-line chat**

```bash
docker compose run --rm agent
```

Type questions at the `User >` prompt; type `exit` to quit.

### Test the Agent

These questions each exercise a different agent capability — a good way to verify the graph built correctly:

| # | Question | Capability exercised |
|---|----------|----------------------|
| 1 | `What are some good sweaters for spring? Nothing too warm please!` | Semantic vector search (`search_products`) |
| 2 | `Which suppliers have the highest number of returns (i.e., credit notes)?` | Supplier returns ranking (`get_top_suppliers_by_returns`) |
| 3 | `What are the top 3 most returned products for supplier 1616? Get those product codes and find other suppliers who have less returns for each product I can use instead.` | Product → supplier swap analysis |
| 4 | `Can you run a customer segmentation analysis?` | GDS community detection (`create_customer_segments`) |
| 5 | `What are the most common product types purchased for each segment?` | Follow-up reasoning over segments |
| 6 | `How many customers, orders, and articles are in the database?` | Open-ended text-to-Cypher (`answer_general_question`) |
| 7 | `For the largest customer group, make a creative spring promotional campaign highlighting recommended products. Draft it as an email.` | Recommendations + creative generation |

> If a question returns empty results, that step's data likely didn't load — re-run `docker compose run --rm pipeline` (or `docker compose down -v` first for a clean slate).

**Tear down** (keeps data volumes):

```bash
docker compose down
```

To also delete the graph data: `docker compose down -v`.

> **Note:** What the Quick Start automates — the manual guide imports CSVs via `docker cp` + hand-run `LOAD CSV` queries in the Browser (Steps 7–8). Docker Compose mounts `data/` into Neo4j's import dir and runs those same queries as scripts (`load_structured.py`, `create_cross_links.py`), so no manual Cypher is needed.

### Quick Start Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `no configuration file provided: not found` | Running `docker compose` from the repo root | `cd customer-graph` first — that's where `docker-compose.yml` lives |
| `dependency failed to start: container ... exited (1)` | Neo4j couldn't start | Check `docker logs customer-graphrag-neo4j` |
| `openai.AuthenticationError: 401 ... Incorrect API key` | Bad `OPENAI_API_KEY` in `.env` | Ensure the line is exactly `OPENAI_API_KEY=sk-...` (no duplicated `OPENAI_API_KEY=` prefix, no quotes/spaces) |
| Port `7475`/`7688` already in use | Another process is using the mapped host port | Edit the `ports:` mapping under the `neo4j` service in `docker-compose.yml` |

---

## 🛠️ Manual Setup

The remaining steps describe the manual, step-by-step workflow. Skip these if you used the Quick Start above.

## Step 1 — Clone the Repository

```bash
git clone https://github.com/neo4j-product-examples/graphrag-examples.git
cd graphrag-examples/customer-graph
```

---

## Step 2 — Create Python Virtual Environment

```bash

brew unlink python@3.14
brew link --overwrite python@3.13

python3 -m venv venv
source venv/bin/activate   # Mac/Linux

cd customer-graph
pip install -r requirements.txt
```

---

## Step 3 — Configure Environment Variables

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=password123
OPENAI_API_KEY=sk-...
```

---

## Step 4 — Start Neo4j via Docker

Instead of AuraDB, run Neo4j Community Edition locally. This single command sets up Neo4j with all required plugins (APOC, APOC Extended, Graph Data Science) and creates named volumes so your data persists across container restarts:

```bash
docker run -d \
  --name neo4j \
  -p 7474:7474 \
  -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password123 \
  -e NEO4J_PLUGINS='["apoc", "apoc-extended", "graph-data-science"]' \
  -e NEO4J_dbms_security_procedures_unrestricted='apoc.*,genai.*,gds.*' \
  -e NEO4J_dbms_security_procedures_allowlist='apoc.*,genai.*,gds.*' \
  -e NEO4J_dbms_default__listen__address=0.0.0.0 \
  -e NEO4J_dbms_default__advertised__address=localhost \
  -v docker_neo4j_data:/data \
  -v docker_neo4j_logs:/logs \
  neo4j:5.18-community
```

![](img/docker_image.png)

Wait ~30 seconds for startup, then open Neo4j Browser at **http://localhost:7474**
Login: `neo4j` / `password123`

Verify plugins loaded:
```cypher
RETURN gds.version()
```
![](img/noe4j_local_image.png)


> **Note:** The `genai` plugin is not available on Neo4j 5.18 Community. We handle embeddings in Python instead — see Step 9.

---

## Step 5 — Apply Code Fixes (Skip no need)

The `neo4j-graphrag` library has breaking API changes since the original tutorial was written. Before running any scripts, apply all fixes documented in [`CODE_CHANGES.md`](./CODE_CHANGES.md).

Files are updated already no need to change any code:
- `rag_schema_from_onto.py` — renamed schema classes
- `unstructured_ingest.py` — deprecated imports + pass schema directly
- `ingest_post_processing.py` — replace genai plugin with Python embeddings
- `graphrag/retail_service.py` — fix relationship paths + add missing methods
- `graphrag/retail_plugin.py` — expose new agent tool

---

## Step 6 — Run Unstructured PDF Ingestion

This reads the PDFs (`data/credit-notes.pdf`, `data/fashion-catalog.pdf`), uses the ontology in `ontos/customer.ttl` to guide LLM entity extraction, and writes a knowledge graph to Neo4j:

```bash
python unstructured_ingest.py
```

This takes several minutes. When complete, verify in Neo4j Browser:

```cypher
MATCH (n) RETURN labels(n), count(n) ORDER BY count(n) DESC
```

You should see nodes tagged `__KGBuilder__` and `__Entity__` with labels like `CreditNote`, `Order`, `Article`, `Product`.

---

## Step 7 — Import Structured CSV Data

The original tutorial uses **Aura Importer** (AuraDB-only GUI tool). We replace it with `LOAD CSV` Cypher queries.

### 7a — Copy CSVs into the Docker Container

```bash
for f in data/articles.csv data/customers.csv data/order-details.csv data/suppliers.csv data/products.csv; do
    docker cp $f neo4j:/var/lib/neo4j/import/
done
```

Verify files are inside the container:

```bash
docker exec neo4j ls /var/lib/neo4j/import/
```

### 7b — Run LOAD CSV Queries in Neo4j Browser

> **Scripted alternative:** instead of pasting the blocks below, you can run `python load_structured.py` (after copying the CSVs in 7a). It executes these exact queries in order.

Run each block **one at a time, in this exact order**:

**1. Suppliers**
```cypher
LOAD CSV WITH HEADERS FROM 'file:///suppliers.csv' AS row
MERGE (s:Supplier {supplierId: row.supplierId})
SET s.name = row.supplierName,
    s.address = row.supplierAddress;
```

**2. Products**
```cypher
LOAD CSV WITH HEADERS FROM 'file:///products.csv' AS row
MERGE (p:Product {productCode: row.productCode})
SET p.name = row.prodName,
    p.productTypeNo = row.productTypeNo,
    p.productTypeName = row.productTypeName,
    p.productGroupName = row.productGroupName,
    p.garmentGroupNo = row.garmentGroupNo,
    p.garmentGroupName = row.garmentGroupName,
    p.description = row.detailDesc;
```

**3. Articles** (links to Products and Suppliers)
```cypher
LOAD CSV WITH HEADERS FROM 'file:///articles.csv' AS row
MERGE (a:Article {articleId: row.articleId})
SET a.productCode = row.productCode,
    a.name = row.prodName,
    a.productTypeName = row.productTypeName,
    a.graphicalAppearanceNo = row.graphicalAppearanceNo,
    a.graphicalAppearanceName = row.graphicalAppearanceName,
    a.colourGroupCode = row.colourGroupCode,
    a.colourGroupName = row.colourGroupName
WITH a, row
MATCH (p:Product {productCode: row.productCode})
MERGE (a)-[:VARIANT_OF]->(p)
WITH a, row
MATCH (s:Supplier {supplierId: row.supplierId})
MERGE (a)-[:SUPPLIED_BY]->(s);
```

**4. Customers**
```cypher
LOAD CSV WITH HEADERS FROM 'file:///customers.csv' AS row
MERGE (c:Customer {customerId: row.customerId})
SET c.firstName = row.fn,
    c.active = row.active,
    c.clubMemberStatus = row.clubMemberStatus,
    c.fashionNewsFrequency = row.fashionNewsFrequency,
    c.age = toInteger(row.age),
    c.postalCode = row.postalCode;
```

**5. Orders, Transactions and Relationships**

> ⚠️ **Important:** Use `toInteger(row.orderId)` — this is critical for linking with PDF-extracted entities in the next step.

```cypher
LOAD CSV WITH HEADERS FROM 'file:///order-details.csv' AS row
MERGE (o:Order {orderId: toInteger(row.orderId)})
WITH o, row
MERGE (t:Transaction {txId: row.txId})
SET t.date = row.tDat,
    t.price = toFloat(row.price),
    t.salesChannelId = row.salesChannelId
MERGE (o)-[:HAS_TRANSACTION]->(t)
WITH o, t, row
MATCH (c:Customer {customerId: row.customerId})
MERGE (c)-[:PLACED]->(o)
WITH o, t, row
MATCH (a:Article {articleId: row.articleId})
MERGE (t)-[:CONTAINS]->(a);
```

---

## Step 8 — Create Cross-Links Between Structured and Unstructured Data

The LLM extracts `orderId` and `articleId` as integers from PDFs, but `LOAD CSV` imports them as strings by default. This causes joins between structured (CSV) and unstructured (PDF) nodes to silently fail. Run these three queries in Neo4j Browser to fix the types and create the cross-links.

> **Scripted alternative:** run `python create_cross_links.py` to apply all three queries (and verify the link counts) automatically.


**Fix Article ID type (string → integer):**
```cypher
MATCH (a:Article) WHERE NOT '__KGBuilder__' IN labels(a)
SET a.articleId = toInteger(a.articleId)
```

**Link CreditNotes to structured Articles:**
```cypher
MATCH (c:CreditNote)-[:REFUND_OF_ARTICLE]->(a1:Article)
WHERE '__KGBuilder__' IN labels(a1)
MATCH (a2:Article) WHERE NOT '__KGBuilder__' IN labels(a2)
AND a2.articleId = a1.articleId
MERGE (c)-[:REFUND_OF_ARTICLE_STRUCTURED]->(a2)
```

**Link CreditNotes to Suppliers via the Order chain:**
```cypher
MATCH (c:CreditNote)-[:REFUND_FOR_ORDER]->(o1:Order)
MATCH (o2:Order)-[:HAS_TRANSACTION]->(t:Transaction)-[:CONTAINS]->(a:Article)-[:SUPPLIED_BY]->(s:Supplier)
WHERE o1.orderId = o2.orderId
MERGE (c)-[:RETURNED_TO_SUPPLIER]->(s)
```

Verify both links were created:
```cypher
MATCH (c:CreditNote)-[:REFUND_OF_ARTICLE_STRUCTURED]->(a) RETURN count(*) AS articleLinks
```
```cypher
MATCH (c:CreditNote)-[:RETURNED_TO_SUPPLIER]->(s) RETURN count(*) AS supplierLinks
```

Both should return values greater than 0.

---

## Step 9 — Run Post-Processing (Embeddings + Vector Index)

The original tutorial uses the `genai.vector.encodeBatch` Neo4j procedure (not available on Community 5.18). The updated `ingest_post_processing.py` generates embeddings directly via the OpenAI Python SDK in batches of 500:

```bash
python ingest_post_processing.py
```

Expected output:
```
Formatting Product Text
Creating Product Text Embeddings
  Found 8018 products to embed
  Embedded 500/8018 products
  Embedded 1000/8018 products
  ...
  Embedded 8018/8018 products
Creating Product Vector Index
Waiting for vector index to come online...
Done.
```

---

## Step 10 — Run the Agent

You can use either the command-line agent or the browser chat UI.

**Command line:**

```bash
cd graphrag
python cli_agent.py
```

**Browser chat UI (Streamlit):**

```bash
cd graphrag
streamlit run app.py
```

Then open the URL Streamlit prints (default **http://localhost:8501**). The UI has a chat window plus clickable sample questions in the sidebar. (With Docker, use `docker compose up -d web` instead — see the Quick Start.)

![Browser chat UI answering a supplier-returns question](customer-graph/assets/chat-ui.png)

The agent uses Semantic Kernel with OpenAI `gpt-4o-mini` and has access to these tools:
- **`search_products`** — semantic vector search over product descriptions
- **`recommend_products`** — graph-based collaborative filtering
- **`create_customer_segments`** — GDS Leiden community detection
- **`get_product_order_supplier_info`** — order and return stats by product
- **`get_supplier_order_product_info`** — order and return stats by supplier
- **`get_top_suppliers_by_returns`** — ranks all suppliers by credit note count
- **`answer_general_question`** — text-to-Cypher for arbitrary graph queries

### Sample Questions

```
**Q: What are some good sweaters for spring? Nothing too warm please!**

Here are some great lightweight sweaters perfect for spring:

| # | Product | Description |
|---|---------|-------------|
| 1 | [Queen Sweater](https://representative-domain/product/677930) | Lightweight sweatshirt fabric with ribbing around neckline, cuffs, and hem |
| 2 | [Stressan Light Knit Jumper](https://representative-domain/product/358483) | Light, fine, soft knit with long sleeves, raw edges, rounded hem |
| 3 | [King Sweater](https://representative-domain/product/716999) | Short top in lightweight sweatshirt fabric with ribbed details |
| 4 | [Sorbet Sweatshirt](https://representative-domain/product/822888) | Boxy-style top with round neckline and low dropped shoulders |
| 5 | [Grace Sweater](https://representative-domain/product/796033) | Soft knit with low dropped shoulders and ribbed neckline |
| 6 | [Sandrine](https://representative-domain/product/827370) | Cotton blend top with wide ribbing around neckline |
| 7 | [Puff Sweater](https://representative-domain/product/783925) | Soft fine knit with wool, relaxed fit, dropped shoulders |
| 8 | [Buffy Lace Sweater](https://representative-domain/product/758790) | Soft rib knit with lace sections and dropped shoulders |
```

```
Which suppliers have the highest number of returns (i.e., credit notes)?
```
```
What are the top 3 most returned products for supplier 1616? Get those product codes and find other suppliers who have less returns for each product I can use instead.
```
```
Can you run a customer segmentation analysis?
```
```
What are the most common product types purchased for each segment?
```
```
For the largest group make a creative spring promotional campaign for them highlighting recommended products. Draft it as an email.
```

---

## Troubleshooting

| Error | Cause | Fix |
|---|---|---|
| `ImportError: cannot import name 'SchemaEntity'` | Library API change | Rename to `NodeType` — see CODE_CHANGES.md |
| `ImportError: cannot import name 'SchemaConfig'` | Library API change | Rename to `GraphSchema` — see CODE_CHANGES.md |
| `ValidationError: List should have at least 1 item` | Pydantic now rejects empty properties list | Use `make_node()` helper — see CODE_CHANGES.md |
| `TypeError: missing argument 'node_types'` | `create_schema_model` params renamed | See CODE_CHANGES.md |
| `AttributeError: 'GraphSchema' has no attribute 'entities'` | Field renamed | Pass `schema=neo4j_schema` directly to `SimpleKGPipeline` |
| `ProcedureNotFound: genai.vector.encodeBatch` | GenAI plugin not on Community 5.18 | Use Python OpenAI embeddings — see CODE_CHANGES.md |
| Supplier/article returns always 0 | ID type mismatch between CSV (string) and PDF (integer) | Run Step 8 cross-link queries |
| `gds.graph.drop` not found | GDS plugin missing | Add `graph-data-science` to Docker plugins — Step 4 |
| GDS projection fails | Wrong relationship names in original code | Fix `ORDERED/CONTAINS` → `PLACED/HAS_TRANSACTION` — see CODE_CHANGES.md |
| Agent says "no supplier data available" | Missing `get_top_suppliers_by_returns` tool | Add new method — see CODE_CHANGES.md |
