# ChatCraft Legal and Professional Services

As a plugin to ChatCraft, one microservice will be the entry into the services provided, if you decide to have
more than one microservice that is fine, however the main microservice will be the main entry into services provided
if routes in additional services need to be exposed outside of the services, you may use the /manifest route
for further explanation of this you may refer to the file PLUGIN_ARCHITECTURE.md

## AI intelligence module built on the ChatCraft Agentic Platform. It brings document intelligence,
## legal research, drafting assistance, and compliance monitoring into a single conversational interface —
## designed specifically for the Nigerian legal market and the realities of legal practice in Nigeria.

## The agent is deployed independently of other ChatCraft modules. It relies on shared platform infrastructure —
## authentication, audit logging, document storage, and vector search — but no other agent or platform component depends on it.
## It can be activated for any tenant that requires it and removed without impact on any other deployed capability.

# Design Philosophy
The agent is a force-multiplier for legal professionals — not a replacement. Every output is advisory.
The lawyer reviews, refines, and takes professional responsibility for all work product.
The agent eliminates the hours spent on information gathering, document review, and research so that legal professionals
can spend their time on the work that genuinely requires their expertise and judgement.

The Modules ar as follows


01 - Contract Intelligence

The anchor feature of the agent. A lawyer uploads any contract — in PDF, Word, or scanned format — and the agent delivers an instant, structured analysis.
This replaces hours of manual clause-by-clause review with a comprehensive, consistent, and auditable analysis in seconds. Uploaded documents must be
distinguishable from documents uploaded for the customer facing RAG service. documents uploaded in this instance is for internal consumption.
Example queries:
•	Summarise the key obligations and deadlines in this shareholders agreement
•	What termination rights does each party have under this contract?
•	Flag any unusual or one-sided clauses in this loan agreement
•	Compare these two versions of this contract and show me what changed
•	Does this contract have a governing law clause and which jurisdiction does it specify?

Contract Intelligence includes the following capabilities:
•	Clause-by-clause breakdown — obligations, representations, warranties, conditions precedent, events of default, termination, governing law, dispute resolution
•	Risk flagging — clauses that deviate from standard Nigerian practice, unusual liability caps, one-sided indemnities, missing standard protections
•	Key date extraction — all deadlines, notice periods, renewal dates, and condition satisfaction dates extracted into a structured timeline
•	Redline intelligence — compare two versions of a document and surface every material change with an explanation of its significance
•	Missing clause detection — flags where a standard clause is absent, such as a force majeure provision, confidentiality clause, or limitation of liability
•	Risk summary report — overall contract risk assessment rated Low, Medium, or High with specific negotiation recommendations
•	Multi-document analysis — upload an entire agreement suite and ask cross-document questions
•	document citation and reference

In addition to the above I think we should have the concept of workspace or project, where a number of uploaded documents belong and hence
any querying etc will be based on the selected documents only.

02 - Legal Research Agent

A natural language research interface over Nigerian case law, statutes, subsidiary legislation, and regulatory materials. Replaces keyword-based search with conversational queries that surface relevant authority,
summarise holdings, and cite sources — in the way a well-read senior associate would respond.
Example queries:
•	Find Supreme Court decisions on piercing the corporate veil of Nigerian subsidiaries
•	What does Nigerian case law say about the enforceability of penalty clauses?
•	Has the Court of Appeal considered force majeure clauses in oil and gas contracts in the last 10 years?
•	What are the current FIRS transfer pricing documentation requirements for related party transactions above N300m?
•	Summarise the CBN circular on loan restructuring issued in 2023 and what it requires of commercial banks

03 - Document Drafting Assistant

The agent drafts standard Nigerian legal documents from a brief description of requirements. It applies the firm's house style,
uses correct defined terms, and produces a first draft that the lawyer refines — collapsing hours of blank-page drafting into minutes of targeted editing.
Example queries:
•	Draft an NDA between two Nigerian companies for a technology partnership. The disclosing party is TechVentures Ltd and the receiving party is Innovate Nigeria Ltd. Duration is 2 years.
•	Draft a board resolution approving the appointment of a new director under CAMA 2020
•	Generate a demand letter for an unpaid invoice of N5m outstanding for 90 days
•	Draft a tenancy agreement for a commercial property in Victoria Island Lagos for a 3-year term
•	Prepare a pre-action protocol letter before filing a breach of contract claim in the Federal High Court

Drafting capabilities include:
•	Standard transactional documents — NDAs, shareholder agreements, share purchase agreements, joint venture agreements, term sheets
•	Corporate secretarial documents — board resolutions, AGM notices, written resolutions, directors' service agreements, all aligned to CAMA 2020
•	Banking and finance documents — facility letters, debentures, legal mortgages, guarantee agreements, security documents
•	Employment documents — employment contracts, non-compete agreements, staff handbook provisions, redundancy notices
•	Property documents — tenancy agreements, lease agreements, deeds of assignment, deeds of sublease, title investigation reports
•	Litigation documents — statements of claim, statements of defence, affidavits, witness statements, originating summons
•	Regulatory filings — CAC forms, SEC filings, regulatory applications with the correct procedural format

04 - Due Diligence Agent

Designed for transactional lawyers managing large data rooms. The agent processes an entire set of uploaded documents simultaneously
and answers structured due diligence questions across all of them — collapsing days of document review into a structured, cross-referenced due diligence report.
Example queries:
•	Are there any change of control provisions across these agreements that would be triggered by this acquisition?
•	Which of these contracts contain assignment restrictions?
•	Identify all litigation references and pending disputes mentioned across these documents
•	List every regulatory licence referenced in these documents and flag any that are expiring within 12 months
•	Which contracts have no governing law clause?

