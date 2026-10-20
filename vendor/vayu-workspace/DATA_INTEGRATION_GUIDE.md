# VĀYÚ Productivity Workspace — Enterprise Data Intelligence Extension

**Release:** 19 October 2026. **Operation:** offline / local / read-only. **Cost:** no paid service or new dependencies.

## Start

1. Extract the ZIP into a new folder on Windows; keep the folder structure unchanged.
2. Double-click `Start.cmd` (Python 3.10+). The normal Founder Desk, analytics, knowledge sphere and opt-in gesture control remain present.
3. In **Vāyú Business → Analytics & intelligence**, open the three new tabs:
   - **Capability audit:** 30 code-evidence-based use cases, paths into the inspected VAOS/VYNDI OS GitHub revisions, known closure requirements. Includes 175 additional *opportunity categories*, not installed features.
   - **Source intake:** upload selected source exports, get missing-ID/duplicate-ID counts, matched foreign-key counts, orphan references and missing source-family coverage.
   - **Ledger trace:** navigate imported source records, exact outgoing foreign-key matches and incoming links. Search and inspect full row fields; export the selected imported source as JSON.
4. The original **Overview, Trends, Workload, Kanban, Data quality, Explore, Scenarios, Records, Definitions and Features** views are retained. The previous single-file CSV upload continues to work in those views.

## Export and import records

Export *authorized* **CSV or JSON** records from the appropriate VYNDI OS, VAOS, VEDM or other system. Import **each file** into its matching record family. Keep identifiers as columns. Supported categories:

| Source family | Example ID field | Linking fields in other files |
| --- | --- | --- |
| Sales orders | `sales_order_id` | `sales_order_id` |
| Production job cards | `job_card_id` | `job_card_id` |
| Purchase orders | `purchase_order_id` or `po_id` | `purchase_order_id`, `po_id` |
| Goods receipts | `goods_receipt_id` or `grn_id` | `goods_receipt_id` |
| Sales invoices | `sales_invoice_id` | `sales_invoice_id` |
| Supplier invoices | `supplier_invoice_id` | `supplier_invoice_id` |
| Posted journal lines | `entry_id` / `line_id` | Source-specific journal linking requires further schema mapping |
| Customer receipts | `customer_receipt_id` | Source-specific receipt linking requires further schema mapping |
| Inventory records | `inventory_id` | Not automatically joined on `sku`, as SKU alone is not a unique record ID |
| Quality NCR/CAPA | `ncr_id` or `capa_id` | `ncr_id`, `capa_id` |
| Engineering and VEDM | `evidence_id` or `revision_id` | `evidence_id`, `revision_id` |
| VAOS executions | `execution_id` | `execution_id` |

Sample structure (illustrative, **not a production record**):

```csv
job_card_id,sales_order_id,status
DEMO-JC1,DEMO-SO1,Planned
```

This link is only resolvable after **a separate sales-order file** containing `sales_order_id=DEMO-SO1` is imported. This tool deliberately **does not** guess that two records match just because their generic `id` fields contain the same text.

- JSON must contain an array of flat, scalar records or a top-level object with a `rows` array.
- Each file is limited to **2 MB**, **20,000 rows**, and **50 columns**; up to **12 uploaded files per workspace session**.
- The original CSV parser supports quoted commas and newlines. JSON and CSV files are read entirely inside your browser session.
- The imported source register is **not written to `workspace-data`**; it clears when the browser session is lost or the page is reloaded. Preserve originals. Use **Export manifest** to save coverage metadata (without the source rows).
- Personal and Business workspaces have separate source selections and imports. Do not import sensitive personnel or customer records unless their local handling is authorized.

## Source integrity and governance

| Code label | Meaning |
| --- | --- |
| `Code evidenced` | An implementation path was identified at the pinned revision. Does **not** certify behavior or live deployment. |
| `Partial / qualified data needed` | Parts of the capability exist, but governed source data, integration, period closure or acceptance are unresolved. |
| `Not verified in code` | No dedicated operational implementation was established from the targeted files reviewed. |
| `UNVERIFIED_UPLOAD` / `HOLD` | Source file uploaded by the user; no signed provenance, complete ledger, production authority or authenticity verified. |
| `Exact reference` | Matching field and record identifier under a known foreign-key naming rule. **Not a validated accounting journal reconciliation.** |
| `Orphan reference` | Target family imported, but no matching target identifier. |
| `Missing source family` | A recognized foreign-key field exists, but the target family isn't uploaded. |

**Important limitations:**

- This is **not** a copy of the @Data plugin and **does not** embed its remote capabilities.
- **No automatic GitHub, Gmail, Drive, database, Cloudflare, VYNDI OS, VAOS, or VEDM live synchronization.** No keys have been added, no subscriptions enabled.
- **No transactional write-back, approvals, automatic supplier payments, stock changes, or business commitments.**
- A matched ID is only a navigational link. Live statutory accounts, financial consolidation, audit findings, employee SLAs, FEA validation, forecasting and 100%-complete drill-down need original source-system authority, qualification and explicit additional schemas.
- Group financial totals remain **HOLD** when divisions, intercompany eliminations or posted journal attribution cannot be verified.
- Every repo reference in the Capability audit points to a *specific inspected commit*, not automatically the latest head.

## Verification

From the extracted folder, with Node.js if installed for developer checks:

```powershell
node --test tests/data-intelligence.test.cjs
```

The tool is usable without Node.js or these tests. Automated tests cover capability inventory, evidence pins, format bounds, upload quality, exact foreign-key and reverse links, missed links, XSS escaping and missing-source identification. Isolated Chromium UI smoke tests covered the capability audit, CSV upload, record drill-down and mobile width. The container's administrator policy blocked full navigation to a local site, so a complete end-to-end Windows device session has **not** been claimed.
