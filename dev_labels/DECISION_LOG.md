# Classification decision log

## O2 — draft BL request without attachments

`email_003` and `email_006` ask the team to send a draft BL **for checking** but do not include attachments. We route this wording to `GENERAL`: it requests a future document but does not contain either source needed to start a comparison. A request with a single detected SI or BL and the same check wording is `BL_COMPARISON`, because the available shipping document establishes that the comparison workflow is already active; Phase 7 can then surface the missing partner as review work.

The small dev set is team-authored from participant email content; it is not derived from organizer answer keys.

## Phase 12 review limitation

The current 40-email dev set was labeled by one reviewer only. It has not had
an independently labeled overlap subset or reconciliation pass, so it must be
treated as a regression signal rather than independently corroborated ground
truth. The corresponding Phase 12 roadmap item remains unchecked.

Decision: BL_COMPARISON, status OK, no defects, no review reason.
Reason: The brief defines the class as document-check requests. These emails are follow-ups
in a document-check thread. With no attachments promised there is nothing to compare and
nothing missing, so OK is the neutral status. They contain no SI content, so not SI_REQUEST.
Also consistent with the baseline scoreboard, where about 94 comparison emails had landed in
GENERAL and 91 emails match this phrase pattern.
Related rule: SI_REQUEST requires shipment-specific SI content (or a specific request to
prepare an SI for a shipment). A generic reminder to submit SIs is GENERAL.
Risk: the reference may assign a different status to these; check the next /submit.