Due diligence capabilities include:
•	Multi-document upload and simultaneous analysis — entire data rooms processed as a single queryable corpus
•	Structured due diligence report generation — categorised by: corporate, commercial, employment, regulatory, litigation, property, intellectual property, and tax
•	Gap analysis — documents referenced in agreements but not provided in the data room are flagged automatically
•	Cross-document inconsistency detection — identifies where different documents contain conflicting provisions
•	Change of control analysis — flags all provisions triggered by ownership change across the document set
•	Assignment and transfer restriction mapping — extracts all consent requirements for novation or assignment
•	Security package review for banking transactions — completeness check on debentures, mortgages, guarantees, and supporting corporate authorities


05 - Regulatory Compliance Monitor

A continuously updated intelligence layer that ingests regulations, circulars, and gazettes from Nigerian regulatory bodies
and alerts the legal team when new developments are relevant to their clients or practice areas. Particularly valuable for in-house legal teams at banks,
telcos, and oil and gas companies operating under multiple regulatory frameworks simultaneously.
Example queries:
•	What new CBN regulations have been issued in the last 30 days that affect commercial lending?
•	Summarise all FIRS circulars issued this year relating to withholding tax on service contracts
•	Has the SEC issued any new rules on public offers since January 2026?
•	What are our current filing obligations under CAMA 2020 for a company with a financial year ending December 2025?
•	Compare our current AML policy against the current CBN AML guidelines and flag any gaps

Regulatory sources continuously monitored and ingested:
•	Central Bank of Nigeria — banking regulations, circulars, guidelines, prudential standards, and consumer protection framework
•	Securities and Exchange Commission — capital market rules, investment management regulations, public offer guidelines
•	Federal Inland Revenue Service — tax circulars, practice notes, transfer pricing guidelines, WHT regulations
•	Corporate Affairs Commission — company law updates, filing requirements, beneficial ownership regulations
•	Nigerian Communications Commission — telecommunications licensing, data protection, consumer regulations
•	Nigerian Upstream Petroleum Regulatory Commission — petroleum industry regulations under the PIA
•	Federal Competition and Consumer Protection Commission — competition law, merger control thresholds, consumer protection
•	Federal Government Official Gazette — enacted statutes, subsidiary legislation, executive orders
•	National Assembly — Bills at various stages, recently enacted legislation

06 - Litigation Support Agent

  06    Litigation Support Agent
A set of capabilities designed specifically for litigators — from pre-action preparation through to post-judgement analysis.
The agent organises case materials, tracks procedural deadlines, assists with document drafting, and analyses opposing arguments.
Example queries:
•	Build a chronology of events from these pleadings and supporting documents
•	Summarise the key arguments made by opposing counsel in their brief of argument and identify the weakest points
•	What is the limitation period for a breach of contract claim arising from a construction contract in Nigeria?
•	Draft an affidavit in support of a motion for interlocutory injunction based on these facts
•	Summarise this Supreme Court judgement — what was held and what is the ratio decidendi?

Litigation support capabilities include:
•	Case chronology builder — extracts all material dates from pleadings, affidavits, and correspondence into a structured timeline
•	Evidence organiser — categorises, labels, and summarises documentary evidence by relevance and evidentiary value
•	Limitation period calculator — identifies applicable limitation periods under the Limitation Law and flags approaching deadlines
•	Opposing argument analyser — reads opposing briefs and identifies the core arguments, the authorities relied upon, and potential weaknesses
•	Judgement summariser — extracts facts, issues, held, ratio decidendi, and obiter dicta from any uploaded judgement
•	Hearing and filing deadline tracker — maintains a calendar of all procedural deadlines across active matters
•	Pre-action protocol checker — validates that proposed court filings comply with applicable procedural rules before filing


07 - Knowledge Management & Institutional Memory

The long-term stickiness feature. Every document the firm or legal team works on — contracts negotiated, research memos prepared, opinions issued,
transaction documents closed — becomes part of a searchable, queryable institutional knowledge base.
This captures the expertise that currently lives only in the heads of senior lawyers and walks out the door when they leave.
Example queries:
                  •	Has our firm done a transaction similar to this acquisition before? What precedents do we have?
                  •	Find all the force majeure clauses we have negotiated in oil and gas contracts in the last 3 years and show me the positions we achieved
                  •	What legal opinions has our firm issued on this question before?
                  •	Show me all the precedent NDA templates we have used for technology clients
                  •	What is our standard position on limitation of liability clauses in IT contracts?

Knowledge management capabilities include:
•	Matter document ingestion — all documents from closed matters are ingested and indexed with matter metadata
•	Precedent search — find previous documents of the same type across all closed matters
•	Clause precedent library — extract and search specific clause types across all ingested documents
•	Opinion and memo library — all legal opinions and research memos become queryable by topic, statute, or court
•	Client matter history — a complete, queryable view of everything the firm has done for a specific client across all matters
•	Negotiation position tracking — record and retrieve the positions achieved in past negotiations on key commercial points
•	Expertise mapping — identify which lawyers in the firm have worked on matters involving specific legal issues or industries


08 - Some Assumptions

The application will have some standard information / ingestions which will be available across all tenants that use the service, such as
1. Supreme Court abd Appeal decisions (nigeralii.org)
2. All federal statutes CAMA, BOFIA, FIRS Act, Land Use Act, CFRN etc
3. All CBN circulars (cbn.gov.ng)
4. SEC Nigeria - Capital Market Rule, Investment Management regulations, public offer guidelines
5. FIRS Tax circulars, practise notes, WHT tables, transfer pricing guidelines
6. CAC - Company law regulations, filling forms, CAMA 2020
7. BAILI - English case law
8. Any other relevant laws, constitution, institutions  etc (NCC, NUPRC, FCCPC, ECOWAS Court etc)


