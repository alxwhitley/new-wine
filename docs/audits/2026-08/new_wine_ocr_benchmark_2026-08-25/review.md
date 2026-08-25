# New Wine OCR blind benchmark review

**Decision:** Alex accepted blind Candidate C on 2026-08-25.

**Revealed identity:** Candidate C was Gemini `gemini-3.7-flash`. This is the
accepted initial OCR model for the issue-level New Wine review pipeline.

## Scope and accounting

- Source: `NewWineMagazine_Issue_02-1973 8.30.09 PM.pdf`
- PDF SHA-256: `98856c9cd9b9855e2a71ea3152f65472a8d06a9f54c3eac678b6f45f1b7df183`
- Severe-failure pages: 4 and 31
- Good-control pages: 3 and 10
- Candidates: 3
- Calls attempted/stored/errored/retried: 12 / 12 / 0 / 0
- Approved ceiling: $0.25
- Actual list-price cost: $0.06754230
- Candidate C list-price cost: $0.01948275
- Blind report SHA-256: `9e45550337f986f2a269ae73bc3cf5722ff1e17b674b770d2529b9fcccf13c14`

## Review basis

Candidate A was rejected because it omitted a substantial portion of Exodus
15:26 on control page 3. Candidates B and C both recovered the substantive
material across the severe failures and controls. Candidate C was accepted for
the strongest overall completeness and lack of the visible spelling
substitution found in B. Its residual defects were formatting-level: retained
line-end hyphenation and occasional Markdown emphasis. They are not missing
source material and remain visible to the downstream completeness reviewer.

The accepted decision activates only the next no-write issue review. It does
not authorize a production database write, backlog batch, or any file move.
