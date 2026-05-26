# AdSurf Architecture & Workflow Flowchart

This diagram illustrates the complete end-to-end flow of the Amazon Ads AI Automation Control Center, emphasizing the "Human Approval" boundary and the MVP Bulk Sheet export requirement.

```mermaid
graph TD
    classDef browser fill:#f9f9f9,stroke:#333,stroke-width:2px;
    classDef backend fill:#e1f5fe,stroke:#01579b,stroke-width:2px;
    classDef worker fill:#fff3e0,stroke:#e65100,stroke-width:2px;
    classDef db fill:#e8f5e9,stroke:#1b5e20,stroke-width:2px;
    classDef ai fill:#f3e5f5,stroke:#4a148c,stroke-width:2px;
    classDef amazon fill:#fff8e1,stroke:#f57f17,stroke-width:2px;
    classDef human fill:#ffebee,stroke:#b71c1c,stroke-width:3px,color:#b71c1c,font-weight:bold;

    subgraph "Frontend (apps/web)"
        User((User / Agency))
        UI[Next.js Dashboard]:::browser
    end

    subgraph "Cloud Backend"
        API[FastAPI Server apps/api]:::backend
        DB[(Supabase PostgreSQL)]:::db
        Storage[(Supabase Storage)]:::db
        Auth[Supabase Auth]:::db
    end

    subgraph "Background Processing (workers/)"
        FPW[File Processing Worker]:::worker
        CGW[Campaign Generation Worker]:::worker
        MW[Monitoring Worker]:::worker
        Agents[AI Agents / Configured Rules]:::ai
    end

    subgraph "External"
        Amazon[Amazon Ads Portal]:::amazon
    end

    %% Phase 1: Upload & Process
    User -- "1. Logs in" --> Auth
    User -- "2. Uploads Competitor\nKeyword CSV" --> UI
    UI -- "3. Stores File" --> Storage
    UI -- "4. Notifies API" --> API
    API -- "5. Dispatches Job" --> FPW
    FPW -- "6. Cleans & Normalizes" --> DB

    %% Phase 2: AI & Campaign Gen
    DB -. "triggers state change" .-> CGW
    CGW <-->|7. Applies Deterministic Rules\n& AI Explanations| Agents
    CGW -- "8. Generates Draft\nCampaign Plan" --> DB

    %% Phase 3: The Prime Directive (Human Approval)
    DB -- "9. Loads Draft" --> API
    API -- "10. Sent to Dashboard" --> UI
    UI -- "11. Reviews Plan" --> HumanApprove{HUMAN\nAPPROVAL}:::human
    HumanApprove -- "12. Approves Data" --> API

    %% Phase 4: Bulk Export (MVP focus)
    API -- "13. Triggers Export" --> CGW
    CGW -- "14. Creates Amazon\nBulk Sheet (XLSX)" --> Storage
    UI -- "15. Downloads Sheet" --> Storage
    User -- "16. Uploads to Amazon" --> Amazon

    %% Phase 5: Monitoring (Future)
    MW -- "17. Ingests daily metrics" --> DB
    MW <-->|18. 14-day rules context| Agents
    MW -- "19. Drafts Recommendations" --> DB
    DB -. "Needs Approval" .-> HumanApprove
```
