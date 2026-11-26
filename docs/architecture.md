# System Architecture & Workflow Diagram

```mermaid
flowchart TD
    U[User Request / Turn] --> A[Single-Agent LLM Orchestrator<br/>temperature=0.0, max_steps=8]
    A --> C{Critical Info Missing<br/>or Ambiguous?}
    C -- Yes (Date / Unit / Product) --> CL[record_clarification<br/>Ask User & Stop]
    C -- No --> T1[Tool 1: get_inventory_and_demand<br/>Live read + 24h stale_data check]
    T1 --> T2[Tool 2: calculate_net_requirements<br/>Day-by-day projection + Anti-double counting]
    T2 --> N{Net Requirement > 0?}
    N -- No --> NO[Outcome: no_order<br/>Explain coverage]
    N -- Yes --> T3[Tool 3: compare_suppliers<br/>FX + Freight + Price Breaks + Lead Time + Budget<br/>Sanitize untrusted supplier notes]
    T3 --> E{Eligible Supplier Exists?}
    E -- No --> NE[Outcome: no_eligible_supplier]
    E -- Yes --> DR[Create Draft vN + SHA-256 Data Fingerprint<br/>Outcome: requisition_draft]
    DR --> HITL{Explicit User Approval<br/>in Next Turn?}
    HITL -- No / Rejected --> WAIT[Do Not Log<br/>Await Approval or Revision]
    HITL -- Yes --> T4[Tool 4: manage_requisition]
    T4 --> IDEM{Already Logged?}
    IDEM -- Yes --> DUP[Return Existing ID<br/>Prevent Duplicate]
    IDEM -- No --> FRESH{Data Fingerprint<br/>Unchanged?}
    FRESH -- Changed --> REAPP[Update Draft + warnings: data_changed<br/>awaiting_reapproval: true]
    FRESH -- Unchanged --> LOG[Log Requisition to Test Env<br/>Physical stock unchanged]