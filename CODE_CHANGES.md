# Code Changes

> All changes required to adapt the [original tutorial](https://github.com/neo4j-product-examples/graphrag-examples/tree/main/customer-graph) to run on Neo4j Community Edition via Docker.
>
> Two categories of changes:
> 1. **Library API fixes** — `neo4j-graphrag` renamed classes and parameters since the tutorial was written
> 2. **Community Edition fixes** — replacing AuraDB-only features with open alternatives

---

## `rag_schema_from_onto.py`

### 1. Update imports — classes renamed

```python
# BEFORE
from neo4j_graphrag.experimental.components.schema import (
    SchemaBuilder, SchemaEntity, SchemaProperty, SchemaRelation, SchemaConfig
)

# AFTER
from neo4j_graphrag.experimental.components.schema import (
    SchemaBuilder, NodeType, PropertyType, RelationshipType, GraphSchema
)
```

### 2. Add helper functions — Pydantic now rejects empty `properties` list

Add these before `getSchemaFromOnto`:

```python
def make_node(label, description, props):
    kwargs = {'label': label, 'description': description}
    if props:
        kwargs['properties'] = props
    return NodeType(**kwargs)

def make_rel(label, description):
    return RelationshipType(label=label, description=description)
```

### 3. Update `getPropertiesForClass` — `SchemaProperty` → `PropertyType`

```python
def getPropertiesForClass(g, cat):
    props = []
    for dtp in g.subjects(RDFS.domain, cat):
        if (dtp, RDF.type, OWL.DatatypeProperty) in g:
            propName = getLocalPart(dtp)
            propDesc = next(g.objects(dtp, RDFS.comment), "")
            props.append(PropertyType(
                name=propName,
                type=convert_to_di_data_type(next(g.objects(dtp, RDFS.range), "")),
                description=propDesc
            ))
    return props
```

### 4. Update `getSchemaFromOnto` — use helpers and fix `create_schema_model` params

```python
def getSchemaFromOnto(path) -> GraphSchema:
    g = Graph()
    g.parse(path)
    schema_builder = SchemaBuilder()
    classes = {}
    entities = []
    rels = []
    triples = []

    for cat in g.subjects(RDF.type, OWL.Class):
        classes[cat] = None
        entities.append(make_node(
            label=getLocalPart(cat),
            description=next(g.objects(cat, RDFS.comment), ""),
            props=getPropertiesForClass(g, cat)
        ))
    for cat in g.objects(None, RDFS.domain):
        if not cat in classes.keys():
            classes[cat] = None
            entities.append(make_node(
                label=getLocalPart(cat),
                description=next(g.objects(cat, RDFS.comment), ""),
                props=getPropertiesForClass(g, cat)
            ))
    for cat in g.objects(None, RDFS.range):
        if not (cat.startswith("http://www.w3.org/2001/XMLSchema#") or cat in classes.keys()):
            classes[cat] = None
            entities.append(make_node(
                label=getLocalPart(cat),
                description=next(g.objects(cat, RDFS.comment), ""),
                props=getPropertiesForClass(g, cat)
            ))

    for op in g.subjects(RDF.type, OWL.ObjectProperty):
        rels.append(make_rel(
            label=getLocalPart(op),
            description=next(g.objects(op, RDFS.comment), "")
        ))

    for op in g.subjects(RDF.type, OWL.ObjectProperty):
        relname = getLocalPart(op)
        doms = [getLocalPart(dom) for dom in g.objects(op, RDFS.domain) if dom in classes]
        rans = [getLocalPart(ran) for ran in g.objects(op, RDFS.range) if ran in classes]
        for d in doms:
            for r in rans:
                triples.append((d, relname, r))

    # BEFORE: create_schema_model(entities=..., relations=..., potential_schema=...)
    # AFTER:
    return schema_builder.create_schema_model(
        node_types=entities,
        relationship_types=rels,
        patterns=triples
    )
```

---

## `unstructured_ingest.py`

### 1. Update deprecated imports

```python
# BEFORE
from neo4j_graphrag.experimental.components.pdf_loader import DataLoader
from neo4j_graphrag.experimental.components.types import PdfDocument, DocumentInfo

# AFTER
from neo4j_graphrag.experimental.components.data_loader import DataLoader, PdfLoader
from neo4j_graphrag.experimental.components.types import LoadedDocument, DocumentInfo
```

### 2. Update `PdfLoaderWithPageBreaks` — `PdfDocument` → `LoadedDocument`

```python
# BEFORE
class PdfLoaderWithPageBreaks(DataLoader):
    async def run(self, filepath: Path) -> PdfDocument:
        ...
        return PdfDocument(text=text, document_info=DocumentInfo(path=filepath))

# AFTER
class PdfLoaderWithPageBreaks(DataLoader):
    async def run(self, filepath: Path) -> LoadedDocument:
        ...
        return LoadedDocument(text=text, document_info=DocumentInfo(path=filepath))
```

### 3. Pass `GraphSchema` directly to `SimpleKGPipeline`

```python
# BEFORE
kg_builder = SimpleKGPipeline(
    llm=llm,
    driver=driver,
    embedder=embedder,
    entities=list(neo4j_schema.entities.values()),
    relations=list(neo4j_schema.relations.values()),
    potential_schema=...,
    from_pdf=True,
)

# AFTER — schema object passed directly, no separate entities/relations args
kg_builder = SimpleKGPipeline(
    llm=llm,
    driver=driver,
    embedder=embedder,
    schema=neo4j_schema,
    from_pdf=True,
)
```

---

## `ingest_post_processing.py`

### Full replacement — genai plugin not available on Community 5.18

The original uses `genai.vector.encodeBatch` (Neo4j GenAI plugin). Replace with Python/OpenAI batched embeddings:

```python
import os
from dotenv import load_dotenv
from neo4j import GraphDatabase
from openai import OpenAI

load_dotenv()
NEO4J_URI = os.getenv("NEO4J_URI")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD")

driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))

# Format product text properties
print("Formatting Product Text")
driver.execute_query('''
MATCH(p:Product)
OPTIONAL MATCH(p)-[:PART_OF]->(c:ProductCategory)
OPTIONAL MATCH(p)-[:PART_OF]->(t:ProductType)
SET p.text = '##Product\n' +
    'Name: ' + coalesce(p.name,'') + '\n' +
    'Type: ' + coalesce(t.name, '') + '\n' +
    'Category: ' + coalesce(c.name, '') + '\n' +
    'Description: ' + coalesce(p.description, ''),
    p.url = 'https://representative-domain/product/' + p.productCode
RETURN count(p) AS propertySetCount
''')

# Generate embeddings in batches via OpenAI Python SDK
# Replaces: genai.vector.encodeBatch (not available on Community 5.18)
print("Creating Product Text Embeddings")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

with driver.session(database="neo4j") as session:
    products = session.run(
        "MATCH (n:Product) WHERE size(n.description) <> 0 RETURN elementId(n) AS id, n.text AS text"
    ).data()

    print(f"  Found {len(products)} products to embed")

    BATCH_SIZE = 500  # reduces 8000+ API calls to ~17 batched calls
    for i in range(0, len(products), BATCH_SIZE):
        batch = products[i:i + BATCH_SIZE]
        response = client.embeddings.create(
            input=[p["text"] for p in batch],
            model="text-embedding-ada-002"
        )
        for j, item in enumerate(response.data):
            session.run(
                "MATCH (n) WHERE elementId(n) = $id CALL db.create.setNodeVectorProperty(n, 'textEmbedding', $vector)",
                id=batch[j]["id"], vector=item.embedding
            )
        print(f"  Embedded {min(i + BATCH_SIZE, len(products))}/{len(products)} products")

# Create vector index
print("Creating Product Vector Index")
driver.execute_query('''
CREATE VECTOR INDEX product_text_embeddings IF NOT EXISTS FOR (n:Product) ON (n.textEmbedding)
OPTIONS {indexConfig: {
 `vector.dimensions`: toInteger($dimension),
 `vector.similarity_function`: 'cosine'
}}
''', dimension=1536)

print("Waiting for vector index to come online...")
driver.execute_query('CALL db.awaitIndex("product_text_embeddings", 300)')

print("Done.")
driver.close()
```

---

## `graphrag/retail_service.py`

### 1. Fix `get_product_order_supplier_info` — wrong relationship paths + type mismatch

```python
# BEFORE
MATCH(p:Product)<-[:VARIANT_OF]-(a:Article)-[:SUPPLIED_BY]->(s)
WHERE p.productCode IN $productCodes
WITH *,
  COUNT {MATCH (:Order)-[:CONTAINS]->(a)} AS numberOfOrders,
  COUNT {MATCH (:CreditNote)-[:REFUND_OF_ARTICLE]-(a)} AS numberOfRefunds

# AFTER — correct path + toString() handles int/string type mismatch
MATCH(p:Product)<-[:VARIANT_OF]-(a:Article)-[:SUPPLIED_BY]->(s)
WHERE p.productCode IN [code IN $productCodes | toString(code)]
WITH *,
  COUNT {MATCH (:Order)-[:HAS_TRANSACTION]->(:Transaction)-[:CONTAINS]->(a)} AS numberOfOrders,
  COUNT {MATCH (:CreditNote)-[:REFUND_OF_ARTICLE_STRUCTURED]->(a)} AS numberOfRefunds
```

### 2. Fix `get_supplier_order_product_info` — wrong relationship paths + type mismatch

```python
# BEFORE
MATCH(p:Product)<-[:VARIANT_OF]-(:Article)-[:SUPPLIED_BY]->(s)
WHERE s.supplierId IN $supplierIds
WITH DISTINCT p, s,
  COUNT {MATCH (:Order)-[:CONTAINS]->()-[:VARIANT_OF]->(p)} AS numberOfOrders,
  COUNT {MATCH (:CreditNote)-[:REFUND_OF_ARTICLE]-()-[:VARIANT_OF]->(p)} AS numberOfRefunds

# AFTER — include article in WITH, correct paths, toString() for type mismatch
MATCH(p:Product)<-[:VARIANT_OF]-(a:Article)-[:SUPPLIED_BY]->(s)
WHERE s.supplierId IN [id IN $supplierIds | toString(id)]
WITH DISTINCT p, s, a,
  COUNT {MATCH (:Order)-[:HAS_TRANSACTION]->(:Transaction)-[:CONTAINS]->(a)} AS numberOfOrders,
  COUNT {MATCH (:CreditNote)-[:REFUND_OF_ARTICLE_STRUCTURED]->(a)-[:VARIANT_OF]->(p)} AS numberOfRefunds
```

### 3. Fix `run_customer_segmentation` — wrong relationship paths in GDS projection

```python
# BEFORE — uses ORDERED and CONTAINS which don't exist in our graph
MATCH(c1:Customer)-[:ORDERED]->()-[:CONTAINS]->(a:Article)
      <-[:CONTAINS]-()<-[:ORDERED]-(c2:Customer)

# AFTER — correct paths matching our CSV import structure
MATCH(c1:Customer)-[:PLACED]->()-[:HAS_TRANSACTION]->(:Transaction)-[:CONTAINS]->(a:Article)
      <-[:CONTAINS]-(:Transaction)<-[:HAS_TRANSACTION]-()<-[:PLACED]-(c2:Customer)
```

### 4. Add new method `get_top_suppliers_by_returns`

The original tutorial has no method to rank all suppliers by returns — the agent had no entry point to answer "which suppliers have the most returns?" without already knowing supplier IDs. Add this method:

```python
async def get_top_suppliers_by_returns(self, limit: int = 10) -> list[SupplierInfo]:
    res = self._driver.execute_query("""
    MATCH (c:CreditNote)-[:RETURNED_TO_SUPPLIER]->(s:Supplier)
    WITH s, count(c) AS totalReturns
    ORDER BY totalReturns DESC
    LIMIT $limit
    RETURN s.supplierId AS supplierId,
        s.name AS name,
        totalReturns,
        0 AS totalOrders,
        [] AS supplierInfos
    """, limit=limit)
    supplier_infos = []
    for item in res.records:
        supplier_infos.append(item.data())
    return supplier_infos
```

---

## `graphrag/retail_plugin.py`

### Add kernel function for new method

```python
@kernel_function
async def get_top_suppliers_by_returns(self, limit: int = 10) -> Annotated[List[SupplierInfo], "A list of suppliers ranked by number of returns/credit notes"]:
    """Get suppliers with the highest number of returns (credit notes).
    Use this when asked which suppliers have the most returns without specific supplier ids."""
    return await self.retail_service.get_top_suppliers_by_returns(limit=limit)
```

---

## Neo4j Browser — Cross-Link Queries

Run these once in Neo4j Browser after completing the CSV import (Step 8 in SETUP_GUIDE.md).

**Why these are needed:** Aura Importer (used in the original tutorial) handles ID type consistency automatically. When using manual `LOAD CSV`, IDs are imported as strings while the LLM extracts them as integers from PDFs — this silently breaks all joins between structured and unstructured nodes.

```cypher
-- 1. Fix Article IDs (string → integer to match PDF-extracted IDs)
MATCH (a:Article) WHERE NOT '__KGBuilder__' IN labels(a)
SET a.articleId = toInteger(a.articleId)
```

```cypher
-- 2. Link PDF CreditNotes to structured CSV Articles
MATCH (c:CreditNote)-[:REFUND_OF_ARTICLE]->(a1:Article)
WHERE '__KGBuilder__' IN labels(a1)
MATCH (a2:Article) WHERE NOT '__KGBuilder__' IN labels(a2)
AND a2.articleId = a1.articleId
MERGE (c)-[:REFUND_OF_ARTICLE_STRUCTURED]->(a2)
```

```cypher
-- 3. Link PDF CreditNotes to structured CSV Suppliers via Order chain
MATCH (c:CreditNote)-[:REFUND_FOR_ORDER]->(o1:Order)
MATCH (o2:Order)-[:HAS_TRANSACTION]->(t:Transaction)-[:CONTAINS]->(a:Article)-[:SUPPLIED_BY]->(s:Supplier)
WHERE o1.orderId = o2.orderId
MERGE (c)-[:RETURNED_TO_SUPPLIER]->(s)
```
