# ADR-0003 · Scoped append-only belief histories

Date: 2026-11-23  
Status: Accepted for the MVP belief slice

Schema 2 adds belief revisions and ordered evidence links in the existing SQLite store. A belief is identified by its scope and ID, and its first revision creates the identity. The store assigns revision IDs, actor and recorded time. An immediate transaction checks the expected parent, appends the revision, and links supporting and refuting evidence. Foreign keys enforce shared scope. Failed attempts leave the database unchanged. The MVP keeps no failed-attempt audit trail.

The current projection selects the highest sequence. A recorded-time cutoff is inclusive and excludes later knowledge, including retroactive corrections. An effective-time filter matches the half-open validity interval. When both are supplied, the newest revision meeting both filters wins. Different beliefs can carry competing propositions, and a revision keeps its supporting and refuting links. The store treats propositions as derived states and rejects attempts to label them as observations. A link records provenance, without implying independent corroboration or verified truth.

The host supplies an authenticated scope grant before reaching the store. Unknown and inaccessible reads have the same API shape. Missing and out-of-scope evidence links produce the same error. This local boundary does not guarantee constant-time database access. Access to database files remains a host responsibility.
